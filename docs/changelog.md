# Changelog

All notable changes to `hermes-morning-run` are tracked here. The format loosely follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions are cut when a batch of changes ships together, not on a fixed cadence.

## [2.0.0] — 2026-08-20 — RSS-first rewrite

The pipeline was originally LLM-first: fetch candidate URLs, feed them to a Gemma-4-26B curator, ask it to select and summarize. Over months of live use this proved unreliable in three specific ways:

1. **URL mangling** — the LLM would truncate trailing digits, URL-encode `?`, or add stray characters to source URLs. The validator (correctly) rejected the output, so 8 of 20 news topics regularly wrote `> [!warning] No qualifying story surfaced today.` even when there was fresh content.
2. **Category bias** — the papers curator always picked from `quant-ph`, `cs.AI`, `cs.LG`. Five other configured arXiv categories had fresh papers every day and never got surfaced.
3. **Runtime** — the pipeline was regularly taking 30–40 min per topic due to LLM latency; a single morning run was pushing past 2 hours.

`v2.0.0` rewrites the three worst offenders to be RSS-first. The publisher already ships title, description, publish date, and image via RSS — feeding that back through an LLM to re-summarize was net-negative.

### Changed
- **`news.py`** — rewrite. Direct RSS fetch per topic via `feedparser`, `ThreadPoolExecutor` fan-out across topic sources, DDGS retained as fallback when RSS returns < `picks * 3` hits. Selection is deterministic: 4-bucket priority `(rss+site_hint) > (rss) > (ddgs+site_hint) > (ddgs)`, tiebreak by `pub_date` descending, then per-domain dedupe within topic. Preserves the anti-fabrication guarantee trivially because we render publisher content verbatim. Runtime: ~5s per topic (was ~90–120s).
- **`papers.py`** — rewrite. Parallel fetch of all configured arXiv categories + four journal RSS pseudo-categories (Nature Physics, PRL, bioRxiv, Quanta Magazine). Selection is round-robin: every category with candidates gets `picks[0]` before any gets `picks[1]`, with a per-category cap. `MAX_PICKS=8`, `MAX_PER_CATEGORY_PICKED=2`. In the first live run this surfaced 5 different categories vs the previous run's 3. Runtime: ~1s for the whole stream.
- **`tech.py`** — rewrite. Parallel fetch of HN top/best/show + Lobsters hottest + configured Reddit tech subs. Per-source diversity cap `{HN: 3, HN Best: 2, Show HN: 2, Lobsters: 2, Reddit: 3}`, priority order HN → Lobsters → Reddit → HN Best → Show HN. Reddit uses `old.reddit.com` + browser User-Agent + 1.5s polite delay between sub fetches (a change forced by Reddit's 429 storms). Runtime: ~5–15s.
- **User-Agent** — RSS fetches now identify as `Mozilla/5.0 (…) Firefox/128.0` rather than `hermes-morning/1.0`. Several outlets (Ars Technica, some Nature Group properties) 403 the old identifier.
- **`feed_health.py`** — atomic-write hardening. The previous `_save()` wrote to a shared `feed-health.tmp` and used `Path.replace()`, which raced under `ThreadPoolExecutor`. Added a lazy-init module-level `threading.Lock` around the write, and the temp filename is now suffixed with `{pid}.{time_ns()}` so cross-process writers from concurrent morning runs also can't collide.

### Removed
- **LLM curator prompts** from `news.py`, `papers.py`, `tech.py`. The `_SELECTION_SYSTEM` prompts, `_build_user_prompt`, and post-hoc `_validate` (which was the URL-mangling failure surface) are all gone from the normal path. `llm` is no longer imported in any of those three modules.

### Fixed
- News no longer writes phantom `[!warning] No qualifying <topic> story surfaced today.` when RSS has fresh content.
- Papers stream now represents all configured arXiv categories over the week instead of collapsing to three.
- Tech stream is now source-diverse instead of dominated by whichever bucket had the flashiest scores.
- Concurrent RSS fetches no longer race on `feed-health.json` writes.

### Retained (unchanged)
- **`watchlist.py`** stays LLM-based. Transcript→summary is one of the few places the LLM adds real value; publisher-provided metadata isn't a substitute for reading the video.
- **`curiosity.py`** stays LLM-based. Same reason: it's genuinely a synthesis task, not an aggregation task.
- **`brief.py`** composer stays as-is. Anti-fabrication rules, four-account Gmail + Calendar OAuth remain.

### Migration notes
- No config changes required for existing deployments.
- Restart the `hermes-morning.timer` or wait for the next fire.
- The first run may look thinner if some feeds are stale — that's real, not a regression; the LLM was previously papering over gaps by picking anyway.

## [1.5.0] — 2026-08-09 — Failsafes and feed rot repair

### Added
- Circuit-breaker feed-health tracker (`feed_health.py`). URLs that fail for `WARN_THRESHOLD=3` consecutive days log a warning; at `SKIP_THRESHOLD=10` they're skipped entirely, with a probe attempt every Nth day after.
- Full IT / security / compliance audit written to the vault (see `_staging/` for the playbook version).

### Changed
- Replaced nine dead RSS URLs with live alternatives: Pitchfork (dead) → Bandcamp Daily; Criterion → Letterboxd; Frieze → Hyperallergic; It's Nice That (403) → Design Observer; Nautilus (dead feed) → alt endpoint; Ars Security User-Agent bump; EurekAlert → Smithsonian Science; Japan Times feed migration; Linuxiac → 9to5Linux.

### Fixed
- Reddit fetches switched to `old.reddit.com` + polite 1.5s inter-sub delay after chronic 429s from the JSON API on the new domain.

## [1.4.0] — 2026-08 — Wake-on-LAN over WiFi

### Added
- `wowlan-enable.service` on the inference host configures WoWLAN magic-packet reception so the host can be woken from suspend over WiFi (the ROG has no ethernet).
- Orchestrator's `morning-run.sh` sends the magic packet and polls `llama-server` readiness before dispatching work.

## [1.3.0] — 2026-07 — Multi-account Google OAuth

### Added
- `oauth-grant.py` — one-shot PKCE flow to mint refresh tokens per account, stored in `~/.hermes/mcp-tokens/`.
- Four Gmail + four Calendar accounts (personal, work, plus two educational institution accounts).
- `google.py` handles token refresh with 60s pre-expiry margin, 401 retry, and preserves `refresh_token` when Google doesn't reissue.

### Known issue
- Google OAuth "Testing mode" apps have refresh tokens that expire after 7 days. Publishing the OAuth consent screen removes this restriction. If you see `HTTP 400 invalid_grant` across all accounts, re-run `oauth-grant.py` for each and check your OAuth app's publishing status.

## [1.2.0] — 2026-06 — Wikilink stubbing + concept graph

### Added
- `concept-stubs.py` — post-run pass that creates empty notes in `07 References/` and `04 People/` for any new `[[wikilink]]` mentioned in the day's content. Makes the graph view immediately populated.
- `connection-finder.py` — surfaces cross-note conceptual links (LLM-augmented).

## [1.1.0] — 2026-06 — Dashboard and weekly recap

### Added
- `🏠 Dashboard.md` — always-open landing note aggregating today's callouts across streams.
- `weekly-recap.sh` + `weekly.py` — Sunday roll-up of the week's headlines.

## [1.0.0] — 2026-06 — Initial deployment

### Added
- Orchestrator / inference-host split with WoL.
- News, Papers, Tech, Watchlist, Curiosity, Releases streams (all LLM-first at this stage).
- `📌 Daily Brief` composer with Gmail + Calendar integration.
- Systemd timer at 05:55 IST daily.
- Obsidian Git sync to phone / tablet.
