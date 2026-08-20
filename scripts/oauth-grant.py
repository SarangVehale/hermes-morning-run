#!/usr/bin/env python3
"""
oauth-grant.py — run Google OAuth PKCE flow for a Hermes MCP server entry
directly, without going through Hermes Agent's tool-calling loop. Saves tokens
in the exact JSON format Hermes reads from ~/.hermes/mcp-tokens/<name>.json.

Usage:
    python3 ~/scripts/oauth-grant.py gmail_work
    python3 ~/scripts/oauth-grant.py gmail_personal
    python3 ~/scripts/oauth-grant.py gmail_iitm
    python3 ~/scripts/oauth-grant.py gmail_nfsu
    python3 ~/scripts/oauth-grant.py calendar_work    # re-auth if needed

For each invocation: a browser tab opens at Google's consent page. Log in
as the matching account, click Allow, the tab closes. Done.

Prerequisites:
- ~/.hermes/mcp-tokens/<name>.client.json must already exist (Hermes creates
  it automatically on `hermes mcp list` for any configured server).
- The Cloud Console OAuth client (whose client_id/secret are in client.json)
  must have the required scopes added in its consent screen, and your account
  must be a test user on that OAuth consent screen.
"""
from __future__ import annotations

import base64
import hashlib
import http.server
import json
import os
import secrets
import socketserver
import sys
import time
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

HOME = Path.home()
TOKENS_DIR = HOME / ".hermes" / "mcp-tokens"

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
]
CALENDAR_SCOPES = [
    "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
    "https://www.googleapis.com/auth/calendar.events.freebusy",
    "https://www.googleapis.com/auth/calendar.events.readonly",
    # Google Tasks lives under the same account as Calendar. Adding the
    # scope here means re-granting calendar_* picks up Tasks too — no need
    # for separate tasks_* accounts.
    "https://www.googleapis.com/auth/tasks.readonly",
]
# Every grant asks for ALL scopes the orchestrator might need. Why: all 8
# service entries (gmail_X, calendar_X) share the same OAuth client_id, and
# Google's OAuth provider silently invalidates older refresh tokens for a
# `(client_id, user, scope_set)` combination when a new grant arrives with
# a different scope set. Without this, re-granting calendar_personal would
# kill the gmail_personal refresh token (and vice versa) — the scope-loop
# bug. Asking for the union every time keeps every sibling token alive.
ALL_SCOPES = sorted(set(GMAIL_SCOPES + CALENDAR_SCOPES))

# Which other token files should be updated whenever this one is granted.
# Keyed by the Google account email — populated from the matching token file
# pair (gmail_personal + calendar_personal both point at you.personal@example.com).
SIBLING_PREFIXES = ("gmail_", "calendar_")

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"


def _pkce_pair() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).rstrip(b"=").decode()
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    return verifier, challenge


def _ensure_meta_cached(server_name: str) -> None:
    """Hermes uses meta.json (Google's discovery doc) for OAuth provider info.
    Calendar_work already had one after its earlier successful TUI flow; the
    Gmail ones don't yet. Fetch + save so Hermes is happy."""
    meta_path = TOKENS_DIR / f"{server_name}.meta.json"
    if meta_path.exists():
        return
    with urllib.request.urlopen(DISCOVERY_URL) as resp:
        meta = json.loads(resp.read().decode())
    meta_path.write_text(json.dumps(meta, indent=2))
    meta_path.chmod(0o600)
    print(f"  cached OAuth metadata to {meta_path.name}")


