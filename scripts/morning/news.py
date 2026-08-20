"""Daily News stream — RSS-first, no LLM.

For each topic, fetch its configured RSS feeds (and optionally DDGS as a
fallback when no RSS is configured or when RSS was empty). The publisher
wrote a title, a description, a publication date, and often supplied a
hero image via `<enclosure>` or `<media:content>` — that's already a
finished callout. We just render it.

Design choices:
  - **No LLM in the normal path.** Zero chance of URL hallucination, zero
    'no qualifying story' rejections, wall-time seconds not minutes.
  - **Trust the publisher.** RSS <description> is the summary. If the
    publisher wrote a bad summary, that's editorial, not our problem.
  - **Deterministic order.** Most recent first (by <pubDate>), tie-break
    by feed order. No LLM 'curation' subjectivity to debug.
  - **Anti-fabrication trivial.** We only render what came in. No prompt
    engineering, no validators, no cross-checks needed.

Topics live in `~/.hermes/morning-config.yaml` under `news.topics`.
Defaults in `DEFAULT_TOPICS` below."""
from __future__ import annotations

import datetime
import html as html_mod
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

import feedparser

from . import config, feed_health, images, vault

try:
    from ddgs import DDGS
except ImportError:  # pragma: no cover
    DDGS = None  # type: ignore


@dataclass
class Topic:
    name: str
    label: str
    queries: list[str]
    site_hints: list[str]
    rss: list[str]
    picks: int = 1


