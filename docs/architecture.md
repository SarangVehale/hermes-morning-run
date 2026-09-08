# Architecture

The pipeline is a plain Python package (`morning/`) invoked from a plain bash script (`morning-run.sh`) fired by a plain systemd timer. Everything else is layered on top of that.

<div class="toc"><div class="toc-title">On this page</div>
<ul>
  <li><a href="#one-machine">One machine</a></li>
  <li><a href="#the-pipeline-order">The pipeline order</a></li>
  <li><a href="#stream-modules-in-detail">Stream modules in detail</a></li>
  <li><a href="#the-brief-composer">The Brief composer</a></li>
  <li><a href="#anti-fabrication-guarantees">Anti-fabrication guarantees</a></li>
  <li><a href="#feed-health-circuit-breaker">Feed health circuit breaker</a></li>
  <li><a href="#llm-layer">LLM layer</a></li>
  <li><a href="#oauth-gmail--calendar">OAuth (Gmail + Calendar)</a></li>
  <li><a href="#systemd-units">systemd units</a></li>
  <li><a href="#configuration-files">Configuration files</a></li>
  <li><a href="#state-files">State files</a></li>
</ul>
</div>

## One machine

Since v2.1 the pipeline runs on a single always-on machine. There is no inference host, no wake-on-LAN, no GPU dependency. Any machine that can run Python and shell out to `claude -p` is sufficient — an old laptop is fine.

