"""Real Calendar stream — replaces calendar_stub.py.

Pulls today's events from all 4 calendar_* accounts, dedupes by event ID
(priority work > personal > iitm > nfsu on collision), formats per the
Dashboard's "Scheduled today" spec. All-day events listed first
alphabetically, then timed events sorted by start time.

Each event is rendered as a markdown checkbox so it can be ticked off as the
day passes. Response status (accepted/tentative/declined/needsAction) is
honored per the spec.
"""
from __future__ import annotations

import datetime
import re
import sys
import urllib.parse
from dataclasses import dataclass, field
from typing import Any

from . import google


CALENDAR_BASE = "https://www.googleapis.com/calendar/v3/calendars/primary/events"

# Account-tag priority for dedup (higher = preferred when same event appears
# in two calendars).
ACCOUNT_PRIORITY = {
    "calendar_work":     3,
    "calendar_personal": 2,
    "calendar_iitm":     1,
    "calendar_nfsu":     0,
}
ACCOUNT_TAG = {
    "calendar_work":     "work",
    "calendar_personal": "personal",
    "calendar_iitm":     "iitm",
    "calendar_nfsu":     "nfsu",
}


@dataclass
class Event:
    id: str
    account: str
    title: str
    is_all_day: bool
    start_dt: datetime.datetime | None  # tz-aware for timed
    end_dt:   datetime.datetime | None
    start_date: datetime.date | None = None  # populated for all-day events
    attendees: list[str] = field(default_factory=list)
    me_response: str = "accepted"  # accepted/tentative/declined/needsAction
    location: str = ""
    hangout_link: str = ""
    html_link: str = ""
    deadline_marker: str = ""


def _now_ist() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30)))


def _today_window_iso() -> tuple[str, str]:
    """Return (timeMin, timeMax) as RFC3339 strings spanning today in IST."""
    now = _now_ist()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + datetime.timedelta(days=1)
    return start.isoformat(), end.isoformat()


_DEADLINE_RE = re.compile(r"\b(due|deadline|by|EOD)\b", re.IGNORECASE)


def _extract_deadline(text: str) -> str:
    """Return the matched phrase if a deadline marker is present, else ''."""
    if not text:
        return ""
    m = _DEADLINE_RE.search(text)
    return m.group(0).lower() if m else ""


def _parse_dt(value: str) -> datetime.datetime:
    """Parse Google's RFC3339 — may have +05:30 or Z."""
    return datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))


def _fetch_account(account: str, time_min: str | None = None, time_max: str | None = None) -> list[Event]:
    if time_min is None or time_max is None:
        time_min, time_max = _today_window_iso()
    qs = urllib.parse.urlencode({
        "timeMin": time_min,
        "timeMax": time_max,
        "singleEvents": "true",
        "orderBy": "startTime",
        "maxResults": "250",
    })
    out: list[Event] = []
    try:
        data = google.bearer_get_json(account, f"{CALENDAR_BASE}?{qs}")
    except google.GoogleAuthError as e:
        print(f"[calendar] {account}: {e}", file=sys.stderr)
        raise
    me_email = google.CALENDAR_ACCOUNTS.get(account, "").lower()
    for item in data.get("items", []):
        if item.get("status") == "cancelled":
            continue
        start = item.get("start", {})
        end = item.get("end", {})
        is_all_day = "date" in start and "dateTime" not in start
        start_dt = None
        end_dt = None
        start_date = None
        if is_all_day:
            try:
                start_date = datetime.date.fromisoformat(start["date"])
            except (KeyError, ValueError):
                continue
        else:
            try:
                start_dt = _parse_dt(start["dateTime"])
                end_dt = _parse_dt(end["dateTime"]) if "dateTime" in end else None
            except (KeyError, ValueError):
                continue
        # Find my response status if I'm in the attendees list.
        me_response = "accepted"
        attendees: list[str] = []
        for a in item.get("attendees", []) or []:
            email = (a.get("email") or "").lower()
            name = a.get("displayName") or a.get("email") or ""
            if email == me_email:
                me_response = a.get("responseStatus") or "accepted"
            else:
                if name:
                    attendees.append(name)
        deadline = _extract_deadline(item.get("summary") or "") or _extract_deadline(item.get("description") or "")
        out.append(Event(
            id=item.get("id") or "",
            account=account,
            title=(item.get("summary") or "(no title)").strip(),
            is_all_day=is_all_day,
            start_dt=start_dt,
            end_dt=end_dt,
            start_date=start_date,
            attendees=attendees,
            me_response=me_response,
            location=(item.get("location") or "").strip(),
            hangout_link=item.get("hangoutLink") or "",
            html_link=item.get("htmlLink") or "",
            deadline_marker=deadline,
        ))
    return out


def _dedup(events: list[Event]) -> list[Event]:
    """Keep the highest-priority account's copy when event_id collides."""
    best: dict[str, Event] = {}
    for ev in events:
        existing = best.get(ev.id)
        if existing is None or ACCOUNT_PRIORITY[ev.account] > ACCOUNT_PRIORITY[existing.account]:
            best[ev.id] = ev
    return list(best.values())


def _format_attendees(attendees: list[str], cap: int = 2) -> str:
    if not attendees:
        return ""
    shown = attendees[:cap]
    rest = len(attendees) - cap
    parts = [f"[[{n}]]" for n in shown]
    if rest > 0:
        parts.append(f"+{rest} others")
    return "attendees: " + ", ".join(parts)


def _format_location(ev: Event) -> str:
    if ev.hangout_link:
        return f"[Meet]({ev.hangout_link})"
    if ev.location:
        return ev.location
    return ""


