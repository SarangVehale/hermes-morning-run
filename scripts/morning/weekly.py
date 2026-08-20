"""Weekly recap stream — Sunday 20:00 IST.

Reads the past 7 days (Mon-Sun) of stream notes + daily notes and composes a
dashboard-style recap per `📅 Weekly Recap.md`'s spec. Anti-fabrication:
everything we feed to the LLM is verbatim text from already-written stream
notes; the LLM only picks + writes short framings. Calendar and Email sections
stay as `[!warning]` stubs until OAuth refresh.

Invoke: `python -m morning.weekly` (with PYTHONPATH=~/scripts)."""
from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from . import llm, vault


# -- Date math -----------------------------------------------------------------

def week_window() -> tuple[datetime.date, datetime.date]:
    """Return (monday, sunday) covering the week the recap is recapping.

    Sunday 20:00 IST runs — the week is Monday of this week through today
    (Sunday). If invoked on a non-Sunday, falls back to the most recent
    completed Monday-Sunday range."""
    today = vault.now_ist().date()
    # weekday(): Monday=0, Sunday=6
    if today.weekday() == 6:
        monday = today - datetime.timedelta(days=6)
        sunday = today
    else:
        # Most recent completed week
        sunday = today - datetime.timedelta(days=today.weekday() + 1)
        monday = sunday - datetime.timedelta(days=6)
    return monday, sunday


def week_heading(monday: datetime.date) -> str:
    return f"### [[Week of {monday.strftime('%m-%d-%y')}]]"


def month_heading_for(monday: datetime.date) -> str:
    return monday.strftime("## %Y-%m")


# -- Stream entry extraction ---------------------------------------------------

_DAY_HEADING = re.compile(r"^### \[\[(\d{2})-(\d{2})-(\d{2}) \w{3}\]\]\s*$", re.MULTILINE)


@dataclass
class DayEntry:
    date: datetime.date
    body: str


def extract_week_entries(stream_path: Path, monday: datetime.date, sunday: datetime.date) -> list[DayEntry]:
    """Return entries from `stream_path` whose `### [[MM-DD-YY ddd]]` heading
    falls within [monday, sunday]. Bodies are extracted up to the next day
    heading or `## YYYY-MM` heading."""
    content = vault.read(stream_path)
    if not content:
        return []

    headings = list(_DAY_HEADING.finditer(content))
    entries: list[DayEntry] = []
    for i, m in enumerate(headings):
        mm, dd, yy = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            d = datetime.date(2000 + yy, mm, dd)
        except ValueError:
            continue
        if not (monday <= d <= sunday):
            continue
        body_start = m.end()
        # Body runs until next day heading, next month heading, or end.
        next_day = headings[i + 1].start() if i + 1 < len(headings) else len(content)
        next_month = content.find("\n## ", body_start, next_day)
        body_end = next_month if next_month != -1 else next_day
        body = content[body_start:body_end].strip()
        entries.append(DayEntry(date=d, body=body))
    return entries


def all_callouts(body: str) -> list[str]:
    """Split a day-section body into individual `>` callouts (each starting with
    `> [!...]`). Non-callout paragraphs are returned as their own entries."""
    lines = body.splitlines()
    blocks: list[str] = []
    cur: list[str] = []
    in_callout = False
    for line in lines:
        if line.startswith("> [!"):
            if cur:
                blocks.append("\n".join(cur).strip())
                cur = []
            in_callout = True
            cur.append(line)
        elif line.startswith(">"):
            cur.append(line)
        elif line.strip() == "":
            if cur:
                blocks.append("\n".join(cur).strip())
                cur = []
            in_callout = False
        else:
            if cur and not in_callout:
                cur.append(line)
            elif cur:
                blocks.append("\n".join(cur).strip())
                cur = [line]
                in_callout = False
            else:
                cur = [line]
                in_callout = False
    if cur:
        blocks.append("\n".join(cur).strip())
    return [b for b in blocks if b]


# -- Daily-note + heatmap data -------------------------------------------------

def count_daily_notes(monday: datetime.date, sunday: datetime.date) -> int:
    """Number of day-files in `02 Daily/YYYY/MM/` within the window."""
    count = 0
    d = monday
    while d <= sunday:
        path = vault.DAILY / f"{d.year}" / f"{d.month:02d}" / f"{d.strftime('%m-%d-%y')} {d.strftime('%a')}.md"
        if path.exists():
            count += 1
        d += datetime.timedelta(days=1)
    return count


def current_streak() -> int:
    """How many days back from today (inclusive) have a daily note, before the
    first gap."""
    today = vault.now_ist().date()
    streak = 0
    d = today
    while True:
        path = vault.DAILY / f"{d.year}" / f"{d.month:02d}" / f"{d.strftime('%m-%d-%y')} {d.strftime('%a')}.md"
        if path.exists():
            streak += 1
            d -= datetime.timedelta(days=1)
        else:
            break
    return streak


