# History

Every decision this project made was a reaction to something that broke. This page walks through the whole timeline from June 2026 to today.

<div class="toc"><div class="toc-title">On this page</div>
<ul>
  <li><a href="#june-2026--the-original-idea">June 2026 — the original idea</a></li>
  <li><a href="#v10-late-june--first-live-deployment">v1.0 (late June) — first live deployment</a></li>
  <li><a href="#v11-early-july--dashboard-and-weekly-recap">v1.1 (early July) — Dashboard and Weekly Recap</a></li>
  <li><a href="#v12-mid-july--concept-graph">v1.2 (mid-July) — concept graph</a></li>
  <li><a href="#v13-late-july--multi-account-google-oauth">v1.3 (late July) — multi-account Google OAuth</a></li>
  <li><a href="#v14-early-august--wake-on-lan-over-wifi">v1.4 (early August) — Wake-on-LAN over WiFi</a></li>
  <li><a href="#v15-august-9--failsafes-and-feed-rot-repair">v1.5 (August 9) — failsafes and feed-rot repair</a></li>
  <li><a href="#the-reliability-crisis-august-15-19">The reliability crisis (August 15-19)</a></li>
  <li><a href="#the-audit-august-19">The audit (August 19)</a></li>
  <li><a href="#the-rss-first-insight-august-20-morning">The RSS-first insight (August 20 morning)</a></li>
  <li><a href="#v20-august-20--the-rss-first-rewrite">v2.0 (August 20) — the RSS-first rewrite</a></li>
  <li><a href="#still-failing-august-20-afternoon">"Still failing" (August 20 afternoon)</a></li>
  <li><a href="#publication-august-20-evening">Publication (August 20 evening)</a></li>
  <li><a href="#v21-august-21--decommissioning-rog">v2.1 (August 21) — decommissioning ROG</a></li>
</ul>
</div>

## June 2026 — the original idea

The problem: too much time lost to app-switching in the morning. Open news app, doomscroll. Open email app, get distracted by a subject line. Open YouTube, watch a suggested video that has nothing to do with what you came for. By the time you actually start work, an hour is gone.

The goal was to compress the whole morning-input ritual into one Obsidian note. Everything worth reading, one page, before the phone becomes hostile. Then close the phone until lunch.

Constraints that shaped the design:

- **Privacy** — no personal email or calendar data leaves the LAN. That ruled out hosted "daily digest" products.
- **Cost** — the pipeline runs 365 days a year. Even $0.02/day of tokens is $7/year of psychic tax.
- **Own the reader** — Obsidian. Familiar, mobile-friendly, syncs via git, has a plugin ecosystem.
- **Two machines** — an old HP EliteBook was always-on anyway (media server duty). A ROG Flow X13 with a decent GPU could sleep between briefings. Splitting orchestration from inference meant the always-on machine didn't need a GPU and the GPU machine didn't need to be always-on.

## v1.0 (late June) — first live deployment

The first working pipeline was LLM-first. For each stream:

1. Fetch a pool of candidate items (RSS + web search).
2. Feed the pool to Gemma-4-26B running on `llama.cpp` on the ROG.
3. Ask the model to pick the 3-5 most important, summarize each, and return structured output.
4. Validate the URLs against the candidate pool, render callouts, insert into the day's stream note.

Streams at v1.0: **News, Papers, Tech, Watchlist, Curiosity, Releases**, plus the **Brief** composer that read the six streams and produced a landing note.

Systemd timer at 05:55 IST. WoL over ethernet (later ripped out — see v1.4). Git commit + push after the run.

At this stage the shape worked. The pipeline ran. The vault populated. It felt like magic for about a week.

## v1.1 (early July) — Dashboard and Weekly Recap

Two additions after the first week of use:

- **`🏠 Dashboard.md`** — always-open landing note, aggregates today's callouts across streams so you don't have to click through each stream note in turn. Reduced clicks-per-morning from ~7 to ~1.
- **`weekly-recap.sh` + `weekly.py`** — Sunday roll-up. Reads the week's stream notes, picks a handful of "still worth remembering" items per stream. The daily notes are ephemeral; the weekly is what you skim later.

## v1.2 (mid-July) — concept graph

Obsidian's [[wikilinks]] auto-create nothing. If a callout mentions `[[OpenAI]]`, that link only becomes a real note when someone creates `07 References/OpenAI.md`. Otherwise it's a broken link.

Two scripts fixed this:

- **`concept-stubs.py`** — post-run pass, greps the day's stream additions for `[[Name]]` patterns, creates empty notes in `07 References/` (concepts) or `04 People/` (attendees, senders) for any that don't already exist. The graph view populates immediately.
- **`connection-finder.py`** — LLM-augmented, finds cross-note conceptual links ("this new curiosity is related to that paper you read three weeks ago"). Nice-to-have; doesn't run daily.

## v1.3 (late July) — multi-account Google OAuth

The Brief composer needed real inbox and calendar context. Four accounts to unify:

- `personal` — everyday Gmail
- `work` — a secondary Gmail
- `iitm` — IIT Madras Online BS student account (part-time)
- `nfsu` — NFSU academic account (part-time)

Each account got two MCP-server entries: one for Gmail, one for Calendar. Eight refresh tokens in total, stored in `~/.hermes/mcp-tokens/`. `oauth-grant.py` — a one-shot PKCE flow — was written to mint each token by opening a browser tab, waiting for the redirect, and writing the JSON.

`google.py` handled runtime concerns: refresh when access token is within 60s of expiring, retry once on 401 with force-refresh, preserve `refresh_token` when Google doesn't reissue.

<div class="callout warn"><div class="callout-title">Foreshadowing</div>
Google OAuth "Testing mode" apps issue refresh tokens that expire after 7 days. We didn't publish the consent screen. This didn't matter for a while because we were actively re-granting. It came back to haunt us in August — see <a href="mistakes.html#the-two-month-oauth-outage">Mistakes</a>.
</div>

## v1.4 (early August) — Wake-on-LAN over WiFi

The ROG Flow X13 has no ethernet port. Wake-on-LAN over WiFi requires the WiFi chip to keep listening for magic packets while the host sleeps — that's WoWLAN.

Two changes on the ROG:

- **`wowlan-enable.service`** — runs `iw phy0 wowlan enable magic-packet` at boot, so a magic packet from the LAN can wake the machine.
- **suspend-then-hibernate** — actually keep the machine reachable via WoWLAN. Deep sleep (S3) is fine; hibernate (S4) kills the WiFi entirely and defeats the purpose.

On the orchestrator, `morning-run.sh` sent the magic packet via `wakeonlan`, then polled `curl http://$RYZEN_IP:8080/health` until `llama-server` responded. Only then did it start dispatching stream work.

## v1.5 (August 9) — failsafes and feed-rot repair

By early August the daily notes were showing gaps. A user-facing complaint:

> day by day, one by one services are failing. and they have kept failing since the first week!!

Two problems, one fix each:

**Feed rot**. Nine RSS URLs had gone dead over ~six weeks:

| Dead source | Replacement |
|---|---|
| Pitchfork RSS (404) | Bandcamp Daily |
| Criterion Current RSS (404) | Letterboxd blog feed |
| Frieze RSS (dropped) | Hyperallergic |
| It's Nice That (403 on the UA) | Design Observer |
| Nautilus feed (dropped) | alt endpoint at `/rss/all` |
| Ars Technica security (403 on the UA) | UA bumped to browser |
| EurekAlert (paywall) | Smithsonian Science |
| Japan Times feed URL changed | new URL |
| Linuxiac (404) | 9to5Linux |

**Feed health circuit breaker** — `feed_health.py`. State in `~/.hermes/state/feed-health.json` tracking `consecutive_failures`, `last_success`, `last_fail`, `last_reason` per URL.

Thresholds:

- `WARN_THRESHOLD = 3` — log a stderr warning that appears in the systemd journal.
- `SKIP_THRESHOLD = 10` — skip the URL entirely, but retry once every 10th day as a probe (recovery detection).

Reddit fetches switched to `old.reddit.com` + a browser User-Agent + a 1.5s polite delay between subs after chronic 429s from the JSON API on the new domain.

<div class="callout wrong"><div class="callout-title">Latent bug we didn't notice</div>
The <code>_save()</code> function wrote to a shared <code>feed-health.tmp</code> filename and used <code>Path.replace()</code>. Under <code>ThreadPoolExecutor</code>, two concurrent RSS fetches racing on the temp file caused sporadic <code>FileNotFoundError: '/home/USER/.hermes/state/feed-health.tmp' -> '/home/USER/.hermes/state/feed-health.json'</code>. This wasn't fixed until v2.0. See <a href="mistakes.html#feed-health-race-condition">Mistakes</a>.
</div>

## The reliability crisis (August 15-19)

Between August 15 and 19, three things converged:

1. **News was failing on 8 of 20 topics daily** — the LLM was mangling URLs in structured output (truncating trailing digits, URL-encoding `?`, adding stray characters). The validator (correctly) rejected the output, so those 8 topics wrote `> [!warning] No qualifying story surfaced today.` every single day, even when the RSS had plenty of fresh content.
2. **Papers was thin** — 5 of 8 configured arXiv categories never surfaced. The LLM curator was choosing from the same 3 (`quant-ph`, `cs.AI`, `cs.LG`) because they had the shiniest abstracts.
3. **ROG fans ramping up randomly** — investigation revealed the WoL schedule was firing whether or not the previous morning's run had completed, so on a run failure the ROG stayed awake indefinitely.

User frustration hit a peak:

> half of the services have failed. and the entire vault along with the ui is a mess and everything is broken. 90% of features have failed.

## The audit (August 19)

Wrote a full IT / security / compliance audit into the vault as `AUDIT-2026-08-19.md`. Status matrix (🟢/🟡/🔴) for each component; sections for perception vs reality, IT findings (P0/P1/P2), security findings, compliance findings, remediation plan.

Initial reporting claimed ~75% success rate. User pushed back:

> that is not 75% success. That is more than 50% failure as other than there is just curiosity, tech news (which I care much less about) and papers.

Recalibration: by *reading-value* — how much of what landed in the vault was actually worth reading — it was closer to 40% success, 60% failure. The 75% number was counting "did the script exit 0" as success; that was the wrong metric for a subjective daily-briefing product.

## The RSS-first insight (August 20 morning)

The unlock came from a user question:

> how hard is it to just fetch things from the source. It doesn't even need llm knowledge.

This inverted the design premise. The v1 architecture assumed the LLM's job was to *select and summarize*. But publishers already ship structured metadata via RSS: title, description, publish date, image URL. The LLM was being asked to re-summarize a summary — and mangling the URL in the process.

The right split for a daily briefing:

| Task | Right tool |
|---|---|
| Aggregation (which items are new/relevant) | Deterministic Python (RSS + round-robin + per-source diversity) |
| Summarization of transcript-shaped content | LLM (video transcripts) |
| Synthesis (curiosity — pick a concept, write an angle) | LLM |

Everything in column 1 the LLM was doing badly, adding failure surface. Everything in column 2 it was doing well.

## v2.0 (August 20) — the RSS-first rewrite

Three modules rewritten RSS-first, one race fix:

- **`news.py`** (799 lines) — parallel RSS fetch per topic via `feedparser` + `ThreadPoolExecutor`, DDGS retained as fallback when RSS returns fewer than `picks * 3` hits. Deterministic 4-bucket selection: `(rss+site_hint) > (rss) > (ddgs+site_hint) > (ddgs)`, tiebreak on `pub_date` desc, then per-domain dedupe. Runtime: ~5s per topic (was ~90-120s).
- **`papers.py`** (376 lines) — parallel fetch of all configured arXiv categories + four journal RSS pseudo-categories. Round-robin: every category with candidates gets picks[0] before any gets picks[1]. `MAX_PICKS=8`, `MAX_PER_CATEGORY_PICKED=2`. Runtime: ~1s.
- **`tech.py`** (449 lines) — parallel fetch of HN top/best/show + Lobsters + Reddit tech subs. Per-source diversity cap `{HN: 3, HN Best: 2, Show HN: 2, Lobsters: 2, Reddit: 3}`.
- **`feed_health.py`** race fix — lazy-init module-level `threading.Lock` around the write, `{pid}.{time_ns()}` suffix in the temp filename so cross-process concurrent runs also can't collide.

Post-rewrite metrics from the first live run:

| Metric | v1 | v2 |
|---|---|---|
| News topics filling (of 20) | 12/20 | 20/20 |
| Papers categories represented (of 10) | 3/10 | 5-8/10 (varies daily) |
| Tech source diversity | HN-dominated | HN + Lobsters + Reddit balanced |
| Fabrication risk | Non-zero (LLM URL mangling) | Zero (structural) |
| Full-run wall clock | ~120 min | ~15-25 min |

## "Still failing" (August 20 afternoon)

Post-rewrite, user reported:

> still failing I believe

Investigation showed the RSS-first streams were fine. The actual failure was **Google OAuth**: all 8 tokens (4 Gmail + 4 Calendar) had been returning `HTTP 400 invalid_grant` since **June 22-24**. Fifty-eight days of the Brief opening with two walls of warning callouts where the schedule and inbox should be.

Root cause: the OAuth consent screen was still in Testing mode. Refresh tokens in Testing mode expire in 7 days. The last successful grant was late June; from that point on, every morning wrote the same `[!warning] Calendars unreachable` block.

Fix path: publish the OAuth consent screen and re-run `oauth-grant.py` for each of the 8 accounts. Requires browser consent, so the fix wasn't applied autonomously.