def _format_event(ev: Event) -> str:
    tag = ACCOUNT_TAG[ev.account]
    title_link = f"[{ev.title}]({ev.html_link})" if ev.html_link else ev.title

    # Response status modifiers per the spec.
    if ev.me_response == "tentative":
        title_link += " (tentative)"
    elif ev.me_response == "needsAction":
        title_link += " (no response)"

    if ev.is_all_day:
        time_part = "all-day"
    else:
        st = ev.start_dt.strftime("%H:%M") if ev.start_dt else "??:??"
        et = ev.end_dt.strftime("%H:%M") if ev.end_dt else st
        time_part = f"{st}-{et}"

    pieces = [f"{time_part} — [{tag}] {title_link}"]
    att = _format_attendees(ev.attendees)
    if att:
        pieces.append(att)
    loc = _format_location(ev)
    if loc:
        pieces.append(loc)
    if ev.deadline_marker:
        pieces.append(f"deadline: {ev.deadline_marker}")

    line = " · ".join(pieces)

    if ev.me_response == "declined":
        # Wrap content after the checkbox in strikethrough; checkbox itself
        # stays clickable.
        line = f"~~{line}~~"

    return f"- [ ] {line}"


def run() -> str:
    """Return the body string for Brief/Dashboard's 'Scheduled today' section."""
    all_events: list[Event] = []
    account_failures: list[tuple[str, str]] = []
    for account in google.CALENDAR_ACCOUNTS:
        try:
            all_events.extend(_fetch_account(account))
        except google.GoogleAuthError as e:
            account_failures.append((account, str(e)))

    if not all_events and not account_failures:
        return "Nothing scheduled."

    if not all_events and account_failures:
        return (
            "> [!warning] Calendars unreachable — events not loaded\n"
            + "\n".join(f"> - {a}: {e[:120]}" for a, e in account_failures)
        )

    events = _dedup(all_events)
    # All-day first (alphabetical), then timed (chronological).
    all_day = sorted([e for e in events if e.is_all_day], key=lambda x: x.title.lower())
    timed = sorted([e for e in events if not e.is_all_day], key=lambda x: x.start_dt or datetime.datetime.min)

    lines: list[str] = []
    if all_day:
        lines.extend(_format_event(e) for e in all_day)
    if timed:
        if all_day:
            lines.append("")
        lines.extend(_format_event(e) for e in timed)

    if account_failures:
        lines.append("")
        lines.append(
            "> [!warning] Some calendars unreachable: "
            + ", ".join(a for a, _ in account_failures)
        )

    return "\n".join(lines)


def events_in_window(start: datetime.date, end_inclusive: datetime.date) -> tuple[list[Event], list[tuple[str, str]]]:
    """Pull events across all 4 calendars in `[start 00:00, end_inclusive 23:59]`
    IST. Returns (deduped_events_sorted_by_start, per_account_failures).

    Used by the weekly recap for the Mon-Sun window. Same dedup priority
    (work > personal > iitm > nfsu) as `run()`."""
    tz = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    start_dt = datetime.datetime.combine(start, datetime.time.min, tz)
    end_dt = datetime.datetime.combine(end_inclusive + datetime.timedelta(days=1), datetime.time.min, tz)
    time_min = start_dt.isoformat()
    time_max = end_dt.isoformat()

    all_events: list[Event] = []
    failures: list[tuple[str, str]] = []
    for account in google.CALENDAR_ACCOUNTS:
        try:
            all_events.extend(_fetch_account(account, time_min, time_max))
        except google.GoogleAuthError as e:
            failures.append((account, str(e)))
    events = _dedup(all_events)
    # Sort: all-day first by date+title, then timed by start.
    def _key(e: Event):
        if e.is_all_day:
            # All-day events don't have a start_dt; use a sentinel date.
            return (0, e.title.lower())
        return (1, e.start_dt or datetime.datetime.min.replace(tzinfo=tz))
    events.sort(key=_key)
    return events, failures


def format_event_for_week(ev: Event, day: datetime.date | None = None) -> str:
    """Same line shape as _format_event but with a day prefix so the user can
    scan the week vertically. Pass `day` explicitly to avoid string-replacing
    URLs that contain `?` characters."""
    tag = ACCOUNT_TAG[ev.account]
    title_link = f"[{ev.title}]({ev.html_link})" if ev.html_link else ev.title

    if ev.me_response == "tentative":
        title_link += " (tentative)"
    elif ev.me_response == "needsAction":
        title_link += " (no response)"

    if ev.is_all_day:
        d = day or ev.start_date
        day_label = d.strftime("%a %d %b") if d else "?"
        time_part = "all-day"
    else:
        if ev.start_dt is None:
            return ""
        day_label = ev.start_dt.strftime("%a %d %b")
        st = ev.start_dt.strftime("%H:%M")
        et = ev.end_dt.strftime("%H:%M") if ev.end_dt else st
        time_part = f"{st}-{et}"

    pieces = [f"{day_label} · {time_part} — [{tag}] {title_link}"]
    if ev.attendees:
        shown = ev.attendees[:2]
        rest = len(ev.attendees) - 2
        att = ", ".join(f"[[{n}]]" for n in shown)
        if rest > 0:
            att += f", +{rest} others"
        pieces.append(f"attendees: {att}")
    if ev.hangout_link:
        pieces.append(f"[Meet]({ev.hangout_link})")
    elif ev.location:
        pieces.append(ev.location)
    if ev.deadline_marker:
        pieces.append(f"deadline: {ev.deadline_marker}")

    line = " · ".join(pieces)
    if ev.me_response == "declined":
        line = f"~~{line}~~"
    return f"- [ ] {line}"


if __name__ == "__main__":
    print(run())
