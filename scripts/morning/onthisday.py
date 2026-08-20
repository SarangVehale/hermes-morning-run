"""Wikipedia 'on this day' stream.

Pulls historical events for today's date from the free Wikimedia REST API
(no auth needed) and produces one callout with the top 3 events.

Endpoint: https://api.wikimedia.org/feed/v1/wikipedia/en/onthisday/all/MM/DD
Returns: events, births, deaths, holidays, selected for today's month-day.

Every entry includes a `[Wikipedia]({url})` citation back to the article the
fact came from. No LLM call — facts are pulled verbatim from Wikipedia's
curated lists."""
from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass

from . import vault


URL_TMPL = "https://api.wikimedia.org/feed/v1/wikipedia/en/onthisday/all/{mm:02d}/{dd:02d}"
UA = "hermes-morning/1.0 (hermes-morning@example.com)"


@dataclass
class Event:
    year: int
    text: str
    url: str         # primary Wikipedia URL for the event subject
    category: str    # "events", "births", "deaths", "selected"


def _fetch() -> dict | None:
    today = vault.now_ist().date()
    url = URL_TMPL.format(mm=today.month, dd=today.day)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as e:
        print(f"[onthisday] fetch failed: {type(e).__name__}: {e}", file=sys.stderr)
        return None


def _to_events(data: dict, category: str, max_n: int = 10) -> list[Event]:
    out: list[Event] = []
    for entry in data.get(category, [])[:max_n]:
        year = int(entry.get("year") or 0)
        text = (entry.get("text") or "").strip()
        pages = entry.get("pages") or []
        url = ""
        if pages:
            url = pages[0].get("content_urls", {}).get("desktop", {}).get("page", "")
            if not url:
                url = f"https://en.wikipedia.org/wiki/{pages[0].get('titles', {}).get('canonical', '')}"
        if year and text and url:
            out.append(Event(year=year, text=text, url=url, category=category))
    return out


def _wikilink_text(text: str) -> str:
    """Wikipedia returns plain text — preserve named entities by converting the
    most common pattern (the first capitalized phrase) to a wikilink. Keep it
    light to avoid mangling sentences."""
    # No automatic wikilinking — Wikipedia text already references articles by
    # name. Returning verbatim avoids creating broken stubs.
    return text


def run() -> str:
    data = _fetch()
    if not data:
        return (
            "> [!info]- On this day — fetch failed\n"
            "> Wikimedia API unreachable. Skipped."
        )

    events  = _to_events(data, "events", max_n=10)
    selected = _to_events(data, "selected", max_n=8)
    pool = selected + events

    # Dedupe near-duplicates by year + first 60 chars of text.
    seen: set[tuple[int, str]] = set()
    dedup: list[Event] = []
    for e in pool:
        key = (e.year, e.text[:60].lower())
        if key in seen:
            continue
        seen.add(key)
        dedup.append(e)
    pool = dedup

    if not pool:
        return (
            "> [!info]- On this day — nothing surfaced\n"
            "> Wikimedia returned no events for today's date."
        )
    # Bias toward variety: take 1 most-recent + 1 oldest + 1 middle so the
    # output spans eras instead of all crashing into the last decade.
    pool.sort(key=lambda e: -e.year)
    if len(pool) >= 3:
        top = [pool[0], pool[len(pool) // 2], pool[-1]]
    else:
        top = pool

    today = vault.now_ist().date()
    header = f"> [!info]- On this day — {today.strftime('%B %d')}"
    lines = [header]
    for e in top:
        lines.append(f"> - **{e.year}** · {_wikilink_text(e.text)} · [Wikipedia]({e.url})")
    return "\n".join(lines)


if __name__ == "__main__":
    print(run())
