"""Daily Papers stream — deterministic, no LLM curation.

Fetches arXiv per configured category (plus optional journal RSS feeds like
Nature Physics and PRL), dedupes, and picks papers via strict round-robin
across categories. Renders the abstract VERBATIM.

Why no LLM: the previous LLM-curated flow biased heavily to quant-ph/cs.AI
because those categories have showier abstracts. Round-robin gives every
configured category a floor — one pick per category before any category
gets a second — so cs.IT, cond-mat.str-el, physics.comp-ph actually get
seen instead of being crowded out.

State at `~/.hermes/state/papers-seen-ids.json` — a paper's arXiv id + version
is remembered so revisions don't re-surface as fresh."""
from __future__ import annotations

import datetime
import json
import re
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

import feedparser

from . import config, feed_health, vault


ARXIV_CATEGORIES = config.get("papers", "categories",
                              default=["quant-ph", "cs.IT", "cs.AI", "cs.LG", "cond-mat.mes-hall"])

# Additional non-arXiv journal RSS feeds. Round-robin treats each of these
# as its own "category" so they always get a floor. All serve plain RSS with
# title + author + abstract already prepared by the publisher.
#
# Format: {"category_label": "rss_url", ...}
EXTRA_FEEDS: dict[str, str] = config.get("papers", "extra_feeds", default={
    "Nature Physics":  "https://www.nature.com/nphys.rss",
    "PRL":             "https://feeds.aps.org/rss/recent/prl.xml",
    "bioRxiv":         "https://connect.biorxiv.org/biorxiv_xml.php?subject=all",
    "Quanta":          "https://www.quantamagazine.org/feed/",
})

# /api/query is the supported daily endpoint — the legacy /rss/ feeds explicitly
# skip Saturday/Sunday, which makes them useless for a 7-day scheduler.
_ARXIV_API = (
    "http://export.arxiv.org/api/query?"
    "search_query=cat:{cat}"
    "&sortBy=submittedDate&sortOrder=descending"
    "&max_results=30"
)


def ARXIV_FEEDS() -> dict[str, str]:
    return {cat: _ARXIV_API.format(cat=cat) for cat in ARXIV_CATEGORIES}

STATE_FILE = vault.STATE_DIR / "papers-seen-ids.json"

_ARXIV_ID = re.compile(r"(\d{4}\.\d{4,5})(v\d+)?")


@dataclass
class Paper:
    arxiv_id: str
    version: str
    title: str
    authors: list[str]
    category: str
    submitted: str       # YYYY-MM-DD, best effort
    abstract: str
    abs_url: str
    pdf_url: str

    @property
    def id_with_v(self) -> str:
        return f"{self.arxiv_id}{self.version}"


def _load_state() -> dict[str, str]:
    """Return {arxiv_id: latest_seen_version}."""
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_state(state: dict[str, str]) -> None:
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(STATE_FILE)


def _parse_authors(raw: str) -> list[str]:
    raw = re.sub(r"<[^>]+>", "", raw)  # strip HTML
    parts = [p.strip() for p in raw.replace(" and ", ",").split(",")]
    return [p for p in parts if p]


def _fetch_feed(category: str, url: str) -> list[Paper]:
    try:
        parsed = feedparser.parse(url)
    except Exception as e:
        print(f"[papers] fetch failed for {category}: {e}", file=sys.stderr)
        return []
    out: list[Paper] = []
    for entry in parsed.entries:
        link = entry.get("link", "")
        m = _ARXIV_ID.search(link) or _ARXIV_ID.search(entry.get("id", ""))
        if not m:
            continue
        arxiv_id = m.group(1)
        version = m.group(2) or ""

        summary = entry.get("summary", "") or entry.get("description", "")
        # arXiv abstracts arrive prefixed with "Abstract:" sometimes.
        summary = re.sub(r"^\s*Abstract:\s*", "", summary, flags=re.IGNORECASE)
        summary = re.sub(r"<[^>]+>", "", summary).strip()

        # Atom: `authors` is a list of dicts ({'name': ...}). RSS: single `author` string.
        raw_authors = entry.get("authors") or entry.get("author") or ""
        if isinstance(raw_authors, list):
            authors = [a.get("name", "").strip() for a in raw_authors if a.get("name")]
        else:
            authors = _parse_authors(str(raw_authors))

        submitted = ""
        if "published_parsed" in entry and entry.published_parsed:
            submitted = datetime.datetime(*entry.published_parsed[:6]).strftime("%Y-%m-%d")
        elif "updated_parsed" in entry and entry.updated_parsed:
            submitted = datetime.datetime(*entry.updated_parsed[:6]).strftime("%Y-%m-%d")

        out.append(Paper(
            arxiv_id=arxiv_id,
            version=version,
            title=re.sub(r"\s+", " ", entry.get("title", "")).strip(),
            authors=authors,
            category=category,
            submitted=submitted,
            abstract=summary,
            abs_url=f"https://arxiv.org/abs/{arxiv_id}",
            pdf_url=f"https://arxiv.org/pdf/{arxiv_id}.pdf",
        ))
    return out


