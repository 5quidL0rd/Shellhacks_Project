"""Disk cache keyed by a plain string.

plans.md is explicit that the demo must not depend on live API calls, so every
fetcher writes through this. During the hackathon, deleting data/cache/ is the
only way to force a refetch, which is the behaviour we want on stage.
"""
import json
import time
from typing import Any, Callable

from .config import CACHE_DIR


import tempfile
from pathlib import Path

FALLBACK_CACHE_DIR = Path(tempfile.gettempdir()) / "shellhacks_cache"


def _safe_name(key: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in key) + ".json"


def _path(key: str) -> Path:
    return CACHE_DIR / _safe_name(key)


def _fallback_path(key: str) -> Path:
    return FALLBACK_CACHE_DIR / _safe_name(key)


def load(key: str, max_age_seconds: float | None = None) -> Any | None:
    for path in (_path(key), _fallback_path(key)):
        if not path.exists():
            continue
        if max_age_seconds is not None and time.time() - path.stat().st_mtime > max_age_seconds:
            return None
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
    return None


def save(key: str, value: Any) -> None:
    data = json.dumps(value, indent=2, default=str)
    try:
        _path(key).write_text(data)
    except (OSError, PermissionError):
        try:
            FALLBACK_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            _fallback_path(key).write_text(data)
        except (OSError, PermissionError):
            pass


def cached(key: str, producer: Callable[[], Any], max_age_seconds: float | None = None) -> Any:
    """Return the cached value, else call producer and cache what it returns.

    If producer raises but a stale entry exists, the stale entry wins. A demo
    that shows slightly old data beats a demo that shows a traceback.
    """
    hit = load(key, max_age_seconds)
    if hit is not None:
        return hit
    try:
        value = producer()
    except Exception:
        stale = load(key)
        if stale is not None:
            return stale
        raise
    save(key, value)
    return value
