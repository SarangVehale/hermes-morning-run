"""Regenerate `🏠 Dashboard.md` after all streams have written.

Preserves the prompt callout, heatmap-calendar block, and footer link strip.
Regenerates: today's heading, weather,
the 5 collapsed discovery callouts (each pulling the top item from its
stream's freshly-written body), and the streak counter.

Yesterday's dashboard is archived to `02 Daily/{prev_year}/{prev_month}/{prev_MM-DD-YY ddd} dashboard.md`
the first time the new dashboard is written each day."""
from __future__ import annotations

import datetime
import json
import re
from pathlib import Path

from . import vault


STATE_FILE = vault.STATE_DIR / "dashboard.json"


# -- Preamble extraction -------------------------------------------------------

_HEATMAP_END = re.compile(r"^```\s*$", re.MULTILINE)


def _split_preamble(content: str) -> tuple[str, str]:
    """Return (preserved_preamble_through_prompt_callout, regen_zone).

    Preserve frontmatter + prompt callout + the `---` separator that ends it.
    Everything AFTER that `---` is regenerated each run — the heatmap, streak
    line, today's content, footer. Keeping the heatmap regenerable lets us
    tweak it (e.g. switch to dataviewjs) without manual file edits.
    """
    fm_end = content.find("\n---\n", 3)
    if fm_end == -1:
        return "", content
    body_start = fm_end + len("\n---\n")
    # Find the next `---` after the frontmatter — that's the separator below
    # the prompt callout (the dashboard convention).
    next_hr = content.find("\n---\n", body_start)
    if next_hr == -1:
        return content[:body_start], ""
    cut = next_hr + len("\n---\n")
    return content[:cut], content[cut:]


def _heatmap_block(year: int) -> str:
    """Reading-depth heatmap.

    Cell intensity reflects HOW DEEPLY you explored that day:
      1 = dashboard only or a single shallow open
      2 = a few stream notes
      3 = drilled into summaries / references
      4 = sustained navigation across folders

    Mechanism: a one-time `file-open` workspace listener appends `(path, depth)`
    entries to `.hermes-reading-log.json` in the vault root. The heatmap reads
    that log + the existing daily-note presence and computes per-day intensity
    as: `max(1, ceil(log2(unique_files_opened + 1)))` blended with the
    average folder depth. Requires Dataview + JavaScript Queries enabled.
    """
    return (
        "```dataviewjs\n"
        "const year = " + str(year) + ";\n"
        "const LOG_PATH = \".hermes-reading-log.json\";\n"
        "\n"
        "// ── Install a single global file-open listener (idempotent) ──\n"
        "if (!window.__hermesReadingTrackerInstalled) {\n"
        "  window.__hermesReadingTrackerInstalled = true;\n"
        "  app.workspace.on(\"file-open\", async (file) => {\n"
        "    if (!file || !file.path) return;\n"
        "    if (file.path.startsWith(\".\") || file.path.endsWith(\".json\")) return;\n"
        "    const depth = file.path.split(\"/\").length;\n"
        "    const today = new Date().toISOString().slice(0, 10);\n"
        "    let log = {};\n"
        "    const logFile = app.vault.getAbstractFileByPath(LOG_PATH);\n"
        "    if (logFile) {\n"
        "      try { log = JSON.parse(await app.vault.read(logFile)); } catch (e) {}\n"
        "    }\n"
        "    if (!log[today]) log[today] = {};\n"
        "    log[today][file.path] = Math.max(log[today][file.path] || 0, depth);\n"
        "    const body = JSON.stringify(log, null, 2);\n"
        "    if (logFile) await app.vault.modify(logFile, body);\n"
        "    else await app.vault.create(LOG_PATH, body);\n"
        "  });\n"
        "}\n"
        "\n"
        "// ── Read log + daily-note presence → entries ──\n"
        "let readingLog = {};\n"
        "const logFile = app.vault.getAbstractFileByPath(LOG_PATH);\n"
        "if (logFile) {\n"
        "  try { readingLog = JSON.parse(await app.vault.read(logFile)); } catch (e) {}\n"
        "}\n"
        "\n"
        "const entries = [];\n"
        "const yearStr = String(year);\n"
        "\n"
        "// Reading-depth contributions\n"
        "for (const [date, files] of Object.entries(readingLog)) {\n"
        "  if (!date.startsWith(yearStr + \"-\")) continue;\n"
        "  const paths = Object.keys(files);\n"
        "  const depths = Object.values(files);\n"
        "  const breadth = Math.min(4, Math.max(1, Math.ceil(Math.log2(paths.length + 1))));\n"
        "  const avgDepth = depths.reduce((a, b) => a + b, 0) / Math.max(1, depths.length);\n"
        "  // Blend: weight breadth more, soften with depth bonus\n"
        "  const intensity = Math.min(4, Math.max(1, Math.round(breadth * 0.7 + (avgDepth / 2) * 0.3)));\n"
        "  entries.push({ date, intensity });\n"
        "}\n"
        "\n"
        "// Daily-note presence ensures days with no reading log still light up\n"
        "const folder = `02 Daily/${year}`;\n"
        "for (const page of dv.pages(`\"${folder}\"`)) {\n"
        "  const m = page.file.name.match(/^(\\d{2})-(\\d{2})-(\\d{2}) /);\n"
        "  if (!m) continue;\n"
        "  const date = `20${m[3]}-${m[1]}-${m[2]}`;\n"
        "  if (!entries.find(e => e.date === date)) {\n"
        "    entries.push({ date, intensity: 1 });\n"
        "  }\n"
        "}\n"
        "\n"
        "renderHeatmapCalendar(this.container, {\n"
        "  year,\n"
        "  colors: {\n"
        "    default: ['#161b22', '#0e4429', '#006d32', '#26a641', '#39d353'],\n"
        "  },\n"
        "  showCurrentDayBorder: true,\n"
        "  defaultEntryIntensity: 1,\n"
        "  entries,\n"
        "});\n"
        "```"
    )