def _dedup(papers: list[Paper]) -> list[Paper]:
    """Keep first occurrence of each arxiv_id (in feed iteration order)."""
    seen: set[str] = set()
    out: list[Paper] = []
    for p in papers:
        if p.arxiv_id in seen:
            continue
        seen.add(p.arxiv_id)
        out.append(p)
    return out


MAX_PICKS = config.get("papers", "max_picks", default=8)
MAX_PER_CATEGORY_PICKED = config.get("papers", "max_per_category_picked", default=2)


def _select_top(pool: list[Paper], *, prefer_model: str = "primary") -> list[Paper]:
    """Deterministic round-robin selection across categories.

    Every category with candidates gets picks[0] before any category
    gets picks[1]. Ensures cs.IT, cond-mat.*, physics.* etc. surface
    even when quant-ph and cs.AI dominate the raw pool.

    prefer_model kwarg is accepted for signature compat but ignored — no LLM."""
    if not pool:
        return []

    by_cat: dict[str, list[Paper]] = {}
    for p in pool:
        by_cat.setdefault(p.category, []).append(p)
    # Within each category, freshest first (arXiv fetch already sorts DESC).
    cats = sorted(by_cat.keys())   # stable alphabetical order across categories

    picked: list[Paper] = []
    per_cat_count: dict[str, int] = {}
    round_num = 0
    while len(picked) < MAX_PICKS:
        made_progress = False
        for c in cats:
            if len(picked) >= MAX_PICKS:
                break
            if per_cat_count.get(c, 0) >= MAX_PER_CATEGORY_PICKED:
                continue
            if not by_cat[c]:
                continue
            picked.append(by_cat[c].pop(0))
            per_cat_count[c] = per_cat_count.get(c, 0) + 1
            made_progress = True
        if not made_progress:
            break
        round_num += 1

    return picked


def _cap_abstract(text: str, word_cap: int = 400) -> str:
    """Mostly a no-op now — abstracts are passed through in full. Cap only
    at a defensive 400 words to catch the rare meta-paper that quotes 5
    pages in its abstract."""
    words = text.split()
    if len(words) <= word_cap:
        return text
    truncated = " ".join(words[:word_cap])
    for end in (truncated.rfind("."), truncated.rfind("?"), truncated.rfind("!")):
        if end >= len(truncated) - 30 and end > 0:
            return truncated[:end + 1] + "…"
    return truncated + "…"


_REAL_ARXIV_ID = re.compile(r"^\d{4}\.\d{4,5}$")


def _render_paper(p: Paper) -> str:
    # Authors as plain text — users don't want stubs auto-created for
    # researchers they'll never read about. If you want a particular author,
    # wikilink them manually in your own notes.
    authors_md = ", ".join(p.authors[:6])
    if len(p.authors) > 6:
        authors_md += ", et al."
    abstract = _cap_abstract(p.abstract)

    # Header + link labels depend on whether this is a real arXiv paper
    # (matches YYYY.NNNNN[N]) or a journal RSS entry (sha1 pseudo-id).
    if _REAL_ARXIV_ID.match(p.arxiv_id):
        header = f"> [!paper]- arXiv:{p.arxiv_id} — {p.title}"
        links = f"> **Links:** [arXiv]({p.abs_url}) · [PDF]({p.pdf_url})"
    else:
        header = f"> [!paper]- {p.category} — {p.title}"
        # Journal PDFs are usually gated behind the article page, so we only
        # link the article. Suppress the duplicate PDF link.
        links = f"> **Link:** [{p.category}]({p.abs_url})"

    lines = [
        header,
        f"> **Authors:** {authors_md}" if authors_md else "> **Authors:** —",
        f"> **Category:** {p.category}",
        f"> **Submitted:** {p.submitted or '—'}",
        ">",
        f"> **Abstract:** {abstract}",
        ">",
        links,
    ]
    return "\n".join(lines)


