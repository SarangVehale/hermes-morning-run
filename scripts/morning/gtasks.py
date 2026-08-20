"""Google Tasks stream.

Pulls open tasks across all 4 Google accounts via the Tasks API and renders
them for the dashboard's "Tasks for today" section. Calendar events ≠ tasks —
this surfaces actual checkboxes the user keeps in Google Tasks (which sits
inside Google Calendar's web UI), separating them from the all-day-event
shape that Calendar returns.

Scope required on each `calendar_*` account:
    https://www.googleapis.com/auth/tasks.readonly

If a token lacks the scope (existing tokens granted before 2026-06-11), the
API returns 403; this module logs a single warning per run rather than
spamming the dashboard, and shows a one-line `[!warning]` so the user knows
to re-grant.
"""
from __future__ import annotations

import datetime
import sys
import urllib.parse
from dataclasses import dataclass

from . import google


TASKS_API = "https://tasks.googleapis.com/tasks/v1"
TASKLISTS = f"{TASKS_API}/users/@me/lists"


@dataclass
class GTask:
    account: str         # "calendar_work" etc. — reuses calendar token
    list_title: str      # name of the task list (e.g. "My Tasks")
    title: str
    notes: str
    due: datetime.date | None
    web_view_link: str   # link to open in Google Tasks web UI
    completed: bool


def _tasks_url(list_id: str) -> str:
    qs = urllib.parse.urlencode({
        "showCompleted": "false",
        "showHidden":    "false",
        "maxResults":    "100",
    })
    return f"{TASKS_API}/lists/{urllib.parse.quote(list_id)}/tasks?{qs}"


def _parse_due(raw: str) -> datetime.date | None:
    """Google Tasks `due` is RFC3339 at midnight UTC ('2026-06-15T00:00:00.000Z')."""
    if not raw:
        return None
    try:
        return datetime.date.fromisoformat(raw[:10])
    except ValueError:
        return None


def _fetch_account(account: str) -> tuple[list[GTask], str | None]:
    """Return (tasks, error_or_none). On scope-missing 403, returns
    `([], "scope-missing")` so the caller can surface a single notice."""
    try:
        lists = google.bearer_get_json(account, TASKLISTS)
    except google.GoogleAuthError as e:
        msg = str(e)
        if "403" in msg or "insufficient" in msg.lower():
            return [], "scope-missing"
        print(f"[gtasks] {account}: lists failed: {e}", file=sys.stderr)
        return [], "fetch-failed"

    out: list[GTask] = []
    for tl in lists.get("items", []) or []:
        list_id = tl.get("id") or ""
        list_title = tl.get("title") or "Tasks"
        if not list_id:
            continue
        try:
            tasks = google.bearer_get_json(account, _tasks_url(list_id))
        except google.GoogleAuthError as e:
            print(f"[gtasks] {account}/{list_title}: tasks failed: {e}", file=sys.stderr)
            continue
        for item in tasks.get("items", []) or []:
            if item.get("status") == "completed":
                continue
            out.append(GTask(
                account=account,
                list_title=list_title,
                title=(item.get("title") or "(untitled)").strip(),
                notes=(item.get("notes") or "").strip(),
                due=_parse_due(item.get("due", "")),
                web_view_link=item.get("webViewLink") or "",
                completed=False,
            ))
    return out, None


# Reuse the calendar_* tokens — Tasks lives under the same Google account.
ACCOUNT_TAG = {
    "calendar_work":     "work",
    "calendar_personal": "personal",
    "calendar_iitm":     "iitm",
    "calendar_nfsu":     "nfsu",
}


def fetch_all() -> tuple[list[GTask], list[tuple[str, str]]]:
    """Pull open tasks from every calendar_* account. Returns
    (tasks, [(account, note), ...]) where notes are warnings to surface."""
    all_tasks: list[GTask] = []
    notes: list[tuple[str, str]] = []
    for account in ACCOUNT_TAG:
        tasks, err = _fetch_account(account)
        all_tasks.extend(tasks)
        if err == "scope-missing":
            notes.append((account, "no `tasks.readonly` scope — re-run oauth-grant"))
        elif err:
            notes.append((account, err))
    return all_tasks, notes


def _format_task(t: GTask) -> str:
    tag = ACCOUNT_TAG.get(t.account, "?")
    title = t.title.replace("|", "/")
    if t.web_view_link:
        title = f"[{title}]({t.web_view_link})"
    pieces = [f"[{tag}] {t.list_title}: {title}"]
    if t.due:
        pieces.append(f"due {t.due.isoformat()}")
    if t.notes and len(t.notes) < 200:
        pieces.append(t.notes.splitlines()[0][:120])
    return "- [ ] " + " · ".join(pieces)


def render_for_today() -> str:
    """Filter to tasks due today or overdue, render as checkboxes."""
    today = datetime.date.today()
    tasks, notes = fetch_all()
    due_now = [t for t in tasks if t.due and t.due <= today]
    if not due_now:
        body = "Nothing due today."
    else:
        # Soonest-overdue first.
        due_now.sort(key=lambda t: (t.due or today, t.title.lower()))
        body = "\n".join(_format_task(t) for t in due_now)
    if notes:
        body += "\n\n> [!warning] Some accounts couldn't surface Google Tasks:"
        for acct, note in notes:
            body += f"\n> - {acct}: {note}"
    return body


def render_open_threads(soft_cap: int = 5) -> str:
    """Render all open tasks (no due-date filter) — used for the
    "Open threads" section, which is genuinely *open* work to revisit."""
    tasks, notes = fetch_all()
    today = datetime.date.today()
    # Drop already-due ones (those go to "Tasks for today").
    backlog = [t for t in tasks if not t.due or t.due > today]
    if not backlog:
        body = "No open backlog tasks."
    else:
        # No date → sort by list name then title. Dated future tasks → by date asc.
        backlog.sort(key=lambda t: (t.due or datetime.date.max, t.list_title.lower(), t.title.lower()))
        body = "\n".join(_format_task(t) for t in backlog[:soft_cap])
        if len(backlog) > soft_cap:
            body += f"\n\n_+ {len(backlog) - soft_cap} more in Google Tasks._"
    if notes:
        body += "\n\n> [!warning] Some accounts couldn't surface Google Tasks:"
        for acct, note in notes:
            body += f"\n> - {acct}: {note}"
    return body


if __name__ == "__main__":
    print("--- Tasks for today ---")
    print(render_for_today())
    print()
    print("--- Open threads ---")
    print(render_open_threads())