# -- Stream "top item" extractors ----------------------------------------------

def _first_callout(body: str) -> str:
    """Return the first contiguous `> ` block in `body`, or empty."""
    lines = body.splitlines()
    start = -1
    end = -1
    for i, line in enumerate(lines):
        if line.startswith("> "):
            if start == -1:
                start = i
            end = i + 1
        elif start != -1 and not line.startswith(">"):
            break
    if start == -1:
        return ""
    return "\n".join(lines[start:end])


def _first_n_callouts(body: str, n: int) -> list[str]:
    """Return up to `n` contiguous `>` callout blocks from `body`. Blocks are
    separated by one or more non-`>` lines."""
    blocks: list[str] = []
    cur: list[str] = []
    for line in body.splitlines():
        if line.startswith(">"):
            cur.append(line)
        else:
            if cur:
                blocks.append("\n".join(cur))
                cur = []
                if len(blocks) >= n:
                    return blocks
    if cur and len(blocks) < n:
        blocks.append("\n".join(cur))
    return blocks[:n]


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(s: str) -> str:
    return _SLUG_RE.sub("-", s.lower()).strip("-")


def _tags_for_callout(stream: str, header: str) -> str:
    """Build a `#daily/<stream>` + `#daily/<stream>/<topic-slug>` tag string.

    For news/tech the topic comes before the colon (`Local: ...`, `HN — ...`).
    For papers/releases we just emit the stream tag."""
    base = f"#daily/{stream}"
    head = header.lstrip("> []!- ").split("]-", 1)[-1].strip() if "]-" in header else header
    # Strip everything after a wikilink-arrow if present.
    head = head.split("[[", 1)[0].strip()
    sub = ""
    if stream in ("news",):
        m = re.match(r"([\w/ ]+?):\s", head)
        if m:
            sub = _slugify(m.group(1))
    elif stream == "tech":
        # "HN — Project ..." or "Reddit r/sub — Title ..."
        m = re.match(r"([\w ]+?)\s+—\s", head)
        if m:
            sub = _slugify(m.group(1).split()[0])
    elif stream == "papers":
        # Header looks like "arXiv:NNNN.NNNNN — Title"; tag with arxiv.
        sub = "arxiv"
    if sub:
        return f"{base} #daily/{stream}/{sub}"
    return base