def _fetch_journal_rss(label: str, url: str) -> list[Paper]:
    """Fetch a non-arXiv journal RSS. Journal feeds don't give us arXiv IDs,
    so we synthesise a stable ID from the URL for dedupe purposes."""
    import hashlib
    if feed_health.should_skip(url):
        return []
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Firefox/128.0",
            "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9",
        })
        with urllib.request.urlopen(req, timeout=12) as r:
            raw = r.read()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
        print(f"[papers] journal fetch failed {label}: {type(e).__name__}: {e}", file=sys.stderr)
        feed_health.record_failure(url, f"{type(e).__name__}")
        return []
    feed_health.record_success(url)

    parsed = feedparser.parse(raw)
    out: list[Paper] = []
    for e in parsed.entries[:8]:
        link = (e.get("link") or "").strip()
        title = re.sub(r"\s+", " ", e.get("title") or "").strip()
        if not link or not title:
            continue
        # Synthesise a pseudo-arxiv-id so dedupe/state work uniformly.
        pseudo_id = hashlib.sha1(link.encode()).hexdigest()[:12]
        raw_abs = e.get("summary") or e.get("description") or ""
        abs_text = re.sub(r"<[^>]+>", " ", raw_abs)
        abs_text = re.sub(r"\s+", " ", abs_text).strip()
        submitted = ""
        for k in ("published_parsed", "updated_parsed"):
            if e.get(k):
                submitted = datetime.datetime(*e[k][:6]).strftime("%Y-%m-%d")
                break
        # Author list — journal RSS varies wildly, best-effort
        authors = []
        for a in (e.get("authors") or []):
            n = a.get("name", "").strip()
            if n:
                authors.append(n)
        if not authors and e.get("author"):
            authors = _parse_authors(str(e["author"]))
        out.append(Paper(
            arxiv_id=pseudo_id,
            version="",
            title=title,
            authors=authors,
            category=label,       # e.g. "Nature Physics" — treated as its own category
            submitted=submitted,
            abstract=abs_text or "(No abstract in feed.)",
            abs_url=link,
            pdf_url=link,          # journal PDFs are gated; link to article page
        ))
    return out


def run(*, prefer_model: str = "primary") -> str:
    """Deterministic pipeline: parallel fetch → dedupe → round-robin → render.

    prefer_model kwarg accepted for orchestrator signature compat, ignored.
    No LLM calls anywhere."""
    state = _load_state()

    all_papers: list[Paper] = []
    # Fetch arXiv categories + journal feeds in parallel — big latency win.
    fetch_jobs: list[tuple[str, str, str]] = [
        ("arxiv", cat, url) for cat, url in ARXIV_FEEDS().items()
    ] + [
        ("journal", label, url) for label, url in EXTRA_FEEDS.items()
    ]
    with ThreadPoolExecutor(max_workers=min(8, len(fetch_jobs))) as pool_exec:
        futures = {
            pool_exec.submit(_fetch_feed if kind == "arxiv" else _fetch_journal_rss,
                             label, url): (kind, label)
            for kind, label, url in fetch_jobs
        }
        for fut in as_completed(futures):
            kind, label = futures[fut]
            try:
                all_papers.extend(fut.result())
            except Exception as e:
                print(f"[papers] {kind} {label} raised {type(e).__name__}: {e}", file=sys.stderr)

    if not all_papers:
        body = (
            "> [!warning] Daily Papers: no feed entries fetched\n"
            "> All arXiv + journal feeds returned empty or failed. Check network."
        )
        vault.insert_today_entry(vault.STREAM_NOTES["papers"], body)
        vault.set_frontmatter_updated(vault.STREAM_NOTES["papers"])
        return body

    all_papers = _dedup(all_papers)

    # Drop papers we've already covered at the same-or-higher version.
    fresh = [p for p in all_papers if state.get(p.arxiv_id, "") != p.version]
    pool = fresh or all_papers

    picks = _select_top(pool)

    if not picks:
        body = "Light feed today — nothing crossed the selection criteria."
    else:
        body = "\n\n".join(_render_paper(p) for p in picks)

    # Persist seen-versions so revisions are learned.
    for p in pool:
        prev = state.get(p.arxiv_id, "")
        if not prev or p.version > prev:
            state[p.arxiv_id] = p.version
    _save_state(state)

    vault.insert_today_entry(vault.STREAM_NOTES["papers"], body)
    vault.set_frontmatter_updated(vault.STREAM_NOTES["papers"])
    return body


if __name__ == "__main__":
    print(run())
