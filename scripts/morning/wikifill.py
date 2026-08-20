"""wikifill — every wikilink the system creates resolves to a note with
substance.

Replaces concept-stubs.py. The earlier approach generated frontmatter-only
files for every dangling `[[X]]` reference, which made the random-note widget
useless and the graph view noisy with content-less nodes. Now each new note
gets one of three bodies, in priority order:

  1. Wikipedia summary — for notable entities (people, places, companies,
     products, concepts). Uses Wikipedia's REST summary endpoint, which
     returns ~2 paragraphs of curated prose plus a source URL.

  2. DDGS fallback — for niche items (specific GitHub projects, indie tools,
     local-only entities). Pulls the top web search hit's title + snippet +
     URL.

  3. Minimal substantive stub — when both above fail. Includes the
     `first_referenced_in` provenance + a one-line nudge so the file isn't
     empty.

Every fill carries a `[Source](url)` line so the user can verify or expand
from the original.

Invoke:
    python -m morning.wikifill --vault $VAULT_ROOT [--cap 80] [--today-only]
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

try:
    from ddgs import DDGS
except ImportError:
    DDGS = None  # type: ignore

# Optional: when the orchestrator runs us via `-m morning.wikifill`, the LLM
# module is on the path and we use it for disambiguation. As a standalone
# script (rare) we degrade — no LLM, fall back to first-non-disambig hit.
try:
    from . import llm as _llm  # type: ignore
except (ImportError, ValueError):
    try:
        from morning import llm as _llm  # type: ignore
    except Exception:
        _llm = None  # type: ignore


WIKILINK = re.compile(r"\[\[([^\]|#]+?)(?:\|[^\]]+)?\]\]")
ARXIV_PATTERN = re.compile(r"^arXiv[ :]?\d{4}\.\d{4,5}(v\d+)?$", re.IGNORECASE)
PERSON_PATTERN = re.compile(r"^[A-Z][a-zà-ÿ]+(?:[\s'-][A-Z][a-zà-ÿ]+){1,3}$")
INVALID_CHARS = re.compile(r"[\[\]/\\<>:\"|*?]")

WIKIPEDIA_SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
# Extracts endpoint gives multi-paragraph plain text — much fuller than the
# summary endpoint. We pull a substantial chunk and let the user read.
WIKIPEDIA_EXTRACT = (
    "https://en.wikipedia.org/w/api.php"
    "?action=query&prop=extracts&explaintext=1&exsectionformat=plain"
    "&exchars=2400&format=json&redirects=1&titles={title}"
)
# Search API — used when summary lands on a disambiguation page so we can
# pick the best-matching real article instead of giving up.
WIKIPEDIA_SEARCH = (
    "https://en.wikipedia.org/w/api.php"
    "?action=query&list=search&srlimit=5&format=json&srsearch={query}"
)
UA = "hermes-morning/1.0 (hermes-morning@example.com)"

# Disambiguation page raw extract — to enumerate candidate meanings of an
# ambiguous term ("NDA" → Non-disclosure agreement, National Defence
# Academy, etc.).
WIKIPEDIA_DISAMBIG_PAGE = (
    "https://en.wikipedia.org/w/api.php"
    "?action=parse&prop=wikitext&format=json&page={title}"
)

# Description keywords that mark a Wikipedia subject as a real human person.
# Used to route into 04 People/ instead of the Title-Case heuristic. Avoid
# overly generic profession words (`general`, `judge`, `doctor`) that also
# appear in office/concept descriptions ("Chief judge of...", "General-purpose
# language"). Stick to nouns that almost only describe humans.
_PERSON_DESC_KEYWORDS = (
    "physicist", "mathematician", "chemist", "biologist", "engineer",
    "scientist", "researcher", "professor", "philosopher", "economist",
    "politician", "writer", "novelist", "poet", "journalist", "historian",
    "musician", "actor", "actress", "filmmaker", "producer", "athlete",
    "footballer", "cricketer", "ceo", "founder", "entrepreneur",
    "inventor", "activist", "lawyer",
    "diplomat", "admiral",
    "artist", "painter", "sculptor", "architect", "designer",
    "primatologist", "zoologist", "anthropologist", "psychologist",
    "pioneer",
    "born ", "biographer",
)
# When description contains these we are clearly NOT a person.
_NONPERSON_DESC_KEYWORDS = (
    "concept", "theory", "method", "algorithm", "model", "language",
    "framework", "library", "protocol", "format", "encoding", "system",
    "kernel", "operating system", "software", "hardware", "device",
    "company", "organization", "organisation", "corporation", "agency",
    "institution", "university", "school", "college", "publisher",
    "city", "town", "village", "country", "region", "state", "province",
    "river", "mountain", "ocean", "sea", "lake", "island",
    "film", "movie", "novel", "book", "album", "song", "video game",
    "phenomenon", "process", "principle", "field", "branch",
    "species", "genus", "family", "disease", "syndrome", "compound",
    "particle", "element", "molecule", "tool", "product",
)
# Concrete entities that aren't people but belong outside 07 References too —
# orgs/products/places land in 07 References (concept folder) by default,
# which matches the user's vault structure (one concept folder, not many).
RESEARCH_HINT_KEYWORDS = ("paper", "preprint", "arxiv")

# Single-word common nouns / verbs / adjectives that the LLM streams wikilink
# but that aren't really concepts you'd want a note for. Skip silently.
_COMMON_WORDS = {
    "the", "and", "or", "with", "from", "into", "for", "this", "that",
    "what", "when", "where", "why", "how", "can", "may", "will", "today",
    "yesterday", "tomorrow", "all", "some", "any", "one", "two", "many",
    "use", "uses", "used", "using",
    "data", "time", "year", "day", "system", "team", "work", "code",
    "energy", "power", "process", "method",
    "name", "note", "creator", "source", "title", "topic", "date",
}

# Patterns that look like template/example placeholders inside prompt
# callouts — never real notes.
_PLACEHOLDER_RE = re.compile(
    r"^(name|note|creator|source|title|topic|date|"
    r"mm-dd-yy|yyyy-mm-dd|week of)",
    re.IGNORECASE,
)


@dataclass
class Reference:
    """A wikilink occurrence in a source note, with its enclosing paragraph
    captured so disambiguation has real context to work with."""
    path: Path
    context: str   # paragraph (or up to ~700 chars) around the wikilink


@dataclass
class FillResult:
    target: str
    folder: str
    source: str  # "wikipedia" / "ddgs" / "stub" / "ambiguous"
    url: str
    success: bool


# -- Vault scanning ------------------------------------------------------------

_CONTEXT_WINDOW_CHARS = 700


def _extract_context(text: str, link_pos: int) -> str:
    """Pull ~700 chars around `link_pos`, clamped to paragraph boundaries
    where convenient. Used to give the disambiguator real signal."""
    half = _CONTEXT_WINDOW_CHARS // 2
    start = max(0, link_pos - half)
    end   = min(len(text), link_pos + half)
    # Expand toward nearest blank-line boundaries
    para_start = text.rfind("\n\n", 0, start)
    if para_start != -1 and link_pos - para_start < _CONTEXT_WINDOW_CHARS * 1.5:
        start = para_start + 2
    para_end = text.find("\n\n", end)
    if para_end != -1 and para_end - link_pos < _CONTEXT_WINDOW_CHARS * 1.5:
        end = para_end
    snippet = text[start:end]
    # Strip callout glyphs, wikilink syntax leftovers, leading > marks.
    snippet = re.sub(r"^>\s?", "", snippet, flags=re.MULTILINE)
    snippet = re.sub(r"!?\[(?:\|\d+)?\]\([^)]*\)", "", snippet)  # markdown images/links
    snippet = re.sub(r"\s+", " ", snippet).strip()
    return snippet[:_CONTEXT_WINDOW_CHARS]


def find_dangling(vault: Path, today_only: bool = True) -> list[tuple[str, list[Reference]]]:
    """Return [(target, [Reference(path, context_paragraph), ...])] for every
    dangling wikilink in files touched today (if today_only) or anywhere in
    vault.

    The `context` field is the paragraph (~700 chars) around the wikilink in
    the source note — used downstream to disambiguate ambiguous terms like
    "NDA" between National Defence Academy and Non-disclosure agreement."""
    existing: set[str] = set()
    for md in vault.rglob("*.md"):
        if any(part.startswith(".") for part in md.parts):
            continue
        existing.add(md.stem)

    today = datetime.date.today()
    refs: dict[str, list[Reference]] = {}
    for md in vault.rglob("*.md"):
        if any(part.startswith(".") for part in md.parts):
            continue
        if today_only:
            try:
                mtime = datetime.date.fromtimestamp(md.stat().st_mtime)
            except OSError:
                continue
            if mtime != today:
                continue
        try:
            raw = md.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        text = _strip_prompt_callouts(raw)
        for m in WIKILINK.finditer(text):
            target = m.group(1).strip()
            if not target or target in existing:
                continue
            if not _is_valid_target(target):
                continue
            context = _extract_context(text, m.start())
            refs.setdefault(target, []).append(Reference(path=md, context=context))

    # Order by reference count (most-referenced first → most important to fill).
    return sorted(refs.items(), key=lambda kv: -len(kv[1]))


_EMAIL_NOISE_RE = re.compile(
    r"^(.*-jobnotification|.*-newsletter|all-students|donot[_-]?reply|"
    r"noreply.*|no-reply.*|.*-team|.*\.com|.*\.in|.*@.*)$",
    re.IGNORECASE,
)


def _is_valid_target(target: str) -> bool:
    if not target or len(target) > 120:
        return False
    if INVALID_CHARS.search(target):
        return False
    if target.endswith(".md") or target.endswith("—") or target.endswith("-"):
        return False
    if "  " in target:
        return False
    if target.lower() in _COMMON_WORDS:
        return False
    if _PLACEHOLDER_RE.match(target):
        return False
    # Email/newsletter-sender-shaped strings — never real concepts.
    if _EMAIL_NOISE_RE.match(target):
        return False
    # Very short uppercase initialisms (NDA, AUR, RBI, CVE) are almost always
    # ambiguous without strong context. Wikifill caller will only proceed if
    # the LLM disambiguator picks confidently; the new ambiguous-stub path
    # already handles these well. Keep — they're worth attempting.
    return True


def _strip_prompt_callouts(text: str) -> str:
    """Remove `> [!prompt]-` blocks before scanning. The wikilinks inside them
    (`[[Note|↗]]`, `[[Creator - YYYY-MM-DD - Topic]]`, etc.) are agent-
    instruction examples, not real targets."""
    lines = text.splitlines()
    out: list[str] = []
    skipping = False
    for line in lines:
        if line.startswith("> [!prompt]"):
            skipping = True
            continue
        if skipping:
            if line.startswith(">"):
                continue
            skipping = False
        out.append(line)
    return "\n".join(out)


def classify(target: str, description: str = "") -> str:
    """Decide which folder a new note belongs in.

    Preferred signal is Wikipedia's `description` field (a short noun phrase
    like "British mathematician" or "free operating system kernel"). When
    that's available we route by it. Falls back to the Title-Case person
    heuristic only when we have no description (e.g. DDGS / minimal stub
    paths), and even then it's a guess — better than always-People."""
    if ARXIV_PATTERN.match(target):
        return "06 Research"

    desc = description.lower().strip()
    if desc:
        # Strongest signal: a year-range like "(1932–1985)" or a birth year
        # like "born 1969" — Wikipedia uses this only for biographies.
        if re.search(r"\((?:c\.?\s*)?\d{4}[\-––]\d{0,4}\)?", desc):
            return "04 People"
        if re.search(r"\bborn\s+\d{4}", desc):
            return "04 People"
        # Profession-noun match — use word boundaries so "general-purpose"
        # doesn't trigger via "general", and "administered" doesn't trigger
        # via "minister".
        for k in _PERSON_DESC_KEYWORDS:
            if k.endswith(" "):  # already has trailing whitespace
                if k in desc:
                    return "04 People"
            elif re.search(rf"\b{re.escape(k)}\b", desc):
                return "04 People"
        # Anything else with a description is NOT a person. The description
        # is Wikipedia's own one-line categorization — if it doesn't say
        # "physicist" or "born YYYY", we should trust it and route concepts/
        # places/orgs/products to References. Skipping this and falling
        # through to PERSON_PATTERN was the bug that gave us "Magnetic Field"
        # and "Adrenal Glands" in 04 People/.
        return "07 References"

    # No description from Wikipedia. Be conservative: only route to People
    # when the name strongly looks like a person AND none of the concept
    # tells appear.
    target_lower = target.lower()
    concept_tells = ("theory", "kernel", "system", "infrastructure", "algorithm",
                     "encoding", "protocol", "framework", "method", "model",
                     "pattern", "language", "ratio", "function", "principle",
                     "law", "effect", "concept", "phenomenon", "machine",
                     "learning", "computing", "engineering", "physics",
                     "chemistry", "biology", "code", "stack", "filesystem")
    if any(t in target_lower for t in concept_tells):
        return "07 References"
    if PERSON_PATTERN.match(target):
        return "04 People"
    return "07 References"