def _rewrite_callout(callout: str, *, type_token: str, suffix_link: str, section_label: str = "", tag_stream: str = "") -> str:
    """Replace the callout header with `> [!type]- {Section} — {headline} ↗`.

    Adding the section label up front (`News — ...`, `Papers — ...`) so the
    user can scan stream provenance without reading the wikilink at the end.
    """
    lines = callout.splitlines()
    if not lines:
        return callout
    first = lines[0]
    m = re.match(r"^>\s*\[!\w+\]-?\s*(.+?)\s*$", first)
    headline = m.group(1) if m else first.lstrip("> ").strip()
    prefix = f"{section_label} — " if section_label else ""
    header = f"> [!{type_token}]- {prefix}{headline}"
    if suffix_link:
        header += f" {suffix_link}"
    if tag_stream:
        header += f"   {_tags_for_callout(tag_stream, header)}"
    lines[0] = header
    return "\n".join(lines)


def _section_news(news_body: str) -> str:
    cos = _first_n_callouts(news_body, 3)
    if not cos:
        return "> [!note]- No news surfaced today\n> Stream returned no entries."
    return "\n\n".join(
        _rewrite_callout(co, type_token="note", suffix_link="", section_label="", tag_stream="news")
        for co in cos
    )


def _section_papers(papers_body: str) -> str:
    cos = _first_n_callouts(papers_body, 3)
    if not cos:
        return f"> [!paper]- Quiet feed today\n> {papers_body.strip()[:200]}"
    return "\n\n".join(
        _rewrite_callout(co, type_token="paper", suffix_link="", section_label="", tag_stream="papers")
        for co in cos
    )


def _section_tech(tech_body: str) -> str:
    cos = _first_n_callouts(tech_body, 3)
    if not cos:
        return "> [!tech]- Nothing crossed threshold today\n> Stream returned no entries."
    return "\n\n".join(
        _rewrite_callout(co, type_token="tech", suffix_link="", section_label="", tag_stream="tech")
        for co in cos
    )


def _section_releases(releases_body: str) -> str:
    cos = _first_n_callouts(releases_body, 5)
    if not cos:
        return f"> [!note]- No new releases\n> {releases_body.strip()[:200]}"
    return "\n\n".join(
        _rewrite_callout(co, type_token="note", suffix_link="", section_label="", tag_stream="releases")
        for co in cos
    )


def _section_watchlist(watchlist_body: str) -> str:
    """Watchlist sections are paragraphs ending in `Detail: [[wikilink]].`
    Pull up to 3 of those and render as a bullet list inside the callout."""
    paragraphs = [p.strip() for p in watchlist_body.split("\n\n") if p.strip()]
    item_paragraphs = [p for p in paragraphs if not p.startswith("> [!warning]")]
    bullets: list[str] = []
    for p in item_paragraphs:
        det = re.search(r"Detail:\s*\[\[([^\]]+)\]\]", p)
        if not det:
            continue
        # The "angle" is everything after the creator wikilink, up to the
        # `Detail:` marker, stripped of trailing punctuation. Using the
        # `Detail:` boundary avoids breaking on version numbers like "0.1a2".
        body_match = re.match(r"\[\[[^\]]+\]\]\s*(.+?)\s*(?:New-to-vault concepts:[^.]*\.\s*)?Detail:", p, re.DOTALL)
        angle = ""
        if body_match:
            angle = body_match.group(1).strip()
            # Trim to a single sentence if it has multiple.
            sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z])", angle)
            if sentences:
                angle = sentences[0].strip()
        bullets.append(f"> - [[{det.group(1)}]] — {angle}" if angle else f"> - [[{det.group(1)}]]")
        if len(bullets) >= 3:
            break
    if not bullets:
        return "> [!note]- Watchlist — nothing new today [[🎬 Daily Watchlist|↗]]\n> No new items from any tracked creator."
    header = f"> [!note]- Watchlist — {len(item_paragraphs)} new item(s) [[🎬 Daily Watchlist|↗]]"
    return "\n".join([header] + bullets)


