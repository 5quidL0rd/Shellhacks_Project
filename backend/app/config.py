"""Environment-backed settings. Everything Story Mode needs to run."""
import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")

CACHE_DIR = BACKEND_DIR / "data" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "")
FMP_API_KEY = os.getenv("FMP_API_KEY", "")
SEC_USER_AGENT = os.getenv("SEC_USER_AGENT", "ShellhacksPortfolioStory contact@example.com")

# A daily move at least this large (in percent) is worth explaining.
MOVE_THRESHOLD_PCT = float(os.getenv("MOVE_THRESHOLD_PCT", "3.0"))
# Never put more than this many beats in one story; the chart gets unreadable.
MAX_STORY_BEATS = int(os.getenv("MAX_STORY_BEATS", "12"))
# How far back Story Mode looks.
STORY_LOOKBACK_DAYS = int(os.getenv("STORY_LOOKBACK_DAYS", "180"))
