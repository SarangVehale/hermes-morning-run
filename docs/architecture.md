# Architecture

## Two machines, one pipeline

The system is split across two hosts because the orchestrator wants to be always-on and cheap (an old laptop is fine) while the inference host wants a GPU and can afford to sleep between runs.

### Orchestrator
- Runs 24/7. Systemd timer fires the pipeline at 05:55 IST (adjust to your locale).
- Holds the Obsidian vault as a git working tree.
- Runs `morning-run.sh` which wakes the inference host, dispatches per-stream work, then powers the host back down.
- Handles all the non-LLM work: RSS fetches, HTTP requests, git commit/push, OAuth token refresh, feed-health bookkeeping.

### Inference host
- Sleeps most of the day.
- Woken via Wake-on-LAN (over WiFi via WoWLAN — the ROG in the reference deployment has no ethernet).
- Serves three `llama.cpp` endpoints:
  - **primary**: bigger model for summarization / synthesis (Gemma-4-26B in the reference).
  - **fallback**: smaller/faster model for time-sensitive stages (Qwen2.5-3B).
  - **heavy**: reserved for weekly-recap / long-context work.

## The pipeline

`morning-run.sh` on the orchestrator is the entry point. It runs streams in a specific order — deterministic ones first, then LLM ones, then the composer.

```
weather       (fast, sync)
   ↓
news          (RSS-first, parallel per topic)
papers        (RSS-first, parallel across arXiv + journals)
tech          (RSS-first, parallel across HN/Lobsters/Reddit)
releases      (GitHub API, per-repo)
onthisday     (Wikipedia)
   ↓
watchlist     (RSS discovery, LLM summary per new item)
curiosity     (LLM synthesis)
   ↓
brief         (reads everything above + Gmail + Calendar, composes landing note)
dashboard     (roll-up)
   ↓
concept-stubs (create empty notes for new [[wikilinks]])
   ↓
git commit && git push
```

Each stream writes to its own note in `01 Updates/`. The composer reads those notes, not the runner's in-memory results — this is deliberate so a stream that crashes late doesn't take the whole run down.

## Stream design

### News

Twenty configured topics. For each: parallel RSS fetch of ~5 preferred sources with DuckDuckGo Search as a fallback if RSS returns < `picks * 3` hits.

Selection is deterministic with a 4-bucket priority:

1. RSS hit + configured site hint match
2. RSS hit
3. DDGS hit + site hint match
4. DDGS hit

Ties break on `pub_date` descending. Per-domain dedupe caps repetition within a topic.

Rendering is verbatim publisher metadata: title (with source domain), image (via `media_content` / `media_thumbnail` / `enclosures`), description snippet truncated at sentence boundary within 480 chars, source link. First mention of a well-known entity in the day's news gets a `[[wikilink]]` so the concept graph populates.

### Papers

Round-robin across arXiv categories plus four journal RSS feeds treated as pseudo-categories (Nature Physics, PRL, bioRxiv, Quanta Magazine). Every category with candidates gets its first pick before any category gets a second. Per-category cap prevents any single feed from dominating.

Configuration is in `~/.hermes/morning-config.yaml`:

```yaml
papers:
  arxiv_categories:
    - quant-ph
    - cs.IT
    - cs.AI
    - cs.LG
    - cond-mat.mes-hall
    # …
  max_picks: 8
  max_per_category: 2
```

### Tech

