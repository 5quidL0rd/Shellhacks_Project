"""Quote facts computed from daily bars."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.quotes import quote_from_bars  # noqa: E402


def bars(closes, volume=100):
    return [{"date": f"2026-01-{i + 1:02d}", "close": c, "volume": volume} for i, c in enumerate(closes)]


def test_daily_change_and_price():
    q = quote_from_bars("X", bars([100, 110]))
    assert (q["price"], q["prev_close"], q["change"], q["change_pct"]) == (110, 100, 10, 10.0)
    assert q["as_of"] == "2026-01-02"


def test_period_returns_only_when_history_covers_them():
    q = quote_from_bars("X", bars([100 + i for i in range(10)]))
    assert q["returns"]["1W"] == round((109 - 104) / 104 * 100, 3)
    assert "1M" not in q["returns"] and "3M" not in q["returns"]
    assert q["returns"]["6M"] == 9.0  # whole window


def test_range_and_sparkline():
    q = quote_from_bars("X", bars([5, 1, 9, 4] + [3] * 40))
    assert (q["range"]["low"], q["range"]["high"]) == (1, 9)
    assert len(q["sparkline"]) == 30
    assert q["sparkline"][-1]["close"] == 3


def test_volume_versus_the_previous_sessions():
    b = bars([1, 2, 3])
    b[-1]["volume"] = 300
    assert quote_from_bars("X", b)["volume_vs_avg"] == 3.0


def test_too_little_history_is_none():
    assert quote_from_bars("X", bars([1])) is None
