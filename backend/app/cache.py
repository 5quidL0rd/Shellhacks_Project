"""Disk cache keyed by a plain string.

plans.md is explicit that the demo must not depend on live API calls, so every
fetcher writes through this. During the hackathon, deleting data/cache/ is the
only way to force a refetch, which is the behaviour we want on stage.
"""
import json
import time
from typing import Any, Callable

from .config import CACHE_DIR


def _path(key: str):
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in key)
    return CACHE_DIR / f"{safe}.json"


def load(key: str, max_age_seconds: float | None = None) -> Any | None:
    path = _path(key)
    if not path.exists():
        return None
    if max_age_seconds is not None and time.time() - path.stat().st_mtime > max_age_seconds:
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return None


def save(key: str, value: Any) -> None:
    _path(key).write_text(json.dumps(value, indent=2, default=str))


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
