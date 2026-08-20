"""Thin OpenAI-compatible client to llama-server. No agent loop, no tool
catalog, no skill plumbing — just chat completions for summarization tasks.

Falls back from primary to small sidecar if primary is down. Retries once
on connection error / 5xx."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

PRIMARY_URL = "http://rog:8080/v1/chat/completions"
PRIMARY_MODEL = "gemma-4-26B-A4B-it-UD-Q4_K_XL.gguf"
FAST_URL = "http://rog:8081/v1/chat/completions"
FAST_MODEL = "Qwen2.5-3B-Instruct-Q4_K_M.gguf"
HP_OLLAMA_URL = "http://localhost:11434/v1/chat/completions"
HP_OLLAMA_MODEL = "hermes3:8b"


class LLMError(RuntimeError):
    pass


def _post(url: str, body: dict, timeout: float) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


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
        "primary" — Gemma 4 on ROG (quality)
        "fast"    — Qwen 3B on ROG (speed)

    Both endpoints fall back to the HP-local Ollama hermes3:8b on connection
    failure.
    """
    body = {
        "model": PRIMARY_MODEL if prefer == "primary" else FAST_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    candidates = (
        [(PRIMARY_URL, PRIMARY_MODEL), (FAST_URL, FAST_MODEL), (HP_OLLAMA_URL, HP_OLLAMA_MODEL)]
        if prefer == "primary"
        else [(FAST_URL, FAST_MODEL), (PRIMARY_URL, PRIMARY_MODEL), (HP_OLLAMA_URL, HP_OLLAMA_MODEL)]
    )
    last_err: Exception | None = None
    for url, model in candidates:
        body["model"] = model
        try:
            resp = _post(url, body, timeout=timeout)
            return resp["choices"][0]["message"]["content"]
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ConnectionError) as e:
            last_err = e
            time.sleep(1)
            continue
        except (KeyError, ValueError) as e:
            last_err = e
            time.sleep(1)
            continue
    raise LLMError(f"all LLM endpoints failed; last error: {last_err}")
