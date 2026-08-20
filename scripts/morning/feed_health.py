"""Feed health tracker — remember which RSS URLs are failing so we can
skip them for the day, and surface a warning when they've been dead
for many days in a row.

Persistent state at ~/.hermes/state/feed-health.json:
    {
      "https://example.com/rss": {
        "consecutive_failures": 3,
        "last_success":  "2026-08-05T05:55:00",
        "last_fail":     "2026-08-08T05:55:00",
        "last_reason":   "HTTPError 404"
      }
    }

Two helpers:
    record_success(url)              — resets counter
    record_failure(url, reason)      — increments counter
    should_skip(url) -> bool         — True if this URL has been dead for
                                        >= SKIP_THRESHOLD consecutive days
                                        AND was tried at least once today
    should_warn(url) -> bool         — True at WARN_THRESHOLD

Circuit-breaker semantics: if a feed has failed on N consecutive days
we still try it once per morning (it might have come back), but after
K days we skip it entirely to avoid wasted time.
"""
from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path


STATE_FILE = Path.home() / ".hermes" / "state" / "feed-health.json"
WARN_THRESHOLD = 3    # log a warning at this many consecutive failures
SKIP_THRESHOLD = 10   # skip the feed entirely (silent) at this many


def _load() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


_LOCK = None  # lazy-init module-level lock, avoids importing threading at top level


def _save(state: dict) -> None:
    """Atomic write. Uses a threading lock so concurrent RSS fetches from
    the news topic-fan-out don't race on the same `.tmp` file."""
    global _LOCK
    if _LOCK is None:
        import threading
        _LOCK = threading.Lock()
    with _LOCK:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        # Include pid+time in the tmp suffix so even cross-process writers
        # from two morning-runs firing simultaneously don't collide.
        import os, time as _t
        tmp = STATE_FILE.with_suffix(f".{os.getpid()}.{_t.time_ns()}.tmp")
        tmp.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(STATE_FILE)


def record_success(url: str) -> None:
    state = _load()
    entry = state.get(url, {})
    entry["consecutive_failures"] = 0
    entry["last_success"] = datetime.datetime.now().isoformat(timespec="seconds")
    entry.pop("last_reason", None)
    state[url] = entry
    _save(state)


def record_failure(url: str, reason: str) -> int:
    """Record a failure; return the new consecutive_failures count."""
    state = _load()
    entry = state.get(url, {})
    entry["consecutive_failures"] = int(entry.get("consecutive_failures", 0)) + 1
    entry["last_fail"] = datetime.datetime.now().isoformat(timespec="seconds")
    entry["last_reason"] = reason[:200]
    state[url] = entry
    _save(state)
    n = entry["consecutive_failures"]
    if n >= WARN_THRESHOLD:
        print(f"[feed_health] {url} has failed {n} consecutive times ({reason[:80]})", file=sys.stderr)
    return n


def should_skip(url: str) -> bool:
    """Skip this URL entirely if it's failed >= SKIP_THRESHOLD days.
    Every SKIP_THRESHOLD-th day we retry once to check if it's back —
    when consecutive_failures % SKIP_THRESHOLD == 0 we still allow it."""
    state = _load()
    n = int(state.get(url, {}).get("consecutive_failures", 0))
    if n < SKIP_THRESHOLD:
        return False
    # Every SKIP_THRESHOLD-th call, let it through as a probe.
    if n % SKIP_THRESHOLD == 0:
        return False
    return True
