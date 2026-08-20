"""Hero-image resolver shared by news / tech / watchlist / curiosity streams.

Goal: for a given source URL, return a stable image URL we can embed inline
in the dashboard. Three strategies, in priority order:

  1. YouTube thumbnail (`https://i.ytimg.com/vi/{id}/maxresdefault.jpg`) —
     for any watchlist youtube.com / youtu.be URL.
  2. OG image — fetch the page HTML, parse the first `<meta property=og:image>`
     or `<meta name=twitter:image>` tag. Works for ~95% of modern news /
     blog / Show HN sites.
  3. None — caller falls back to no image. Streams must degrade gracefully.

Caching: results stored at `~/.hermes/image_cache/<sha1>.json` so we don't
re-fetch the same URL every morning. Cache TTL = 7 days (news pages can
update their OG image).
"""
from __future__ import annotations

import datetime
import hashlib
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


CACHE_DIR = Path.home() / ".hermes" / "image_cache"
CACHE_TTL_DAYS = 7
UA = "hermes-morning/1.0 (hermes-morning@example.com)"
HTTP_TIMEOUT = 10.0
MAX_HTML_BYTES = 256 * 1024   # only need the <head>; cap to be polite

_YT_ID_RE = re.compile(
    r"(?:youtu\.be/|youtube\.com/(?:watch\?(?:.+&)?v=|embed/|shorts/))"
    r"([A-Za-z0-9_-]{6,})"
)

# Order matters: OG image first, then Twitter card, then any image hint we can
# find in <head>.
_META_PATTERNS = (
    re.compile(r'<meta[^>]+property=["\']og:image(?::secure_url)?["\'][^>]+content=["\']([^"\']+)["\']', re.IGNORECASE),
    re.compile(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']', re.IGNORECASE),
    re.compile(r'<meta[^>]+name=["\']twitter:image(?::src)?["\'][^>]+content=["\']([^"\']+)["\']', re.IGNORECASE),
    re.compile(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image["\']', re.IGNORECASE),
    re.compile(r'<link[^>]+rel=["\']image_src["\'][^>]+href=["\']([^"\']+)["\']', re.IGNORECASE),
)


def _ensure_dir() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _cache_path(url: str) -> Path:
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()
    return CACHE_DIR / f"{digest}.json"


def _read_cache(url: str) -> str | None | object:
    """Return the cached image URL (str), the sentinel `False` for a known
    miss, or None if cache absent / stale."""
    p = _cache_path(url)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    saved_at = data.get("saved_at", "")
    try:
        ts = datetime.datetime.fromisoformat(saved_at)
    except ValueError:
        return None
    if (datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) - ts).days >= CACHE_TTL_DAYS:
        return None
    image = data.get("image")
    if image == "":
        return False  # known miss
    return image


def _write_cache(url: str, image: str | None) -> None:
    _ensure_dir()
    payload = {
        "url": url,
        "image": image or "",
        "saved_at": datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds"),
    }
    p = _cache_path(url)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(p)


def _youtube_thumb(url: str) -> str | None:
    m = _YT_ID_RE.search(url)
    if not m:
        return None
    vid = m.group(1)
    # maxresdefault.jpg isn't always present; hqdefault.jpg always is. Use the
    # always-present one. Obsidian renders both fine.
    return f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"


def _fetch_og(url: str) -> str | None:
    """Pull the <head> from `url` and extract the best image meta tag."""
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml",
        })
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
            raw = r.read(MAX_HTML_BYTES).decode("utf-8", errors="replace")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
        print(f"[images] fetch failed {url}: {type(e).__name__}", file=sys.stderr)
        return None

    # Cut at </head> so we don't scan body content.
    head_end = raw.lower().find("</head>")
    if head_end > 0:
        raw = raw[:head_end]

    for pattern in _META_PATTERNS:
        m = pattern.search(raw)
        if m:
            img = m.group(1).strip()
            if not img.startswith(("http://", "https://")):
                # Resolve relative URL.
                img = urllib.parse.urljoin(url, img)
            # Reject obvious 1×1 trackers + svg badges by extension.
            low = img.lower()
            if low.endswith((".svg", ".gif")) and "logo" in low:
                continue
            return img
    return None


def resolve(url: str) -> str | None:
    """Resolve a hero image URL for the given source URL.

    Returns the image URL on success, None on miss. Caches both outcomes."""
    if not url or not url.startswith(("http://", "https://")):
        return None

    # YouTube first — no need to hit the page.
    yt = _youtube_thumb(url)
    if yt:
        return yt

    cached = _read_cache(url)
    if cached is False:
        return None
    if isinstance(cached, str) and cached:
        return cached

    image = _fetch_og(url)
    _write_cache(url, image)
    return image


def embed(url: str, width_hint: int = 640) -> str:
    """Return a Markdown image-embed line for the given source URL, or an
    empty string if no image was resolved. Streams call this to splice an
    image into a callout body without raising on failure."""
    img = resolve(url)
    if not img:
        return ""
    # Obsidian image-embed: `![|width](url)` for sized rendering.
    return f"![|{width_hint}]({img})"


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        print(f"{arg} → {resolve(arg)}")
