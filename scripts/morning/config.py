"""Single tunables file — `~/.hermes/config.yaml`.

Reads the YAML once at import time and exposes typed accessors. Stream
modules call `config.get(...)` instead of hardcoding constants, so changing
behaviour is editing one file, not chasing constants across the codebase.

Defaults live in this module; the YAML overrides any subset of them. Missing
keys fall through to defaults silently.

Reload: a process restart picks up YAML changes (the morning runner restarts
every fire). For interactive testing call `config.reload()`."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


CONFIG_PATH = Path(os.environ.get(
    "HERMES_MORNING_CONFIG",
    str(Path.home() / ".hermes" / "morning-config.yaml"),
))


# -- Defaults — everything tunable lives here. -------------------------------

DEFAULTS: dict[str, Any] = {
    "llm": {
        "primary_url": "http://rog:8080/v1/chat/completions",
        "primary_model": "gemma-4-26B-A4B-it-UD-Q4_K_XL.gguf",
        "fast_url": "http://rog:8081/v1/chat/completions",
        "fast_model": "Qwen2.5-3B-Instruct-Q4_K_M.gguf",
        "hp_ollama_url": "http://localhost:11434/v1/chat/completions",
        "hp_ollama_model": "hermes3:8b",
        "default_timeout_s": 300,
        "max_tokens_default": 400,
    },
    "tech": {
        "hn_min_score": 80,
        "hn_show_min_score": 40,
        "subreddits": ["LocalLLaMA", "selfhosted", "MachineLearning"],
        "max_pool_size": 40,
        "target_picks_min": 5,
        "target_picks_max": 7,
    },
    "papers": {
        "categories": ["quant-ph", "cs.IT", "cs.AI", "cs.LG", "cond-mat.mes-hall"],
        "max_per_category": 30,
        "max_picks": 5,
    },
    "watchlist": {
        "max_items_per_run": 8,
        "transcript_timeout_s": 120,
        "summary_max_tokens": 1200,
    },
    "releases": {
        "first_run_cap_per_repo": 1,
        "summary_max_tokens": 200,
    },
    "curiosities": {
        "cooldown_days": 60,
    },
    "weather": {
        "lat": 18.63,
        "lon": 73.81,
        "timezone": "Asia/Kolkata",
    },
    "maintenance": {
        "log_retention_days": 30,
        "state_backup_retention": 14,
        "vault_backup_retention": 30,
        "vault_backup_root": str(Path.home() / "backups" / "vault-ai"),
    },
    "doctor": {
        "slow_stream_threshold_s": 600,
        "stale_heartbeat_hours": 26,
    },
}


_cache: dict[str, Any] = {}


def _deep_merge(base: dict, overlay: dict) -> dict:
    """Override base with overlay, recursively for nested dicts."""
    out = dict(base)
    for k, v in overlay.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def reload() -> dict[str, Any]:
    """Reread the YAML file. Useful for tests or REPL."""
    global _cache
    if CONFIG_PATH.exists():
        try:
            overlay = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as e:
            print(f"[config] YAML parse failed for {CONFIG_PATH}: {e}; using defaults", flush=True)
            overlay = {}
    else:
        overlay = {}
    _cache = _deep_merge(DEFAULTS, overlay)
    return _cache


def get(*path: str, default: Any = None) -> Any:
    """Look up a dotted-path key. Returns `default` on miss.

    Examples:
        config.get("tech", "hn_min_score")  →  80
        config.get("llm", "primary_model")  →  "gemma-4-26B..."
    """
    if not _cache:
        reload()
    cur: Any = _cache
    for part in path:
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def write_default_if_missing() -> bool:
    """First-run helper: write a fully-populated YAML at CONFIG_PATH if absent.
    The file is a complete snapshot of DEFAULTS — easy to edit, easy to revert."""
    if CONFIG_PATH.exists():
        return False
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(yaml.safe_dump(DEFAULTS, sort_keys=False), encoding="utf-8")
    return True


# Initialize on import so callers can use `config.get(...)` immediately.
reload()