## Publication (August 20 evening)

Sanitized the bundle (deleted `.env`, replaced personal emails with placeholders, replaced ROG MAC with `AA:BB:CC:DD:EE:FF`, replaced `/home/sarang/` paths with `/home/USER/`, replaced `User=sarang` with `User=USER`), initialized a git repo, published to `SarangVehale/hermes-morning-run` as a public repo, enabled GitHub Pages from `main:/docs` with the Cayman theme, wrote the initial CHANGELOG.md documenting v1.0 → v2.0.

## v2.1 (August 21) — decommissioning ROG

The morning of August 21, one more inversion:

> can you get rid of all the models from rog and add claude sonnet as the runner for every morning. and also all the files and overhead from rog. Anything related to our morning runs, clean up rog completely.

The reasoning was quiet but decisive. v2.0 had already stripped the LLM out of the news / papers / tech streams — those were pure RSS aggregation now. What remained on the LLM side was:

- Watchlist: transcript → summary. A few calls per morning.
- Curiosity: one synthesis call per morning.
- Weekly recap: one call per week.
- Odds and ends: `wikifill`, `connection-finder`, occasional `doctor` health checks.

That's ~15-20 LLM calls per morning. Not enough to justify:

- A 1.5GB `llama.cpp` build on the inference host.
- 27GB of GGUF models (Gemma-4-26B, Hermes-4-14B, Qwen2.5-3B).
- WoWLAN configuration and the magic-packet reliability dance.
- Two systemd services on the inference host.
- The 120-line "wake the ROG, wait for it, dispatch, power it back down" block in `morning-run.sh`.
- The occasional "ROG fans are ramping up" mystery when a run half-failed and left the machine on.

The user is already a Claude Code / claude.ai Pro subscriber. That subscription includes usage. Shelling out to `claude -p --model sonnet` gets an authenticated Sonnet 5 call for free (already-paid), with no per-token billing on top of the subscription.

Changes:

- **`llm.py`** — completely rewritten. Was: raw HTTP POST to `http://rog:8080/v1/chat/completions` (llama-server, Gemma) with fallback to `http://rog:8081` (Qwen) then to HP-local ollama. Now: `subprocess.run(["claude", "-p", "--model", "sonnet", "--restricted", "--output-format", "text", "--system-prompt", system])`, stdin = user prompt. HP-local ollama retained as fallback.
- **`morning-run.sh`** — 195 lines → 82 lines. Removed WoL block, ROG-up polling, `llama-server` start over SSH, `/v1/models` probe, `llama-server` stop, ROG poweroff, all `RYZEN_*` env knobs, `SKIP_ROG_START` / `SKIP_ROG_STOP` compatibility shims.
- **On the ROG** (via SSH): stopped and disabled `llama-server-primary.service` and `llama-server-fast.service` (user scope), deleted the unit files, `daemon-reload`ed, `rm -rf ~/models` (27GB), `rm -rf ~/llama.cpp` (1.5GB). Total freed: 28GB. Verification: zero units matching `llama|hermes|wowlan`, zero directories matching `models|llama.cpp|scripts|.hermes`.
- **In the published repo**: removed `systemd/llama-server-primary.service`, `systemd/llama-server-fallback.service`, `systemd/llama-server-heavy.service`.
- **Preserved**: HP-local ollama fallback (offline scenarios), all RSS-first stream code, Gmail/Calendar OAuth (still uses `~/.hermes/mcp-tokens/`), `concept-stubs.py`, `wikifill`, `connection-finder`.

Post-decommission architecture is one machine: an old laptop with Python and the `claude` CLI. Total wall-clock dropped from 15-25 min to 5-15 min (no more ROG cold-start latency, no more WoL wait window).

### Verification sweep

After the deletions, ran a 14-point cleanliness sweep on ROG. Anyone decommissioning their own inference host — for any reason, not just switching to a hosted LLM — can use this as a template.

