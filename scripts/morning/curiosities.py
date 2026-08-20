"""Curiosities stream — surface interesting historical/retro tech items.

Fires from `releases.py` when no new GitHub releases land. Reads topic list
from `_curiosities.yaml`, picks one that hasn't been surfaced in the last 60
days, does a DuckDuckGo search, and emits a `[!info]-` callout with a real
source URL.

Anti-fabrication: the URL in the callout MUST be one of the URLs the search
returned. The LLM only writes the framing prose."""
from __future__ import annotations

import datetime
import json
import random
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from . import llm, vault

try:
    from ddgs import DDGS
except ImportError:
    DDGS = None  # type: ignore


CURIOSITIES_YAML = vault.VAULT / "_curiosities.yaml"
STATE_FILE = vault.STATE_DIR / "curiosities-shown.json"
DISCOVERED_FILE = vault.STATE_DIR / "curiosities-discovered.json"
COOLDOWN_DAYS = 60


@dataclass
class Topic:
    name: str
    angle: str  # search/framing hint, e.g. "retrospective"


@dataclass
class Hit:
    title: str
    url: str
    snippet: str


# -- Parse the YAML topic list (no PyYAML dep) ---------------------------------

def _parse_topics(raw: str) -> list[Topic]:
    out: list[Topic] = []
    in_list = False
    current: dict[str, str] = {}

    def _flush() -> None:
        nonlocal current
        if current.get("name"):
            out.append(Topic(name=current["name"], angle=current.get("angle", "history")))
        current = {}

    for raw_line in raw.splitlines():
        line = raw_line.split("#", 1)[0].rstrip() if not raw_line.strip().startswith("#") else ""
        if not line:
            continue
        if line.startswith("topics:"):
            in_list = True
            continue
        if not in_list:
            continue
        m_dash = re.match(r"\s*-\s*name:\s*(.+?)\s*$", line)
        if m_dash:
            _flush()
            current = {"name": m_dash.group(1).strip()}
            continue
        m_kv = re.match(r"\s+(\w+):\s*(.+?)\s*$", line)
        if m_kv and current:
            current[m_kv.group(1)] = m_kv.group(2).strip()
    _flush()
    return out


