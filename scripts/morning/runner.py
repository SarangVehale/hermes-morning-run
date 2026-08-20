"""Morning workflow orchestrator entry point.

Replaces the single-prompt-to-Hermes-Agent approach. Each stream is its own
Python module with a `run(ctx) -> StreamResult` callable; the runner imports
them in a fixed dependency order, captures failures per stream (so one broken
stream doesn't kill the whole brief), and composes the final Dashboard + Brief
at the end.

Invoke from bash via `python3 -m morning.runner` (with `~/scripts` on
PYTHONPATH) or `python3 ~/scripts/morning/runner.py`.

Phases:
    1. Tasks            (local file parse — fast, no deps)
    2. Email stub       (writes warning to Triage)
    3. Calendar stub    (returns warning string)
    4. News             (web search — NOT YET IMPLEMENTED)
    5. Papers           (arXiv RSS — NOT YET IMPLEMENTED)
    6. Tech             (HN / Reddit — NOT YET IMPLEMENTED)
    7. Releases         (GitHub API — NOT YET IMPLEMENTED)
    8. Watchlist        (RSS + yt-dlp — NOT YET IMPLEMENTED)
    9. Brief composition
    10. Dashboard regen
    11. Daily note touch
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import re
import sys
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from . import curiosities, dashboard, llm, news, onthisday, papers, releases, tech, vault, watchlist, weather


@dataclass
class StreamResult:
    name: str
    ok: bool
    brief_snippet: str = ""        # what the Brief composer should embed
    dashboard_snippet: str = ""    # what the Dashboard composer should embed
    error: str = ""
    meta: dict[str, Any] = field(default_factory=dict)
    duration_ms: int = 0           # wall time spent on this stream


@dataclass
class RunContext:
    dry_run: bool
    results: dict[str, StreamResult] = field(default_factory=dict)

    def record(self, r: StreamResult) -> None:
        self.results[r.name] = r


# -- Stream wrappers (thin adapters around stream modules) ---------------------

def _run_weather(ctx: RunContext) -> StreamResult:
    line = weather.run()
    return StreamResult(
        name="weather", ok=not line.startswith("> [!warning]"),
        brief_snippet=line, dashboard_snippet=line,
    )


def _run_news(ctx: RunContext) -> StreamResult:
    body = news.run()
    snippet = "see [[📰 Daily News]]"
    return StreamResult(
        name="news", ok=True,
        brief_snippet=snippet, dashboard_snippet=body,
        meta={"topics": len(news.TOPICS)},
    )


def _run_papers(ctx: RunContext) -> StreamResult:
    body = papers.run()
    snippet = "see [[📄 Daily Papers]]"
    return StreamResult(
        name="papers", ok=True,
        brief_snippet=snippet, dashboard_snippet=body,
        meta={"categories": len(papers.ARXIV_CATEGORIES)},
    )


def _run_tech(ctx: RunContext) -> StreamResult:
    body = tech.run()
    snippet = "see [[🔬 Daily Tech]]"
    return StreamResult(
        name="tech", ok=True,
        brief_snippet=snippet, dashboard_snippet=body,
        meta={"subs": len(tech.SUBREDDITS)},
    )


def _run_releases(ctx: RunContext) -> StreamResult:
    body = releases.run()
    snippet = "see [[🔄 GitHub Releases]]"
    return StreamResult(
        name="releases", ok=True,
        brief_snippet=snippet, dashboard_snippet=body,
        meta={"tools": len(releases._load_tools())},
    )


def _run_curiosity(ctx: RunContext) -> StreamResult:
    body = curiosities.daily_run()
    return StreamResult(
        name="curiosity", ok=bool(body),
        brief_snippet=body, dashboard_snippet=body,
    )


def _run_watchlist(ctx: RunContext) -> StreamResult:
    body = watchlist.run()
    snippet = "see [[🎬 Daily Watchlist]]"
    return StreamResult(
        name="watchlist", ok=True,
        brief_snippet=snippet, dashboard_snippet=body,
        meta={"creators": len(watchlist._load_watchlist())},
    )


def _run_onthisday(ctx: RunContext) -> StreamResult:
    body = onthisday.run()
    return StreamResult(
        name="onthisday", ok=not body.startswith("> [!info]- On this day — fetch failed"),
        brief_snippet=body, dashboard_snippet=body,
    )


def _not_implemented(name: str) -> Callable[[RunContext], StreamResult]:
    def _runner(_ctx: RunContext) -> StreamResult:
        body = (
            f"> [!warning] {name} stream not yet implemented in the Python "
            "orchestrator\n"
            f"> Module `morning/{name}.py` is pending. Until then this section "
            "is intentionally blank rather than fabricated."
        )
        return StreamResult(
            name=name, ok=True, brief_snippet=body, dashboard_snippet=body,
            meta={"pending": True},
        )
    return _runner


STREAMS: list[tuple[str, Callable[[RunContext], StreamResult]]] = [
    ("weather",   lambda ctx: _run_weather(ctx)),
    ("news",      lambda ctx: _run_news(ctx)),
    ("papers",    lambda ctx: _run_papers(ctx)),
    ("tech",      lambda ctx: _run_tech(ctx)),
    ("releases",   lambda ctx: _run_releases(ctx)),
    ("curiosity",  lambda ctx: _run_curiosity(ctx)),
    ("watchlist",  lambda ctx: _run_watchlist(ctx)),
    ("onthisday",  lambda ctx: _run_onthisday(ctx)),
]


# -- Composition (Brief + Dashboard) -------------------------------------------

_HEADLINE_SYSTEM = (
    "You write a one-sentence headline that captures the cross-cutting theme of "
    "the user's morning briefing. You will be given short excerpts from the "
    "News, Papers, Tech, Watchlist and Releases streams that landed today. "
    "Identify the dominant thread, if any.\n"
    "\n"
    "Examples of good headlines:\n"
    "- AI regulation news cluster + a quantum-error-correction paper run.\n"
    "- Quiet day; the loudest item is local — Pune metro extension.\n"
    "- Mostly hardware: new GPU, Strix Halo benches, and a ThinkPad teardown.\n"
    "\n"
    "If no clear theme is visible, output EXACTLY: 'Mixed morning — no dominant thread.'\n"
    "\n"
    "OUTPUT: one line, no preamble, no markdown, no quotes."
)


def _compose_headline(ctx: RunContext, *, prefer_model: str = "primary") -> str:
    """LLM-generated single-sentence theme summary for the top of the Brief."""
    chunks: list[str] = []
    for name in ("news", "papers", "tech", "watchlist", "releases"):
        r = ctx.results.get(name)
        if not r or not r.ok or not r.dashboard_snippet:
            continue
        # Just feed the headers of the top callouts.
        for line in r.dashboard_snippet.splitlines():
            if line.startswith("> [!"):
                chunks.append(f"[{name}] {line.lstrip('> []!- ').strip()[:200]}")
                if sum(1 for c in chunks if c.startswith(f"[{name}]")) >= 2:
                    break
    if not chunks:
        return "Mixed morning — no dominant thread."
    user = "Today's stream headers:\n\n" + "\n".join(chunks) + "\n\nGive me one sentence."
    try:
        return llm.chat(
            system=_HEADLINE_SYSTEM, user=user,
            max_tokens=80, temperature=0.3, prefer=prefer_model,
        ).strip().strip('"').strip("'").splitlines()[0]
    except llm.LLMError:
        return "Mixed morning — no dominant thread."


def _compose_brief(ctx: RunContext) -> str:
    """Build today's Brief entry body. Reading-only briefing — no
    tasks, no email, no calendar. Section order: Headline → Weather →
    From the streams."""
    def _get(name: str) -> str:
        r = ctx.results.get(name)
        if r is None:
            return "*(skipped)*"
        if not r.ok:
            return f"> [!warning] {name} stream failed: {r.error}"
        return r.brief_snippet or "Nothing today."

    headline = _compose_headline(ctx)

    parts: list[str] = []
    parts.append(f"_**Headline:** {headline}_")
    parts.append("**Weather**\n\n" + _get("weather"))
    parts.append(
        "**From the streams**\n\n"
        "- News: " + _summarize_stream(ctx, "news") + "\n"
        "- Papers: " + _summarize_stream(ctx, "papers") + "\n"
        "- Tech: " + _summarize_stream(ctx, "tech") + "\n"
        "- Releases: " + _summarize_stream(ctx, "releases") + "\n"
        "- Watchlist: " + _summarize_stream(ctx, "watchlist")
    )
    return "\n\n".join(parts)


_STREAM_LINKS = {
    "news":      "📰 Daily News",
    "papers":    "📄 Daily Papers",
    "tech":      "🔬 Daily Tech",
    "releases":  "🔄 GitHub Releases",
    "watchlist": "🎬 Daily Watchlist",
}


_DIRECT_URL_RE = re.compile(r"\[(?:Source|Release notes|arXiv|Detail|Discussion)\]\((https?://[^\s)]+)\)")


def _summarize_stream(ctx: RunContext, name: str) -> str:
    """Extract a 1–2 sentence digest from the stream's top item for the Brief's
    'From the streams' section, plus a direct citation to the source URL the
    LLM pulled from. Falls back to a plain wikilink if no callout."""
    r = ctx.results.get(name)
    link = f"[[{_STREAM_LINKS.get(name, name)}]]"
    if r is None:
        return "*(skipped)*"
    if not r.ok:
        return f"failed — {r.error}"
    if r.meta.get("pending"):
        return "*(stream pending)*"

    body = r.dashboard_snippet or ""
    digest = _first_callout_digest(body)
    if not digest:
        return f"see {link}"

    # Find the first source URL inside the top callout (the URL the LLM cited).
    src_match = _DIRECT_URL_RE.search(_first_callout_block(body))
    if src_match:
        return f"{digest} — {link} · [source]({src_match.group(1)})"
    return f"{digest} — {link}"


def _first_callout_block(body: str) -> str:
    """Return the full first `>` block (including footer lines) so URL search
    matches against `[Source](...)` lines."""
    lines = body.splitlines()
    out: list[str] = []
    in_block = False
    for line in lines:
        if line.startswith(">"):
            in_block = True
            out.append(line)
        elif in_block:
            break
    return "\n".join(out)


def _first_callout_digest(body: str) -> str:
    """Return up to 2 sentences from the first callout's body in `body`.
    Strips the callout header and `> ` prefixes. Empty if no callout."""
    lines = body.splitlines()
    in_callout = False
    body_lines: list[str] = []
    for line in lines:
        if line.startswith("> [!"):
            in_callout = True
            continue
        if in_callout and line.startswith(">"):
            stripped = line[1:].lstrip()
            # Stop at "Links:", "Source:", "[Source]" footer style lines.
            if stripped.startswith("**Links:**") or stripped.startswith("[Source]") or stripped.startswith("[Release notes]"):
                break
            body_lines.append(stripped)
        elif in_callout:
            break
    text = " ".join(s for s in body_lines if s).strip()
    if not text:
        return ""
    # Strip leading bold tags like `**Authors:** ...` and `**Abstract:**`.
    text = re.sub(r"^\*\*[^*]+\*\*\s*", "", text)
    # First two sentences only.
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z\[])", text, maxsplit=2)
    digest = " ".join(sentences[:2]).strip()
    # Cap length defensively.
    if len(digest) > 280:
        digest = digest[:277].rstrip() + "…"
    return digest


# -- Driver --------------------------------------------------------------------

# Per-stream wall-time budgets. Newer/slower streams get more headroom.
# A stream that exceeds its budget is reported as failed and the orchestrator
# moves on; the thread keeps running until it returns (best-effort isolation
# without process-level kill, which would risk corrupting state writes).
_STREAM_TIMEOUTS_SEC = {
    "weather":   30,
    "news":      1800,   # 15 topics × DDGS+RSS+LLM
    "papers":    600,
    "tech":      600,
    "releases":  1200,
    "curiosity": 300,    # DDGS + LLM + Wikipedia validation for 5 suggestions
    "watchlist": 2400,
    "onthisday": 60,
}
_DEFAULT_TIMEOUT = 300


def _run_stream(name: str, fn: Callable[[RunContext], StreamResult], ctx: RunContext) -> StreamResult:
    """Run a stream with per-stream timeout + exception isolation."""
    budget = _STREAM_TIMEOUTS_SEC.get(name, _DEFAULT_TIMEOUT)
    started = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"hermes-{name}") as pool:
        future = pool.submit(fn, ctx)
        try:
            result = future.result(timeout=budget)
            result.duration_ms = int((time.monotonic() - started) * 1000)
            return result
        except concurrent.futures.TimeoutError:
            return StreamResult(
                name=name, ok=False,
                error=f"Stream exceeded {budget}s timeout",
                duration_ms=int((time.monotonic() - started) * 1000),
            )
        except Exception as e:
            return StreamResult(
                name=name, ok=False,
                error=f"{type(e).__name__}: {e}\n{traceback.format_exc()}",
                duration_ms=int((time.monotonic() - started) * 1000),
            )


def _write_heartbeat(ctx: RunContext) -> None:
    """Drop a status file the dashboard + doctor surface."""
    path = vault.STATE_DIR / "last_run.json"
    payload = {
        "completed_at": vault.now_ist().strftime("%Y-%m-%dT%H:%M:%S%z"),
        "ok": all(r.ok for r in ctx.results.values()),
        "streams": {n: r.ok for n, r in ctx.results.items()},
        "timings_ms": {n: r.duration_ms for n, r in ctx.results.items()},
        "errors": {n: r.error[:300] for n, r in ctx.results.items() if r.error},
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2))
    tmp.replace(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="morning.runner")
    parser.add_argument("--dry-run", action="store_true",
                        help="Skip vault writes; print composed Brief to stdout instead.")
    parser.add_argument("--only", default="",
                        help="Comma-separated stream names to run (default: all).")
    args = parser.parse_args(argv)

    ctx = RunContext(dry_run=args.dry_run)
    only = {s.strip() for s in args.only.split(",") if s.strip()}

    for name, fn in STREAMS:
        if only and name not in only:
            continue
        print(f"[runner] stream: {name}", file=sys.stderr, flush=True)
        ctx.record(_run_stream(name, fn, ctx))

    brief_body = _compose_brief(ctx)

    if args.dry_run:
        print("\n===== composed brief =====\n")
        print(brief_body)
        print("\n===== per-stream status =====\n")
        for name, r in ctx.results.items():
            tag = "ok" if r.ok else "FAIL"
            print(f"  [{tag}] {name}  meta={json.dumps(r.meta)}")
            if not r.ok:
                print(f"        error: {r.error.splitlines()[0]}")
        return 0

    # Write the Brief.
    vault.insert_today_entry(vault.STREAM_NOTES["brief"], brief_body)
    vault.set_frontmatter_updated(vault.STREAM_NOTES["brief"])

    # Regenerate the Dashboard.
    dashboard.regenerate({
        "weather_dashboard":    ctx.results.get("weather",    StreamResult("", False)).dashboard_snippet,
        "news_dashboard":       ctx.results.get("news",       StreamResult("", False)).dashboard_snippet,
        "papers_dashboard":     ctx.results.get("papers",     StreamResult("", False)).dashboard_snippet,
        "tech_dashboard":       ctx.results.get("tech",       StreamResult("", False)).dashboard_snippet,
        "releases_dashboard":   ctx.results.get("releases",   StreamResult("", False)).dashboard_snippet,
        "curiosity_dashboard":  ctx.results.get("curiosity",  StreamResult("", False)).dashboard_snippet,
        "watchlist_dashboard":  ctx.results.get("watchlist",  StreamResult("", False)).dashboard_snippet,
        "onthisday_dashboard":  ctx.results.get("onthisday",  StreamResult("", False)).dashboard_snippet,
    })

    # Touch today's daily note with a one-line activity summary.
    _touch_daily_note(ctx)

    _write_heartbeat(ctx)

    # Print machine-readable summary for the bash wrapper / logs.
    print(json.dumps({
        "ok": all(r.ok for r in ctx.results.values()),
        "streams": {n: {"ok": r.ok, "meta": r.meta, "error": r.error[:200] if r.error else ""}
                    for n, r in ctx.results.items()},
    }, indent=2))

    return 0 if all(r.ok for r in ctx.results.values()) else 2


def _touch_daily_note(ctx: RunContext) -> None:
    """Initialize today's daily note with proper frontmatter and append a
    one-line activity entry. Per HERMES.md, no top-level `# Heading` —
    Obsidian uses the filename as the title.

    The daily note is an append-only log of what each run touched. The rich
    per-day Brief lives in `📌 Daily Brief.md`, not here."""
    p = vault.daily_note_path()
    existing = vault.read(p)
    now = vault.now_ist().strftime("%Y-%m-%dT%H:%M:%S")
    line = f"- {now} — morning-run touched: {', '.join(sorted(ctx.results.keys()))}"

    if existing:
        # If the file was created in legacy `# Heading` mode, strip it and
        # graft on proper frontmatter the first time we touch it.
        if existing.startswith("# "):
            stripped = re.sub(r"^# [^\n]*\n+", "", existing)
            stripped = re.sub(r"^## Activity\n+", "", stripped)
            fm = (
                "---\n"
                f"created: {vault.today_str()}\n"
                f"updated: {now}\n"
                "unread: true\n"
                "---\n\n"
                "## Activity\n\n"
            )
            existing = fm + stripped
        if line in existing:
            return
        # Bump `updated:` in frontmatter if present.
        existing = re.sub(
            r"^(updated:)[^\n]*",
            f"\\1 {now}",
            existing,
            count=1,
            flags=re.MULTILINE,
        )
        vault.write(p, existing.rstrip() + "\n" + line + "\n")
        return

    body = (
        "---\n"
        f"created: {vault.today_str()}\n"
        f"updated: {now}\n"
        "unread: true\n"
        "---\n\n"
        "## Activity\n\n"
        f"{line}\n"
    )
    vault.write(p, body)


if __name__ == "__main__":
    sys.exit(main())
