"""Grounded financial Q&A through Snowflake Cortex AI_COMPLETE."""
from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from . import portfolio, quotes
from .live_market import live_quote
from .snowflake_db import get_connection
from .universe import SYMBOLS


def answer(question: str, symbol: str | None, holdings: list[str], positions: dict | None = None) -> dict:
    question = question.strip()
    if not question or len(question) > 700:
        raise ValueError("Ask a question up to 700 characters long.")
    symbol = (symbol or "").strip().upper()
    if symbol and symbol not in SYMBOLS:
        raise ValueError("The selected stock is not supported.")
    supported, _ = portfolio.parse_holdings(holdings)
    supported = supported[:15]
    context: dict = {"selected_stock": symbol or None, "holdings": supported}
    if symbol:
        try:
            context["live_quote"] = live_quote(symbol)
        except Exception as exc:
            context["live_quote_unavailable"] = str(exc)
        saved = quotes.quotes([symbol])["quotes"].get(symbol)
        if saved:
            context["historical_quote"] = saved
    if supported:
        context["shared_dependencies"] = [
            {"name": row["name"], "holding_count": row["holding_count"],
             "holdings": [h["ticker"] for h in row["holdings"]]}
            for row in portfolio.xray(supported)[:10]
        ]
    requested_positions = {
        ticker: value for ticker, value in (positions or {}).items()
        if ticker in supported and isinstance(value, dict)
        and isinstance(value.get("shares"), (int, float))
        and 0 < value["shares"] <= 1_000_000
    }
    if requested_positions:
        context["positions"] = requested_positions
        live_positions = {}
        with ThreadPoolExecutor(max_workers=5) as pool:
            pending = {pool.submit(live_quote, ticker): ticker for ticker in requested_positions}
            for future in as_completed(pending):
                ticker = pending[future]
                try:
                    quote = future.result()
                    shares = requested_positions[ticker]["shares"]
                    live_positions[ticker] = {"shares": shares, "market_value": round(shares * quote["price"], 2),
                                              "quote": quote}
                except Exception:
                    pass
        context["live_positions"] = live_positions
    prompt = (
        "You are Portfolio X-Ray's financial data assistant. Answer the user's question using "
        "ONLY the JSON data below. Explain calculations plainly. Cite the provider and exact "
        "as-of timestamp or date for prices. Historical prices and filing relationships are not "
        "live. If requested data is absent, say so and suggest the closest available view. "
        "Do not invent prices, financial advice, or unseen documents. Keep the response under "
        "180 words.\n\nDATA:\n" + json.dumps(context, default=str)[:18000] +
        "\n\nUSER QUESTION:\n" + question
    )
    model = os.getenv("SNOWFLAKE_CORTEX_MODEL", "llama3.3-70b")
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT AI_COMPLETE(%s, %s)", (model, prompt))
            row = cursor.fetchone()
    if not row or not row[0]:
        raise RuntimeError("Snowflake Cortex returned no answer. Check model access for this role.")
    return {"answer": str(row[0]), "model": model, "provider": "Snowflake Cortex",
            "selected_stock": symbol or None, "data": context}
