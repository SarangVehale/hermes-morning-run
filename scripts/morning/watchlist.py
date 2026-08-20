"""Daily Watchlist stream.

For each creator in `_watchlist.yaml`, fetch the latest items (YT channel RSS
or blog RSS/Atom), pull transcript / HTML, summarize via the LLM, and write a
detail file under `08 Summaries/`. The stream note gets a one-paragraph index
entry per item with a wikilink to its detail.

Hard caps:
- 8 items processed per morning run
- First-run state-empty: only the single most-recent item per creator
"""
from __future__ import annotations

import datetime
import html as html_mod
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

import feedparser

from . import config, feed_health, images, llm, vault


STATE_FILE = vault.STATE_DIR / "watchlist-last-seen.json"
SUMMARIES_ROOT = vault.SUMMARIES
UA = "hermes-morning/1.0 (hermes-morning@example.com)"
YT_FEED = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
MAX_ITEMS_PER_RUN = config.get("watchlist", "max_items_per_run", default=8)


@dataclass
class Creator:
    name: str
    source: str           # "youtube" or "blog"
    channel_id: str = ""  # YT only
    url: str = ""         # blog homepage
    feed: str = ""        # blog feed URL


@dataclass
class Item:
    creator: Creator
    item_id: str          # YT video id or blog post URL
    title: str
    url: str
    published: str        # YYYY-MM-DD


# -- Watchlist YAML parse ------------------------------------------------------

def _parse_watchlist(raw: str) -> list[Creator]:
    """Minimal YAML parser for the watchlist shape. Avoids PyYAML dep."""
    creators: list[Creator] = []
    section = ""
    current: dict[str, str] = {}

    def _flush() -> None:
        nonlocal current
        if not current:
            return
        if section == "youtube":
            creators.append(Creator(
                name=current.get("name", ""),
                source="youtube",
                channel_id=current.get("channel_id", "") or "",
            ))
        elif section == "blogs":
            feed = current.get("feed", "") or ""
            if feed.lower() in ("null", "none", ""):
                feed = ""
            creators.append(Creator(
                name=current.get("name", ""),
                source="blog",
                url=current.get("url", "") or "",
                feed=feed,
            ))
        current = {}

    for raw_line in raw.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        m_section = re.match(r"^(youtube|blogs):\s*$", line)
        if m_section:
            _flush()
            section = m_section.group(1)
            continue
        m_dash = re.match(r"\s*-\s*(\w+):\s*(.*?)\s*$", line)
        if m_dash:
            _flush()
            current = {m_dash.group(1): m_dash.group(2)}
            continue
        m_kv = re.match(r"\s+(\w+):\s*(.*?)\s*$", line)
        if m_kv:
            current[m_kv.group(1)] = m_kv.group(2)
    _flush()
    # Filter out malformed.
    return [c for c in creators if c.name and (c.channel_id or c.feed)]


def _load_watchlist() -> list[Creator]:
    raw = vault.read(vault.WATCHLIST_YAML)
    return _parse_watchlist(raw) if raw else []


# -- State ---------------------------------------------------------------------

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


# -- YouTube discovery ---------------------------------------------------------

def _fetch_yt_feed(channel_id: str) -> list[dict]:
    """Fetch a YouTube channel RSS. YouTube's RSS endpoint routinely
    5xx-errors on individual channels for minutes at a time. Retry twice
    with backoff, then record failure via feed_health. After
    SKIP_THRESHOLD consecutive days of failure the channel is silently
    skipped for that morning."""
    import time
    url = YT_FEED.format(channel_id=channel_id)
    fh_key = f"yt:{channel_id}"
    if feed_health.should_skip(fh_key):
        return []

    last_reason = ""
    for attempt in (1, 2, 3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=15) as r:
                raw = r.read()
            feed_health.record_success(fh_key)
            return feedparser.parse(raw).entries  # type: ignore[return-value]
        except urllib.error.HTTPError as e:
            last_reason = f"HTTPError {e.code}"
            # Retry on transient 5xx and 429. 404 = channel really gone.
            if e.code in (429, 500, 502, 503) and attempt < 3:
                time.sleep(2 * attempt)
                continue
            break
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last_reason = f"{type(e).__name__}"
            if attempt < 3:
                time.sleep(2 * attempt)
                continue
            break

    print(f"[watchlist] yt feed failed {channel_id}: {last_reason}", file=sys.stderr)
    feed_health.record_failure(fh_key, last_reason)
    return []