def grant(server_name: str) -> None:
    client_info_path = TOKENS_DIR / f"{server_name}.client.json"
    if not client_info_path.exists():
        sys.exit(
            f"ERROR: {client_info_path} not found. Run `hermes mcp list` first "
            "so Hermes creates the client.json files, then retry."
        )

    client_info = json.loads(client_info_path.read_text())
    client_id = client_info["client_id"]
    client_secret = client_info["client_secret"]

    if server_name.startswith(SIBLING_PREFIXES):
        # Always request the full union of scopes. See ALL_SCOPES comment.
        scopes = ALL_SCOPES
    else:
        sys.exit(f"ERROR: unknown server-name prefix in '{server_name}'")

    _ensure_meta_cached(server_name)

    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(16)
    auth_code: dict[str, str | None] = {"v": None}

    class CallbackHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if (
                "code" in qs
                and qs.get("state", [None])[0] == state
                and "error" not in qs
            ):
                auth_code["v"] = qs["code"][0]
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(
                    b"<html><body style='font-family:sans-serif;padding:2em'>"
                    b"<h1>Auth complete</h1>"
                    b"<p>You can close this tab and return to the terminal.</p>"
                    b"</body></html>"
                )
            else:
                err = qs.get("error", ["?"])[0]
                self.send_response(400)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(f"OAuth error: {err}".encode())

        def log_message(self, format: str, *args) -> None:  # silence access log
            pass

    # OAUTH_PORT=<n> forces a fixed callback port. Default 0 = random.
    # OAUTH_BIND=<addr> sets the bind address (default 127.0.0.1).
    # OAUTH_HOST=<name> sets the hostname/IP used in the redirect URI
    # (default same as OAUTH_BIND). For Tailscale: set OAUTH_BIND=0.0.0.0
    # and OAUTH_HOST=<HP-HOSTNAME> (or the Tailscale IP) so a browser on another
    # Tailscale node can reach the callback over the tailnet.
    fixed_port = int(os.environ.get("OAUTH_PORT", "0"))
    bind_addr = os.environ.get("OAUTH_BIND", "127.0.0.1")
    redirect_host = os.environ.get("OAUTH_HOST", bind_addr if bind_addr not in ("0.0.0.0", "::") else "127.0.0.1")
    server = socketserver.TCPServer((bind_addr, fixed_port), CallbackHandler)
    server.timeout = 180
    port = server.server_address[1]
    redirect_uri = f"http://{redirect_host}:{port}/callback"

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(scopes),
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "access_type": "offline",
        "state": state,
        "prompt": "consent",
    }
    full_auth_url = f"{AUTH_URL}?{urllib.parse.urlencode(params)}"

    print(f"\n[{server_name}] opening browser for consent...")
    print(f"If browser doesn't open, paste this URL into one manually:\n  {full_auth_url}\n")
    webbrowser.open(full_auth_url)

    print("  waiting for callback (up to 3 min)...")
    server.handle_request()
    server.server_close()

    if auth_code["v"] is None:
        sys.exit(f"ERROR: no auth code received for {server_name}")

    print("  exchanging code for tokens...")
    body = urllib.parse.urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "code": auth_code["v"],
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
        "code_verifier": verifier,
    }).encode()
    req = urllib.request.Request(
        TOKEN_URL,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            token_data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        err_body = e.read().decode() if e.fp else ""
        sys.exit(f"ERROR: token exchange failed ({e.code}): {err_body}")

    expires_in = token_data.get("expires_in")
    if expires_in is not None:
        token_data["expires_at"] = time.time() + int(expires_in)

    # Write the token to this service's file AND every sibling service file
    # pointing at the same Google account. The cleanest way to derive
    # siblings is by stripping the prefix and matching the account-suffix:
    # `gmail_personal` ⇄ `calendar_personal`, etc.
    account_suffix = server_name.split("_", 1)[1] if "_" in server_name else ""
    targets = [server_name]
    if account_suffix:
        for prefix in SIBLING_PREFIXES:
            sibling = f"{prefix}{account_suffix}"
            if sibling != server_name:
                # Only mirror to siblings that have a client.json (i.e. were
                # set up in Hermes). Don't create orphan files.
                if (TOKENS_DIR / f"{sibling}.client.json").exists():
                    targets.append(sibling)

    payload = json.dumps(token_data, indent=2)
    for name in targets:
        p = TOKENS_DIR / f"{name}.json"
        p.write_text(payload)
        p.chmod(0o600)
        marker = "" if name == server_name else " (mirrored)"
        print(f"  ✓ tokens saved to {p.name}{marker}")
    print(f"    scopes granted: {token_data.get('scope', '(not reported)')}")


def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    grant(sys.argv[1])


if __name__ == "__main__":
    main()