def _load_topics() -> list[Topic]:
    """User-curated YAML + LLM-discovered JSON. Combined pool for picking."""
    raw = vault.read(CURIOSITIES_YAML)
    topics = _parse_topics(raw) if raw else []
    seen_names = {t.name.lower() for t in topics}
    if DISCOVERED_FILE.exists():
        try:
            discovered = json.loads(DISCOVERED_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            discovered = []
        for d in discovered:
            name = d.get("name", "").strip()
            if name and name.lower() not in seen_names:
                topics.append(Topic(name=name, angle=d.get("angle", "history")))
                seen_names.add(name.lower())
    return topics


# -- State (last-shown dates) --------------------------------------------------

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


def _pick_topic(topics: list[Topic], state: dict[str, str]) -> Topic | None:
    """Pick a topic not surfaced in the last COOLDOWN_DAYS. If all are within
    cooldown, pick the least-recently-surfaced one."""
    if not topics:
        return None
    today = vault.now_ist().date()
    eligible: list[Topic] = []
    for t in topics:
        last = state.get(t.name, "")
        if not last:
            eligible.append(t)
            continue
        try:
            last_date = datetime.date.fromisoformat(last)
        except ValueError:
            eligible.append(t)
            continue
        if (today - last_date).days >= COOLDOWN_DAYS:
            eligible.append(t)
    if eligible:
        return random.choice(eligible)
    # All within cooldown — pick the one whose last show was furthest in the past.
    topics_sorted = sorted(topics, key=lambda t: state.get(t.name, "0001-01-01"))
    return topics_sorted[0] if topics_sorted else None


# -- Search --------------------------------------------------------------------

def _domain(url: str) -> str:
    m = re.match(r"https?://([^/]+)/?", url)
    if not m:
        return ""
    host = m.group(1).lower()
    return host[4:] if host.startswith("www.") else host


_HIGH_SIGNAL_DOMAINS = (
    # Broadly good long-form / retrospective sources across the topic pool
    "arstechnica.com", "ieee.org", "spectrum.ieee.org", "technologyreview.com",
    "wired.com", "theverge.com", "engadget.com", "restofworld.org",
    "atlasobscura.com", "smithsonianmag.com", "nautil.us",
    "designmuseum.org", "moma.org", "cooperhewitt.org",   # design / museum
    "hackaday.com", "adafruit.com",                        # maker / hardware
    "computerhistory.org", "vintageeverydaycomputers.com", # computing history
    "en.wikipedia.org", "britannica.com",                  # baseline
    "nasa.gov", "esa.int", "nature.com",                   # science
    "criterion.com", "sight-sound.co.uk",                  # film culture (if surfaced)
    "hifi.com", "stereophile.com", "hifinews.com",         # audio classics
    "silodrome.com", "petrolicious.com", "hagerty.com",    # cars / motorbikes
    "hackernoon.com", "phoronix.com", "lwn.net",           # linux / open source
)


def _score_hit(url: str, title: str, snippet: str) -> int:
    """Rank a hit by likely-substance signal. Higher wins.

      +3 for a high-signal domain (curated editorial vs. random SEO)
      +2 if title/snippet mentions concrete years, dimensions, materials
      +1 if the URL path looks like an article (has slashes, not root)
      -3 if URL is a shopping / affiliate page
      -2 if URL looks like a listicle (has 'top-N-'/'best-of'/'-vs-')
    """
    score = 0
    ul = url.lower()
    for d in _HIGH_SIGNAL_DOMAINS:
        if d in ul:
            score += 3
            break
    if any(sig in (title + " " + snippet).lower()
           for sig in ("1980s", "1990s", "1970s", "designed by",
                       "released in", "launched in", "invented",
                       "prototype", "patent", "originally")):
        score += 2
    path = urllib.parse.urlparse(url).path
    if path.count("/") >= 2 and len(path) > 6:
        score += 1
    if any(bad in ul for bad in ("amazon.", "ebay.", "shopping", "aliexpress")):
        score -= 3
    if re.search(r"top-\d+|best-of|\d+-vs-\d+|-review-2\d{3}", ul):
        score -= 2
    return score


def _search(topic: Topic) -> list[Hit]:
    if DDGS is None:
        return []
    # Multi-angle query set. Broad first, retrospective/story next, and
    # a "history <topic>" query which reliably surfaces enthusiast wikis
    # + museum-caption content for design + retro-tech topics.
    queries = [
        f"{topic.name} {topic.angle}",
        f"{topic.name} history retrospective",
        f"{topic.name} designed by launched",
        f'"{topic.name}" review museum retrospective',
        f"{topic.name}",
    ]
    seen: dict[str, Hit] = {}
    try:
        with DDGS() as d:
            for q in queries:
                for r in d.text(q, max_results=5, safesearch="off"):
                    url = r.get("href") or r.get("url") or ""
                    if not url or url in seen:
                        continue
                    seen[url] = Hit(
                        title=(r.get("title") or "").strip(),
                        url=url,
                        snippet=(r.get("body") or "").strip(),
                    )
    except Exception as e:
        print(f"[curiosities] search failed: {type(e).__name__}: {e}", file=sys.stderr)

    # Rank by domain quality + concrete-detail signals, then keep top 8.
    hits = sorted(
        seen.values(),
        key=lambda h: -_score_hit(h.url, h.title, h.snippet),
    )
    return hits[:8]


# -- LLM framing ---------------------------------------------------------------

_SYSTEM = (
    "You frame a single 'Curiosity' callout for a personal knowledge vault. "
    "The user has saved a list of objects, people, machines, effects, and "
    "design classics they want to revisit (Tizio lamps, BMW E30s, Feynman, "
    "ThinkPads, Purkinje effect, PinePhone, etc.). Each morning we surface "
    "one — a moment of reflection before they read the news.\n"
    "\n"
    "── PICK A SOURCE ────────────────────────────────────────\n"
    "You get a topic, an angle hint, and a numbered list of candidate hits "
    "(title + URL + snippet, ranked by expected quality). Choose ONE:\n"
    "  ★ Prefer editorial / museum / enthusiast / archival writeups — "
    "    Ars Technica, IEEE Spectrum, MIT Tech Review, Wired, Atlas Obscura, "
    "    Smithsonian, Cooper Hewitt, Design Museum, Computer History Museum, "
    "    Silodrome, Hackaday, LWN.\n"
    "  ★ Wikipedia and Britannica are acceptable *baselines* but never the "
    "    first choice when a substantive editorial source is present.\n"
    "  ★ Avoid shopping pages, e-commerce, affiliate 'top-10' articles, and "
    "    press-release rehashes.\n"
    "  ★ Prefer a source with concrete details (year, designer, materials, "
    "    dimensions, patents, prototype history) over one with vibes.\n"
    "\n"
    "── WRITE THE PARAGRAPH ──────────────────────────────────\n"
    "  ▸ 7-10 sentences. A rich, satisfying paragraph — the user reads this "
    "    with morning coffee and wants to be transported for a full minute. "
    "    Aim for the depth of a good long-form museum wall text, a well-"
    "    written obituary, or a Jasper Morrison catalogue essay.\n"
    "  ▸ Pack in concrete specifics: designer name + year + place of "
    "    manufacture, materials, dimensions or mass, the technical or "
    "    cultural constraint that shaped it, and — critically — ONE "
    "    memorable anecdote or telling detail that a reader will remember: "
    "    a design fight, a launch failure, a quirky patent, an unusual user, "
    "    a rediscovery story, the person who kept it alive after everyone "
    "    else forgot.\n"
    "  ▸ Weave in cultural context: what was happening in the world when "
    "    this appeared, what came before it, what came after because of it.\n"
    "  ▸ Zero hype adjectives ('iconic', 'legendary', 'stunning', "
    "    'game-changing', 'revolutionary'). If it's iconic the reader knows.\n"
    "  ▸ Do NOT begin with 'The [topic]…' or 'In [year],…' — vary openings. "
    "    Try starting with the designer, the constraint, the failure, the "
    "    unexpected user, or a memorable sensory detail.\n"
    "  ▸ Wikilink 3-6 notable people/places/makers/movements per entry: "
    "    [[Achille Castiglioni]], [[Bauhaus]], [[Zeiss]], [[Ulm School]].\n"
    "  ▸ If a snippet doesn't back a claim, LEAVE IT OUT. Don't invent.\n"
    "  ▸ End the paragraph with a resonant closer — where the thing lives "
    "    now, what it influenced, who still champions it — not a summary "
    "    sentence.\n"
    "\n"
    "── FORMAT (exact) ───────────────────────────────────────\n"
    "> [!info]- Curiosity — {Topic} · {4-7 word angle}\n"
    "> Paragraph as above, per the writing rules.\n"
    "> [Source](https://exact-url-from-input)\n"
    "\n"
    "RULES:\n"
    "  - The Source URL MUST be one of the provided URLs, copied verbatim.\n"
    "  - The topic name appears exactly as given; do NOT translate or "
    "    rephrase.\n"
    "  - No code fences, no surrounding prose, just the callout block."
)


def _build_user_prompt(topic: Topic, hits: list[Hit]) -> str:
    lines = [f"Topic: {topic.name}", f"Angle: {topic.angle}", "", "Candidates:"]
    for i, h in enumerate(hits, 1):
        lines.append(f"{i}. {h.title}")
        lines.append(f"   URL: {h.url}")
        if h.snippet:
            lines.append(f"   Snippet: {h.snippet[:280]}")
    lines.append("")
    lines.append("Write the callout now.")
    return "\n".join(lines)


_URL_RE = re.compile(r"\[Source\]\((https?://[^\s)]+)\)")


def _validate_callout(text: str, hits: list[Hit]) -> str | None:
    text = text.strip()
    if text.startswith("```"):
        text = "\n".join(l for l in text.splitlines() if not l.strip().startswith("```")).strip()
    m = _URL_RE.search(text)
    if not m:
        return None
    if m.group(1) not in {h.url for h in hits}:
        return None
    if not text.startswith("> [!"):
        return None
    return text


_OG_IMAGE_RE = re.compile(
    r'<meta\s+(?:property|name)=["\']og:image(?::secure_url)?["\']\s+content=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
_OG_IMAGE_RE_REVERSED = re.compile(
    r'<meta\s+content=["\']([^"\']+)["\']\s+(?:property|name)=["\']og:image(?::secure_url)?["\']',
    re.IGNORECASE,
)
_TWITTER_IMAGE_RE = re.compile(
    r'<meta\s+(?:property|name)=["\']twitter:image["\']\s+content=["\']([^"\']+)["\']',
    re.IGNORECASE,
)


# Image-URL substrings that almost always mean "decoration not content".
_IMG_JUNK = (
    "logo", "header", "footer", "banner", "icon", "favicon", "spacer",
    "blank", "pixel", "advert", "tracking", "sprite", "social", "share",
    "avatar", "thumb_small",
)
_IMG_TAG_RE = re.compile(r'<img\s+[^>]*src=["\']([^"\']+)["\']', re.IGNORECASE)


def _resolve_url(base: str, url: str) -> str:
    url = url.strip()
    if url.startswith("//"):
        return "https:" + url
    if url.startswith(("http://", "https://")):
        return url
    return urllib.parse.urljoin(base, url)


def _looks_like_content_image(url: str) -> bool:
    lower = url.lower()
    if any(j in lower for j in _IMG_JUNK):
        return False
    # Skip 1x1 trackers / data URIs.
    if lower.startswith("data:") or "1x1" in lower:
        return False
    # Skip very small images by URL hint (some sites use width markers).
    if re.search(r"[/_-](w|width|s|small)=?(?:\d{1,2}|x?\d{1,2})\D", lower):
        return False
    return True


def _wikipedia_topic_image(topic_name: str) -> str:
    """Return the lead-image URL of the Wikipedia article for `topic_name`,
    if one exists. Topic-relevant by definition (it's the article's
    representative image). Returns '' when Wikipedia has no entry or no
    thumbnail.

    Preferred over og:image scraping because og:image often returns the
    site's brand banner instead of an image of the actual object."""
    title = urllib.parse.quote(topic_name.replace(" ", "_"))
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "hermes-morning/1.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception:
        return ""
    if data.get("type") == "disambiguation":
        return ""
    # Prefer originalimage (full resolution), fall back to thumbnail.
    img = (data.get("originalimage") or {}).get("source") or ""
    if not img:
        img = (data.get("thumbnail") or {}).get("source") or ""
    return img


def _extract_image(url: str) -> str:
    """Fetch the source page and pick the best representative image.

    Priority:
      1. <meta property="og:image">  (modern social-preview convention)
      2. <meta name="twitter:image">
      3. First <img src=...> in the body whose URL doesn't look like
         logo/header/banner/icon/sprite/spacer junk.
    """
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "hermes-morning/1.0"})
        with urllib.request.urlopen(req, timeout=12) as r:
            raw = r.read(200 * 1024).decode("utf-8", errors="replace")
    except Exception as e:
        print(f"[curiosities] image fetch failed for {url}: {type(e).__name__}: {e}", file=sys.stderr)
        return ""

    # 1+2: og:image / twitter:image
    for pattern in (_OG_IMAGE_RE, _OG_IMAGE_RE_REVERSED, _TWITTER_IMAGE_RE):
        m = pattern.search(raw)
        if m:
            return _resolve_url(url, m.group(1))

    # 3: first non-junk <img> in body
    for m in _IMG_TAG_RE.finditer(raw):
        candidate = _resolve_url(url, m.group(1))
        if _looks_like_content_image(candidate):
            return candidate
    return ""