def streak_break_day(monday: datetime.date, sunday: datetime.date) -> str | None:
    """If the streak broke inside [monday, sunday], return that day's `Wed` form."""
    d = monday
    last_state: bool | None = None
    break_day: datetime.date | None = None
    while d <= sunday:
        path = vault.DAILY / f"{d.year}" / f"{d.month:02d}" / f"{d.strftime('%m-%d-%y')} {d.strftime('%a')}.md"
        is_present = path.exists()
        if last_state is True and not is_present:
            break_day = d
            break
        last_state = is_present
        d += datetime.timedelta(days=1)
    return break_day.strftime("%a") if break_day else None


# -- Concept stub density ------------------------------------------------------

CONCEPT_DIRS = [vault.VAULT / "07 References", vault.VAULT / "04 People", vault.VAULT / "06 Research"]


def concept_stub_counts(monday: datetime.date, sunday: datetime.date) -> tuple[int, int]:
    """Return (created_this_week, still_empty). 'Empty' = file has only
    frontmatter, no body content beyond it."""
    created = 0
    empty = 0
    monday_dt = datetime.datetime.combine(monday, datetime.time.min)
    sunday_dt = datetime.datetime.combine(sunday, datetime.time.max)
    for root in CONCEPT_DIRS:
        if not root.exists():
            continue
        for md in root.rglob("*.md"):
            try:
                stat = md.stat()
            except OSError:
                continue
            mtime = datetime.datetime.fromtimestamp(stat.st_mtime)
            if not (monday_dt <= mtime <= sunday_dt):
                continue
            created += 1
            text = vault.read(md)
            # "Empty" if body after the closing `---\n` is whitespace-only.
            fm_end = text.find("\n---\n", 3)
            body = text[fm_end + len("\n---\n"):] if fm_end != -1 else text
            if not body.strip():
                empty += 1
    return created, empty


# -- LLM theme picker ----------------------------------------------------------

_THEME_SYSTEM = (
    "You read a week of brief summaries from a personal knowledge vault and "
    "give the user ONE sentence describing the dominant thread of the week. "
    "Examples of good outputs:\n"
    "  - 'Quantum error correction news + a heavy local-LLM watchlist week.'\n"
    "  - 'Mostly travel and meetings; very few news items of note.'\n"
    "  - 'AI regulation news cluster + Linus Tech Tips dominated the watchlist.'\n"
    "If no dominant thread is visible, output EXACTLY: 'Mixed week — no dominant thread.'\n"
    "OUTPUT: one line, no preamble, no markdown, no quotes."
)


def llm_theme(week_blob: str, *, prefer_model: str = "primary") -> str:
    try:
        out = llm.chat(
            system=_THEME_SYSTEM,
            user=f"This week's stream content:\n\n{week_blob[:8000]}\n\nGive me one sentence.",
            max_tokens=80,
            temperature=0.3,
            prefer=prefer_model,
        ).strip()
    except llm.LLMError as e:
        return f"(theme inference failed: {e})"
    # Strip surrounding quotes if the LLM added any.
    return out.strip().strip('"').strip("'").splitlines()[0]


# -- Section builders ----------------------------------------------------------

def _stream_callout(stream_key: str, entries: list[DayEntry], header_text: str,
                    type_token: str, cap: int) -> str:
    """Collapse the top `cap` callouts from a stream's week into one
    dropdown-style callout."""
    note_name = vault.STREAM_NOTES[stream_key].stem
    arrow = f"[[{note_name}|↗]]"
    callouts: list[tuple[datetime.date, str]] = []
    for entry in entries:
        for block in all_callouts(entry.body):
            if block.startswith("> [!warning]"):
                continue
            callouts.append((entry.date, block))
    if not callouts:
        return f"> [!{type_token}]- {header_text} — quiet week {arrow}\n> Nothing notable this week."
    # Most recent first, take top `cap`.
    callouts.sort(key=lambda x: x[0], reverse=True)
    top = callouts[:cap]
    header_lines = [f"> [!{type_token}]- {header_text} — {len(callouts)} item(s) this week {arrow}"]
    for date, block in top:
        # Obsidian nested callouts: each line gets an extra `> ` prefix.
        nested = "\n".join(f"> {line}" for line in block.splitlines())
        header_lines.append(nested)
        header_lines.append(">")
    return "\n".join(header_lines).rstrip(">").rstrip()