# Default topics — full list of 13 verticals + international. Override via
# config.yaml's `news.topics` if you want to drop, reorder, or add new ones.
DEFAULT_TOPICS: list[dict[str, Any]] = [
    # 1. Hyperlocal
    {
        "name": "Local", "label": "Local — Pune / PCMC", "picks": 1,
        "queries": [
            "PCMC news today", "Pune civic body news today",
            "Pune Pimpri Chinchwad transit infrastructure news today",
        ],
        "site_hints": ["punemirror.com", "hindustantimes.com", "timesofindia.indiatimes.com", "indianexpress.com"],
        "rss": [],
    },
    # 2. India national
    {
        "name": "India", "label": "India", "picks": 1,
        "queries": [
            "India national news today", "India economy politics news today",
            "India major incident news today",
        ],
        "site_hints": ["thehindu.com", "indianexpress.com", "livemint.com", "bloombergquint.com"],
        "rss": ["https://www.thehindu.com/news/national/feeder/default.rss"],
    },
    # 3. AI
    {
        "name": "AI", "label": "AI — model + research", "picks": 2,
        "queries": [
            "AI model release announcement today", "Anthropic OpenAI DeepMind news today",
            "open source LLM release today",
        ],
        "site_hints": ["anthropic.com", "openai.com", "deepmind.google", "huggingface.co", "ai.meta.com", "qwenlm.github.io"],
        "rss": [],
    },
    # 4. Big Tech (global) — Reuters/Bloomberg-tier + trade press.
    # Picks 2 (was 1) to give this section real weight — tech is the
    # user's daily beat and the previous single-item cap was starving it.
    {
        "name": "Tech", "label": "Tech — global", "picks": 2,
        "queries": [
            "major tech company news today",
            "tech product launch announcement today",
            "tech security breach M&A regulation today",
            "AI chip GPU foundry news today",
            "developer tools release news today",
        ],
        "site_hints": [
            # Wire services + business press
            "reuters.com", "bloomberg.com", "ft.com", "wsj.com",
            # Consumer tech press
            "theverge.com", "arstechnica.com", "wired.com",
            "engadget.com", "techcrunch.com",
            # Hardware / benchmarks trade press
            "tomshardware.com", "anandtech.com", "servethehome.com",
            "hothardware.com",
            # UK / EU tech press
            "theregister.com", "sifted.eu", "techeu.com",
            # International tech reporting
            "restofworld.org", "rest-of-world.com",
            "protocol.com",   # tech policy
            "theinformation.com",
        ],
        "rss": [
            "https://www.theverge.com/rss/index.xml",
            "https://feeds.arstechnica.com/arstechnica/index",
            "https://www.wired.com/feed/rss",
            "https://www.engadget.com/rss.xml",
            "https://techcrunch.com/feed/",
            "https://www.tomshardware.com/feeds/all",
            "https://www.theregister.com/headlines.atom",
            "https://restofworld.org/feed/latest/",
        ],
    },
    # 5. America — deep-context tech analysis (long-form US-only)
    {
        "name": "America", "label": "America — deep tech", "picks": 1,
        "queries": [
            "Ars Technica news today", "The Information tech analysis today",
            "Stratechery analysis today", "Wired technology today",
        ],
        "site_hints": ["arstechnica.com", "wired.com", "theinformation.com", "stratechery.com", "nytimes.com", "washingtonpost.com"],
        "rss": [
            "https://feeds.arstechnica.com/arstechnica/index",
            "https://www.wired.com/feed/rss",
        ],
    },
    # 6. EU / regulation
    {
        "name": "EU", "label": "EU — regulation + startups", "picks": 1,
        "queries": [
            "EU tech regulation news today", "European startup funding announcement today",
            "Sifted EU tech news today",
        ],
        "site_hints": ["sifted.eu", "euractiv.com", "politico.eu", "eubusiness.com", "lemonde.fr"],
        "rss": [
            "https://sifted.eu/feed",
        ],
    },
    # 7. Japan — tech & society
    {
        "name": "Japan", "label": "Japan — tech & society", "picks": 1,
        "queries": [
            "Nikkei Asia tech news today", "Japan technology news today",
            "Japanese AI startup news today",
        ],
        "site_hints": ["asia.nikkei.com", "japantimes.co.jp", "itmedia.co.jp", "techinasia.com", "japantoday.com"],
        # japantimes.co.jp 403s our UA. Use Asia Nikkei + ITmedia + Japan Today instead.
        "rss": [
            "https://asia.nikkei.com/rss/feed/nar",
            "https://rss.itmedia.co.jp/rss/2.0/itmedia_all.xml",
            "https://www.japantimes.co.jp/feed/",
        ],
    },
    # 7a. China — tech & science (intentionally narrower than Japan/EU; not
    # political coverage, just tech/science movements)
    {
        "name": "China", "label": "China — tech & science", "picks": 1,
        "queries": [
            "China technology news today",
            "China semiconductor research news today",
            "Chinese AI model release today",
            "China science breakthrough today",
        ],
        "site_hints": ["scmp.com", "caixinglobal.com", "pandaily.com", "sixthtone.com", "technode.com", "asia.nikkei.com"],
        "rss": [
            "https://pandaily.com/feed",
            "https://technode.com/feed/",
        ],
    },
    # 7b. Korea — tech & science (Samsung/LG/Hynix/Naver/Kakao + research)
    {
        "name": "Korea", "label": "Korea — tech & science", "picks": 1,
        "queries": [
            "South Korea technology news today",
            "Samsung LG SK Hynix news today",
            "Korean AI startup news today",
            "KAIST Seoul National University research today",
        ],
        "site_hints": ["koreaherald.com", "koreatimes.co.kr", "en.yna.co.kr", "asia.nikkei.com", "technode.com"],
        "rss": [
            "https://www.koreaherald.com/rss/feed.xml",
            "https://en.yna.co.kr/RSS/news.xml",
        ],
    },
    # 8. Macro / markets
    {
        "name": "Macro", "label": "Macro — India + global", "picks": 1,
        "queries": [
            "Nifty Sensex India markets today", "USD INR RBI policy today",
            "oil gold crypto market news today",
        ],
        "site_hints": ["livemint.com", "reuters.com", "bloomberg.com", "moneycontrol.com"],
        "rss": ["https://www.livemint.com/rss/markets"],
    },
    # 9. World
    {
        "name": "World", "label": "World — geopolitics", "picks": 1,
        "queries": [
            "world geopolitics news today", "international conflict diplomacy news today",
            "global disaster news today",
        ],
        "site_hints": ["reuters.com", "apnews.com", "aljazeera.com"],
        "rss": ["https://feeds.bbci.co.uk/news/world/rss.xml"],
    },
    # 10. Physics / Quantum (separate stream items still in Papers, but news goes here)
    {
        "name": "Physics", "label": "Physics / Quantum", "picks": 1,
        "queries": [
            "quantum computing news announcement today",
            "IBM Google Quantinuum quantum hardware milestone today",
            "condensed matter physics breakthrough today",
            "National Quantum Mission quantum policy news today",
            "Nature Physics paper release today",
        ],
        "site_hints": [
            "ibm.com", "research.google", "quantinuum.com", "ionq.com",
            "psiquantum.com", "atomcomputing.com",
            "quantamagazine.org",              # deep physics longform
            "spectrum.ieee.org", "physicsworld.com",
            "nature.com/nphys",                # Nature Physics
            "aps.org",                          # American Physical Society
            "phys.org",
            "sciencedaily.com/news/matter_energy",
        ],
        "rss": [
            "https://www.quantamagazine.org/feed/",
            "https://physicsworld.com/feed/",
            "https://phys.org/rss-feed/physics-news/",
        ],
    },
    # 11. Climate / energy
    {
        "name": "Climate", "label": "Climate + energy", "picks": 1,
        "queries": [
            "climate policy news today", "renewable energy announcement today",
            "carbon emissions report today",
        ],
        "site_hints": ["climatewire.com", "carbonbrief.org", "reuters.com", "iea.org"],
        "rss": ["https://www.carbonbrief.org/feed/"],
    },
    # 12. Health / biotech
    {
        "name": "Health", "label": "Health + biotech", "picks": 1,
        "queries": [
            "biotech FDA approval news today", "clinical trial result news today",
            "India health policy news today",
        ],
        "site_hints": ["statnews.com", "endpts.com", "nature.com", "thelancet.com"],
        "rss": [
            "https://www.statnews.com/feed/",
        ],
    },
    # 13. Science (broad, non-quantum)
    {
        "name": "Science", "label": "Science — broad", "picks": 1,
        "queries": [
            "Nature journal news today",
            "Science magazine news today",
            "research breakthrough announcement today",
            "Quanta Magazine article today",
            "big science discovery this week",
        ],
        "site_hints": [
            "nature.com", "science.org", "scientificamerican.com",
            "newscientist.com", "quantamagazine.org",
            "eurekalert.org",           # embargo-lifted press releases
            "aeon.co/science", "nautil.us",
            "arstechnica.com/science",
            "smithsonianmag.com/smart-news",
            "phys.org", "sciencedaily.com",
            "spectrum.ieee.org",
        ],
        "rss": [
            "https://www.nature.com/nature.rss",
            "https://www.quantamagazine.org/feed/",
            "https://feeds.arstechnica.com/arstechnica/science",
            "https://www.smithsonianmag.com/rss/latest_articles/",
        ],
    },
    # 14. Infosec — breaches, malware, supply-chain compromise, CVEs.
    # Picks 2 here because the user explicitly wants deeper security coverage
    # (AUR compromise, npm/pypi supply-chain attacks, ransomware incidents).
    {
        "name": "Infosec", "label": "Infosec — breaches + supply chain", "picks": 2,
        "queries": [
            "security breach disclosure today",
            "malware supply chain compromise today",
            "CVE vulnerability disclosed today",
            "ransomware attack incident today",
        ],
        "site_hints": [
            "bleepingcomputer.com", "thehackernews.com", "krebsonsecurity.com",
            "schneier.com", "arstechnica.com", "securityweek.com",
            "darkreading.com", "therecord.media",
        ],
        "rss": [
            "https://www.bleepingcomputer.com/feed/",
            "https://feeds.feedburner.com/TheHackersNews",
            "https://krebsonsecurity.com/feed/",
            "https://www.schneier.com/feed/atom/",
            "https://arstechnica.com/security/feed/",
        ],
    },
    # 15. Linux / open-source ecosystem — kernel releases, distro news,
    # package-repo compromises (AUR, Debian, etc.), notable upstream changes.
    {
        "name": "Linux", "label": "Linux + open-source", "picks": 2,
        "queries": [
            "Linux kernel release news today",
            "Arch Linux AUR Debian Ubuntu Fedora news today",
            "open source supply chain compromise today",
            "GNOME KDE Wayland release news today",
        ],
        "site_hints": [
            "phoronix.com", "lwn.net", "opensource.com", "lwn.net",
            "kernel.org", "archlinux.org", "debian.org", "ubuntu.com",
            "fedoramagazine.org", "linuxiac.com",
        ],
        "rss": [
            "https://www.phoronix.com/rss.php",
            "https://lwn.net/headlines/rss",
            "https://9to5linux.com/feed",
            "https://fedoramagazine.org/feed/",
        ],
    },
    # 16. Ideas / Longform — for the days you want to read something that
    # isn't news at all. Long-form essays, literary journals, review-of-books
    # pieces. This is the biggest horizon-expander in the digest.
    {
        "name": "Ideas", "label": "Ideas + longform essays", "picks": 2,
        "queries": [
            "long form essay ideas today",
            "long read magazine essay this week",
            "review of books essay today",
            "philosophy essay Aeon today",
        ],
        "site_hints": [
            "aeon.co", "nautil.us", "longreads.com",
            "lrb.co.uk",              # London Review of Books
            "nybooks.com",            # New York Review of Books
            "lithub.com", "publicbooks.org",
            "theguardian.com/news/series/the-long-read",
            "theatlantic.com", "harpers.org", "newyorker.com",
            "granta.com", "theparisreview.org",
            "noemamag.com",           # Berggruen — big-picture ideas
            "marginalrevolution.com", "astralcodexten.substack.com",
        ],
        "rss": [
            "https://aeon.co/feed.rss",
            "https://nautil.us/feed/",
            "https://longreads.com/feed/",
            "https://www.lrb.co.uk/feeds/rss",
            "https://www.nybooks.com/feed/",
            "https://lithub.com/feed/",
            "https://noemamag.com/feed/",
            "https://marginalrevolution.com/feed",
        ],
    },
    # 17. Culture — film, music, art, photography criticism.
    {
        "name": "Culture", "label": "Culture — film / music / art", "picks": 1,
        "queries": [
            "film review criticism today",
            "art exhibition review today",
            "music album review today",
            "photography essay today",
        ],
        "site_hints": [
            "sightandsoundmagazine.com", "criterion.com",
            "indiewire.com", "filmcomment.com",
            "pitchfork.com", "npr.org/music",
            "artforum.com", "frieze.com", "e-flux.com",
            "aperture.org", "magnumphotos.com", "lensculture.com",
            "theringer.com", "theatlantic.com/culture",
            "thebaffler.com",
        ],
        "rss": [
            "https://letterboxd.com/criterion/rss/",
            "https://pitchfork.com/feed/feed-album-reviews/rss",
            "https://hyperallergic.com/feed/",
            "https://www.e-flux.com/rss",
            "https://aperture.org/feed/",
            "https://thebaffler.com/feed",
        ],
    },
    # 18. Design + Architecture — the visual/built-environment horizon.
    {
        "name": "Design", "label": "Design + architecture", "picks": 1,
        "queries": [
            "architecture project completed today",
            "industrial product design launch today",
            "design magazine article today",
        ],
        "site_hints": [
            "dezeen.com", "archdaily.com",
            "wallpaper.com", "domusweb.it",
            "designmilk.com", "itsnicethat.com",
            "designboom.com", "core77.com",
            "curbed.com", "architecturalrecord.com",
            "detail-online.com",
        ],
        "rss": [
            "https://www.dezeen.com/feed/",
            "https://www.archdaily.com/feed",
            "https://www.designboom.com/feed/",
            "https://feeds.feedburner.com/itsnicethat",
            "https://www.wallpaper.com/rss",
        ],
    },
]


