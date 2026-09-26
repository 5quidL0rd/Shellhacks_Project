#!/usr/bin/env python3
"""Smoke-test each data source and key before building anything.

    python -m scripts.check_sources
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config  # noqa: E402
from app.sources import edgar, news, prices  # noqa: E402


def check(label: str, fn) -> bool:
    try:
        detail = fn()
    except Exception as exc:
        print(f"  FAIL  {label}: {type(exc).__name__}: {exc}")
        return False
    print(f"  OK    {label}: {detail}")
    return True


def main() -> int:
    print("Keys present:")
    for name in ("GEMINI_API_KEY", "FINNHUB_API_KEY", "FMP_API_KEY"):
        print(f"  {'yes' if getattr(config, name) else 'NO '}  {name}")
    print(f"  SEC_USER_AGENT = {config.SEC_USER_AGENT}")

    print("\nSources:")
    results = [
        check("yfinance prices", lambda: f"{len(prices.daily_bars('NVDA', 30))} NVDA bars"),
        check("SEC filings", lambda: f"{len(edgar.recent_filings('NVDA'))} filings"),
        check("SEC fundamentals",
              lambda: f"concepts {sorted(edgar.quarterly_fundamentals('NVDA'))}"),
        check("Finnhub news", lambda: f"{len(news.company_news('NVDA', 30))} articles"),
    ]

    print("\nGemini:")
    def gemini_probe():
        from google import genai
        client = genai.Client(api_key=config.GEMINI_API_KEY)
        reply = client.models.generate_content(
            model=config.GEMINI_MODEL, contents="Reply with the single word: ready"
        )
        return f"{config.GEMINI_MODEL} -> {reply.text.strip()[:40]}"
    results.append(check("generate_content", gemini_probe))

    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
