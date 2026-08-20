"""Daily Tech stream — deterministic, no LLM.

Aggregates from four sources:
  - Hacker News: top + best (weekly best-of) + Show HN
  - Lobsters — small, invite-only, less enterprise-SaaS noise than HN
  - A configurable set of subreddits (LocalLLaMA, selfhosted, rust,
    golang, homelab, kubernetes, devops, neovim, emacs, etc.)

Score-filter, dedupe by URL, drop big-tech corp announcements + listicles,
sort by score, apply per-source diversity cap, render as `[!tech]-` callouts
with title + points/comments metadata + Source link + Discussion link.

**No LLM.** The item's title is the content; the reader clicks through if
interested. This removes URL hallucination risk entirely and cuts the
stream from ~10 minutes to ~30 seconds."""
from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any

import feedparser

from . import config, feed_health, images, vault


HN_TOP = "https://hacker-news.firebaseio.com/v0/topstories.json"
HN_BEST = "https://hacker-news.firebaseio.com/v0/beststories.json"
HN_SHOW = "https://hacker-news.firebaseio.com/v0/showstories.json"
HN_ITEM = "https://hacker-news.firebaseio.com/v0/item/{id}.json"
HN_DISCUSS = "https://news.ycombinator.com/item?id={id}"

LOBSTERS_RSS = "https://lobste.rs/rss"
LOBSTERS_ITEM = "https://lobste.rs/s/{id}"

# High-signal + on-topic-for-Sarang subs. Skew: infra, systems, low-level,
# local LLM, self-hosting, editor culture. Deliberately no r/technology
# (mostly news reposts) or r/programming (too broad, lots of noise).
DEFAULT_SUBREDDITS = [
    "LocalLLaMA", "selfhosted", "MachineLearning",
    "rust", "golang", "zig",
    "homelab", "kubernetes", "devops", "docker",
    "opensource", "commandline", "linux",
    "neovim", "emacs",
    "dataengineering", "ExperiencedDevs",
]
SUBREDDITS = config.get("tech", "subreddits", default=DEFAULT_SUBREDDITS)
# Reddit's .json endpoint is now 403 without OAuth. Use the RSS feed which
# still serves anonymous traffic. Trade-off: RSS doesn't expose `score` per
# entry, so we drop the numeric score filter for Reddit and rely on the
# `top?t=day` ordering (already Reddit-curated by score).
# old.reddit.com is significantly less aggressive about rate-limiting the
# .rss endpoint than the modern www hostname. Keep the modern host as a
# secondary fallback in case old.reddit.com goes away or gets locked down.
REDDIT_TOP_OLD = "https://old.reddit.com/r/{sub}/top.rss?t=day&limit=20"
REDDIT_TOP_WWW = "https://www.reddit.com/r/{sub}/top.rss?t=day&limit=20"
REDDIT_TOP = REDDIT_TOP_OLD  # kept for backward compat if imported

HN_MIN_SCORE = config.get("tech", "hn_min_score", default=80)
HN_SHOW_MIN_SCORE = config.get("tech", "hn_show_min_score", default=40)
HN_BEST_MIN_SCORE = config.get("tech", "hn_best_min_score", default=200)  # weekly best — bar higher

# Pool budget after dedup/filter — 40 was too small for the wider intake.
POOL_CAP = config.get("tech", "pool_cap", default=60)

UA = "hermes-morning/1.0 (hermes-morning@example.com)"
# Reddit rate-limits by UA and bot-fingerprint aggressively; use a real
# browser string for the reddit-specific fetch path.
BROWSER_UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Firefox/128.0")


@dataclass
class TechItem:
    source: str        # "HN" / "Show HN" / "Reddit"
    sub: str           # subreddit name (Reddit only) or ""
    title: str
    url: str           # the external URL the item points at
    discuss_url: str   # HN thread or Reddit permalink
    score: int
    comments: int


def _fetch_json(url: str, timeout: float = 15.0) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _safe_fetch_json(url: str) -> Any:
    try:
        return _fetch_json(url)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as e:
        print(f"[tech] fetch failed {url}: {type(e).__name__}: {e}", file=sys.stderr)
        return None