def _section_watchlist(entries: list[DayEntry]) -> str:
    """Top 5 watchlist items by detail-wikilink count (proxy for innovation)."""
    arrow = "[[🎬 Daily Watchlist|↗]]"
    items: list[tuple[datetime.date, str, str]] = []  # (date, wikilink_target, angle)
    for entry in entries:
        for para in (p.strip() for p in entry.body.split("\n\n") if p.strip()):
            if para.startswith("> [!warning]"):
                continue
            det = re.search(r"Detail:\s*\[\[([^\]]+)\]\]", para)
            if not det:
                continue
            body_m = re.match(r"\[\[[^\]]+\]\]\s*(.+?)\s*(?:New-to-vault concepts:[^.]*\.\s*)?Detail:", para, re.DOTALL)
            angle = body_m.group(1).strip() if body_m else ""
            sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z])", angle)
            angle = sentences[0].strip() if sentences else angle[:160]
            items.append((entry.date, det.group(1), angle))
    if not items:
        return f"> [!note]- Watchlist — quiet week {arrow}\n> No new items from any tracked creator."
    items.sort(key=lambda x: x[0], reverse=True)
    top = items[:5]
    lines = [f"> [!note]- Watchlist — top 5 of {len(items)} new this week {arrow}"]
    for date, target, angle in top:
        if angle:
            lines.append(f"> - [[{target}]] — {angle}")
        else:
            lines.append(f"> - [[{target}]]")
    return "\n".join(lines)


# -- Top-level run -------------------------------------------------------------

def run(*, prefer_model: str = "primary", dry_run: bool = False) -> str:
    monday, sunday = week_window()
    daily_count = count_daily_notes(monday, sunday)
    streak = current_streak()
    broke_on = streak_break_day(monday, sunday)
    stubs_created, stubs_empty = concept_stub_counts(monday, sunday)

    news_entries     = extract_week_entries(vault.STREAM_NOTES["news"],     monday, sunday)
    papers_entries   = extract_week_entries(vault.STREAM_NOTES["papers"],   monday, sunday)
    tech_entries     = extract_week_entries(vault.STREAM_NOTES["tech"],     monday, sunday)
    releases_entries = extract_week_entries(vault.STREAM_NOTES["releases"], monday, sunday)
    watch_entries    = extract_week_entries(vault.STREAM_NOTES["watchlist"], monday, sunday)

    # Theme — feed the LLM short blurbs from each stream.
    blob_parts: list[str] = []
    for label, entries in [
        ("News", news_entries), ("Papers", papers_entries), ("Tech", tech_entries),
        ("Releases", releases_entries), ("Watchlist", watch_entries),
    ]:
        for e in entries[-3:]:  # most recent few per stream
            preview = re.sub(r"\s+", " ", e.body)[:300]
            blob_parts.append(f"[{label} {e.date.isoformat()}] {preview}")
    week_blob = "\n".join(blob_parts)
    theme = llm_theme(week_blob, prefer_model=prefer_model) if week_blob else "Mixed week — no dominant thread."

    # Compose body.
    week_h = week_heading(monday)
    parts = [
        week_h,
        "",
        f"**Theme of the week:** {theme}",
        "",
        _stream_callout("news",     news_entries,     "News",      "note", cap=3),
        "",
        _section_watchlist(watch_entries),
        "",
        _stream_callout("papers",   papers_entries,   "Papers",    "paper", cap=3),
        "",
        _stream_callout("tech",     tech_entries,     "Tech",      "tech", cap=3),
        "",
        _stream_callout("releases", releases_entries, "GitHub Releases", "note", cap=5),
        "",
        f"**Concept stub density:** {stubs_created} created this week ({stubs_empty} still empty, {stubs_created - stubs_empty} filled in).",
        "",
        (f"**Heatmap status:** {daily_count}/7 days touched. Current streak: {streak} days."
         + (f" Streak broke on {broke_on}." if broke_on else "")),
    ]
    body = "\n".join(parts)

    if dry_run:
        return body

    # Insert week entry into the recap note using same monthly-grouping convention.
    path = vault.STREAM_NOTES["weekly"]
    content = vault.read(path)
    mh = month_heading_for(monday)
    if not content:
        new = f"{mh}\n\n{body}\n"
        vault.write(path, new)
    else:
        # Use vault.insert_today_entry-style logic but for week-heading.
        from . import vault as _v
        insert_at = _v.find_insertion_point(content)
        # Look for existing week-heading
        existing_idx = content.find(week_h, insert_at)
        if existing_idx != -1:
            next_week = content.find("\n### [[Week of ", existing_idx + len(week_h))
            if next_week == -1:
                content = content[:existing_idx] + body + "\n"
            else:
                content = content[:existing_idx] + body + "\n\n" + content[next_week + 1:]
        else:
            mh_idx = content.find(mh, insert_at)
            if mh_idx != -1:
                after_mh = content.find("\n", mh_idx) + 1
                content = content[:after_mh] + "\n" + body + "\n\n" + content[after_mh:]
            else:
                content = content[:insert_at] + f"{mh}\n\n{body}\n\n" + content[insert_at:]
        vault.write(path, content)

    vault.set_frontmatter_updated(path)
    return body


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="morning.weekly")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    body = run(dry_run=args.dry_run)
    if args.dry_run:
        print(body)
    else:
        print(json.dumps({"ok": True, "len": len(body)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
