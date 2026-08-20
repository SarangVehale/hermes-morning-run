"""Vault path constants + read/write helpers + daily note management.

Convention from HERMES.md: each stream note has its [!prompt]- callout at the
top; today's entry gets inserted IMMEDIATELY AFTER the closing `>` line of
that callout (or after the existing `## YYYY-MM` header if present for today's
month)."""
from __future__ import annotations

import datetime
import re
from pathlib import Path

VAULT = Path.home() / "vault-ai"
UPDATES = VAULT / "01 Updates"
DAILY = VAULT / "02 Daily"
SUMMARIES = VAULT / "08 Summaries"

STREAM_NOTES = {
    "news":        UPDATES / "📰 Daily News.md",
    "watchlist":   UPDATES / "🎬 Daily Watchlist.md",
    "papers":      UPDATES / "📄 Daily Papers.md",
    "tech":        UPDATES / "🔬 Daily Tech.md",
    "releases":    UPDATES / "🔄 GitHub Releases.md",
    "curiosity":   UPDATES / "🪅 Daily Curiosity.md",
    "brief":       UPDATES / "📌 Daily Brief.md",
    "triage":      UPDATES / "📥 Email Triage.md",
    "dashboard":   VAULT / "🏠 Dashboard.md",
    "weekly":      UPDATES / "📅 Weekly Recap.md",
}

TASKS_FILE = VAULT / "📋 Tasks.md"
HERMES_FILE = VAULT / "HERMES.md"
WATCHLIST_YAML = VAULT / "_watchlist.yaml"
TOOLS_YAML = VAULT / "_tools.yaml"

STATE_DIR = Path.home() / ".hermes" / "state"
STATE_DIR.mkdir(parents=True, exist_ok=True)


def now_ist() -> datetime.datetime:
    """Return current datetime in IST (UTC+5:30)."""
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30)))


def today_str() -> str:
    """`06-06-26 Sat` form used in vault note headings."""
    d = now_ist().date()
    return d.strftime("%m-%d-%y") + " " + d.strftime("%a")


def daily_note_path() -> Path:
    """Path to today's daily note in 02 Daily/YYYY/MM/."""
    d = now_ist().date()
    return DAILY / f"{d.year}" / f"{d.month:02d}" / f"{today_str()}.md"


def month_heading() -> str:
    return now_ist().strftime("## %Y-%m")


def day_heading() -> str:
    return f"### [[{today_str()}]]"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def write(path: Path, text: str) -> None:
    """Atomic write: tmp file + rename, so partial writes can't corrupt the
    target on power loss or an interrupted run."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


# -- Stream note insertion -----------------------------------------------------

_PROMPT_CALLOUT_END = re.compile(
    r"^(> .*\n)+(?=\n(?!>))",
    re.MULTILINE,
)


def find_insertion_point(content: str) -> int:
    """Return the byte offset immediately after the closing `>` line of the
    top-of-file `[!prompt]-` callout block, plus one blank line. Used to insert
    today's entry without touching the durable spec callout."""
    # Find the end of the contiguous `> ...` block that starts at line 1 (after frontmatter).
    # Frontmatter is between `---\n` ... `\n---\n`.
    fm_end = content.find("\n---\n", 3)
    body_start = fm_end + len("\n---\n") if fm_end != -1 else 0
    # Skip blank lines after frontmatter.
    i = body_start
    while i < len(content) and content[i] in " \n":
        i += 1
    # Walk the prompt-callout block (lines starting with `>`).
    while i < len(content):
        end_of_line = content.find("\n", i)
        if end_of_line == -1:
            end_of_line = len(content)
        line = content[i:end_of_line]
        if line.startswith(">"):
            i = end_of_line + 1
            continue
        # First non-callout line; this is where we insert (one blank line below).
        if line.strip() == "":
            return end_of_line + 1
        return i
    return len(content)


def insert_today_entry(path: Path, entry_md: str) -> None:
    """Insert today's day-heading + entry markdown after the prompt callout.

    If a `## YYYY-MM` header for the current month already exists, insert the
    day entry under it. Otherwise insert a fresh month header + day entry."""
    content = read(path)
    if not content:
        # File doesn't exist or is empty — just write the entry
        write(path, f"{month_heading()}\n\n{day_heading()}\n\n{entry_md}\n")
        return

    # Find insertion point (after prompt callout)
    insert_at = find_insertion_point(content)

    mh = month_heading()
    dh = day_heading()

    # Is today's day-heading already in the file? If so, replace today's section.
    today_idx = content.find(dh, insert_at)
    if today_idx != -1:
        # Replace from today's heading to the next `### [[` heading (or end of file)
        next_day_idx = content.find("\n### [[", today_idx + len(dh))
        if next_day_idx == -1:
            content = content[:today_idx] + dh + "\n\n" + entry_md.rstrip() + "\n"
        else:
            content = (
                content[:today_idx]
                + dh + "\n\n" + entry_md.rstrip() + "\n\n"
                + content[next_day_idx + 1:]
            )
        write(path, content)
        return

    # Is the current month-heading present? If so, insert today's entry below it.
    mh_idx = content.find(mh, insert_at)
    if mh_idx != -1:
        # Insert today's day-heading right after the month header line.
        after_mh = content.find("\n", mh_idx) + 1
        new_block = f"\n{dh}\n\n{entry_md.rstrip()}\n"
        content = content[:after_mh] + new_block + content[after_mh:]
        write(path, content)
        return

    # Neither today's heading nor this month's header exists — insert fresh block.
    new_block = f"{mh}\n\n{dh}\n\n{entry_md.rstrip()}\n\n"
    content = content[:insert_at] + new_block + content[insert_at:]
    write(path, content)


def set_frontmatter_updated(path: Path, *, set_unread: bool = True) -> None:
    """Update `updated:` (and optionally `unread: true`) in YAML frontmatter.

    Also drops blank lines inside the frontmatter — YAML doesn't need them,
    and a prior round-trip bug here was accumulating one extra blank line
    per call."""
    content = read(path)
    fm_end = content.find("\n---\n", 3)
    if fm_end == -1:
        return
    fm = content[3:fm_end + 1]
    body = content[fm_end + len("\n---\n"):]

    now_str = now_ist().strftime("%Y-%m-%dT%H:%M:%S")
    new_fm_lines: list[str] = []
    saw_updated = saw_unread = False
    for line in fm.splitlines():
        if not line.strip():
            continue  # drop blank lines inside frontmatter
        if line.startswith("updated:"):
            new_fm_lines.append(f"updated: {now_str}")
            saw_updated = True
        elif line.startswith("unread:") and set_unread:
            new_fm_lines.append("unread: true")
            saw_unread = True
        else:
            new_fm_lines.append(line)
    if not saw_updated:
        new_fm_lines.append(f"updated: {now_str}")
    if set_unread and not saw_unread:
        new_fm_lines.append("unread: true")

    write(path, "---\n" + "\n".join(new_fm_lines) + "\n---\n" + body)
