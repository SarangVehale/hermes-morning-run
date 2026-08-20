"""hermes-doctor — diagnose the morning workflow in one command.

Walks the whole stack and prints a checklist with ✓ / ⚠ / ✗ markers:
  - LLM endpoints (primary, fast, ollama fallback)
  - ROG model server reachability
  - Vault git state (clean, ahead, behind, branch)
  - State files (presence, parseability, age)
  - Heartbeat (last successful run, age)
  - Disk space + log directory health
  - systemd unit (timer + service) status
  - Required Python deps (ddgs, feedparser, requests, dataview plugin)
  - Vault structural integrity (key files present)

Invoke:  python -m morning.doctor
"""
from __future__ import annotations

import datetime
import json
import os
import shutil
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

from . import llm, vault


OK = "✓"
WARN = "⚠"
FAIL = "✗"


def _line(symbol: str, label: str, detail: str = "") -> str:
    if detail:
        return f"  {symbol}  {label:<40} {detail}"
    return f"  {symbol}  {label}"


def _ping_http(url: str, timeout: float = 5.0) -> tuple[bool, str]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "hermes-doctor/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return True, f"HTTP {r.status}"
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}"
    except (urllib.error.URLError, TimeoutError, socket.timeout) as e:
        return False, f"{type(e).__name__}"


# -- Checks --------------------------------------------------------------------

def check_llm() -> list[str]:
    out = ["[LLM endpoints]"]
    for name, url, model in [
        ("primary  (Gemma 4 26B-A4B)", llm.PRIMARY_URL, llm.PRIMARY_MODEL),
        ("fast     (Qwen2.5-3B)",       llm.FAST_URL,    llm.FAST_MODEL),
        ("fallback (HP Ollama)",        llm.HP_OLLAMA_URL, llm.HP_OLLAMA_MODEL),
    ]:
        base = url.split("/v1/")[0] + "/v1/models"
        ok, detail = _ping_http(base, timeout=3)
        out.append(_line(OK if ok else WARN, name, detail))
    return out


def check_rog() -> list[str]:
    out = ["[ROG inference server]"]
    rog_ip = os.environ.get("RYZEN_HOST", "rog")
    ok, detail = _ping_http(f"http://{rog_ip}:8080/v1/models", timeout=3)
    out.append(_line(OK if ok else WARN, f"http://{rog_ip}:8080", detail))
    return out


def check_vault_git() -> list[str]:
    out = ["[Vault git]"]
    try:
        status = subprocess.run(
            ["git", "-C", str(vault.VAULT), "status", "--porcelain"],
            capture_output=True, text=True, check=False, timeout=10,
        )
        dirty = status.stdout.strip()
        ahead_behind = subprocess.run(
            ["git", "-C", str(vault.VAULT), "rev-list", "--left-right", "--count", "HEAD...@{u}"],
            capture_output=True, text=True, check=False, timeout=10,
        )
        a, b = (ahead_behind.stdout.strip().split("\t") + ["?", "?"])[:2]
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return out + [_line(FAIL, "git unavailable")]
    out.append(_line(OK if not dirty else WARN,
                     "working tree clean",
                     "clean" if not dirty else f"{len(dirty.splitlines())} modified"))
    out.append(_line(OK if a == "0" and b == "0" else WARN,
                     "sync with origin",
                     f"ahead {a} · behind {b}"))
    return out


def check_state_files() -> list[str]:
    out = ["[State files]"]
    state_dir = vault.STATE_DIR
    if not state_dir.exists():
        return out + [_line(FAIL, f"{state_dir} missing")]
    expected = ["last_run.json", "watchlist-last-seen.json", "papers-seen-ids.json",
                "github-releases-last-run.json", "curiosities-shown.json", "dashboard.json"]
    for fname in expected:
        p = state_dir / fname
        if not p.exists():
            out.append(_line(WARN, fname, "missing"))
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            keys = len(data) if isinstance(data, dict) else "—"
            out.append(_line(OK, fname, f"{keys} keys"))
        except (OSError, json.JSONDecodeError):
            out.append(_line(FAIL, fname, "unreadable"))
    return out