# -- State (streak) ------------------------------------------------------------

def _load_state() -> dict[str, str | int]:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_state(state: dict[str, str | int]) -> None:
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(STATE_FILE)


def _update_streak(state: dict[str, str | int]) -> int:
    today = vault.now_ist().date().isoformat()
    last = str(state.get("last_run_date", ""))
    streak = int(state.get("streak", 0))
    if last == today:
        pass  # re-run; no bump
    elif last:
        last_date = datetime.date.fromisoformat(last)
        today_date = datetime.date.fromisoformat(today)
        if (today_date - last_date).days == 1:
            streak += 1
        else:
            streak = 1
    else:
        streak = 1
    state["last_run_date"] = today
    state["streak"] = streak
    return streak


# -- Archive yesterday ---------------------------------------------------------

def _maybe_archive_yesterday(current: str) -> None:
    """If the existing dashboard's date heading is not today's, archive it."""
    today_h = vault.day_heading()
    if today_h in current:
        return  # already today's
    # Find the most recent `### [[MM-DD-YY ddd]]` in the file.
    m = re.search(r"### \[\[(\d{2}-\d{2}-\d{2}) (\w{3})\]\]", current)
    if not m:
        return
    mm, dd, yy = m.group(1).split("-")
    year = 2000 + int(yy)
    month = int(mm)
    archive_dir = vault.DAILY / f"{year}" / f"{month:02d}"
    archive_path = archive_dir / f"{m.group(1)} {m.group(2)} dashboard.md"
    if archive_path.exists():
        return
    vault.write(archive_path, current)


# -- Build new body ------------------------------------------------------------

def _count_callouts(body: str) -> int:
    """Count distinct `> [!...]` callouts in `body`. Used for the minimap."""
    return sum(1 for line in body.splitlines() if line.startswith("> [!"))


def _watchlist_count(body: str) -> int:
    """Watchlist items are paragraphs containing `Detail: [[...]]`."""
    return sum(1 for line in body.splitlines() if "Detail: [[" in line)


def _minimap_line(ctx_results: dict[str, str]) -> str:
    """At-a-glance one-line summary of the day's stream depth.

    Example: `News 7 · Watchlist 8 · Papers 5 · Tech 6 · Releases curiosity`
    Used so the user knows whether scrolling is worth it."""
    news_n  = _count_callouts(ctx_results.get("news_dashboard", ""))
    pap_n   = _count_callouts(ctx_results.get("papers_dashboard", ""))
    tech_n  = _count_callouts(ctx_results.get("tech_dashboard", ""))
    rel_body = ctx_results.get("releases_dashboard", "")
    rel_n   = _count_callouts(rel_body)
    rel_label = (
        "curiosity" if rel_n == 0 and "Curiosity —" in rel_body
        else "quiet" if rel_n == 0
        else str(rel_n)
    )
    watch_n = _watchlist_count(ctx_results.get("watchlist_dashboard", ""))

    parts = [
        f"News {news_n if news_n else 'quiet'}",
        f"Watchlist {watch_n if watch_n else 'quiet'}",
        f"Papers {pap_n if pap_n else 'quiet'}",
        f"Tech {tech_n if tech_n else 'quiet'}",
        f"Releases {rel_label}",
    ]
    return " · ".join(parts)


def _seven_day_strip() -> str:
    """A row of 7 markers showing daily-note presence for the last 7 days
    (oldest → today). Filled circle = note exists, hollow = missing."""
    today = vault.now_ist().date()
    cells: list[str] = []
    for offset in range(6, -1, -1):
        d = today - datetime.timedelta(days=offset)
        path = vault.DAILY / f"{d.year}" / f"{d.month:02d}" / f"{d.strftime('%m-%d-%y')} {d.strftime('%a')}.md"
        marker = "●" if path.exists() else "○"
        cells.append(f"{marker} {d.strftime('%a')}")
    return "**Last 7 days:** " + "  ".join(cells)


