# Changelog

All notable changes to `hermes-morning-run` are tracked here. Loose [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format; versions are cut when a batch of changes ships together, not on a fixed cadence.

For the *reasoning* behind each change, see the [History](https://sarangvehale.github.io/hermes-morning-run/history.html) and [Mistakes](https://sarangvehale.github.io/hermes-morning-run/mistakes.html) pages of the docs site.

## [2.1.0] — 2026-08-21 — decommission ROG, LLM via claude CLI

The v2.0 rewrite reduced LLM usage to ~15-20 calls per morning. That's not enough to justify a dedicated inference host. v2.1 rips out the two-machine architecture entirely and routes the remaining LLM calls through the `claude` CLI in print mode, authenticated via the user's claude.ai Pro subscription.

### Changed

- **`llm.py`** — completely rewritten. Was: `POST http://rog:8080/v1/chat/completions` (llama-server / Gemma-4-26B) with fallback to `http://rog:8081` (Qwen 3B) then HP-local ollama. Now: `subprocess.run(["claude", "-p", "--model", "sonnet", "--restricted", "--output-format", "text", "--system-prompt", system])`, stdin = user prompt. HP-local ollama retained as fallback. Interface `chat(system, user, ...)` preserved — no changes to callers.
- **`morning-run.sh`** — 195 lines → 82 lines. Removed WoL block, ROG-up polling, `llama-server` SSH start, `/v1/models` probe, `llama-server` SSH stop, ROG poweroff, all `RYZEN_*` env knobs, `SKIP_ROG_START` / `SKIP_ROG_STOP` compatibility shims.

### Removed

- **`systemd/llama-server-primary.service`** — obsolete (was on the inference host).
- **`systemd/llama-server-fallback.service`** — obsolete.
- **`systemd/llama-server-heavy.service`** — obsolete.
- All `RYZEN_*` environment variables from documentation.
- The Wake-on-LAN dependency (`wakeonlan` package) — no longer needed.

### Decommissioned (on the reference inference host)

- Stopped and disabled `llama-server-primary.service` and `llama-server-fast.service` (user scope).
- Deleted the unit files under `~/.config/systemd/user/`.
- `rm -rf ~/models` (27 GB — Gemma-4-26B, Hermes-4-14B, Qwen2.5-3B GGUFs).
- `rm -rf ~/llama.cpp` (1.5 GB build directory).
- Total freed on the reference deployment: 28 GB.

### Preserved (unchanged)

- HP-local ollama fallback (`hermes3:8b` on `http://localhost:11434`) for offline scenarios.
- All RSS-first stream code (`news.py`, `papers.py`, `tech.py`) from v2.0.
- Gmail / Calendar OAuth flow and `~/.hermes/mcp-tokens/` layout.
- `concept-stubs.py`, `wikifill`, `connection-finder`, `weekly-recap`.

### Migration notes

- **Existing deployments:** no config changes required if `claude` CLI is on PATH and logged in.
- Optional: after upgrade, decommission the inference host with the commands in the [History → v2.1](https://sarangvehale.github.io/hermes-morning-run/history.html#v21-august-21--decommissioning-rog) walkthrough. Nothing keeps working when it's gone — the removed ROG dependency is not merely optional.
- **New requirement:** `claude` CLI installed and logged in via `claude /login`. Free-tier Claude Code works but a Pro / Max subscription is recommended for the daily volume.

### Metrics vs v2.0

| Metric | v2.0 (two-machine) | v2.1 (one-machine) |
|---|---|---|
| Machines needed | 2 (orchestrator + GPU inference) | 1 (orchestrator only) |
| Cold-start latency | ~120s (llama-server load 26B GGUF) | ~3s (claude CLI startup) |
| Full-run wall clock | 15-25 min | 5-15 min |
| Disk footprint on inference host | 28 GB (models + llama.cpp) | 0 |
| WoWLAN + WoL complexity | Yes | Removed |
| LLM cost per morning | $0 (local inference) | $0 (Pro subscription covers) |

## [2.0.0] — 2026-08-20 — RSS-first rewrite

The pipeline was originally LLM-first: fetch candidate URLs, feed them to a Gemma-4-26B curator, ask it to select and summarize. Over months of live use this proved unreliable in three specific ways:

1. **URL mangling** — the LLM would truncate trailing digits, URL-encode `?`, or add stray characters to source URLs. The validator (correctly) rejected the output, so 8 of 20 news topics regularly wrote `> [!warning] No qualifying story surfaced today.` even when there was fresh content.
2. **Category bias** — the papers curator always picked from `quant-ph`, `cs.AI`, `cs.LG`. Five other configured arXiv categories had fresh papers every day and never got surfaced.
3. **Runtime** — the pipeline was regularly taking 30-40 min per topic due to LLM latency; a single morning run was pushing past 2 hours.

`v2.0.0` rewrites the three worst offenders to be RSS-first.

### Changed

- **`news.py`** — rewrite. Parallel RSS fetch per topic via `feedparser` + `ThreadPoolExecutor`, DDGS retained as fallback when RSS returns < `picks * 3` hits. Deterministic 4-bucket selection: `(rss+site_hint) > (rss) > (ddgs+site_hint) > (ddgs)`, tiebreak by `pub_date` desc, then per-domain dedupe. Runtime: ~5s per topic (was ~90-120s).
- **`papers.py`** — rewrite. Parallel fetch of all configured arXiv categories + four journal RSS pseudo-categories (Nature Physics, PRL, bioRxiv, Quanta Magazine). Round-robin: every category with candidates gets picks[0] before any gets picks[1], with a per-category cap. `MAX_PICKS=8`, `MAX_PER_CATEGORY_PICKED=2`. Surfaced 5+ categories vs previous 3.
- **`tech.py`** — rewrite. Parallel fetch of HN top/best/show + Lobsters + configured Reddit tech subs. Per-source diversity cap `{HN: 3, HN Best: 2, Show HN: 2, Lobsters: 2, Reddit: 3}`. Reddit uses `old.reddit.com` + browser User-Agent + 1.5s polite delay between sub fetches.
- **User-Agent** — RSS fetches identify as `Mozilla/5.0 (…) Firefox/128.0` rather than `hermes-morning/1.0`. Several outlets (Ars Technica, some Nature Group properties) 403 the old identifier.
- **`feed_health.py`** — atomic-write hardening. Threading lock + `{pid}.{time_ns()}` suffix in the temp filename.

### Removed

- **LLM curator prompts** from `news.py`, `papers.py`, `tech.py`. `_SELECTION_SYSTEM`, `_build_user_prompt`, `_validate` all gone from the normal path. `llm` no longer imported in those three modules.

### Fixed

- News no longer writes phantom `[!warning] No qualifying <topic> story surfaced today.` when RSS has fresh content.
- Papers stream now represents all configured arXiv categories over the week instead of collapsing to three.
- Tech stream is now source-diverse instead of dominated by whichever bucket had the flashiest scores.
- Concurrent RSS fetches no longer race on `feed-health.json` writes.

### Retained (unchanged)

- **`watchlist.py`** stays LLM-based. Transcript→summary is one of the few places the LLM adds real value.
- **`curiosity.py`** stays LLM-based. Same reason: synthesis, not aggregation.
- **`brief.py`** composer stays as-is. Anti-fabrication rules, four-account Gmail + Calendar OAuth remain.

## [1.5.0] — 2026-08-09 — failsafes and feed-rot repair

### Added

- Circuit-breaker feed-health tracker (`feed_health.py`). URLs that fail for `WARN_THRESHOLD=3` consecutive days log a warning; at `SKIP_THRESHOLD=10` they're skipped entirely, probe attempt every Nth day.
- Full IT / security / compliance audit written to the vault.

### Changed

- Replaced nine dead RSS URLs with live alternatives: Pitchfork → Bandcamp Daily; Criterion → Letterboxd; Frieze → Hyperallergic; It's Nice That → Design Observer; Nautilus → alt endpoint; Ars Security UA bump; EurekAlert → Smithsonian Science; Japan Times feed migration; Linuxiac → 9to5Linux.

### Fixed

- Reddit fetches switched to `old.reddit.com` + polite 1.5s inter-sub delay after chronic 429s.

## [1.4.0] — 2026-08 — Wake-on-LAN over WiFi

### Added

- `wowlan-enable.service` on the inference host — WoWLAN magic-packet reception over WiFi (no ethernet on the reference ROG Flow X13).
- Orchestrator's `morning-run.sh` sends magic packet and polls `llama-server` readiness before dispatch.

*(All of this went away in v2.1.)*

## [1.3.0] — 2026-07 — Multi-account Google OAuth

### Added

- `oauth-grant.py` — one-shot PKCE flow to mint refresh tokens per account, stored in `~/.hermes/mcp-tokens/`.
- Four Gmail + four Calendar accounts (personal, work, plus two educational institution accounts).
- `google.py` handles token refresh with 60s pre-expiry margin, 401 retry, and preserves `refresh_token` when Google doesn't reissue.

### Known issue

- Google OAuth "Testing mode" apps issue refresh tokens that expire after 7 days. Publishing the OAuth consent screen removes this. Symptom of hitting this: `HTTP 400 invalid_grant` across all accounts. See [Mistakes → The two-month OAuth outage](https://sarangvehale.github.io/hermes-morning-run/mistakes.html#the-two-month-oauth-outage).

## [1.2.0] — 2026-06 — Wikilink stubbing + concept graph

### Added

- `concept-stubs.py` — post-run pass, creates empty notes in `07 References/` and `04 People/` for any new `[[wikilink]]` mentioned in the day's content.
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
