"""GitHub Releases stream.

Read repo list from `_tools.yaml`, query the GitHub releases endpoint for each,
emit a callout for every release published since this stream last ran. State:
`~/.hermes/state/github-releases-last-run.json` (per-repo `last_published_at`).

Authenticated via `GITHUB_TOKEN` env var if set (5000 req/h) otherwise
unauthenticated (60 req/h, plenty for ~10 repos)."""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import llm, vault


STATE_FILE = vault.STATE_DIR / "github-releases-last-run.json"
UA = "hermes-morning/1.0 (hermes-morning@example.com)"


@dataclass
class Tool:
    repo: str
    name: str
    reason: str
    critical: bool


@dataclass
class Release:
    repo: str
    tool_name: str
    critical: bool
    tag: str
    name: str
    published_at: str  # ISO8601
    html_url: str
    body: str


def _load_tools() -> list[Tool]:
    raw = vault.read(vault.TOOLS_YAML)
    if not raw:
        return []
    tools = _parse_yaml_tools(raw)
    return tools


# Tiny hand-rolled parser for the simple key:value-list format in _tools.yaml.
# Avoids a PyYAML dependency. Spec is stable: list under `tools:` with keys
# `repo`, `name`, `reason`, `critical`.
def _parse_yaml_tools(raw: str) -> list[Tool]:
    out: list[Tool] = []
    current: dict[str, str] = {}
    in_tools = False
    for line in raw.splitlines():
        if line.strip().startswith("#"):
            continue
        if line.startswith("tools:"):
            in_tools = True
            continue
        if not in_tools:
            continue
        if not line.strip():
            if current:
                out.append(_finalize_tool(current))
                current = {}
            continue
        m = re.match(r"\s*-\s*repo:\s*(.+?)\s*$", line)
        if m:
            if current:
                out.append(_finalize_tool(current))
            current = {"repo": m.group(1).strip()}
            continue
        m = re.match(r"\s+(\w+):\s*(.+?)\s*$", line)
        if m and current:
            current[m.group(1)] = m.group(2).strip()
    if current:
        out.append(_finalize_tool(current))
    return out


def _finalize_tool(d: dict[str, str]) -> Tool:
    return Tool(
        repo=d.get("repo", ""),
        name=d.get("name", d.get("repo", "")),
        reason=d.get("reason", ""),
        critical=d.get("critical", "false").lower() == "true",
    )


def _load_state() -> dict[str, str]:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_state(state: dict[str, str]) -> None:
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(STATE_FILE)


def _gh_get(url: str) -> list[dict] | None:
    headers = {"User-Agent": UA, "Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 403:
            print(f"[releases] 403 — rate limited or repo blocked: {url}", file=sys.stderr)
        elif e.code == 404:
            print(f"[releases] 404 — repo missing or no releases: {url}", file=sys.stderr)
        else:
            print(f"[releases] HTTP {e.code} for {url}", file=sys.stderr)
        return None
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"[releases] fetch failed {url}: {type(e).__name__}: {e}", file=sys.stderr)
        return None


def _fetch_releases(tool: Tool, since_iso: str) -> list[Release]:
    url = f"https://api.github.com/repos/{tool.repo}/releases?per_page=10"
    data = _gh_get(url)
    if not data:
        return []
    out: list[Release] = []
    for r in data:
        if r.get("draft") or r.get("prerelease"):
            continue
        body = r.get("body") or ""
        if not body.strip():
            continue
        published = r.get("published_at") or ""
        if since_iso and published <= since_iso:
            continue
        out.append(Release(
            repo=tool.repo,
            tool_name=tool.name,
            critical=tool.critical,
            tag=r.get("tag_name") or "",
            name=r.get("name") or r.get("tag_name") or "",
            published_at=published,
            html_url=r.get("html_url") or "",
            body=body,
        ))
    # First-run safety: with no prior state we'd flood the digest with the last
    # 10 releases per repo. Cap to the single newest in that case — daily runs
    # afterwards see only the deltas, so any release will surface within 24h.
    if not since_iso:
        out.sort(key=lambda r: r.published_at, reverse=True)
        out = out[:1]
    return out