def _short_weather(snippet: str) -> str:
    """Condense Open-Meteo's full sentence into `glyph T°C · label` for the
    status bar."""
    if not snippet or snippet.startswith("> [!warning]"):
        return ""
    # Optional leading glyph (single non-ASCII char + space), then location and metrics.
    m = re.match(
        r"^(?P<glyph>[^\sA-Za-z]\s)?"
        r"[^—]+—\s*(?P<now>\d+°C)\s*now(?:\s*\(feels\s*\d+°C\))?,\s*high\s*(?P<hi>\d+°C)\s*/\s*low\s*(?P<lo>\d+°C),\s*(?P<cond>[^.]+)\.",
        snippet,
    )
    if not m:
        return snippet[:80].rstrip(" .,")
    glyph = (m.group("glyph") or "").strip()
    glyph_prefix = f"{glyph} " if glyph else ""
    return f"{glyph_prefix}{m.group('now')} {m.group('cond')}, hi {m.group('hi')} / lo {m.group('lo')}"


_VAULT_STATS_DV = (
    "```dataviewjs\n"
    "// At-a-glance vault size signal.\n"
    "const all = dv.pages().filter(p => !p.file.path.startsWith(\".obsidian\")).array();\n"
    "const refs = all.filter(p => p.file.path.startsWith(\"07 References\")).length;\n"
    "const people = all.filter(p => p.file.path.startsWith(\"04 People\")).length;\n"
    "const summaries = all.filter(p => p.file.path.startsWith(\"08 Summaries\")).length;\n"
    "const research = all.filter(p => p.file.path.startsWith(\"06 Research\")).length;\n"
    "const today = new Date(); today.setHours(0,0,0,0);\n"
    "const sevenAgo = new Date(today); sevenAgo.setDate(today.getDate() - 7);\n"
    "const newThisWeek = all.filter(p => p.file.ctime && new Date(p.file.ctime.toMillis()) >= sevenAgo).length;\n"
    "dv.paragraph(`**Vault**: ${all.length} notes total · ${refs} references · ${people} people · ${research} research · ${summaries} summaries · **${newThisWeek} new this week**`);\n"
    "```"
)


_ON_THIS_DAY_DV = (
    "```dataviewjs\n"
    "// Find the daily note from 1 week ago and 1 month ago, if they exist.\n"
    "function findDaily(d) {\n"
    "  const mm = String(d.getMonth() + 1).padStart(2, '0');\n"
    "  const dd = String(d.getDate()).padStart(2, '0');\n"
    "  const yy = String(d.getFullYear()).slice(-2);\n"
    "  const ddd = d.toLocaleDateString('en-US', { weekday: 'short' });\n"
    "  const path = `02 Daily/${d.getFullYear()}/${mm}/${mm}-${dd}-${yy} ${ddd}.md`;\n"
    "  return dv.page(path);\n"
    "}\n"
    "const today = new Date(); today.setHours(0,0,0,0);\n"
    "const weekAgo = new Date(today); weekAgo.setDate(today.getDate() - 7);\n"
    "const monthAgo = new Date(today); monthAgo.setMonth(today.getMonth() - 1);\n"
    "const links = [];\n"
    "const wp = findDaily(weekAgo);\n"
    "if (wp) links.push(`A week ago: ${dv.fileLink(wp.file.path)}`);\n"
    "const mp = findDaily(monthAgo);\n"
    "if (mp) links.push(`A month ago: ${dv.fileLink(mp.file.path)}`);\n"
    "if (links.length === 0) {\n"
    "  dv.paragraph(\"_Nothing yet — vault is too young for on-this-day._\");\n"
    "} else {\n"
    "  links.forEach(l => dv.paragraph(l));\n"
    "}\n"
    "```"
)