# -- Wikipedia path ------------------------------------------------------------

_LATEX_BLOCK = re.compile(r"\{\\displaystyle[^}]*\}")
_LATEX_MATH = re.compile(r"[−\-]?\s*log\s*_?\{[^}]*\}", re.IGNORECASE)
# Collapse runs of stray symbols left after MathML strips (e.g. lines like
# `(   −  log  ⁡ (1/2)`).
_STRAY_MATH_LINE = re.compile(r"^\s*[−⁡∑∫∂√∞=()/0-9\s\-\+,.;]{0,40}$")


def _strip_math(text: str) -> str:
    """Remove LaTeX/MathML residue from Wikipedia extracts."""
    text = _LATEX_BLOCK.sub("", text)
    text = _LATEX_MATH.sub("", text)
    # Drop lines that are now pure math/symbol residue or empty after stripping.
    keep: list[str] = []
    for ln in text.splitlines():
        if not ln.strip():
            keep.append(ln); continue
        if _STRAY_MATH_LINE.match(ln):
            continue
        keep.append(ln)
    # Collapse 3+ consecutive blanks down to 1.
    out = re.sub(r"\n{3,}", "\n\n", "\n".join(keep))
    # If the tail ends mid-sentence ("...for example"), cap at the last sentence end.
    last_end = max(out.rfind("."), out.rfind("!"), out.rfind("?"))
    if last_end > 200 and last_end < len(out) - 1:
        # If trailing text after the last sentence looks like math fragment
        # or unfinished display, trim it.
        tail = out[last_end + 1:].strip()
        if not tail or len(tail) < 80 or _STRAY_MATH_LINE.match(tail):
            out = out[:last_end + 1]
    return out.strip()


