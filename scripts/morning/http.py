"""HTTP helpers with retry + exponential backoff.

Centralizes the boilerplate that was scattered across every stream module:
  - User-Agent header
  - Timeout per request
  - Exponential backoff on 429/502/503/504 + connection errors
  - Optional JSON decode

Streams should use `get_text`, `get_json`, or `urlopen_with_retry` instead of
calling `urllib.request.urlopen` directly. That centralizes error handling
and gives us one place to add metrics later."""
from __future__ import annotations

import json
import random
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Iterable


DEFAULT_UA = "hermes-morning/1.0 (hermes-morning@example.com)"

# Status codes that warrant a retry (transient server / rate-limit issues).
_RETRIABLE_STATUS = {429, 500, 502, 503, 504}


class HTTPError(RuntimeError):
    """Raised when all retries are exhausted."""
    def __init__(self, message: str, url: str, last_status: int | None = None):
        super().__init__(message)
        self.url = url
        self.last_status = last_status


def _is_retriable(exc: Exception) -> bool:
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code in _RETRIABLE_STATUS
    if isinstance(exc, (urllib.error.URLError, TimeoutError, ConnectionError)):
        return True
    return False


def urlopen_with_retry(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 15.0,
    max_attempts: int = 3,
    backoff_base: float = 1.5,
    method: str = "GET",
    data: bytes | None = None,
) -> bytes:
    """Open `url` and return the response body bytes. Retries up to
    `max_attempts` times with exponential backoff + jitter on transient
    failures. Raises HTTPError on final failure."""
    req_headers = {"User-Agent": DEFAULT_UA, **(headers or {})}
    req = urllib.request.Request(url, headers=req_headers, method=method, data=data)
    last_exc: Exception | None = None
    last_status: int | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            last_exc = e
            last_status = e.code
            if not _is_retriable(e):
                raise HTTPError(f"HTTP {e.code} on {url}", url, e.code) from e
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last_exc = e
        # Backoff before next attempt (unless this was the last one).
        if attempt < max_attempts:
            sleep_s = (backoff_base ** attempt) + random.uniform(0, 0.5)
            print(f"[http] retry {attempt}/{max_attempts-1} for {url} after {sleep_s:.1f}s — {type(last_exc).__name__}", file=sys.stderr)
            time.sleep(sleep_s)
    raise HTTPError(
        f"all {max_attempts} attempts failed for {url}: {type(last_exc).__name__}: {last_exc}",
        url, last_status,
    ) from last_exc


def get_text(url: str, **kwargs: Any) -> str:
    """GET → decoded utf-8 text. Same kwargs as urlopen_with_retry."""
    return urlopen_with_retry(url, **kwargs).decode("utf-8", errors="replace")


def get_json(url: str, **kwargs: Any) -> Any:
    """GET → parsed JSON. Same kwargs as urlopen_with_retry."""
    body = urlopen_with_retry(url, **kwargs)
    return json.loads(body.decode("utf-8"))


def get_many(urls: Iterable[str], **kwargs: Any) -> list[tuple[str, str | None, str | None]]:
    """Sequential GETs returning (url, text_or_None, error_or_None) per URL.
    Doesn't raise — failures captured per-URL so the caller can degrade
    gracefully."""
    out: list[tuple[str, str | None, str | None]] = []
    for u in urls:
        try:
            out.append((u, get_text(u, **kwargs), None))
        except HTTPError as e:
            out.append((u, None, str(e)))
    return out