_RANDOM_NOTE_DV = (
    "```dataviewjs\n"
    "// Surface a random SUBSTANTIVE read — a watchlist summary or one of\n"
    "// your own essays — to broaden horizons. Wikifill stubs (Wikipedia/DDGS\n"
    "// 1-paragraph summaries) are excluded; the random-note slot is for deep\n"
    "// reads, not introductions. Curiosities live in their own section.\n"
    "const pool = dv.pages('\"07 References\" OR \"08 Summaries\" OR \"04 People\" OR \"06 Research\"')\n"
    "  .filter(p => !p.file.name.startsWith(\"_\") && p.file.name.length > 2)\n"
    "  // Skip auto-filled stubs — their fill_source field is set by wikifill.py.\n"
    "  .filter(p => !p.fill_source)\n"
    "  // Substantive content threshold — watchlist details are 1-3KB,\n"
    "  // user-written essays similar. Wikifill stubs are 500-1500B.\n"
    "  .filter(p => (p.file.size || 0) > 2000)\n"
    "  .array();\n"
    "if (pool.length === 0) {\n"
    "  dv.paragraph(\"_(no substantive notes yet — write or watch something deep)_\");\n"
    "} else {\n"
    "  const r = pool[Math.floor(Math.random() * pool.length)];\n"
    "  dv.paragraph(`Random read → ${dv.fileLink(r.file.path)}  _(reload page for a new one)_`);\n"
    "}\n"
    "```"
)


# Random previous curiosity from the 🪅 Daily Curiosity history.
# Parses the file, splits on the `> [!info]- Curiosity —` callout boundaries,
# and renders one chosen at random as a collapsed callout. Reload the page
# (or tap the dot in the heatmap) for a different one. Today's curiosity
# stays visible up top under the Curiosity heading; this widget surfaces a
# *past* one to reread — the user said they enjoy these and like rotation.
_RANDOM_CURIOSITY_DV = (
    "```dataviewjs\n"
    "// Pick a random past curiosity from the 🪅 Daily Curiosity history.\n"
    "const path = '01 Updates/🪅 Daily Curiosity.md';\n"
    "const file = app.vault.getAbstractFileByPath(path);\n"
    "if (!file) {\n"
    "  dv.paragraph('_(no curiosity history yet)_');\n"
    "} else {\n"
    "  const raw = await app.vault.read(file);\n"
    "  // Each curiosity entry starts with `> [!info]- Curiosity —` and ends\n"
    "  // at the next blank line that's followed by `### ` (a date heading)\n"
    "  // or the start of the next callout/section.\n"
    "  const blocks = [];\n"
    "  const lines = raw.split('\\n');\n"
    "  let cur = null;\n"
    "  for (const line of lines) {\n"
    "    if (line.startsWith('> [!info]- Curiosity')) {\n"
    "      if (cur) blocks.push(cur.join('\\n'));\n"
    "      cur = [line];\n"
    "    } else if (cur !== null) {\n"
    "      if (line.startsWith('>')) {\n"
    "        cur.push(line);\n"
    "      } else if (line.trim() === '') {\n"
    "        // Blank line — entry ended. Flush.\n"
    "        blocks.push(cur.join('\\n'));\n"
    "        cur = null;\n"
    "      }\n"
    "    }\n"
    "  }\n"
    "  if (cur) blocks.push(cur.join('\\n'));\n"
    "  if (blocks.length === 0) {\n"
    "    dv.paragraph('_(no past curiosities recorded)_');\n"
    "  } else {\n"
    "    const pick = blocks[Math.floor(Math.random() * blocks.length)];\n"
    "    // Render as raw markdown so the callout, image, and source link all\n"
    "    // appear. paragraph() escapes; we need rawMarkdown.\n"
    "    const span = dv.el('div', '');\n"
    "    await dv.api.renderValue(pick, span, dv.component, path, true);\n"
    "    dv.paragraph(`_From ${blocks.length} past curiosities · reload for another_`);\n"
    "  }\n"
    "}\n"
    "```"
)