def _new_yt_items(creator: Creator, last_id: str) -> list[Item]:
    if not creator.channel_id:
        return []
    entries = _fetch_yt_feed(creator.channel_id)
    out: list[Item] = []
    for e in entries:
        vid = (e.get("yt_videoid") or "").strip()
        if not vid and e.get("id"):
            m = re.search(r"video:([\w-]+)", e["id"])
            if m:
                vid = m.group(1)
        if not vid:
            continue
        if vid == last_id:
            break
        published = ""
        if e.get("published_parsed"):
            published = datetime.datetime(*e.published_parsed[:6]).strftime("%Y-%m-%d")
        out.append(Item(
            creator=creator,
            item_id=vid,
            title=(e.get("title") or "").strip(),
            url=f"https://www.youtube.com/watch?v={vid}",
            published=published,
        ))
    # First-run safety: cap to single newest per channel.
    if not last_id and out:
        out = out[:1]
    return out


# -- Blog discovery ------------------------------------------------------------

def _fetch_feed(url: str) -> list[dict]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
        print(f"[watchlist] blog feed failed {url}: {type(e).__name__}: {e}", file=sys.stderr)
        return []
    return feedparser.parse(raw).entries  # type: ignore[return-value]


def _new_blog_items(creator: Creator, last_url: str) -> list[Item]:
    if not creator.feed:
        return []
    entries = _fetch_feed(creator.feed)
    out: list[Item] = []
    for e in entries:
        link = e.get("link", "").strip()
        if not link:
            continue
        # Some feeds return relative URLs — resolve against the feed/blog root.
        if not link.startswith(("http://", "https://")):
            base = creator.url or creator.feed
            link = urllib.parse.urljoin(base, link)
        if link == last_url:
            break
        published = ""
        for key in ("published_parsed", "updated_parsed"):
            if e.get(key):
                published = datetime.datetime(*e[key][:6]).strftime("%Y-%m-%d")
                break
        out.append(Item(
            creator=creator,
            item_id=link,
            title=(e.get("title") or "").strip(),
            url=link,
            published=published,
        ))
    if not last_url and out:
        out = out[:1]
    return out


# -- YouTube transcript --------------------------------------------------------

_YT_DLP = os.environ.get("YT_DLP", os.path.expanduser("~/.local/bin/yt-dlp"))


def _yt_transcript(video_id: str) -> str:
    """Return plain-text transcript or empty string if unavailable."""
    if not Path(_YT_DLP).exists() and not _which(_YT_DLP):
        print(f"[watchlist] yt-dlp not found at {_YT_DLP}", file=sys.stderr)
        return ""
    with tempfile.TemporaryDirectory(prefix="hermes-yt-") as td:
        try:
            subprocess.run(
                [
                    _YT_DLP,
                    "--quiet", "--skip-download",
                    "--write-auto-sub", "--sub-lang", "en",
                    "--sub-format", "json3",
                    "-o", f"{td}/%(id)s",
                    f"https://www.youtube.com/watch?v={video_id}",
                ],
                check=False, timeout=120, capture_output=True,
            )
        except subprocess.TimeoutExpired:
            print(f"[watchlist] yt-dlp timeout on {video_id}", file=sys.stderr)
            return ""
        # Find any .json3 file written.
        for p in Path(td).glob("*.json3"):
            return _json3_to_text(p)
    return ""


def _which(prog: str) -> str | None:
    for d in os.environ.get("PATH", "").split(":"):
        p = Path(d) / Path(prog).name
        if p.is_file() and os.access(p, os.X_OK):
            return str(p)
    return None


def _json3_to_text(path: Path) -> str:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    parts: list[str] = []
    for ev in data.get("events", []):
        for s in ev.get("segs", []) or []:
            txt = s.get("utf8", "")
            if txt:
                parts.append(txt)
    text = "".join(parts)
    # Collapse repeats and excessive whitespace.
    text = re.sub(r"\s+", " ", text).strip()
    return text


# -- Blog HTML fetch -----------------------------------------------------------

_HTML_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def _fetch_blog_text(url: str) -> str:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
        print(f"[watchlist] blog fetch failed {url}: {type(e).__name__}: {e}", file=sys.stderr)
        return ""
    # Strip script/style first, then all tags. Crude but defuddle-free.
    raw = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", raw, flags=re.IGNORECASE | re.DOTALL)
    text = html_mod.unescape(_HTML_TAG.sub(" ", raw))
    return _WS.sub(" ", text).strip()


# -- LLM summarization ---------------------------------------------------------

_SUMMARY_SYSTEM = (
    "You write detailed structured summaries of YouTube videos and blog posts "
    "for a personal knowledge vault. The user wants the substance — what was "
    "actually said, what specific numbers/names/concepts appeared — not a "
    "marketing-style 'this video covers X' framing.\n"
    "\n"
    "OUTPUT exactly this structure (no code fences, no preamble):\n"
    "> [!summary]- One-sentence framing of the whole item.\n"
    "\n"
    "## What was covered\n"
    "\n"
    "Three to six paragraphs walking through the substance. Specific names, "
    "numbers, dates, claims. Wikilink concepts on first mention: [[Concept]].\n"
    "\n"
    "## New to this vault\n"
    "\n"
    "Bulleted list of [[Wikilinked Concept]] items the creator introduced that "
    "you would not expect to already be in a generic knowledge base. Aim for "
    "5–12. If nothing qualifies, write `- Nothing new this time.`\n"
    "\n"
    "## Builds on\n"
    "\n"
    "Bulleted list of [[Wikilinked Concept]] items that are well-established "
    "prerequisites for understanding this. If unknown, write `- (unknown)`.\n"
)