def _embed_image_in_callout(callout: str, source_url: str, topic_name: str = "") -> str:
    """Insert an image embed after the title line.

    Priority:
      1. Wikipedia's article-lead image for the topic — actually represents
         the object/person/place we're talking about
      2. Source page's og:image — usually accurate but sometimes a site banner

    No-op when nothing found — keeps callout shape stable."""
    img = ""
    if topic_name:
        img = _wikipedia_topic_image(topic_name)
    if not img:
        img = _extract_image(source_url)
    if not img:
        return callout
    lines = callout.splitlines()
    if not lines:
        return callout
    image_line = f"> ![|480]({img})"
    return "\n".join([lines[0], image_line] + lines[1:])


# -- Entry point ---------------------------------------------------------------

def _persist_to_note(body: str) -> None:
    """Insert today's curiosity into 🪅 Daily Curiosity.md and bump frontmatter."""
    path = vault.STREAM_NOTES["curiosity"]
    vault.insert_today_entry(path, body)
    vault.set_frontmatter_updated(path)


def run(*, prefer_model: str = "primary") -> str:
    """Return a single callout body (no header). Empty string if disabled."""
    topics = _load_topics()
    if not topics:
        return ""

    state = _load_state()
    topic = _pick_topic(topics, state)
    if not topic:
        return ""

    hits = _search(topic)
    if not hits:
        # Surface the topic anyway, without an external link.
        body = (
            f"> [!info]- Curiosity — {topic.name} · {topic.angle}\n"
            f"> You wrote down [[{topic.name}]] as something worth revisiting. "
            f"No fresh sources surfaced today — search it later when you have a moment."
        )
        state[topic.name] = vault.now_ist().date().isoformat()
        _save_state(state)
        return body

    try:
        raw = llm.chat(
            system=_SYSTEM,
            user=_build_user_prompt(topic, hits),
            max_tokens=900,
            temperature=0.4,
            prefer=prefer_model,
        )
    except llm.LLMError as e:
        return (
            f"> [!info]- Curiosity — {topic.name}\n"
            f"> (LLM framing failed: {e}.) Top hit: [{hits[0].title}]({hits[0].url})"
        )

    clean = _validate_callout(raw, hits)
    used_url = ""
    if clean is None:
        # Fallback: cite top hit verbatim, no LLM framing.
        used_url = hits[0].url
        clean = (
            f"> [!info]- Curiosity — {topic.name} · {topic.angle}\n"
            f"> {hits[0].snippet[:240]}\n"
            f"> [Source]({used_url})"
        )
    else:
        m = _URL_RE.search(clean)
        if m:
            used_url = m.group(1)

    # Visual hook: prefer Wikipedia's topic-relevant lead image; fall back
    # to source-page og:image. No-op on miss.
    if used_url:
        clean = _embed_image_in_callout(clean, used_url, topic.name)

    state[topic.name] = vault.now_ist().date().isoformat()
    _save_state(state)

    # Persist to the dedicated note so the dashboard heading has somewhere
    # real to link to (and you have a long-term archive of past curiosities).
    _persist_to_note(clean)

    # Self-extending: ask the LLM for 5 related topics. Validate via Wikipedia.
    # Validated ones append to the discovered list and become future picks.
    try:
        _extend_topic_pool(topic, prefer_model=prefer_model)
    except Exception as e:
        print(f"[curiosities] expansion failed (non-fatal): {type(e).__name__}: {e}", file=sys.stderr)

    return clean