def _section_jump_bar() -> str:
    """In-page anchor pill strip for fast section navigation on mobile."""
    chips = [
        "[News](#news)",
        "[Watchlist](#watchlist)",
        "[Papers](#papers)",
        "[Tech](#tech)",
        "[Releases](#github-releases)",
        "[Curiosity](#curiosity)",
    ]
    return "_Jump:_ " + "  ·  ".join(chips)


def _quick_actions_block() -> str:
    """Reading-focused destinations only. The vault is a briefing, not a
    productivity tool — no task-management entries."""
    today = vault.now_ist().date()
    daily_link = f"02 Daily/{today.year}/{today.month:02d}/{today.strftime('%m-%d-%y')} {today.strftime('%a')}"
    return (
        "#### Quick actions\n"
        "\n"
        f"- [[{daily_link}|Open today's daily note]]\n"
        f"- [[📌 Pinboard|Pinboard — saved for later]]\n"
        f"- [[📑 Highlights|Highlights inbox]]\n"
        f"- [[📅 Weekly Recap|Last week's recap]]\n"
        f"\n"
        f"{_RANDOM_NOTE_DV}\n"
    )


def _health_block() -> str:
    """Surface the last-run heartbeat as a one-line status with leading glyph.
    Glyph carries information at a glance, no decoration."""
    path = vault.STATE_DIR / "last_run.json"
    if not path.exists():
        return "○ Last run: no heartbeat yet."
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "✗ Last run: heartbeat unreadable."
    completed = payload.get("completed_at", "")
    ok = payload.get("ok", False)
    streams = payload.get("streams", {})
    failed = [n for n, s in streams.items() if not s]
    try:
        ts = datetime.datetime.fromisoformat(completed)
        age_h = (vault.now_ist() - ts).total_seconds() / 3600
    except ValueError:
        age_h = -1

    if age_h > 26:
        return (
            f"> [!warning]- ✗ Last run was {age_h:.1f}h ago — the timer may have failed.\n"
            f"> Expected ≤24h. Check `~/.hermes/logs/morning-run-*.log` and "
            f"`systemctl status hermes-morning.service`. Run `python -m morning.doctor` "
            f"for a full diagnostic."
        )
    glyph = "✓" if ok else "⚠"
    status = "all streams ok" if ok else f"degraded: {', '.join(failed)}"
    return f"{glyph} Last run {age_h:.1f}h ago — {status}."


def _vault_panel_block(onthisday_snippet: str = "") -> str:
    """Bottom-of-dashboard: system health + vault stats + looking back + on-this-day."""
    onthisday = onthisday_snippet or "_(on-this-day stream pending)_"
    return (
        "#### System health\n"
        "\n"
        f"{_health_block()}\n"
        "\n"
        "#### In your vault\n"
        "\n"
        f"{_VAULT_STATS_DV}\n"
        "\n"
        "#### Looking back\n"
        "\n"
        f"{_ON_THIS_DAY_DV}\n"
        "\n"
        "#### On this day (world history)\n"
        "\n"
        f"{onthisday}\n"
    )


