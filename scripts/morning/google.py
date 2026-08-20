"""Shared helper for Google APIs (Gmail + Calendar).

Loads OAuth tokens from `~/.hermes/mcp-tokens/<name>.json`, auto-refreshes
when the access_token is within 60s of expiring, and exposes a typed
`bearer_get_json(account, url)` for the stream modules.

Token file shape (written by oauth-grant.py):
    access_token       — bearer for API calls
    refresh_token      — used to mint a new access_token when expired
    expires_at         — unix timestamp; access_token invalid after this
    refresh_token_expires_in — seconds the refresh_token itself is valid for
    scope, token_type, expires_in — informational

Client credentials live in `<name>.client.json` (client_id + client_secret).
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from . import vault


TOKENS_DIR = Path.home() / ".hermes" / "mcp-tokens"
TOKEN_URL = "https://oauth2.googleapis.com/token"

# Account → email mapping, used for log messages and disambiguation.
GMAIL_ACCOUNTS = {
    "gmail_personal": "you.personal@example.com",
    "gmail_work":     "you.work@example.com",
    "gmail_iitm":     "you.iitm@example.com",
    "gmail_nfsu":     "you.nfsu@example.com",
}
CALENDAR_ACCOUNTS = {
    "calendar_personal": "you.personal@example.com",
    "calendar_work":     "you.work@example.com",
    "calendar_iitm":     "you.iitm@example.com",
    "calendar_nfsu":     "you.nfsu@example.com",
}


class GoogleAuthError(RuntimeError):
    """Raised when token refresh fails or a token is unrecoverable."""


def _token_path(account: str) -> Path:
    return TOKENS_DIR / f"{account}.json"


def _client_path(account: str) -> Path:
    return TOKENS_DIR / f"{account}.client.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _save_token(account: str, token_data: dict) -> None:
    """Atomic write; preserves mode 600."""
    path = _token_path(account)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(token_data, indent=2), encoding="utf-8")
    tmp.chmod(0o600)
    tmp.replace(path)


def _refresh(account: str) -> dict:
    """Use the refresh_token to mint a new access_token. Persist the result."""
    token = _load(_token_path(account))
    client = _load(_client_path(account))
    if "refresh_token" not in token:
        raise GoogleAuthError(f"{account} has no refresh_token; re-run oauth-grant.py")

    body = urllib.parse.urlencode({
        "client_id":     client["client_id"],
        "client_secret": client["client_secret"],
        "refresh_token": token["refresh_token"],
        "grant_type":    "refresh_token",
    }).encode()
    req = urllib.request.Request(
        TOKEN_URL, data=body, method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            new_token = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace") if e.fp else ""
        raise GoogleAuthError(f"refresh failed for {account}: HTTP {e.code} — {body_text[:200]}") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise GoogleAuthError(f"refresh failed for {account}: {type(e).__name__}") from e

    # Preserve refresh_token if Google didn't issue a new one (common).
    if "refresh_token" not in new_token and "refresh_token" in token:
        new_token["refresh_token"] = token["refresh_token"]
    if "refresh_token_expires_in" in token and "refresh_token_expires_in" not in new_token:
        new_token["refresh_token_expires_in"] = token["refresh_token_expires_in"]
    expires_in = new_token.get("expires_in")
    if expires_in is not None:
        new_token["expires_at"] = time.time() + int(expires_in)

    _save_token(account, new_token)
    return new_token


def access_token_for(account: str) -> str:
    """Return a valid access_token for `account`, refreshing if needed."""
    if not _token_path(account).exists():
        raise GoogleAuthError(f"{account}: token file missing; run oauth-grant.py {account}")
    token = _load(_token_path(account))
    expires_at = float(token.get("expires_at") or 0)
    # 60s buffer so we don't race the expiry mid-request.
    if expires_at - time.time() < 60:
        token = _refresh(account)
    return token["access_token"]


def bearer_get_json(account: str, url: str, *, timeout: float = 15.0) -> Any:
    """GET `url` with the account's bearer token. Returns parsed JSON.

    Auto-retries once on 401 (re-refresh on the chance the token expired
    between the cached check and the actual request)."""
    for attempt in (1, 2):
        token = access_token_for(account)
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": "hermes-morning/1.0",
        })
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 401 and attempt == 1:
                # Force-refresh and retry once.
                _refresh(account)
                continue
            body = e.read().decode("utf-8", errors="replace") if e.fp else ""
            raise GoogleAuthError(f"{account} → {url}: HTTP {e.code} — {body[:200]}") from e
        except (urllib.error.URLError, TimeoutError) as e:
            raise GoogleAuthError(f"{account} → {url}: {type(e).__name__}: {e}") from e
    # Unreachable, satisfies type-checker.
    raise GoogleAuthError("unreachable")