_EXPAND_SYSTEM = (
    "You are extending the user's 'curiosities' topic list — a personal "
    "collection of historical/retro tech, industrial design, classic cars, "
    "computing history, audio gear, scientists, and similar things the user "
    "wants to be reminded about over time.\n"
    "\n"
    "Given a topic the user JUST surfaced, suggest 5 RELATED topics they'd "
    "likely enjoy reading about next. Categories: industrial design, classic "
    "cars, retro audio, computing history, mobile/phones, scientists, retro "
    "displays, peripherals, watches, gaming.\n"
    "\n"
    "RULES:\n"
    "- Each suggestion is something with a Wikipedia article — use the exact "
    "name that would resolve on Wikipedia.\n"
    "- Avoid generic categories ('keyboards'); be specific ('IBM Selectric').\n"
    "- Avoid duplicates of the seed topic itself.\n"
    "\n"
    "OUTPUT: 5 lines, one suggestion per line, format `name | angle` where "
    "angle is a short 3-5 word framing. No preamble, no numbering. Example:\n"
    "Olivetti Lettera 32 | portable typewriter design\n"
    "AKAI MPC 60 | sampler history"
)


def _wikipedia_exists(name: str) -> bool:
    """Cheap existence check via Wikipedia's REST summary endpoint."""
    import urllib.parse
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(name)}"
    req = urllib.request.Request(url, headers={"User-Agent": "hermes-morning/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read().decode("utf-8"))
            # Disambiguation pages count as existing but are noisy — accept anyway.
            return data.get("type") not in (None, "https://mediawiki.org/wiki/HyperSwitch/errors/not_found")
    except Exception:
        return False


def _extend_topic_pool(seed: Topic, *, prefer_model: str = "primary") -> int:
    """Ask LLM for 5 related topics, validate each against Wikipedia, append
    the validated ones to DISCOVERED_FILE. Returns count added."""
    try:
        raw = llm.chat(
            system=_EXPAND_SYSTEM,
            user=f"Seed topic: {seed.name}\nSeed angle: {seed.angle}\n\nGive me 5 related suggestions.",
            max_tokens=200,
            temperature=0.6,
            prefer=prefer_model,
        )
    except llm.LLMError:
        return 0

    suggestions: list[Topic] = []
    for line in raw.strip().splitlines():
        line = line.strip().lstrip("-*•1234567890. ")
        if not line:
            continue
        if "|" in line:
            name, angle = (s.strip() for s in line.split("|", 1))
        else:
            name, angle = line, "history"
        if not name:
            continue
        suggestions.append(Topic(name=name, angle=angle))
    suggestions = suggestions[:5]

    existing_names: set[str] = {t.name.lower() for t in _load_topics()}
    if DISCOVERED_FILE.exists():
        try:
            current_discovered = json.loads(DISCOVERED_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            current_discovered = []
    else:
        current_discovered = []

    added = 0
    for s in suggestions:
        if s.name.lower() in existing_names:
            continue
        if not _wikipedia_exists(s.name):
            print(f"[curiosities] Wikipedia validation failed for {s.name!r}, skipping", file=sys.stderr)
            continue
        current_discovered.append({"name": s.name, "angle": s.angle, "added": vault.now_ist().date().isoformat(), "seed": seed.name})
        existing_names.add(s.name.lower())
        added += 1

    if added:
        tmp = DISCOVERED_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(current_discovered, indent=2), encoding="utf-8")
        tmp.replace(DISCOVERED_FILE)
        print(f"[curiosities] extended pool by {added} (total discovered: {len(current_discovered)})", file=sys.stderr)
    return added


def daily_run(*, prefer_model: str = "primary") -> str:
    """Same as run() but always fires (not gated on empty releases). Used as
    a standalone daily stream alongside news/papers/tech/etc."""
    return run(prefer_model=prefer_model)


if __name__ == "__main__":
    print(run())
