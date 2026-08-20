"""Parse `📋 Tasks.md` and surface today's open tasks for the Brief.

Format expected (see vault file for the canonical convention):
    ## Today
    - [ ] task name #urgent
    - [x] done task
    ## This week
    - [ ] backlog item
    ## Eventually

Returns a structure the Brief composer can render directly. We do NOT modify
Tasks.md from here — the user owns that file and reviews completions manually.
"""
from __future__ import annotations

import datetime
import re
import subprocess
from dataclasses import dataclass, field
from typing import Iterable

from . import vault


@dataclass
class Task:
    text: str
    done: bool
    section: str  # "Today" / "This week" / "Eventually"
    tags: list[str] = field(default_factory=list)
    line_no: int = 0  # 1-indexed line number in 📋 Tasks.md, for git-blame age lookup

    @property
    def urgent(self) -> bool:
        return "urgent" in self.tags

    @property
    def today_tag(self) -> bool:
        return "today" in self.tags


@dataclass
class TasksResult:
    today: list[Task]
    this_week: list[Task]
    eventually: list[Task]
    raw_count: int


_CHECKBOX = re.compile(r"^\s*-\s*\[(?P<state>[ xX])\]\s*(?P<text>.+?)\s*$")
_TAG = re.compile(r"#(\w+)")
_HEADING = re.compile(r"^##\s+(.+?)\s*$")


def _parse_tasks(content: str) -> list[Task]:
    section = ""
    tasks: list[Task] = []
    for line_no, line in enumerate(content.splitlines(), start=1):
        m_head = _HEADING.match(line)
        if m_head:
            section = m_head.group(1).strip()
            continue
        m_cb = _CHECKBOX.match(line)
        if not m_cb:
            continue
        text = m_cb.group("text")
        # Skip placeholders the user left in the seed file.
        if text.startswith("(") and text.endswith(")"):
            continue
        tags = [t.lower() for t in _TAG.findall(text)]
        tasks.append(
            Task(
                text=text,
                done=m_cb.group("state").lower() == "x",
                section=section,
                tags=tags,
                line_no=line_no,
            )
        )
    return tasks


def task_age_days() -> dict[int, int]:
    """Return {line_no: days_since_line_was_added} for `📋 Tasks.md` via git
    blame. Lines we can't blame (uncommitted) map to 0 — treat as fresh."""
    try:
        out = subprocess.run(
            ["git", "-C", str(vault.VAULT), "blame", "--line-porcelain", str(vault.TASKS_FILE)],
            capture_output=True, text=True, timeout=20, check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return {}
    if out.returncode != 0:
        return {}

    ages: dict[int, int] = {}
    today = datetime.date.today()
    line_no = 0
    author_time: int | None = None
    for raw in out.stdout.splitlines():
        if raw.startswith("\t"):
            # The actual file line follows the porcelain header.
            line_no += 1
            if author_time is not None:
                committed = datetime.date.fromtimestamp(author_time)
                ages[line_no] = (today - committed).days
            author_time = None
            continue
        if raw.startswith("author-time "):
            try:
                author_time = int(raw.split(" ", 1)[1])
            except ValueError:
                author_time = None
    return ages


def load() -> TasksResult:
    """Read `📋 Tasks.md` and group open tasks by section."""
    content = vault.read(vault.TASKS_FILE)
    all_tasks = _parse_tasks(content)
    open_tasks = [t for t in all_tasks if not t.done]

    def _in(section: str) -> list[Task]:
        return [t for t in open_tasks if t.section.lower() == section.lower()]

    return TasksResult(
        today=_in("Today"),
        this_week=_in("This week"),
        eventually=_in("Eventually"),
        raw_count=len(all_tasks),
    )


def render_for_brief(result: TasksResult) -> str:
    """Render the Tasks section body for `📌 Daily Brief.md`.

    Urgent items and `#today`-tagged items from any section bubble to the top.
    The rest of `## Today` follows. No cap (per Brief spec: "no cap on urgent/
    deadlines")."""
    surfaced: list[Task] = []
    seen: set[str] = set()

    def _add(t: Task) -> None:
        if t.text in seen:
            return
        surfaced.append(t)
        seen.add(t.text)

    for t in result.today + result.this_week + result.eventually:
        if t.urgent or t.today_tag:
            _add(t)
    for t in result.today:
        _add(t)

    if not surfaced:
        return "Nothing today."

    lines: list[str] = []
    for t in surfaced:
        marker = ""
        if t.urgent:
            marker = " *(urgent)*"
        elif t.today_tag and t.section.lower() != "today":
            marker = f" *(from {t.section})*"
        lines.append(f"- [ ] {t.text}{marker}")
    return "\n".join(lines)