def _fetch_wikipedia_by_title(title_url_part: str) -> dict | None:
    url = WIKIPEDIA_SUMMARY.format(title=title_url_part)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=8) as r:
            return json.loads(r.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None


_DISAMBIG_BULLET = re.compile(
    r"^\*+\s*\[\[([^\]|]+)(?:\|[^\]]+)?\]\]\s*[,–\-—]?\s*(.*?)$",
    re.MULTILINE,
)


def _fetch_disambig_candidates(title_url_part: str) -> list[tuple[str, str]]:
    """Pull the wikitext of a disambiguation page and parse the bullet list
    of candidate articles. Returns [(article_title, short_description)]."""
    url = WIKIPEDIA_DISAMBIG_PAGE.format(title=title_url_part)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return []
    wikitext = (
        data.get("parse", {})
        .get("wikitext", {})
        .get("*", "")
    )
    if not wikitext:
        return []
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for m in _DISAMBIG_BULLET.finditer(wikitext):
        title = m.group(1).strip()
        desc = m.group(2).strip()
        if not title or title.lower() in seen:
            continue
        # Drop common-namespace targets and self-loops.
        if title.startswith(("File:", "Category:", "Help:", "Wikipedia:")):
            continue
        # Strip basic wikitext from description: links, italics, refs.
        desc = re.sub(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", lambda m: m.group(2) or m.group(1), desc)
        desc = re.sub(r"<[^>]+>", "", desc)
        desc = re.sub(r"'{2,}", "", desc)
        desc = re.sub(r"\s+", " ", desc).strip()[:200]
        seen.add(title.lower())
        out.append((title, desc))
        if len(out) >= 30:  # disambig pages can have many entries; 30 caps prompt length
            break
    return out


_DISAMBIG_SYSTEM = (
    "You disambiguate ambiguous wikilink targets by matching them to the "
    "right Wikipedia article given the surrounding article context.\n"
    "\n"
    "You will be given:\n"
    "  TERM: the ambiguous wikilink text\n"
    "  CONTEXT: a paragraph from the source article where this term appears\n"
    "  CANDIDATES: numbered list of Wikipedia articles the term could refer to\n"
    "\n"
    "Method:\n"
    "  1. Read the CONTEXT carefully. Identify the topic domain — military, "
    "law, biology, software, sports, music, geography, etc.\n"
    "  2. Look at each candidate. Match by topic domain only.\n"
    "  3. If exactly one candidate matches the topic, output its number.\n"
    "  4. If multiple plausibly match or none clearly matches, output NONE.\n"
    "\n"
    "STRICT OUTPUT: a single integer (the candidate index) OR the literal "
    "word NONE. No prose, no quotes, no markdown, no period. Wrong meaning "
    "is far worse than NONE — when in doubt, output NONE."
)


def _llm_disambig_pick(term: str, context: str, candidates: list[tuple[str, str]]) -> str | None:
    """Ask the LLM to pick the right candidate. Returns the chosen title, or
    None if the LLM says NONE / fails / no LLM is available."""
    if _llm is None or not candidates or not context.strip():
        return None
    lines = [f"TERM: {term}", "", f"CONTEXT: {context[:600]}", "", "CANDIDATES:"]
    for i, (title, desc) in enumerate(candidates, 1):
        if desc:
            lines.append(f"{i}. {title} — {desc[:140]}")
        else:
            lines.append(f"{i}. {title}")
    lines.append("")
    lines.append("Output the index, or NONE.")
    user = "\n".join(lines)
    try:
        # Use primary model for disambig — the fast model (Qwen 3B) routinely
        # picks the wrong candidate from longer lists, and disambig accuracy
        # matters more than throughput. Worst case ~80 calls/run is fine.
        raw = _llm.chat(
            system=_DISAMBIG_SYSTEM,
            user=user,
            max_tokens=12,
            temperature=0.0,
            prefer="primary",
        ).strip()
    except Exception as e:
        print(f"[wikifill] LLM disambig failed for {term!r}: {e}", file=sys.stderr)
        return None
    if raw.upper().startswith("NONE"):
        return None
    m = re.match(r"\s*(\d+)", raw)
    if not m:
        return None
    idx = int(m.group(1)) - 1
    if 0 <= idx < len(candidates):
        return candidates[idx][0]
    return None


_OFF_CONTEXT_ARTS = ("novel", "film", "movie", "song", "album", "tv series",
                     "band", "musical", "video game", "comic book", "manga",
                     "play (drama)")
_OFF_CONTEXT_TECH = ("encoding", "math", "physics", "quantum", "algorithm",
                     "machine learning", "neural network", "information theory",
                     "compression", "probability", "statistics", "biology",
                     "chemistry", "operating system", "language model",
                     "deep learning", "supply chain", "vulnerability", "kernel",
                     "linux", "AUR", "package", "cybersecurity", "exploit")


def _looks_off_context(description: str, context: str) -> bool:
    """Heuristic: when description looks like 'arts' (novel/film/song) but
    context is technical, the direct hit is probably the wrong sense.

    Symmetric for the other direction is rarely useful since technical
    contexts tend to use specific titles; arts-context wikilinks tend to
    work via direct title."""
    desc_lc = description.lower()
    ctx_lc = context.lower()
    if any(a in desc_lc for a in _OFF_CONTEXT_ARTS) and any(t in ctx_lc for t in _OFF_CONTEXT_TECH):
        return True
    return False


def _gather_search_candidates(target: str, n: int = 6) -> list[tuple[str, str]]:
    """Wikipedia search API → top N hits as (title, snippet). The snippet
    is HTML-y and short, but enough for the LLM to choose. Used in the
    off-context branch."""
    url = WIKIPEDIA_SEARCH.format(query=urllib.parse.quote(target))
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return []
    out: list[tuple[str, str]] = []
    for hit in data.get("query", {}).get("search", [])[:n]:
        title = (hit.get("title") or "").strip()
        snip = re.sub(r"<[^>]+>", "", hit.get("snippet") or "")
        snip = re.sub(r"\s+", " ", snip).strip()
        if title and "(disambiguation)" not in title.lower():
            out.append((title, snip[:180]))
    return out


def _wikipedia_search_top(query: str, skip_titles: set[str] | None = None) -> str | None:
    """When the direct title is a disambiguation, fall back to the search
    API and return the title of the best match (or None).

    `skip_titles` is checked case-insensitively so we don't loop back to the
    same disambiguation page we just left."""
    url = WIKIPEDIA_SEARCH.format(query=urllib.parse.quote(query))
    skip_lc = {s.lower() for s in (skip_titles or set())}
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None
    hits = data.get("query", {}).get("search") or []
    for hit in hits:
        title = (hit.get("title") or "").strip()
        if not title or "(disambiguation)" in title.lower():
            continue
        if title.lower() in skip_lc:
            continue
        return title
    return None


def _fetch_wikipedia(target: str, context_hint: str = "") -> tuple[str, str, str] | None:
    """Return (extract_text, page_url, description) for `target`.

    Three stages:
      1. summary endpoint at /wiki/Target — fast path
      2. if disambiguation, fall back to /w/api.php search for a real article
         (optionally biased by `context_hint`, e.g. the source-note stem)
      3. extracts endpoint for multi-paragraph plain text

    `description` is Wikipedia's short noun-phrase descriptor used for
    folder classification."""
    title_url = urllib.parse.quote(target.replace(" ", "_"))
    summary = _fetch_wikipedia_by_title(title_url)
    if not summary:
        return None

    # --- Disambiguation handling --------------------------------------------
    if summary.get("type") == "disambiguation":
        # Pull the disambig page's candidate list, then let the LLM pick by
        # context. If we can't disambiguate with confidence, return None so
        # the caller writes an "ambiguous" stub rather than fabricating a
        # confidently-wrong note.
        candidates = _fetch_disambig_candidates(title_url)
        picked = _llm_disambig_pick(target, context_hint, candidates)
        if not picked:
            return None
        title_url = urllib.parse.quote(picked.replace(" ", "_"))
        summary = _fetch_wikipedia_by_title(title_url)
        if not summary or summary.get("type") == "disambiguation":
            return None

    # --- Off-context direct hit ---------------------------------------------
    # Even when Wikipedia returns a non-disambig page directly, that page may
    # be totally off-context (e.g. "Random Walk" → 1988 novel when context
    # is about information theory). When we have real paragraph context AND
    # the description's category clashes with what the context suggests,
    # try again via search + LLM picker.
    description = (summary.get("description") or "").strip()
    if context_hint and _looks_off_context(description, context_hint):
        # Try search → LLM pick from search candidates' descriptions.
        candidates = _gather_search_candidates(target)
        # Exclude the off-context article we just looked at.
        candidates = [(t, d) for t, d in candidates if t.lower() != title_url.replace("_", " ").lower()]
        picked = _llm_disambig_pick(target, context_hint, candidates)
        if picked:
            alt_title_url = urllib.parse.quote(picked.replace(" ", "_"))
            alt = _fetch_wikipedia_by_title(alt_title_url)
            if alt and alt.get("type") not in (None, "disambiguation"):
                summary = alt
                description = (summary.get("description") or "").strip()
                title_url = alt_title_url
    page_url = summary.get("content_urls", {}).get("desktop", {}).get("page") or ""

    # Pull the longer extract.
    ext_url = WIKIPEDIA_EXTRACT.format(title=title_url)
    extract = ""
    try:
        req = urllib.request.Request(ext_url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=10) as r:
            ext_data = json.loads(r.read().decode("utf-8"))
        pages = ext_data.get("query", {}).get("pages", {})
        for pid, page in pages.items():
            if pid != "-1":
                extract = (page.get("extract") or "").strip()
                break
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        pass

    if not extract:
        extract = (summary.get("extract") or "").strip()
    if not extract:
        return None

    extract = _strip_math(extract)
    if not extract:
        return None
    return extract, page_url, description


# -- DDGS fallback -------------------------------------------------------------

_HTML_TAG = re.compile(r"<[^>]+>")
_HTML_WS = re.compile(r"\s+")


def _scrape_article(url: str) -> str:
    """Fetch the URL and extract a substantial body-text excerpt. Strips
    script/style/nav/aside, then collapses whitespace. Returns up to ~3000
    chars of useful prose."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read(300 * 1024).decode("utf-8", errors="replace")
    except Exception:
        return ""
    # Strip noise containers
    raw = re.sub(r"<(script|style|nav|aside|footer|header|form)[^>]*>.*?</\1>",
                 " ", raw, flags=re.IGNORECASE | re.DOTALL)
    text = _HTML_TAG.sub(" ", raw)
    text = _HTML_WS.sub(" ", text).strip()
    # Crude trim: take the longest paragraph-ish chunk by joining text after
    # the first 200 chars (often nav/header) and before 3000.
    if len(text) > 3000:
        text = text[200:3200]
    return text.strip()


def _fetch_ddgs(target: str) -> tuple[str, str] | None:
    """Search DDGS for `target`, then fetch the top hit's actual article body
    and extract a multi-paragraph excerpt — much fuller than the snippet."""
    if DDGS is None:
        return None
    try:
        with DDGS() as d:
            hits = list(d.text(target, max_results=4, region="us-en", safesearch="off"))
    except Exception as e:
        print(f"[wikifill] ddgs failed for {target!r}: {type(e).__name__}: {e}", file=sys.stderr)
        return None

    for r in hits:
        url = r.get("href") or r.get("url") or ""
        snippet = (r.get("body") or "").strip()
        if not url:
            continue
        # Try to scrape the actual page for fuller content
        body = _scrape_article(url)
        if body and len(body) >= 300:
            return body[:2400], url
        # Fall back to the longer of snippet vs scraped if both are weak
        if snippet and len(snippet) >= 80:
            combined = body if len(body) > len(snippet) else snippet
            return combined[:2400], url
    return None


# -- Note rendering ------------------------------------------------------------

def _frontmatter(today: str, source: str, url: str, first_referenced_in: Path | None) -> str:
    lines = [
        "---",
        f"created: {today}",
        f"updated: {today}",
        "unread: true",
        f"fill_source: {source}",
    ]
    if url:
        lines.append(f"source_url: \"{url}\"")
    if first_referenced_in is not None:
        try:
            rel = first_referenced_in.relative_to(first_referenced_in.parent.parent.parent)
            ref_stem = first_referenced_in.stem
            lines.append(f"first_referenced_in: \"[[{ref_stem}]]\"")
        except ValueError:
            pass
    lines.append("---")
    return "\n".join(lines) + "\n"


def _render_wikipedia(target: str, extract: str, page_url: str, ref: Path | None) -> str:
    today = datetime.date.today().isoformat()
    fm = _frontmatter(today, "wikipedia", page_url, ref)
    body = (
        f"> [!info] Source — Wikipedia\n"
        f"> [{target} on Wikipedia]({page_url})\n\n"
        f"{extract}\n\n"
        f"---\n_Auto-filled from Wikipedia on {today}. Edit to add your own notes._\n"
    )
    return fm + "\n" + body


def _render_ddgs(target: str, snippet: str, url: str, ref: Path | None) -> str:
    today = datetime.date.today().isoformat()
    fm = _frontmatter(today, "ddgs", url, ref)
    body = (
        f"> [!info] Source\n"
        f"> [{target}]({url})\n\n"
        f"{snippet}\n\n"
        f"---\n_Auto-filled from a web search on {today}. Wikipedia didn't have "
        f"an entry. Edit to add your own notes._\n"
    )
    return fm + "\n" + body


def _render_minimal(target: str, ref: Path | None) -> str:
    today = datetime.date.today().isoformat()
    fm = _frontmatter(today, "stub", "", ref)
    body = (
        f"> [!info] No source surfaced\n"
        f"> Neither Wikipedia nor a web search returned anything substantive "
        f"for `{target}` on {today}.\n\n"
        f"This note was created so the wikilink resolves to a real file. "
        f"Replace this paragraph with your own context, paste a relevant "
        f"link, or delete the file if the reference was incidental.\n"
    )
    return fm + "\n" + body


def _render_ambiguous(target: str, ref_ctx: str, ref: Path | None,
                      candidates: list[tuple[str, str]]) -> str:
    """When wikifill genuinely can't disambiguate, write a stub that's
    honest about it. List the candidate meanings so the user can decide.
    This is strictly better than confidently picking the wrong one."""
    today = datetime.date.today().isoformat()
    fm = _frontmatter(today, "ambiguous", "", ref)
    cand_lines = ""
    if candidates:
        cand_lines = "\n\nPossible meanings (from Wikipedia):\n\n" + "\n".join(
            f"- [[{title}]]" + (f" — {desc}" if desc else "")
            for title, desc in candidates[:8]
        )
    ctx_snippet = ref_ctx[:300].strip()
    ctx_block = ""
    if ctx_snippet:
        ctx_block = f"\n\n> [!info] Context where this was referenced\n> {ctx_snippet}"
    body = (
        f"> [!warning] Ambiguous reference\n"
        f"> `{target}` has multiple meanings on Wikipedia and the source "
        f"context wasn't decisive enough to pick one confidently. Rather "
        f"than guess, this stub lists the candidates."
        f"{ctx_block}{cand_lines}\n\n"
        f"---\n_Auto-stub created on {today}. Pick the right meaning by "
        f"renaming this file or replacing the body._\n"
    )
    return fm + "\n" + body


# -- Driver --------------------------------------------------------------------

def fill_one(vault: Path, target: str, refs: list[Reference]) -> FillResult:
    ref = refs[0].path if refs else None
    # Concatenate up to 2 source paragraphs for stronger disambig signal.
    context = " ".join(r.context for r in refs[:2]) if refs else ""

    # 1. Wikipedia first (with paragraph-context disambiguation)
    wiki = _fetch_wikipedia(target, context_hint=context)
    if wiki is not None:
        extract, page_url, description = wiki
        folder = classify(target, description)
        body = _render_wikipedia(target, extract, page_url, ref)
        path = vault / folder / f"{target}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        return FillResult(target, folder, "wikipedia", page_url, True)

    # 1a. Check whether the failure was disambiguation. If so, write an
    # "ambiguous" stub listing the candidates instead of falling through to
    # DDGS (which usually fabricates a confidently-wrong answer for
    # ambiguous terms).
    title_url = urllib.parse.quote(target.replace(" ", "_"))
    summary_again = _fetch_wikipedia_by_title(title_url)
    if summary_again and summary_again.get("type") == "disambiguation":
        candidates = _fetch_disambig_candidates(title_url)
        folder = classify(target)  # default to references for unknowns
        body = _render_ambiguous(target, context, ref, candidates)
        path = vault / folder / f"{target}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        return FillResult(target, folder, "ambiguous", "", True)

    # 2. DDGS fallback (only when Wikipedia legit doesn't have it)
    folder = classify(target)
    ddgs = _fetch_ddgs(target)
    if ddgs is not None:
        body = _render_ddgs(target, ddgs[0], ddgs[1], ref)
        path = vault / folder / f"{target}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        return FillResult(target, folder, "ddgs", ddgs[1], True)

    # 3. Minimal substantive stub
    body = _render_minimal(target, ref)
    path = vault / folder / f"{target}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return FillResult(target, folder, "stub", "", True)


def run(vault: Path, cap: int = 80, today_only: bool = True) -> dict:
    dangling = find_dangling(vault, today_only=today_only)
    if not dangling:
        return {"created": 0, "by_source": {}, "skipped": 0}

    by_source = {"wikipedia": 0, "ddgs": 0, "stub": 0, "ambiguous": 0}
    created = 0
    capped_at = min(cap, len(dangling))
    for target, refs in dangling[:capped_at]:
        try:
            r = fill_one(vault, target, refs)
            by_source[r.source] = by_source.get(r.source, 0) + 1
            created += 1
            time.sleep(0.1)
        except Exception as e:
            print(f"[wikifill] error filling {target!r}: {type(e).__name__}: {e}", file=sys.stderr)
    return {
        "created": created,
        "by_source": by_source,
        "remaining_dangling": max(0, len(dangling) - capped_at),
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--vault", required=True, type=Path)
    p.add_argument("--cap", type=int, default=80, help="max notes created per run")
    p.add_argument("--today-only", action="store_true",
                   help="only consider dangling links in files touched today")
    p.add_argument("--all", dest="today_only", action="store_false",
                   help="scan all dangling links across the vault")
    p.set_defaults(today_only=True)
    args = p.parse_args()

    report = run(args.vault, cap=args.cap, today_only=args.today_only)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