Fetch order: HN top → HN Best → Show HN → Lobsters hottest → configured Reddit subs. Per-source cap: `{HN: 3, HN Best: 2, Show HN: 2, Lobsters: 2, Reddit: 3}`. Priority order in the round-robin: HN → Lobsters → Reddit → HN Best → Show HN (Lobsters and Reddit are prioritized because their RSS strips scores, so they're at a disadvantage in any score-based tiebreak).

Reddit uses `old.reddit.com` + a browser User-Agent + 1.5s polite delay between subreddit fetches. This is a workaround for aggressive 429 throttling on the JSON API from `www.reddit.com`.

### Watchlist

The one place where the LLM earns its keep. For each YouTube channel in `_watchlist.yaml`:

1. Fetch channel RSS to find videos since last-seen ID (tracked in `~/.hermes/state/watchlist-last-seen.json`).
2. `yt-dlp --write-auto-sub` to grab the transcript. If no auto-subs, skip and log a `[!warning]`.
3. Pass transcript + metadata to the `summarize` skill in `detailed` mode.
4. Write summary to `08 Summaries/{Creator} - {YYYY-MM-DD} - {Topic}.md`.
5. Append an index entry to the day's watchlist stream note.

Blogs work the same way with `defuddle` for HTML → clean markdown.

### Curiosity

The exception to the "no LLM for aggregation" rule. Each day it picks one previously-unseen concept from a Wikipedia crawl seeded by the previous day's curiosities. LLM's job: write a two-paragraph angle on the concept, wikilink related entities. State lives in `curiosities-discovered.json` and `curiosities-shown.json`.

### Brief

Composer. Reads the day's stream notes, picks the top item from each, adds:

- Weather (any public weather API)
- Today's schedule from Google Calendar (four accounts, deduplicated by event ID)
- Today's inbox from Gmail (four accounts, top 5 by importance heuristic, overflow to `📥 Email Triage`)
- Top 5 tasks from `📋 Tasks.md`

Follows a strict anti-fabrication rule: every named person, event, task, and URL comes from a real tool call. Failure modes are `[!warning]` callouts.

## Anti-fabrication guarantees

These are not "please don't hallucinate" prompts. They're structural:

1. **News / Papers / Tech / Releases**: rendered content is publisher metadata, not LLM output. There's no path for the LLM to invent a URL.
2. **Watchlist**: the summary is generated from an actual transcript file that exists on disk. If `yt-dlp` fails, the video is skipped with a `[!warning]`, not summarized speculatively.
3. **Brief**: composer reads stream files (not runner results). If a stream file has no today-anchor, the composer writes `[!warning]` for that section.
4. **Concept stubs**: `concept-stubs.py` runs post-hoc against the actual git-diff of the day's content — it can only create stubs for wikilinks that landed on disk.

## Feed health circuit-breaker

`feed_health.py` tracks consecutive failures per URL in `~/.hermes/state/feed-health.json`. Thresholds:

- **WARN_THRESHOLD = 3** — log a stderr warning that appears in the daily systemd log.
- **SKIP_THRESHOLD = 10** — skip the URL entirely on subsequent days, except one probe attempt every 10th day to detect recovery.

The state file is written atomically with a threading lock + `{pid}.{time_ns()}` temp-file suffix so parallel RSS fetches from the news topic fan-out (and even cross-process concurrent runs) can't race on it.

## OAuth (Gmail + Calendar)

Per-account tokens live in `~/.hermes/mcp-tokens/{account}.json` alongside `{account}.client.json` (client id + secret from Google Cloud Console). `google.py` handles:

- Loading tokens.
- Refreshing when the access token is within 60s of expiring.
- 401 retry with force-refresh.
- Preserving `refresh_token` when Google doesn't reissue.

**Google OAuth "Testing mode" caveat**: consent screens in Testing mode issue refresh tokens that expire after 7 days. Publish the OAuth app to remove this. If you see `HTTP 400 invalid_grant` across all your accounts, that's the most likely cause. Re-run `oauth-grant.py` for each account after publishing.

## systemd units

Reference deployment uses:

| Unit | Host | Purpose |
|---|---|---|
| `hermes-morning.timer` | orchestrator | Fires `hermes-morning.service` at 05:55 IST daily. `Persistent=true`. |
| `hermes-morning.service` | orchestrator | Runs `morning-run.sh` with `TimeoutStartSec=180min`. |
| `hermes-weekly.timer` | orchestrator | Fires `hermes-weekly.service` on Sundays. |
| `llama-server-primary.service` | inference | The main model endpoint. |
| `llama-server-fallback.service` | inference | Small/fast model. |
| `llama-server-heavy.service` | inference | Reserved for weekly-recap. |

## Configuration files

| File | Purpose |
|---|---|
| `~/.hermes/morning-config.yaml` | topics, subreddits, watchlist, model preferences, API keys |
| `~/vault-ai/_watchlist.yaml` | creator watchlist (YouTube channels, blog feeds) |
| `~/vault-ai/_tools.yaml` | GitHub repos to track for releases |
| `~/.hermes/mcp-tokens/*.json` | OAuth tokens (600 perms, gitignored) |
| `~/.hermes/state/*.json` | last-seen markers, feed health, dashboard state |