def _load_topics() -> list[Topic]:
    raw = config.get("news", "topics", default=DEFAULT_TOPICS)
    out: list[Topic] = []
    for entry in raw:
        out.append(Topic(
            name=entry.get("name", "?"),
            label=entry.get("label", entry.get("name", "?")),
            queries=entry.get("queries") or [],
            site_hints=entry.get("site_hints") or [],
            rss=entry.get("rss") or [],
            picks=int(entry.get("picks") or 1),
        ))
    return out


@dataclass
class SearchHit:
    title: str
    url: str
    snippet: str                                # publisher's summary (RSS <description> or DDGS body)
    source: str                                 # registered domain, lowercased
    origin: str                                 # "rss" or "ddgs"
    pub_date: datetime.datetime | None = None   # RSS <pubDate>/<updated>; None for DDGS
    image_url: str = ""                         # RSS <enclosure>/<media:content>; empty means "resolve via images.embed at render"


def _domain(url: str) -> str:
    m = re.match(r"https?://([^/]+)/?", url)
    if not m:
        return ""
    host = m.group(1).lower()
    return host[4:] if host.startswith("www.") else host


def _search_ddgs(query: str, max_results: int = 5) -> list[SearchHit]:
    if DDGS is None:
        return []
    out: list[SearchHit] = []
    try:
        with DDGS() as d:
            for r in d.text(query, max_results=max_results, region="in-en", safesearch="off"):
                url = r.get("href") or r.get("url") or ""
                if not url:
                    continue
                out.append(SearchHit(
                    title=(r.get("title") or "").strip(),
                    url=url,
                    snippet=(r.get("body") or "").strip(),
                    source=_domain(url),
                    origin="ddgs",
                ))
    except Exception as e:
        print(f"[news] ddgs failure for {query!r}: {type(e).__name__}: {e}", file=sys.stderr)
    return out