def _summarize(item: Item, source_text: str, *, prefer_model: str) -> str:
    # Cap source text by character count so the prompt stays under context.
    capped = source_text[:18000]
    user = (
        f"Title: {item.title}\n"
        f"Creator: {item.creator.name}\n"
        f"Source URL: {item.url}\n"
        f"Published: {item.published}\n"
        f"\n"
        f"--- BEGIN SOURCE TEXT ---\n{capped}\n--- END SOURCE TEXT ---\n"
        f"\n"
        f"Write the structured summary now."
    )
    return llm.chat(
        system=_SUMMARY_SYSTEM,
        user=user,
        max_tokens=1200,
        temperature=0.3,
        prefer=prefer_model,
    ).strip()


# -- Detail file write ---------------------------------------------------------

_FN_BAD = re.compile(r"[\\/:*?\"<>|]+")
_FN_WS = re.compile(r"\s+")


def _safe_title(title: str, max_len: int = 80) -> str:
    cleaned = _FN_BAD.sub("", title)
    cleaned = _FN_WS.sub(" ", cleaned).strip()
    return cleaned[:max_len].rstrip(" -")


def _detail_filename(item: Item) -> str:
    return f"{item.creator.name} - {item.published or 'undated'} - {_safe_title(item.title)}.md"


def _wikilink_target(item: Item) -> str:
    """The wikilink text Obsidian will resolve to the detail file (sans .md)."""
    return _detail_filename(item)[:-3]


def _extract_new_concepts(summary_md: str) -> list[str]:
    """Pull wikilinked concepts from the `## New to this vault` section."""
    m = re.search(r"## New to this vault\s*\n(.*?)(?=\n## |\Z)", summary_md, re.DOTALL)
    if not m:
        return []
    return re.findall(r"\[\[([^\]]+)\]\]", m.group(1))


def _read_minutes(text: str) -> int:
    """Rough reading-time estimate at 220 wpm. Rounds up to at least 1 min."""
    words = len(re.findall(r"\b\w+\b", text))
    return max(1, round(words / 220))


def _write_detail(item: Item, summary_md: str, duration: str = "") -> Path:
    today = vault.now_ist().date().isoformat()
    read_min = _read_minutes(summary_md)
    fm = (
        "---\n"
        f"created: {today}\n"
        f"updated: {today}\n"
        f"creator: [[{item.creator.name}]]\n"
        f"source: {item.creator.source}\n"
        f"url: {item.url}\n"
        f"duration: {duration or '—'}\n"
        f"upload_date: {item.published or '—'}\n"
        f"read_minutes: {read_min}\n"
        f"unread: true\n"
        "---\n\n"
    )
    bibliography = f"> [!info] Source\n> [{item.title}]({item.url}) — [[{item.creator.name}]] · ~{read_min} min read\n\n"
    body = fm + bibliography + summary_md.strip() + "\n"

    path = SUMMARIES_ROOT / item.creator.name / "Summaries" / _detail_filename(item)
    vault.write(path, body)
    return path


# -- Stream entry per item -----------------------------------------------------

def _stream_paragraph(item: Item, summary_md: str) -> str:
    """One-paragraph index entry pointing at the detail file + direct source.

    Direct source URL ([Source](url)) is included so the user can jump to the
    original without going through the detail file first. YouTube thumbnails
    embed inline above the paragraph."""
    new_concepts = _extract_new_concepts(summary_md)
    framing = ""
    m = re.search(r"> \[!summary\]-\s*(.+?)\s*\n", summary_md)
    if m:
        framing = m.group(1).rstrip(". ")
    parts = [f"[[{item.creator.name}]]"]
    if framing:
        parts.append(f"covered {framing[0].lower() + framing[1:] if framing else ''}.")
    else:
        parts.append(f"posted '{item.title}'.")
    if new_concepts:
        parts.append("New-to-vault concepts: " + ", ".join(f"[[{c}]]" for c in new_concepts[:8]) + ".")
    parts.append(f"Detail: [[{_wikilink_target(item)}]] · [Source]({item.url}).")
    body = " ".join(parts)

    img_md = images.embed(item.url, width_hint=560)
    if img_md:
        return f"{img_md}\n\n{body}"
    return body


# -- Run -----------------------------------------------------------------------

