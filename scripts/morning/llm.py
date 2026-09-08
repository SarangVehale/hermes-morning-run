"""LLM interface for the morning run.

Uses the `claude` CLI (Claude Code) in print mode. Auth comes from the user's
claude.ai OAuth session (`~/.claude/.credentials.json`) — no API key needed,
no per-token billing (runs against the Pro subscription).

Falls back to HP-local ollama `hermes3:8b` on failure (network out, quota hit,
CLI missing), so streams that need the LLM degrade rather than fail hard.

Interface preserved from the v1 llama.cpp-on-ROG implementation:
  chat(system, user, *, max_tokens, temperature, timeout, prefer) -> str
Callers unchanged; `temperature` / `max_tokens` are accepted for signature
compat but the `claude` CLI uses its own defaults.
"""
from __future__ import annotations

import json
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request


CLAUDE_BIN = "claude"
CLAUDE_MODEL_PRIMARY = "sonnet"   # alias → claude-sonnet-5
CLAUDE_MODEL_FAST = "sonnet"      # sonnet is fast enough; alias if we want haiku later

HP_OLLAMA_URL = "http://localhost:11434/v1/chat/completions"
HP_OLLAMA_MODEL = "hermes3:8b"


class LLMError(RuntimeError):
    """Raised when every configured backend fails."""


def _claude(system: str, user: str, *, model: str, timeout: float) -> str:
    """Shell out to `claude -p`. Reads user prompt on stdin.

    `--restricted` disables built-in Bash/Edit/WebFetch tools — we want a pure
    chat completion, not an agent. Auth is picked up from the user's Claude
    Code login (keychain / ~/.claude/.credentials.json).
    """
    cmd = [
        CLAUDE_BIN, "-p",
        "--model", model,
        "--restricted",
        "--output-format", "text",
        "--system-prompt", system,
    ]
    proc = subprocess.run(
        cmd,
        input=user,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if proc.returncode != 0:
        raise LLMError(f"claude exit {proc.returncode}: {(proc.stderr or proc.stdout)[:300]}")
    out = proc.stdout.strip()
    if not out or out.startswith("Not logged in"):
        raise LLMError(f"claude returned no usable output: {out[:200]}")
    return out


def _ollama(system: str, user: str, *, timeout: float) -> str:
    """Fallback: HP-local ollama on the OpenAI-compat endpoint."""
    body = {
        "model": HP_OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.3,
    }
    req = urllib.request.Request(
        HP_OLLAMA_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={"content-type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ConnectionError) as e:
        raise LLMError(f"ollama fallback unreachable: {e}") from e
    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError) as e:
        raise LLMError(f"ollama returned malformed response: {e}") from e


def chat(
    system: str,
    user: str,
    *,
    max_tokens: int = 400,
    temperature: float = 0.3,
    timeout: float = 300.0,
    prefer: str = "primary",
) -> str:
    """Send a one-shot chat completion. Returns the assistant's content string.

    `prefer`:
        "primary" — claude sonnet (via `claude -p`)
        "fast"    — claude sonnet (same; kept for signature compat)

    Falls back to HP-local ollama hermes3:8b on any claude-side failure.
    """
    model = CLAUDE_MODEL_PRIMARY if prefer == "primary" else CLAUDE_MODEL_FAST
    try:
        return _claude(system, user, model=model, timeout=timeout)
    except (LLMError, FileNotFoundError, subprocess.TimeoutExpired) as claude_err:
        time.sleep(1)
        try:
            return _ollama(system, user, timeout=min(timeout, 120.0))
        except LLMError as ollama_err:
            raise LLMError(
                f"claude failed ({claude_err}); ollama fallback also failed ({ollama_err})"
            ) from claude_err