# Browser-like UA — many outlets 403 our old "hermes-morning/1.0" string.
# Freshness window for RSS entries. 48h was too tight for a Sunday morning
# briefing: weekly-cadence outlets (carbonbrief, sifted) and weekend-quiet
# beats (statnews, EU startup press) routinely produce nothing in a 48-hour
# window over Sat/Sun. 96h covers weekends without dredging up genuinely
# stale news; the callout header shows age when > 24h so the reader can
# see freshness at a glance.
MAX_AGE_HOURS = config.get("news", "max_age_hours", default=96)


_RSS_UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
           "(KHTML, like Gecko) Firefox/128.0")


def _fetch_rss_once(url: str, timeout: float = 12.0) -> bytes | None:
    req = urllib.request.Request(url, headers={
        "User-Agent": _RSS_UA,
        "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, text/xml;q=0.9",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _fetch_rss(url: str, max_items: int = 6) -> list[SearchHit]:
    """Fetch RSS with retry + circuit-breaker.

    - Skip entirely if feed_health has flagged this URL as long-dead.
    - Retry once on 429/500/502/503 with a 3s jitter delay.
    - Record success/failure so the health tracker learns."""
    out: list[SearchHit] = []
    if feed_health.should_skip(url):
        print(f"[news] skipping long-dead feed {url}", file=sys.stderr)
        return out

    raw: bytes | None = None
    last_reason = ""
    for attempt in (1, 2):
        try:
            raw = _fetch_rss_once(url)
            break
        except urllib.error.HTTPError as e:
            last_reason = f"HTTPError {e.code}"
            if e.code in (429, 500, 502, 503) and attempt == 1:
                import time
                time.sleep(3)
                continue
            break
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last_reason = f"{type(e).__name__}: {e}"
            if attempt == 1:
                import time
                time.sleep(1)
                continue
            break

    if raw is None:
        print(f"[news] RSS fetch failed {url}: {last_reason}", file=sys.stderr)
        feed_health.record_failure(url, last_reason)
        return out
    feed_health.record_success(url)
    parsed = feedparser.parse(raw)
    # Only entries within the freshness window (MAX_AGE_HOURS, default 96h
    # to survive weekend-quiet outlets). Newer entries win in the topic sort.
    cutoff = datetime.datetime.now() - datetime.timedelta(hours=MAX_AGE_HOURS)
    for e in parsed.entries[:max_items * 2]:
        link = e.get("link", "").strip()
        if not link:
            continue
        published = None
        for k in ("published_parsed", "updated_parsed"):
            if e.get(k):
                published = datetime.datetime(*e[k][:6])
                break
        if published and published < cutoff:
            continue

        # Image extraction — try, in order, media_content / media_thumbnail
        # / enclosures. This catches ~80% of RSS-embedded hero images before
        # we fall back to images.resolve(url) at render time.
        image_url = ""
        for mc in (e.get("media_content") or []):
            if mc.get("url"):
                image_url = mc["url"]; break
        if not image_url:
            for mt in (e.get("media_thumbnail") or []):
                if mt.get("url"):
                    image_url = mt["url"]; break
        if not image_url:
            for enc in (e.get("enclosures") or []):
                if (enc.get("type") or "").startswith("image/") and enc.get("href"):
                    image_url = enc["href"]; break

        # RSS descriptions come in wildly different lengths. Clean HTML,
        # unescape entities, collapse whitespace. Don't truncate here — the
        # renderer decides how much to show.
        raw_desc = e.get("summary") or e.get("description") or ""
        clean = re.sub(r"<[^>]+>", " ", raw_desc)
        clean = html_mod.unescape(clean)
        clean = re.sub(r"\s+", " ", clean).strip()

        out.append(SearchHit(
            title=re.sub(r"\s+", " ", e.get("title") or "").strip(),
            url=link,
            snippet=clean,
            source=_domain(link),
            origin="rss",
            pub_date=published,
            image_url=image_url,
        ))
        if len(out) >= max_items:
            break
    return out


# --- Collection --------------------------------------------------------------


def _collect_for_topic(t: Topic) -> list[SearchHit]:
    """RSS-first collection.

    1. Fetch all configured RSS feeds for the topic in parallel.
    2. If the pool has fewer than picks*3 hits, top up with DDGS.
    3. Dedupe by URL. Return the whole pool — caller sorts & picks."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    seen: dict[str, SearchHit] = {}

    if t.rss:
        with ThreadPoolExecutor(max_workers=min(6, len(t.rss))) as pool:
            futures = {pool.submit(_fetch_rss, feed, 8): feed for feed in t.rss}
            for fut in as_completed(futures):
                try:
                    for hit in fut.result():
                        if hit.url not in seen:
                            seen[hit.url] = hit
                except Exception as e:
                    print(f"[news] rss fetch raised {type(e).__name__}: {e}", file=sys.stderr)

    # DDGS top-up. Only run if RSS was thin — DDGS is slower + noisier.
    need_topup = len(seen) < max(t.picks * 3, 4)
    if need_topup and t.queries:
        for q in t.queries[:3]:  # cap: 3 queries max per topic
            for hit in _search_ddgs(q):
                if hit.url not in seen:
                    seen[hit.url] = hit
            if len(seen) >= t.picks * 4:
                break

    return list(seen.values())


# --- Selection (deterministic) -----------------------------------------------


def _select(hits: list[SearchHit], topic: Topic) -> list[SearchHit]:
    """Deterministic selection. No LLM.

    Priority order:
      1. RSS hits from a domain in site_hints (publisher we trust for this topic)
      2. RSS hits from other domains
      3. DDGS hits from a site_hint domain
      4. DDGS hits from any domain
    Within each bucket: newest pub_date first (DDGS hits sort last since they
    have no pub_date). Tie-break by title length descending (substance proxy).

    Then dedupe by domain — no more than 1 story per publisher per topic. This
    prevents e.g. three consecutive Ars Technica callouts in the Tech topic."""

    def _bucket(h: SearchHit) -> int:
        is_hint = h.source in topic.site_hints
        if h.origin == "rss" and is_hint: return 0
        if h.origin == "rss": return 1
        if is_hint: return 2
        return 3

    def _key(h: SearchHit) -> tuple:
        # Sort key: bucket asc, then pub_date desc (missing = epoch),
        # then title length desc.
        pd = h.pub_date or datetime.datetime(1970, 1, 1)
        return (_bucket(h), -pd.timestamp(), -len(h.title))

    ranked = sorted(hits, key=_key)

    # Per-domain dedupe within the topic — at most 1 story per source.
    picked: list[SearchHit] = []
    seen_domains: set[str] = set()
    for h in ranked:
        if h.source in seen_domains:
            continue
        seen_domains.add(h.source)
        picked.append(h)
        if len(picked) >= topic.picks:
            break
    return picked


# --- Rendering ---------------------------------------------------------------


_WIKILINK_KEYWORDS = re.compile(
    r"\b(OpenAI|Anthropic|Google|Meta|Microsoft|Apple|Nvidia|IBM|"
    r"Reuters|Bloomberg|Nature|Science|IEEE|MIT|Stanford|CERN|NASA|ESA|"
    r"PCMC|PMC|IIT Madras|Pune|Mumbai|Delhi|Bangalore|Chennai|"
    r"European Commission|European Union|WHO|UN|G20|OPEC|"
    r"Ars Technica|The Verge|Wired|TechCrunch|The Register|Rest of World|"
    r"Financial Times|Guardian|WSJ|New York Times|BBC|Al Jazeera|"
    r"Quanta Magazine|Aeon|Nautilus)\b"
)


def _wikilink_first_mention(text: str) -> str:
    """Wikilink the FIRST occurrence of each known term, once per callout.
    Keeps the graph view interesting without over-linking."""
    seen: set[str] = set()

    def _sub(m: re.Match) -> str:
        term = m.group(0)
        key = term.lower()
        if key in seen:
            return term
        seen.add(key)
        return f"[[{term}]]"

    return _WIKILINK_KEYWORDS.sub(_sub, text)


def _truncate_prose(text: str, max_chars: int = 480) -> str:
    """Truncate at sentence boundary within max_chars. Never mid-word."""
    text = text.strip()
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    # Prefer trailing period/question/exclamation.
    for end_char in (". ", "? ", "! "):
        idx = cut.rfind(end_char)
        if idx > max_chars * 0.6:
            return cut[:idx + 1].rstrip()
    # Fall back to last space, add ellipsis.
    idx = cut.rfind(" ")
    return (cut[:idx] if idx > 0 else cut).rstrip(",.;: ") + "…"


def _render_hit(hit: SearchHit, topic: Topic) -> str:
    """Deterministic callout render. Publisher content, verbatim (light clean)."""
    # Title line — cap at ~90 chars to keep the callout head one line
    title = hit.title.strip()
    if len(title) > 92:
        title = title[:89].rstrip() + "…"
    callout_type = "note"

    # Age tag — only shown when the entry is > 24h old, so the reader can see
    # at a glance that "no fresh news today" isn't hiding a stale item.
    age_tag = ""
    if hit.pub_date:
        hours = (datetime.datetime.now() - hit.pub_date).total_seconds() / 3600
        if hours >= 24:
            days = int(hours // 24)
            age_tag = f" · {days}d ago" if days >= 1 else ""

    header = f"> [!{callout_type}]- {topic.label}: {title} ({hit.source}){age_tag}"

    # Image line — prefer the URL the RSS gave us; otherwise let images.embed
    # try to fetch an OG image from the article page (cached).
    img_url = hit.image_url or (images.resolve(hit.url) or "")
    image_line = f"> ![|640]({img_url})" if img_url else ""

    # Body — publisher's own description, cleaned + truncated + wikilinked
    body_raw = hit.snippet or "(No description provided in feed.)"
    body_text = _truncate_prose(body_raw, max_chars=480)
    body_text = _wikilink_first_mention(body_text)
    body_line = f"> {body_text}"

    # Source line
    src_line = f"> [Source]({hit.url})"

    lines = [header]
    if image_line:
        lines.append(image_line)
    lines.extend(["", body_line, "", src_line])
    return "\n".join(lines)


def _warning_no_content(t: Topic) -> str:
    return (
        f"> [!warning] {t.label}: no fresh items in the last {MAX_AGE_HOURS}h\n"
        f"> {len(t.rss)} RSS feed(s) + {len(t.queries)} DDGS query "
        f"variant(s) returned nothing recent."
    )


# --- Run ----------------------------------------------------------------------


def run(*, prefer_model: str = "primary") -> str:
    """Produce today's entry body for `📰 Daily News.md` and insert it.

    The prefer_model arg is accepted for signature compat with the old LLM-
    based flow, but ignored — no LLM calls happen in the normal path."""
    topics = _load_topics()
    blocks: list[str] = []
    for t in topics:
        hits = _collect_for_topic(t)
        if not hits:
            blocks.append(_warning_no_content(t))
            continue
        picks = _select(hits, t)
        if not picks:
            blocks.append(_warning_no_content(t))
            continue
        for hit in picks:
            blocks.append(_render_hit(hit, t))

    body = "\n\n".join(blocks) if blocks else (
        "> [!warning] News stream produced no items today."
    )
    vault.insert_today_entry(vault.STREAM_NOTES["news"], body)
    vault.set_frontmatter_updated(vault.STREAM_NOTES["news"])
    return body


# Export TOPICS for backward compat.
TOPICS = _load_topics()
