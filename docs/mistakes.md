# Mistakes

Every entry here is a real war story from three months of daily production runs. Names, dates, and diffs preserved so you can see the shape of the failure and — where relevant — the shape of the fix. This page is didactic, not defensive: the goal is that a reader who forks this repo can avoid re-learning what we already broke.

<div class="toc"><div class="toc-title">On this page</div>
<ul>
  <li><a href="#the-llm-mangled-urls-in-structured-output">The LLM mangled URLs in structured output</a></li>
  <li><a href="#papers-was-biased-to-three-arxiv-categories">Papers was biased to three arXiv categories</a></li>
  <li><a href="#the-two-month-oauth-outage">The two-month OAuth outage</a></li>
  <li><a href="#the-heartbeat-that-lied">The heartbeat that lied</a></li>
  <li><a href="#feed-health-race-condition">feed-health race condition</a></li>
  <li><a href="#the-two-machine-architecture-that-was-overkill">The two-machine architecture that was overkill</a></li>
  <li><a href="#reddit-429-storms">Reddit 429 storms</a></li>
  <li><a href="#the-hermes-morning10-user-agent">The hermes-morning/1.0 User-Agent</a></li>
  <li><a href="#the-rog-fan-mystery">The ROG fan mystery</a></li>
  <li><a href="#the-75-success-rate-that-was-actually-40">The "75% success rate" that was actually 40%</a></li>
  <li><a href="#the--staging-zip-file-that-almost-got-published">The _staging zip file that almost got published</a></li>
</ul>
</div>

## The LLM mangled URLs in structured output

**When.** Continuously from v1.0 through v1.5. Discovered concretely around August 15.

**What broke.** The v1 news pipeline fed candidate items (title + URL + snippet) to Gemma-4-26B and asked it to return JSON with the selected picks. A post-hoc validator compared each returned URL to the input pool by exact string match, and rejected anything that didn't match — because a URL the model *invented* is a hallucination we must not render.

The problem: the model often kept the URL almost right but with one of these mutations:

- Truncated trailing digits: `article12345678` → `article12345`
- URL-encoded `?` as `%3F` (semantically identical but string-different): `?utm=foo` → `%3Futm=foo`
- Added a trailing `.` from the end of a sentence: `example.com/story` → `example.com/story.`
- Dropped a trailing slash: `example.com/story/` → `example.com/story`

Exact-match rejection was correct — those characters really can matter (many CMSes 404 on a truncated slug). But it meant **8 of 20 news topics wrote `[!warning] No qualifying story surfaced today.` every single day**, even when the input RSS had five perfectly good candidates.

**Why we didn't fix it in place.** Every fix considered was worse:

- **Fuzzy-match the URL to the pool.** Fuzzy matching lets a truncated slug through, which then 404s when the reader clicks it. Rendering a broken link is worse than rendering a `[!warning]`.
- **Normalize both sides before compare.** Solves the `?/%3F` case but not the truncation case, and adds an entire URL-normalization dependency we didn't want.
- **Trust the LLM's URL and don't validate.** No. This is exactly the fabrication mode the pipeline exists to prevent.
- **Prompt-engineer the model harder.** Tried. Gemma-4-26B kept doing it. The failure mode is inherent to generative decoding — the model gets attention on the URL, generates plausible tokens, and if the exact tokens require the model to precisely copy 40 characters including a random-looking hash, it will sometimes not.

**The fix (v2.0).** Rewrite `news.py`, `papers.py`, `tech.py` to be RSS-first. Render the URL that came from the RSS feed. Don't ever hand a URL to the LLM and ask for it back.

The lesson isn't "LLMs hallucinate URLs" (obvious). It's "the failure mode of LLM-structured-output validation is unfixable in-place — you have to remove the LLM from the loop entirely for tasks where the answer is a URL you already have."

## Papers was biased to three arXiv categories

**When.** From v1.0 launch through v1.5.

**What broke.** The v1 `papers.py` fetched all ~8 configured arXiv categories, dumped every abstract into one big pool, and asked the LLM to pick the 3-5 most interesting. The LLM always picked from three of them: `quant-ph`, `cs.AI`, `cs.LG`.

The other five categories (`cs.IT`, `cond-mat.mes-hall`, `cond-mat.str-el`, `cond-mat.quant-gas`, `physics.comp-ph`) had fresh papers every day and *never* got surfaced. Over 6 weeks, zero papers from `physics.comp-ph`.

**Why.** LLM curation is aesthetic. Given a menu of "here's a paper about quantum error correction thresholds" and "here's a paper about tensor networks for correlated materials", the model picks the first because it's more famous, more meme-adjacent, more like the training corpus. It's not wrong that quant-ph is exciting; it's wrong that the pipeline let the model's aesthetic preferences filter out entire physics subfields.