The v1/v2.0 two-machine architecture is documented in [History](history.html#v14-early-august--wake-on-lan-over-wifi) for context; it was decommissioned once the RSS-first rewrite reduced LLM usage to ~15-20 calls per morning and the `claude` CLI made local inference unnecessary.

## The pipeline order

`morning-run.sh` on the orchestrator is the entry point. Streams run in a specific order — deterministic ones first, then LLM-augmented ones, then the composer.

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
wikifill      (fill dangling wikilinks with Wikipedia/DDGS-backed content)
maintenance   (post-run housekeeping)
   ↓
git commit && git push
```

Each stream writes to its own note in `01 Updates/`. The composer reads those notes, not the runner's in-memory results — this is deliberate so a stream that crashes late doesn't take the whole run down.

Orchestration code: [`scripts/morning/runner.py`](https://github.com/SarangVehale/hermes-morning-run/blob/main/scripts/morning/runner.py) (492 lines). It builds a `[Task]` list of `Callable` per stream, runs them under `ThreadPoolExecutor`, times each, writes a heartbeat file, and returns.

## Stream modules in detail

### News — `scripts/morning/news.py` (799 lines)

Twenty configured topics in `~/.hermes/morning-config.yaml`. For each: parallel RSS fetch of ~5 preferred sources with DuckDuckGo Search as a fallback if RSS returns < `picks * 3` hits.

Key functions:

- `_fetch_rss(url)` — `feedparser.parse(url)` with browser User-Agent, extracts `title`, `link`, `description`, `pub_date` (from `published_parsed` or `updated_parsed`), `image_url` (from `media_content` / `media_thumbnail` / `enclosures`).
- `_collect_for_topic(topic)` — `ThreadPoolExecutor` fan-out across the topic's RSS sources, DDGS fallback.
- `_select(hits, picks=2)` — deterministic 4-bucket priority:
  1. RSS hit + configured site hint match
  2. RSS hit
  3. DDGS hit + site hint match
  4. DDGS hit

  Ties break on `pub_date` descending. Per-domain dedupe caps repetition within a topic.
- `_render_hit(hit)` — verbatim publisher metadata: title with source domain in parens, image (via markdown image syntax), description snippet truncated at sentence boundary within 480 chars, `[Source](url)` link.
- `_wikilink_first_mention(text, entities)` — wraps the first occurrence of a well-known entity (`OpenAI`, `Anthropic`, publisher names) in `[[wikilink]]` syntax so the concept graph populates.

Runtime: ~5s per topic. Total: ~1-2 min across all 20 topics with parallelism.

### Papers — `scripts/morning/papers.py` (376 lines)

Round-robin across arXiv categories plus four journal RSS feeds treated as pseudo-categories (Nature Physics, PRL, bioRxiv, Quanta Magazine). Every category with candidates gets its first pick before any category gets a second. Per-category cap prevents any single feed from dominating.

Key constants:

- `ARXIV_CATEGORIES` — list of `~10` arXiv category codes (`quant-ph`, `cs.IT`, `cs.LG`, `cond-mat.mes-hall`, ...).
- `EXTRA_FEEDS` — four journal RSS URLs; each treated as a pseudo-arxiv category with a synthesised `sha1`-based pseudo-arxiv-id.
- `MAX_PICKS = 8`
- `MAX_PER_CATEGORY_PICKED = 2`

Key functions:

- `_fetch_arxiv(category)` — pulls `http://export.arxiv.org/rss/{category}`.
- `_fetch_journal_rss(url, name)` — non-arXiv journal RSS with pseudo-id derived from `sha1(url + title)`.
- `_select_top(candidates)` — round-robin per category, respecting `MAX_PER_CATEGORY_PICKED`.
- `_render_paper(paper)` — differentiates real arXiv ID vs journal RSS pseudo-id in header + link labels.

Runtime: ~1s total (all feeds fetched in parallel).

### Tech — `scripts/morning/tech.py` (449 lines)

Fetch order: HN top → HN Best → Show HN → Lobsters hottest → configured Reddit subs. Per-source cap: `{HN: 3, HN Best: 2, Show HN: 2, Lobsters: 2, Reddit: 3}`. Priority order in the round-robin: HN → Lobsters → Reddit → HN Best → Show HN. Lobsters and Reddit are prioritized because their RSS strips scores, so they're at a disadvantage in any score-based tiebreak.

Reddit uses `old.reddit.com` + a browser User-Agent + 1.5s polite delay between subreddit fetches. This is a workaround for aggressive 429 throttling on the JSON API from `www.reddit.com` — see [Troubleshooting](troubleshooting.html#reddit-429-storms).

Key functions:

- `_fetch_hn(feed_url, source_label, min_score, limit)` — pulls one of the HN Firebase endpoints, filters to `score >= min_score`, resolves the `.json` for each.
- `_fetch_lobsters(limit)` — pulls `https://lobste.rs/hottest.rss`.
- `_fetch_reddit(sub)` — pulls `https://old.reddit.com/r/{sub}/.rss`.
- `_filter_pool(items)` — strips items whose title matches configured noise patterns.
- `_pick_deterministic(pool, n=8)` — round-robin per source under `PER_SOURCE_CAP`.
- `_render_item(it)` — callout with title, score / comments suffix (if available), image, `[Source]` and `[Discussion]` links.

Runtime: ~5-15s (Reddit polite delays dominate).

### Watchlist — `scripts/morning/watchlist.py` (591 lines)

The one place where the LLM earns its keep. For each YouTube channel in `~/vault-ai/_watchlist.yaml`:

1. Fetch channel RSS to find videos since last-seen ID (tracked in `~/.hermes/state/watchlist-last-seen.json`).
2. `yt-dlp --skip-download --write-auto-sub --sub-lang en --sub-format json3` to grab the transcript. If no auto-subs, skip and log a `[!warning]`.
3. Pass transcript + metadata to `llm.chat(...)` in `detailed` summarization mode.
4. Write summary to `08 Summaries/{Creator}/Summaries/{Creator} - {YYYY-MM-DD} - {Topic}.md`.
5. Append an index entry to the day's watchlist stream note.

Blogs work the same way with `defuddle` for HTML → clean markdown.

Runtime: dominates the morning run — 10-15s per new video, 5-10 new videos per morning typically = 1-3 min.

### Curiosity — `scripts/morning/curiosities.py` (638 lines)

The other LLM-augmented stream. Each day it picks one previously-unseen concept from a Wikipedia crawl seeded by the previous day's curiosities. LLM's job: write a two-paragraph angle on the concept, wikilink related entities. State lives in `curiosities-discovered.json` (candidate queue) and `curiosities-shown.json` (dates seen).

### Releases — `scripts/morning/releases.py` (271 lines)

For each repo in `~/vault-ai/_tools.yaml`, `GET https://api.github.com/repos/{owner}/{repo}/releases/latest`, compare to last-seen timestamp in `~/.hermes/state/github-releases-last-run.json`, write callout if newer. Occasionally uses LLM to summarize a release note when it's very long.

## The Brief composer

Reads the day's stream notes, picks the top item from each, adds:

- **Weather** — Pimpri-Chinchwad by default. Any free weather API.
- **Today's schedule** — Google Calendar, four accounts, deduplicated by event ID, sorted all-day-first then time-ascending, formatted as markdown checkboxes.
- **Inbox** — Gmail, four accounts, top 5 by importance heuristic, overflow to `📥 Email Triage.md`.
- **Top 5 tasks** from `📋 Tasks.md`.

Anti-fabrication rule (from the composer's own prompt-like docstring):

> Every fact you write here comes from a real tool call: a real Gmail MCP call, a real Calendar MCP call, a real read of `📋 Tasks.md`, a real read of today's `📰 Daily News.md` entry. If a required tool fails or returns empty, write `[!warning] <reason>` in the affected section and skip — do not invent plausible-looking placeholders.

## Anti-fabrication guarantees

These are not "please don't hallucinate" prompts. They're structural:

1. **News / Papers / Tech / Releases** — rendered content is publisher metadata, not LLM output. There's no path for the LLM to invent a URL.
2. **Watchlist** — the summary is generated from an actual transcript file that exists on disk. If `yt-dlp` fails, the video is skipped with a `[!warning]`, not summarized speculatively.
3. **Brief** — composer reads stream files (not runner results). If a stream file has no today-anchor, the composer writes `[!warning]` for that section.
4. **Concept stubs** — `concept-stubs.py` runs post-hoc against the actual git-diff of the day's content, so it can only create stubs for wikilinks that actually landed on disk.

## Feed health circuit breaker

`scripts/morning/feed_health.py` (105 lines) tracks consecutive failures per URL in `~/.hermes/state/feed-health.json`. Thresholds:

- **`WARN_THRESHOLD = 3`** — log a stderr warning that appears in the systemd journal.
- **`SKIP_THRESHOLD = 10`** — skip the URL entirely on subsequent days, except one probe attempt every 10th day to detect recovery.

The state file is written atomically with a threading lock + `{pid}.{time_ns()}` temp-file suffix so parallel RSS fetches from the news topic fan-out (and even cross-process concurrent runs) can't race on it. See [Mistakes](mistakes.html#feed-health-race-condition) for the bug this fixed.

## LLM layer

`scripts/morning/llm.py` (~100 lines). Single entry point:

```python
def chat(
    system: str,
    user: str,
    *,
    max_tokens: int = 400,
    temperature: float = 0.3,
    timeout: float = 300.0,
    prefer: str = "primary",
) -> str
```

Implementation: shells out to the `claude` CLI in print mode:

```python
subprocess.run(
    ["claude", "-p",
     "--model", "sonnet",
     "--restricted",
     "--output-format", "text",
     "--system-prompt", system],
    input=user,
    capture_output=True,
    text=True,
    timeout=timeout,
    check=False,
)
```

Why the CLI, not the SDK:

- Auth is inherited from the user's Claude Code / claude.ai OAuth session (`~/.claude/.credentials.json`). No API key management.
- Usage counts against the user's Pro subscription rather than a paid API tier — free for the covered volume.
- The CLI is already installed and up-to-date on any machine where Claude Code is used.
- `--restricted` disables built-in Bash/Edit/WebFetch tools — we want a pure chat completion, not an agent.

On failure (CLI missing, `Not logged in`, non-zero exit, timeout), it falls back to HP-local ollama on `http://localhost:11434/v1/chat/completions` with model `hermes3:8b`. If both fail, raises `LLMError` — the caller decides whether to render `[!warning]` or degrade further.

Callers: `doctor.py`, `curiosities.py`, `releases.py`, `weekly.py`, `runner.py`, `wikifill.py`, `watchlist.py`.

See [Stack](stack.html) for the "why claude CLI, not anthropic SDK" reasoning.

## OAuth (Gmail + Calendar)

Per-account tokens live in `~/.hermes/mcp-tokens/{account}.json` alongside `{account}.client.json` (client id + secret from Google Cloud Console). `scripts/morning/google.py` (147 lines) handles:

- Loading tokens.
- Refreshing when the access token is within 60s of expiring.
- 401 retry with force-refresh.
- Preserving `refresh_token` when Google doesn't reissue.

**Google OAuth "Testing mode" caveat** — consent screens in Testing mode issue refresh tokens that expire after 7 days. Publish the OAuth app to remove this. See [Troubleshooting](troubleshooting.html#oauth-invalid_grant-across-all-accounts).

## systemd units

Since v2.1, only orchestrator-side units. All inference-host units (`llama-server-primary.service`, `llama-server-fallback.service`, `llama-server-heavy.service`) were deleted.

| Unit | Purpose |
|---|---|
| `hermes-morning.timer` | Fires `hermes-morning.service` at 05:55 IST daily. `Persistent=true`. |
| `hermes-morning.service` | Runs `morning-run.sh` with `TimeoutStartSec=180min`. |
| `hermes-weekly.timer` | Fires `hermes-weekly.service` on Sundays. |
| `hermes-weekly.service` | Runs `weekly-recap.sh`. |

## Configuration files

| File | Purpose |
|---|---|
| `~/.hermes/morning-config.yaml` | topics, subreddits, watchlist config, model preferences, API keys |
| `~/vault-ai/_watchlist.yaml` | creator watchlist (YouTube channels, blog feeds) |
| `~/vault-ai/_tools.yaml` | GitHub repos to track for releases |
| `~/.hermes/mcp-tokens/*.json` | OAuth tokens (600 perms, gitignored) |
| `~/.claude/.credentials.json` | Claude Code OAuth session (used by `claude -p`) |

## State files

Under `~/.hermes/state/`:

| File | Purpose |
|---|---|
| `feed-health.json` | per-URL consecutive-failure counter + last success/fail |
| `watchlist-last-seen.json` | per-creator last-seen video/post ID |
| `curiosities-shown.json` | date-of-last-shown for each surfaced curiosity |
| `curiosities-discovered.json` | queue of candidate concepts to surface |
| `papers-seen-ids.json` | arXiv IDs already surfaced |
| `github-releases-last-run.json` | per-repo last-seen release timestamp |
| `last_run.json` | most recent run's per-stream ok/timing |
| `dashboard.json` | streak counter |

{% include nav.html
  prev="history" prev_title="History"
  next="stack" next_title="Stack" %}