def run(*, prefer_model: str = "primary") -> str:
    state = _load_state()
    creators = _load_watchlist()
    if not creators:
        body = "> [!warning] Watchlist: empty `_watchlist.yaml`."
        vault.insert_today_entry(vault.STREAM_NOTES["watchlist"], body)
        vault.set_frontmatter_updated(vault.STREAM_NOTES["watchlist"])
        return body

    # Discover candidate items across all creators — per-creator isolation so
    # one broken feed never kills the whole stream.
    candidates: list[Item] = []
    creator_failures: list[tuple[str, str]] = []
    for c in creators:
        state_key = f"{c.source}:{c.name}"
        last_seen = state.get(state_key, "")
        try:
            if c.source == "youtube":
                candidates.extend(_new_yt_items(c, last_seen))
            elif c.source == "blog":
                candidates.extend(_new_blog_items(c, last_seen))
        except Exception as e:
            creator_failures.append((c.name, f"{type(e).__name__}: {e}"))
            print(f"[watchlist] discovery failed for {c.name}: {type(e).__name__}: {e}", file=sys.stderr)
            continue

    if not candidates:
        body = "Nothing new from the watchlist today."
        vault.insert_today_entry(vault.STREAM_NOTES["watchlist"], body)
        vault.set_frontmatter_updated(vault.STREAM_NOTES["watchlist"])
        return body

    # Round-robin so every creator gets a turn before any creator gets a
    # second slot. Within each creator's queue, newest item first. This is
    # the difference between "Linus drops 2 videos and takes 2 of 8 slots
    # while StarTalk gets cut" and fair rotation.
    by_creator: dict[str, list[Item]] = {}
    for it in candidates:
        by_creator.setdefault(it.creator.name, []).append(it)
    for queue in by_creator.values():
        queue.sort(key=lambda i: i.published, reverse=True)

    # Creators ordered by their newest item's date (descending) — so on a
    # quiet day, the most recently active creators surface first.
    creator_order = sorted(
        by_creator.keys(),
        key=lambda n: by_creator[n][0].published if by_creator[n] else "",
        reverse=True,
    )

    rotated: list[Item] = []
    while creator_order and len(rotated) < MAX_ITEMS_PER_RUN:
        next_round: list[str] = []
        for name in creator_order:
            if not by_creator[name]:
                continue
            rotated.append(by_creator[name].pop(0))
            if by_creator[name]:
                next_round.append(name)
            if len(rotated) >= MAX_ITEMS_PER_RUN:
                break
        creator_order = next_round

    skipped_count = max(0, len(candidates) - len(rotated))
    candidates = rotated

    paragraphs: list[str] = []
    for item in candidates:
        if item.creator.source == "youtube":
            text = _yt_transcript(item.item_id)
            if not text:
                paragraphs.append(
                    f"> [!warning] [[{item.creator.name}]] posted "
                    f"`{item.title}` but auto-subs are unavailable. Skipped. "
                    f"[Watch on YouTube]({item.url})"
                )
                state[f"{item.creator.source}:{item.creator.name}"] = item.item_id
                continue
        else:
            text = _fetch_blog_text(item.url)
            if not text or len(text) < 200:
                paragraphs.append(
                    f"> [!warning] [[{item.creator.name}]] posted "
                    f"`{item.title}` but the page returned no extractable "
                    f"text. Skipped. [Read]({item.url})"
                )
                state[f"{item.creator.source}:{item.creator.name}"] = item.item_id
                continue

        try:
            summary_md = _summarize(item, text, prefer_model=prefer_model)
        except llm.LLMError as e:
            paragraphs.append(
                f"> [!warning] [[{item.creator.name}]] — `{item.title}` summary "
                f"failed: {e}. [Source]({item.url})"
            )
            state[f"{item.creator.source}:{item.creator.name}"] = item.item_id
            continue

        _write_detail(item, summary_md)
        paragraphs.append(_stream_paragraph(item, summary_md))
        state[f"{item.creator.source}:{item.creator.name}"] = item.item_id

    if skipped_count:
        paragraphs.append(
            f"> [!warning] {skipped_count} additional new item(s) were skipped "
            f"by the per-run cap of {MAX_ITEMS_PER_RUN}. Run again or process "
            f"manually."
        )

    if creator_failures:
        paragraphs.append(
            "> [!warning] Creator-feed errors (other creators succeeded):\n"
            + "\n".join(f"> - **{name}** — {err[:120]}" for name, err in creator_failures[:5])
        )

    _save_state(state)

    body = "\n\n".join(paragraphs) if paragraphs else "Nothing new from the watchlist today."
    vault.insert_today_entry(vault.STREAM_NOTES["watchlist"], body)
    vault.set_frontmatter_updated(vault.STREAM_NOTES["watchlist"])
    return body


if __name__ == "__main__":
    print(run())