_SECURITY_TELLS = re.compile(
    r"\b(cve-?\d|vulnerability|exploit|backdoor|malware|ransomware|supply[- ]chain|"
    r"compromised|breach|0[- ]?day|zero[- ]day|rce|sql injection|xss|"
    r"phishing|credential|stolen|aur|npm packages|pypi packages)\b",
    re.IGNORECASE,
)


def _fetch_hn(list_url: str, source: str, min_score: int, limit: int = 50) -> list[TechItem]:
    ids = _safe_fetch_json(list_url) or []
    ids = ids[:limit]
    out: list[TechItem] = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_safe_fetch_json, HN_ITEM.format(id=i)): i for i in ids}
        for fut in as_completed(futures):
            item = fut.result()
            if not item or item.get("dead") or item.get("deleted"):
                continue
            score = int(item.get("score", 0))
            title = item.get("title", "").strip()
            # Security stories get a relaxed score floor so a breach disclosure
            # at 35 points (still under the 80-point cutoff) doesn't get missed.
            is_security = bool(_SECURITY_TELLS.search(title))
            effective_min = max(20, min_score // 3) if is_security else min_score
            if score < effective_min:
                continue
            url = item.get("url") or HN_DISCUSS.format(id=item["id"])
            out.append(TechItem(
                source=source,
                sub="",
                title=title,
                url=url,
                discuss_url=HN_DISCUSS.format(id=item["id"]),
                score=score,
                comments=int(item.get("descendants", 0)),
            ))
    return out


_LOBSTERS_COMMENT_RE = re.compile(r"lobste\.rs/s/([a-z0-9]+)/")


def _fetch_lobsters(limit: int = 25) -> list[TechItem]:
    """Pull Lobsters' front page via RSS. Lobsters is small, invite-only,
    and heavily moderated — much less enterprise-SaaS noise than HN. The
    RSS gives us the external URL directly in <link> and a permalink to
    the comment thread in <guid> / <comments>."""
    try:
        req = urllib.request.Request(LOBSTERS_RSS, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
        print(f"[tech] lobsters fetch failed: {type(e).__name__}: {e}", file=sys.stderr)
        return []
    parsed = feedparser.parse(raw)
    out: list[TechItem] = []
    for entry in parsed.entries[:limit]:
        external = (entry.get("link") or "").strip()
        title = (entry.get("title") or "").strip()
        if not external or not title:
            continue
        # Lobsters comment thread URL is in `comments` (RSS 2.0) or `id`.
        discuss = entry.get("comments") or entry.get("id") or ""
        if not discuss:
            # Fall back to constructing from a lobste.rs/s/XXX link in id/guid
            m = _LOBSTERS_COMMENT_RE.search(str(entry))
            if m:
                discuss = LOBSTERS_ITEM.format(id=m.group(1))
        # If the entry's external link IS already a lobste.rs self-post,
        # discussion == external — that's fine.
        if not discuss:
            discuss = external
        out.append(TechItem(
            source="Lobsters",
            sub="",
            title=title,
            url=external,
            discuss_url=discuss,
            score=0,  # RSS doesn't expose the vote count; ordering is by recency
            comments=0,
        ))
    return out


_REDDIT_OUTBOUND = re.compile(r'\[link\]\(([^)]+)\)')


def _reddit_fetch_once(url: str) -> bytes:
    req = urllib.request.Request(url, headers={
        "User-Agent": BROWSER_UA,
        "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9",
    })
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read()


def _fetch_reddit(sub: str) -> list[TechItem]:
    """Fetch top of r/{sub} with resilience:
      - Try old.reddit.com first (less aggressive rate limiting).
      - On 429, wait 30s and try www.reddit.com as fallback host.
      - On repeated failure, feed_health records + eventually skips."""
    import time
    old_url = REDDIT_TOP_OLD.format(sub=sub)
    new_url = REDDIT_TOP_WWW.format(sub=sub)
    fh_key = f"reddit:{sub}"
    if feed_health.should_skip(fh_key):
        print(f"[tech] skipping long-dead reddit sub {sub}", file=sys.stderr)
        return []

    raw = None
    for url in (old_url, new_url):
        try:
            raw = _reddit_fetch_once(url)
            break
        except urllib.error.HTTPError as e:
            if e.code == 429:
                # Rate-limited on this host; back off and try the other.
                time.sleep(30)
                continue
            print(f"[tech] reddit RSS fetch failed for {sub} @ {url}: HTTPError {e.code}", file=sys.stderr)
            continue
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            print(f"[tech] reddit RSS fetch failed for {sub} @ {url}: {type(e).__name__}", file=sys.stderr)
            continue

    if raw is None:
        feed_health.record_failure(fh_key, "reddit RSS unreachable (both hosts)")
        return []
    feed_health.record_success(fh_key)

    parsed = feedparser.parse(raw)
    out: list[TechItem] = []
    for entry in parsed.entries:
        permalink = entry.get("link", "")
        title = (entry.get("title") or "").strip()
        if not permalink or not title:
            continue
        # Reddit RSS embeds the external link in the summary as `[link](URL)`.
        summary = entry.get("summary", "") or ""
        m = _REDDIT_OUTBOUND.search(summary)
        external = m.group(1).strip() if m else ""
        # If the [link] points back at reddit, it's a self-post — use permalink.
        if not external or external.startswith("https://www.reddit.com") or external.startswith("https://reddit.com"):
            external = permalink
        out.append(TechItem(
            source="Reddit",
            sub=sub,
            title=title,
            url=external,
            discuss_url=permalink,
            score=0,  # RSS doesn't expose score; ordering already reflects it
            comments=0,
        ))
    return out


_BIG_TECH_DOMAINS = {
    "google.com", "blog.google", "ai.googleblog.com", "research.google",
    "openai.com", "anthropic.com", "deepmind.google", "ai.meta.com",
    "microsoft.com", "azure.microsoft.com", "apple.com", "developer.apple.com",
    "aws.amazon.com", "amazon.science", "nvidia.com", "blogs.nvidia.com",
}


def _domain(url: str) -> str:
    m = re.match(r"https?://([^/]+)/?", url)
    if not m:
        return ""
    host = m.group(1).lower()
    return host[4:] if host.startswith("www.") else host


_NOISE_TITLE_RE = re.compile(
    r"\b("
    # SaaS / launch shapes — solo-founder pitch style
    r"my saas|introducing my|i built a|we built a|i made a|"
    r"open sourcing my|"
    # Listicle noise
    r"top \d+|best \d+|\d+ best|\d+ tools|\d+ tips|\d+ ways|"
    r"in 2025|in 2026|in 2027|"
    # Weak-opinion posts
    r"why we left|why i left|why you should|"
    # Fluff
    r"is the future of|the future is|"
    # AI-generated / obvious spam signals
    r"chatgpt wrote|gpt wrote|ai wrote this|"
    # Job / hiring bait — different stream
    r"who's hiring|who is hiring|freelancer\?|seeking freelancer"
    r")\b",
    re.IGNORECASE,
)


def _filter_pool(items: list[TechItem]) -> list[TechItem]:
    seen_urls: set[str] = set()
    out: list[TechItem] = []
    for it in items:
        if it.url in seen_urls:
            continue
        seen_urls.add(it.url)
        d = _domain(it.url)
        if d in _BIG_TECH_DOMAINS:
            continue
        if _NOISE_TITLE_RE.search(it.title):
            continue
        out.append(it)
    # Sort by score descending so the LLM sees strongest first. Items with
    # score=0 (Reddit RSS / Lobsters — no numeric score exposed) sort last.
    out.sort(key=lambda x: -x.score)
    return out[:POOL_CAP]


# --- Deterministic selection -------------------------------------------------

DAILY_PICKS = config.get("tech", "target_picks_max", default=8)
# Per-source diversity cap — no more than N items from one bucket.
PER_SOURCE_CAP: dict[str, int] = {
    "HN":       3,
    "HN Best":  2,
    "Show HN":  2,
    "Lobsters": 2,
    "Reddit":   3,   # across ALL subreddits combined
}


def _pick_deterministic(pool: list[TechItem], n: int = DAILY_PICKS) -> list[TechItem]:
    """Interleave sources so Lobsters + Reddit can't get shut out by HN's raw
    score dominance. Bucket by source (each bucket keeps its score-desc order
    from the pool), then round-robin one pick per source per pass until we hit
    N or every bucket is empty / capped.

    Priority order within a pass: HN → Lobsters → Reddit → HN Best → Show HN.
    Lobsters + Reddit sit ahead of HN Best/Show HN so they're guaranteed a
    slot in pass 1 even though their RSS strips scores (Reddit/Lobsters items
    always sort near the bottom of the score-desc pool)."""
    buckets: dict[str, list[TechItem]] = {}
    for it in pool:
        buckets.setdefault(it.source, []).append(it)

    priority = ["HN", "Lobsters", "Reddit", "HN Best", "Show HN"]
    ordered_sources = [s for s in priority if s in buckets] + \
                      [s for s in buckets if s not in priority]

    picked: list[TechItem] = []
    per_source: dict[str, int] = {}
    while len(picked) < n:
        progressed = False
        for src in ordered_sources:
            if len(picked) >= n:
                break
            if per_source.get(src, 0) >= PER_SOURCE_CAP.get(src, 3):
                continue
            if not buckets[src]:
                continue
            picked.append(buckets[src].pop(0))
            per_source[src] = per_source.get(src, 0) + 1
            progressed = True
        if not progressed:
            break
    return picked


# --- Rendering ---------------------------------------------------------------


def _render_item(it: TechItem) -> str:
    """Deterministic callout: title + points/comments + optional image + source + discussion.

    No LLM prose. The publisher / poster's title is the content. The reader
    clicks through if interested — the extra 5-sentence editorial writeup
    the LLM used to produce was mostly padding anyway."""
    # Title suffix: "· HN, 372 points, 142 comments" or "· r/rust"
    if it.source == "Reddit" and it.sub:
        suffix = f"· r/{it.sub}"
    elif it.score:
        suffix = f"· {it.source}, {it.score} points, {it.comments} comments"
    else:
        suffix = f"· {it.source}"

    # Wikilink the first plausible project name in the title (words in
    # [[double brackets]] show up in the graph and get auto-stubbed)
    title = it.title.strip()
    if len(title) > 96:
        title = title[:93].rstrip() + "…"

    header = f"> [!tech]- {title} {suffix}"

    # Try to attach a hero image from the source URL (cached)
    img_url = images.resolve(it.url) or ""
    image_line = f"> ![|640]({img_url})" if img_url else ""

    # Link line — Source + Discussion, both provided verbatim from the fetcher
    if it.discuss_url and it.discuss_url != it.url:
        links_line = f"> [Source]({it.url}) · [Discussion]({it.discuss_url})"
    else:
        links_line = f"> [Source]({it.url})"

    lines = [header]
    if image_line:
        lines.append(image_line)
    lines.extend(["", links_line])
    return "\n".join(lines)


# --- Run ---------------------------------------------------------------------


def run(*, prefer_model: str = "primary") -> str:
    """Fetch → filter → deterministic pick → render. No LLM. Wall-time seconds.

    prefer_model accepted for orchestrator signature compat, ignored."""
    import time

    all_items: list[TechItem] = []
    all_items.extend(_fetch_hn(HN_TOP,  "HN",      HN_MIN_SCORE,      limit=60))
    all_items.extend(_fetch_hn(HN_BEST, "HN Best", HN_BEST_MIN_SCORE, limit=30))
    all_items.extend(_fetch_hn(HN_SHOW, "Show HN", HN_SHOW_MIN_SCORE, limit=25))
    all_items.extend(_fetch_lobsters(limit=25))
    # Polite delay between reddit subs — 1.5s per sub keeps us below the
    # anonymous rate-limit threshold that produced the 429 storms.
    for i, sub in enumerate(SUBREDDITS):
        if i > 0:
            time.sleep(1.5)
        all_items.extend(_fetch_reddit(sub))

    pool = _filter_pool(all_items)
    if not pool:
        body = (
            "> [!warning] Daily Tech: no items passed filters\n"
            "> HN + Reddit + Lobsters returned nothing above thresholds. "
            "Check network or lower score thresholds in morning-config.yaml."
        )
        vault.insert_today_entry(vault.STREAM_NOTES["tech"], body)
        vault.set_frontmatter_updated(vault.STREAM_NOTES["tech"])
        return body

    picks = _pick_deterministic(pool)
    body = "\n\n".join(_render_item(it) for it in picks)

    vault.insert_today_entry(vault.STREAM_NOTES["tech"], body)
    vault.set_frontmatter_updated(vault.STREAM_NOTES["tech"])
    return body


if __name__ == "__main__":
    print(run())