def _build_body(ctx_results: dict[str, str], streak: int) -> str:
    """Compose lines from `### today` heading through the footer link strip.

    Usability-focused layout:
      1. Heatmap (dataviewjs)
      2. Date heading + status line (weather + streak)
      3. OAuth pill (collapsed, only when applicable)
      4. Quick actions (links to common destinations)
      5. Tasks for today (interactive dataviewjs)
      6. Scheduled / Email (stubs or content)
      7. Open threads (interactive dataviewjs)
      8. Discovery streams: News / Watchlist / Papers / Tech / Releases — each
         a top-level H4 with up to 3 collapsed callouts
      9. Footer link strip
    """
    today_h = vault.day_heading().rstrip()

    weather_short = _short_weather(ctx_results.get("weather_dashboard", "").strip())
    weather_long  = ctx_results.get("weather_dashboard", "").strip()

    news_section      = _section_news(ctx_results.get("news_dashboard", ""))
    watchlist_section = _section_watchlist(ctx_results.get("watchlist_dashboard", ""))
    papers_section    = _section_papers(ctx_results.get("papers_dashboard", ""))
    tech_section      = _section_tech(ctx_results.get("tech_dashboard", ""))
    releases_section  = _section_releases(ctx_results.get("releases_dashboard", ""))

    # Tasks/Open-threads removed — this vault is a reading dashboard, not a
    # productivity tool. Email + calendar dropped for the same reason: they
    # were noise the user reads elsewhere (Gmail app, Google Calendar).

    heatmap = _heatmap_block(vault.now_ist().year)

    streak_chip = f"streak {streak}d" if streak else "streak —"
    chips = [c for c in (weather_short, streak_chip) if c]
    status_row = "  ·  ".join(chips)

    minimap = _minimap_line(ctx_results)
    seven_day = _seven_day_strip()

    # Section heading: the entire title (text + ↗) is the link, so tapping
    # anywhere on the heading line jumps to the source note. Previously only
    # the tiny ↗ glyph was clickable.
    def _h(heading: str, target: str | None = None) -> str:
        if target:
            return f"#### [[{target}|{heading} ↗]]"
        return f"#### {heading}"

    return (
        "\n"
        f"{heatmap}\n\n"
        f"{seven_day}\n\n"
        "---\n\n"
        f"{today_h}\n\n"
        f"_{status_row}_\n\n"
        f"_{minimap}_\n\n"
        f"{_section_jump_bar()}\n\n"
        f"{_quick_actions_block()}\n\n"
        "<div class=\"hermes-discovery\">\n\n"
        f"{_h('News', '📰 Daily News')}\n\n"
        f"{news_section}\n\n"
        f"{_h('Watchlist', '🎬 Daily Watchlist')}\n\n"
        f"{watchlist_section}\n\n"
        f"{_h('Papers', '📄 Daily Papers')}\n\n"
        f"{papers_section}\n\n"
        f"{_h('Tech', '🔬 Daily Tech')}\n\n"
        f"{tech_section}\n\n"
        f"{_h('GitHub Releases', '🔄 GitHub Releases')}\n\n"
        f"{releases_section}\n\n"
        f"{_h('Curiosity', '🪅 Daily Curiosity')}\n\n"
        f"{ctx_results.get('curiosity_dashboard', '_(no curiosity surfaced today)_')}\n\n"
        f"{_RANDOM_CURIOSITY_DV}\n\n"
        "</div>\n\n"
        f"{_vault_panel_block(ctx_results.get('onthisday_dashboard', ''))}\n"
        "---\n\n"
        "_Full streams:_ "
        "[[📌 Daily Brief]] · [[📰 Daily News]] · [[🎬 Daily Watchlist]] · "
        "[[📄 Daily Papers]] · [[🔬 Daily Tech]] · [[🔄 GitHub Releases]] · "
        "[[📌 Pinboard]] · [[📑 Highlights]] · [[📥 Email Triage]] · [[📅 Weekly Recap]]\n"
        + (f"\n<!-- weather long: {weather_long} -->\n" if weather_long and weather_short else "")
    )


# -- Entry point ---------------------------------------------------------------

def regenerate(stream_outputs: dict[str, str]) -> None:
    """`stream_outputs` keys (any may be missing/empty string):
        calendar_dashboard, email_dashboard, news_dashboard,
        papers_dashboard, tech_dashboard, releases_dashboard,
        watchlist_dashboard
    """
    path = vault.STREAM_NOTES["dashboard"]
    existing = vault.read(path)

    _maybe_archive_yesterday(existing)

    preamble, _rest = _split_preamble(existing)
    if not preamble:
        # No prior preamble — rebuild minimally so the file still renders.
        today_iso = vault.now_ist().date().isoformat()
        preamble = (
            "---\n"
            f"created: {today_iso}\n"
            f"updated: {today_iso}\n"
            "regenerated_by: hermes\n"
            "unread: false\n"
            "---\n\n"
            "---\n"
        )

    state = _load_state()
    streak = _update_streak(state)
    _save_state(state)

    body = _build_body(stream_outputs, streak)
    new_content = preamble + body

    vault.write(path, new_content)
    vault.set_frontmatter_updated(path, set_unread=False)