_SUMMARY_SYSTEM = (
    "You write a substantive 3-5 sentence summary of a GitHub release note for "
    "a daily digest. The user runs llama.cpp on a ROG Flow X13, Hermes Agent "
    "on an HP EliteBook, Obsidian with several plugins, yt-dlp for transcripts. "
    "Cover: what's the headline change (feature add, perf improvement, bug "
    "fix), any specific numbers (% perf gain, memory drop, supported models), "
    "and IF something breaks the user's setup — a renamed flag, removed feature, "
    "default-behavior change, new required dep, or major API change — call "
    "that out explicitly using the words 'breaking change' in a dedicated "
    "sentence. If nothing breaks, say so plainly at the end.\n"
    "\n"
    "OUTPUT: 3 to 5 sentences, plain prose. No bullets, no markdown headings, "
    "no code fences, no preamble. Wikilink the tool name on first mention: "
    "[[Tool Name]]."
)


def _summarize(rel: Release, *, prefer_model: str) -> str:
    # Cap body to keep prompts reasonable.
    body = rel.body[:2500]
    user = (
        f"Tool: {rel.tool_name} ({rel.repo})\n"
        f"Critical to workflow: {'yes' if rel.critical else 'no'}\n"
        f"Tag: {rel.tag}\n"
        f"Release name: {rel.name}\n"
        f"\n"
        f"Release notes:\n{body}\n\n"
        f"Write the two-sentence summary now."
    )
    try:
        return llm.chat(
            system=_SUMMARY_SYSTEM,
            user=user,
            max_tokens=400,
            temperature=0.2,
            prefer=prefer_model,
        ).strip()
    except llm.LLMError as e:
        return f"Release notes available at the link below. (Summary unavailable: {e})"


def _render(rel: Release, summary: str) -> str:
    has_breaking = "breaking change" in summary.lower() or (rel.critical and "break" in summary.lower())
    callout = "[!breaking]-" if has_breaking else "[!note]-"
    if rel.name and rel.name.strip() != rel.tag.strip():
        header = f"{rel.tool_name} {rel.tag} — {rel.name}"
    else:
        header = f"{rel.tool_name} {rel.tag}"
    return (
        f"> {callout} {header}\n"
        f"> {summary}\n"
        f"> [Release notes]({rel.html_url})"
    )


def run(*, prefer_model: str = "primary") -> str:
    tools = _load_tools()
    if not tools:
        body = (
            "> [!warning] GitHub Releases: no tools configured\n"
            "> `_tools.yaml` is empty or unparseable."
        )
        vault.insert_today_entry(vault.STREAM_NOTES["releases"], body)
        vault.set_frontmatter_updated(vault.STREAM_NOTES["releases"])
        return body

    state = _load_state()
    new_releases: list[Release] = []
    for t in tools:
        since = state.get(t.repo, "")
        rels = _fetch_releases(t, since)
        new_releases.extend(rels)
        # Advance per-repo state to the newest seen published_at (whether or
        # not it passed our filters — so we don't re-fetch the same release).
        if rels:
            newest = max(r.published_at for r in rels)
            if newest > state.get(t.repo, ""):
                state[t.repo] = newest

    if not new_releases:
        # Curiosities are their own stream now — no fallback inlined here.
        last_run = state.get("__last_run", "")
        body = f"No new releases since {last_run or 'last check'}."
    else:
        # Newest first.
        new_releases.sort(key=lambda r: r.published_at, reverse=True)
        rendered: list[str] = []
        for rel in new_releases:
            summary = _summarize(rel, prefer_model=prefer_model)
            rendered.append(_render(rel, summary))
        body = "\n\n".join(rendered)

    state["__last_run"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    _save_state(state)

    vault.insert_today_entry(vault.STREAM_NOTES["releases"], body)
    vault.set_frontmatter_updated(vault.STREAM_NOTES["releases"])
    return body


if __name__ == "__main__":
    print(run())
