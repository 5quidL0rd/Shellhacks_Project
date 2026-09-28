"""Live tracking accepts ticker-shaped stocks beyond the deep-analysis set."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import live_market  # noqa: E402


def test_tesla_quote_is_allowed_without_story_coverage(monkeypatch):
    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"c": 401.25, "d": 3.5, "dp": 0.88, "pc": 397.75,
                    "o": 399, "h": 402, "l": 395, "t": 1790600000}

    requested = {}

    def fake_get(url, **kwargs):
        requested["symbol"] = kwargs["params"]["symbol"]
        return Response()

    monkeypatch.setenv("FINNHUB_API_KEY", "test-token")
    monkeypatch.setattr(live_market.requests, "get", fake_get)
    live_market._cache.clear()

    quote = live_market.live_quote("tsla")

    assert requested["symbol"] == "TSLA"
    assert quote["price"] == 401.25
    assert quote["provider"] == "Finnhub"


def test_rejects_non_ticker_input():
    assert live_market.valid_symbol("TSLA")
    assert not live_market.valid_symbol("TSLA?token=secret")