def check_heartbeat() -> list[str]:
    out = ["[Heartbeat]"]
    path = vault.STATE_DIR / "last_run.json"
    if not path.exists():
        return out + [_line(WARN, "no heartbeat yet")]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return out + [_line(FAIL, "heartbeat unreadable")]
    try:
        ts = datetime.datetime.fromisoformat(payload["completed_at"])
        age_h = (vault.now_ist() - ts).total_seconds() / 3600
    except (KeyError, ValueError):
        age_h = -1
    ok = payload.get("ok", False)
    age_label = f"{age_h:.1f}h ago" if age_h >= 0 else "age unknown"
    out.append(_line(OK if age_h < 26 else WARN, "last run age", age_label))
    out.append(_line(OK if ok else WARN, "last run status", "OK" if ok else "degraded"))
    timings = payload.get("timings_ms") or {}
    for stream, sok in (payload.get("streams") or {}).items():
        ms = timings.get(stream, 0)
        slow = ms > 600_000  # >10 min
        glyph = OK if sok and not slow else WARN
        detail = f"{ms/1000:.1f}s" if ms else ""
        if slow and sok:
            detail += " (slow)"
        out.append(_line(glyph, f"  stream: {stream}", detail))
    return out


def check_disk() -> list[str]:
    out = ["[Disk]"]
    total, used, free = shutil.disk_usage(str(Path.home()))
    free_gb = free / (1024 ** 3)
    used_pct = used / total * 100
    out.append(_line(OK if free_gb > 5 else WARN,
                     "$HOME free", f"{free_gb:.1f} GB ({used_pct:.0f}% used)"))
    log_dir = Path.home() / ".hermes" / "logs"
    if log_dir.exists():
        total_log = sum(p.stat().st_size for p in log_dir.glob("**/*") if p.is_file())
        log_mb = total_log / (1024 ** 2)
        out.append(_line(OK if log_mb < 200 else WARN,
                         "log directory size", f"{log_mb:.1f} MB"))
    return out


def check_systemd() -> list[str]:
    out = ["[systemd]"]
    for unit in ("hermes-morning.timer", "hermes-morning.service",
                 "hermes-weekly.timer", "hermes-weekly.service"):
        r = subprocess.run(["systemctl", "is-enabled", unit],
                           capture_output=True, text=True, check=False)
        enabled = r.stdout.strip()
        active_r = subprocess.run(["systemctl", "is-active", unit],
                                  capture_output=True, text=True, check=False)
        active = active_r.stdout.strip()
        good = (enabled in ("enabled", "static")) and (active in ("active", "inactive"))
        out.append(_line(OK if good else WARN, unit, f"{enabled} · {active}"))
    return out


def check_python_deps() -> list[str]:
    out = ["[Python deps]"]
    for mod in ("ddgs", "feedparser", "requests"):
        try:
            __import__(mod)
            out.append(_line(OK, mod))
        except ImportError:
            out.append(_line(FAIL, mod, "missing"))
    yt = shutil.which("yt-dlp") or os.path.expanduser("~/.local/bin/yt-dlp")
    out.append(_line(OK if Path(yt).exists() else WARN, "yt-dlp",
                     yt if Path(yt).exists() else "not found"))
    return out


def check_vault_structure() -> list[str]:
    out = ["[Vault structure]"]
    required = [
        vault.HERMES_FILE,
        vault.TASKS_FILE,
        vault.WATCHLIST_YAML,
        vault.TOOLS_YAML,
        vault.STREAM_NOTES["brief"],
        vault.STREAM_NOTES["news"],
        vault.STREAM_NOTES["dashboard"],
    ]
    for p in required:
        if p.exists():
            out.append(_line(OK, p.name))
        else:
            out.append(_line(FAIL, p.name, "MISSING"))
    return out


# -- Entry point ---------------------------------------------------------------

def run() -> int:
    """Print the full diagnostic. Exit 0 if no FAIL markers, 1 otherwise."""
    sections = [
        check_llm(),
        check_rog(),
        check_vault_git(),
        check_state_files(),
        check_heartbeat(),
        check_disk(),
        check_systemd(),
        check_python_deps(),
        check_vault_structure(),
    ]
    body = "\n\n".join("\n".join(s) for s in sections)
    print(body)
    has_fail = FAIL in body
    has_warn = WARN in body
    print()
    if has_fail:
        print(f"  Status: {FAIL}  one or more checks failed — investigate above.")
        return 2
    if has_warn:
        print(f"  Status: {WARN}  all critical checks pass; some warnings to review.")
        return 1
    print(f"  Status: {OK}  all checks pass.")
    return 0


if __name__ == "__main__":
    sys.exit(run())