**The fix (v2.0).** Round-robin selection. Every configured category gets a fresh look each day. The picker walks categories in order, taking one paper per category before starting a second round. Per-category cap (`MAX_PER_CATEGORY_PICKED=2`) prevents any one from dominating even after round-robin resolves.

Post-fix: 5-8 categories represented daily vs previous 3.

Lesson: **any LLM-driven ranking will develop favorites.** For a "surface everything eventually" pipeline you want deterministic round-robin, not learned relevance.

## The two-month OAuth outage

**When.** June 24 → August 20. Fifty-eight days.

**What broke.** All 8 Google OAuth refresh tokens (4 Gmail + 4 Calendar) returned `HTTP 400 invalid_grant` on every refresh attempt. Every Daily Brief for two months opened with two big walls of `[!warning]` where the schedule and inbox should be.

**Why nobody noticed for two months.**

1. The user's *actual* schedule and inbox were being read from phone apps, not the Brief. The Brief was aspirational — a "would be nice if" — not a required workflow.
2. The `[!warning]` blocks were long and ugly, so the user started scrolling past them out of habit.
3. Every stream *below* those blocks (news, papers, tech, watchlist, curiosity) worked fine, so the vault looked "mostly ok".
4. The `last_run.json` heartbeat said `streams.brief: true`. The composer wrote the warnings and exited 0. From the runner's perspective, it succeeded.

**Root cause.** Google OAuth consent screens in **Testing mode** issue refresh tokens that expire after 7 days. Publishing the consent screen removes this restriction. We never published it because Testing mode was "fine for one user" — except the user forgot to re-grant after the tokens quietly rotted.

**The fix path.** Requires user action (browser consent flow):

1. Publish the OAuth consent screen in Google Cloud Console.
2. Re-run `oauth-grant.py` for each of the 8 accounts.
3. Verify token freshness in `~/.hermes/mcp-tokens/*.json` mtime.

**Lessons.**

- **A `[!warning]` in the vault is not a monitoring signal.** If the user scrolls past it once, they'll scroll past it every day. Silent degradation over 58 days is the failure of monitoring, not of Google.
- **`streams.X: true` in the heartbeat is not a success signal.** It's a "the script exited 0" signal. The right question is "did the vault get content the user will read", which is a semantic check the heartbeat can't do.
- **Publish OAuth consent screens on day one.** The 7-day expiry is unforgivably user-hostile for a personal-use pipeline.

## The heartbeat that lied

**When.** Latent from v1.0. Discovered August 20 during the "still failing" investigation.

**What broke.** `runner.py` orchestrates streams under `concurrent.futures.ThreadPoolExecutor` with per-stream `future.result(timeout=budget)`. When `budget` (e.g. 1800s) elapses, `TimeoutError` fires. The runner catches it, marks the stream `ok: false` with `error: "Stream exceeded 1800s timeout"`, and moves on.

But the *thread itself keeps running*. `Future.result(timeout=…)` doesn't cancel the underlying computation — it just gives up waiting. The stream code often finishes its work seconds after the timeout wall, writes its callout into the vault file, and exits cleanly. The vault has content. The heartbeat says failure.

**Why it matters.** The Brief composer reads `last_run.json` to know which streams to summarize. On a late-thread day, the composer sees `news: false` and writes `[!warning] news stream failed` in the Brief — even though the actual `📰 Daily News.md` has today's content.

**Fix (planned but not applied as of v2.1).** The Brief composer should read from the stream files directly, not `last_run.json`. Look for today's anchor (`### [[MM-DD-YY DDD]]`); if present, treat the stream as successful. Since v2.1 the RSS-first streams are all so fast (< 15s) that this rarely fires — but it's still the correct fix.

**Lesson.** Timeouts are advisory in thread pools. Any system that trusts a timeout as a completion signal is lying to itself.

## feed-health race condition

**When.** Latent from v1.5 (when `feed_health.py` was written). Discovered August 20.

**What broke.** `_save()` wrote to a shared temp file:

```python
def _save(state):
    tmp = STATE_FILE.with_suffix(".tmp")  # ← always ".tmp", no unique suffix
    tmp.write_text(json.dumps(state), encoding="utf-8")
    tmp.replace(STATE_FILE)
```

Under `ThreadPoolExecutor` fanout across news topics (each topic making its own parallel RSS fetches), two threads could:

1. Both call `_save()` at the same time.
2. Both write to `feed-health.tmp`.
3. Both call `tmp.replace(STATE_FILE)`.
4. The first winner renames `feed-health.tmp` → `feed-health.json`. Now `feed-health.tmp` no longer exists.
5. The loser's `tmp.replace(STATE_FILE)` raises `FileNotFoundError`.

The result: sporadic `FileNotFoundError` in the logs, and depending on timing, corrupted state (a save that was overwritten by an older concurrent save).

**Fix (v2.0).**

```python
_LOCK = None  # lazy-init module-level lock

def _save(state):
    global _LOCK
    if _LOCK is None:
        import threading
        _LOCK = threading.Lock()
    with _LOCK:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        import os, time as _t
        tmp = STATE_FILE.with_suffix(f".{os.getpid()}.{_t.time_ns()}.tmp")
        tmp.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(STATE_FILE)
```

Two pieces to the fix:

1. **`threading.Lock`** serializes writes *within* one Python process.
2. **`{pid}.{time_ns()}` suffix** on the temp filename prevents collisions *across* processes (two concurrent morning runs — unlikely but possible if the timer fires while a previous run is still going).

Lazy-init because we don't want to `import threading` at module load time for a lock that will never be contended in the single-threaded case.

**Lesson.** "Write to `.tmp`, then `os.replace()`" is the standard atomic-write pattern. It's atomic *per rename call*, not atomic *across concurrent callers*. If more than one thing writes to the same target file, you need a lock or a unique temp path (or both).

## The two-machine architecture that was overkill

**When.** Baked into v1.0. Reversed in v2.1 (today).

**What broke.** The v1 design assumed the LLM was doing heavy lifting — selecting news, summarizing 20 stream items, curating papers, plus watchlist transcript summarization. On that assumption, a two-machine split made sense: keep the always-on machine cheap (no GPU), let the GPU machine sleep between runs.

Once v2.0 stripped the LLM out of news / papers / tech, LLM usage dropped to:

- Watchlist summaries (~10 calls/day)
- Curiosity synthesis (1 call/day)
- Weekly recap (1 call/week)
- Odd doctor / wikifill / releases calls (~3-5/day)

Total: ~15-20 calls per morning. On a Pro-subscription Claude Sonnet 5 endpoint, that's ~1-2 minutes of cumulative LLM time. It did not justify:

- 27GB of GGUF model files on the inference host
- 1.5GB llama.cpp build
- Two systemd `llama-server-*` services
- WoWLAN configuration
- The magic-packet WoL dance in `morning-run.sh` (~120 lines)
- The occasional "ROG fans are ramping up" mystery
- The user's daily-driver ROG being woken up and shut down every morning

**Fix (v2.1).**

- Rewrote `llm.py` to shell out to `claude -p --model sonnet --restricted`.
- Stripped 113 lines from `morning-run.sh`.
- Deleted 3 systemd unit files.
- SSH'd to ROG, stopped and disabled the llama-server services, deleted the units, `rm -rf ~/models ~/llama.cpp` (28GB freed).

**Lesson.** Architecture should follow *current* usage, not aspirational usage. The two-machine split was justified when the LLM was doing everything. Once the LLM's job shrank, keeping the second machine was cost without benefit. Right-sizing is a design skill; downsizing is a design *courage* — it means admitting yesterday's decision no longer fits.

**Sub-lesson from the cleanup.** Ripping out a component is not the same as verifying it's gone. After stopping services and deleting files, we ran a 14-point sweep (systemd both scopes, processes, ports, filesystem, `.config`, `.local`, `.cache`, `/etc`, cron, shell rc, journal, packages, kernel state, `authorized_keys`) and found the deletion was clean — but the same sweep also surfaced two things that would have quietly persisted otherwise: the WoWLAN kernel-state check that returned `-95` (driver doesn't expose the API — nothing to disable, but worth *confirming* rather than assuming), and the SSH trust relationship in `~/.ssh/authorized_keys` that's silently unaffected by "stop and delete" and needs its own explicit decision. Full sweep and both edge cases are documented in [History → v2.1 verification sweep](history.html#verification-sweep).

## Reddit 429 storms

**When.** Continuously from v1.0 through v1.5.

**What broke.** Reddit's `www.reddit.com/r/{sub}/top.json` endpoint aggressively 429s from residential IPs after ~3-4 requests per minute. The v1 tech stream fetched 5-10 subs sequentially with no delay, so runs #4 onward got throttled — the tech stream would show 2 Reddit items instead of the target 10.

**Fix (v1.5).**