```bash
ssh HOST '
echo "1.  systemd (user + system)";  systemctl --user list-unit-files | grep -Ei "llama|hermes|wowlan|morning|gemma|qwen"
                                     sudo systemctl list-unit-files    | grep -Ei "llama|hermes|wowlan|morning|gemma|qwen"
echo "2.  running processes";        ps auxf | grep -iE "llama|gemma|qwen|hermes|morning" | grep -v grep
echo "3.  listening ports";          ss -tln | awk "NR==1 || \$4 ~ /:808[0-9]|:11434/"
echo "4.  filesystem under /home";   find /home/USER -maxdepth 4 \( -iname "*llama*" -o -iname "*gguf*" -o -iname "*hermes*" -o -iname "*morning*" -o -iname "gemma*" -o -iname "qwen*" \)
echo "5.  ~/.config/systemd/user";   ls -la ~/.config/systemd/user/ | grep -Ei "llama|hermes|wowlan|morning"
echo "6.  ~/.local ~/.cache";        find ~/.local ~/.cache -maxdepth 4 \( -iname "*llama*" -o -iname "*gguf*" -o -iname "*hermes*" -o -iname "gemma*" -o -iname "qwen*" \)
echo "7.  /etc /opt /usr/local";     sudo find /etc /opt /usr/local -maxdepth 3 \( -iname "*llama*" -o -iname "*hermes*" -o -iname "*morning*" \)
echo "8.  cron";                     crontab -l; sudo crontab -l; ls /etc/cron.d/ /etc/cron.daily/ /etc/cron.hourly/ | grep -Ei "llama|hermes|morning"
echo "9.  shell rc";                 grep -HniE "LLAMA|HERMES|MORNING" ~/.bashrc ~/.zshrc ~/.profile ~/.bash_profile
echo "10. journal 24h";              journalctl --user --since "24 hours ago" | grep -iE "llama|hermes|morning"
echo "11. pip/uv packages";          pip list | grep -iE "llama|hermes|feedparser"; uv tool list | grep -iE "llama|hermes"
echo "12. WoWLAN state";             sudo iw phy0 wowlan show
echo "13. authorized_keys";          cat ~/.ssh/authorized_keys
echo "14. disk usage";               du -sh ~ && df -h ~ | tail -1
'
```

Anything printed under a numbered line is a residue worth investigating. Silence under a line means clean.

### What we found

| # | Check | Result |
|---|---|---|
| 1 | systemd unit files (both scopes) | clean |
| 2 | Running processes | clean |
| 3 | Listening ports (previously 8080/8081/8082) | clean |
| 4 | Filesystem under `/home` | clean |
| 5 | User systemd `.config` residue | clean |
| 6 | `~/.local` / `~/.cache` residue | clean |
| 7 | `/etc`, `/opt`, `/usr/local` | clean |
| 8 | Cron | clean |
| 9 | Shell rc files (env / aliases) | clean |
| 10 | Journal (last 24h) | clean (only match: the sweep itself) |
| 11 | pip / uv packages | clean |
| 12 | WoWLAN kernel state | see below |
| 13 | `authorized_keys` | 1 key (HP), kept — see below |
| 14 | Disk | 50 GB used / 740 GB (was 70 GB pre-cleanup — 28 GB freed) |

### Two edge cases worth writing down

**`iw phy0 wowlan show` → `Operation not supported (-95)`.** On the reference ROG (an Asus Flow X13 with a Mediatek MT7921 WiFi chip on Arch Linux mainline), the wowlan netlink interface isn't exposed by the driver at all. Both `show` and `disable` fail identically with `-95`. That's not a leftover to clean — it's the driver telling us the API doesn't exist. Whatever wake-on-WiFi was happening in v1.4 must have been at BIOS level (ASUS boards typically expose a "Wake on WLAN" toggle under Power Management), not via the kernel `iw` interface.

Practical consequence: if your inference host has the same driver, there is no post-decommission `wowlan disable` step to run. If your host does support wowlan via `iw`, verify with `sudo iw phy0 wowlan show` and clear with `sudo iw phy0 wowlan disable`.

**`~/.ssh/authorized_keys` on the ex-inference host.** After decommissioning, HP's key was still authorized on ROG. That key is what enabled every `ssh rog` command during this session (stopping services, deleting files, running verification sweeps). Removing it completes the "as if the pipeline never existed" state, at the cost of losing SSH admin access to ROG from HP.

Decision matrix:

| Purpose | Keep the key? |
|---|---|
| Occasional manual admin from HP (backups, updates, file copy) | Keep |
| Ability to bring the ex-inference host back into a pipeline later | Keep |
| Strict decommission to "no HP → ROG trust relationship" | Remove |

We kept it. Removing it — precisely, by matching the exact comment field:

```bash
# First: find the exact identifying string on the target
ssh HOST 'cat ~/.ssh/authorized_keys'   # → look at the comment after the key blob

# Then remove that specific line
ssh HOST "sed -i '/<the comment string>/d' ~/.ssh/authorized_keys"
```

Don't use a generic marker like `HP_KEY` unless the key's comment actually contains that string — `sed`'s pattern has to match the real text after the key blob (typically `user@host` or a manually-set label like `hp -> rog`).

{% include nav.html
  prev="index" prev_title="Home"
  next="architecture" next_title="Architecture" %}