- Switch from `www.reddit.com/r/{sub}/top.json` to `https://old.reddit.com/r/{sub}/.rss`. `old.reddit.com` is less aggressively throttled.
- Send a browser User-Agent (`Mozilla/5.0 ... Firefox/128.0`) instead of `hermes-morning/1.0`.
- Add `time.sleep(1.5)` between subreddit fetches.

Post-fix 429 rate: near zero. Cost: adds ~10-15s to the tech stream.

**Lesson.** APIs and API-like RSS endpoints are the polite path. Some outlets treat them as premium and throttle heavily; the plain public feed is often less-rate-limited. Also — polite delays cost you seconds; getting throttled costs you the entire feed.

## The hermes-morning/1.0 User-Agent

**When.** Continuously until v1.5.

**What broke.** Several outlets 403'd our `hermes-morning/1.0 (contact@example.com)` User-Agent — Ars Technica (security feed especially), some Nature Group properties, occasionally The Verge. Their WAFs classify anything that doesn't look like a browser as suspicious.

**Fix (v1.5).** RSS fetches use `Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0`. 403 rate dropped to zero on the affected outlets.

**Lesson.** "Identify yourself politely with a contact email" is old advice. The modern web treats non-browser UAs as adversarial. If you want to read public content, look like a browser.

## The ROG fan mystery

**When.** Roughly August 10-18.

**What broke.** Randomly, the ROG's fans would ramp up loudly in the middle of the day when nothing was supposed to be running. The user's daily driver was hot and noisy.

**Investigation.** The morning-run.sh script sent a WoL packet, waited for ping, started `llama-server`, dispatched work, then powered ROG off at the end. When a run *half-failed* — say, ssh to ROG timed out during the "stop llama-server" step — the poweroff never fired. ROG stayed awake, with `llama-server` still running, using GPU and thermal headroom.

The next morning's timer fired WoL again, sent it a fresh magic packet, but ROG was already awake so nothing changed; the run proceeded and started *another* pair of `llama-server` processes (or, if they were already up, silently skipped starting them). Over a few days, the ROG accumulated orphaned llama-server processes and never got the poweroff.

**Fix at the time (partial).** Wrapped every ssh call in `|| log "WARNING: ..."` so a single failure didn't abort the script, and made `poweroff` run unconditionally at the end. Not a real fix — a plaster over the systemic problem, which was that the pipeline's state assumed ROG cleanly powered off between runs.

**Real fix (v2.1).** Decommission ROG entirely. No ROG, no fans, no ambiguous state.

**Lesson.** When a component's normal operation depends on a cleanup step that occasionally fails, the state model is wrong. Cleanup should be idempotent and safe to skip; the next run should tolerate whatever mess the previous run left.

## The "75% success rate" that was actually 40%

**When.** August 19, during the audit.

**What broke.** Initial audit reported ~75% of streams "successful". User pushed back:

> that is not 75% success. That is more than 50% failure as other than there is just curiosity, tech news (which I care much less about) and papers. Which was also just 2 papers and that too all out of arxiv. Which is still quite terrible.

**Root cause of the misleading number.** "Success" was defined as `script.exit_code == 0`. The `[!warning]` callouts count as success under that definition — the script did exit 0, even though it filled the vault with warnings.

The right definition of success for a daily-briefing pipeline is *reading-value*: how much of what landed in the vault was actually worth reading. By that measure, with news failing on 8/20 topics, papers producing 2 items from 1 category, and the Brief opening with two OAuth-outage warning walls, the reading-value was closer to 40%.

**Fix.** Recalibrated all subsequent reporting to reading-value. `success_rate = items_the_user_would_actually_read / items_the_user_expects_daily`.

**Lesson.** Choose the metric that matches the user's experience, not the one that's easy to compute. "Did it exit 0" is easy; "was it useful" is what matters.

## The _staging zip file that almost got published

**When.** August 20, during the public repo publication.

**What almost broke.** The bundle at `/home/sarang/Development/hermes-vault-setup/` contained an unrelated `ai-life-skills-main(1).zip` (60KB, from an old planning session, dated June 4). It would have been published to the public GitHub repo unless caught.

**How it was caught.** A file scan for `du -sh /home/sarang/Development/hermes-vault-setup/*` listed all files. The zip stood out because its name matched no obvious pipeline component. A quick `unzip -l` showed it was a snapshot of an unrelated skill authoring project.

**Fix.** Deleted before the initial commit. Added `*.zip` to `.gitignore`.

**Lesson.** Before publishing a bundle to a public repo, list *every file* and confirm each has a reason to be there. Sanitize scans catch secrets. They don't catch "wrong stuff even if not secret".

{% include nav.html
  prev="troubleshooting" prev_title="Troubleshooting"
  next="changelog" next_title="Changelog" %}
