# Troubleshooting

Every entry here corresponds to something that actually broke in production over three months of daily runs. When it broke again, you'd want to remember what the fix was — so it's written down.

<div class="toc"><div class="toc-title">On this page</div>
<ul>
  <li><a href="#the-morning-brief-is-empty-or-has-warnings-everywhere">The morning Brief is empty or has warnings everywhere</a></li>
  <li><a href="#oauth-invalid_grant-across-all-accounts">OAuth invalid_grant across all accounts</a></li>
  <li><a href="#claude--p-returns-not-logged-in">claude -p returns "Not logged in"</a></li>
  <li><a href="#reddit-429-storms">Reddit 429 storms</a></li>
  <li><a href="#dead-rss-feeds">Dead RSS feeds</a></li>
  <li><a href="#ars-technica--other-outlets-403">Ars Technica &amp; other outlets 403</a></li>
  <li><a href="#feed-health-json-race-condition">feed-health.json race condition</a></li>
  <li><a href="#watchlist-yt-dlp-transcript-fails">Watchlist yt-dlp transcript fails</a></li>
  <li><a href="#systemd-timer-drifts-past-05-55">systemd timer drifts past 05:55</a></li>
  <li><a href="#git-conflicts-when-mobile-and-desktop-both-edit">Git conflicts when mobile and desktop both edit</a></li>
  <li><a href="#run-log--heartbeat--vault-lie-about-status">Run log / heartbeat / vault lie about status</a></li>
  <li><a href="#the-diagnostic-command-index">The diagnostic command index</a></li>
  <li><a href="#verifying-a-clean-decommission">Verifying a clean decommission</a></li>
</ul>
</div>

## The morning Brief is empty or has warnings everywhere

**Symptoms.** Open the Daily Brief and it opens with two big walls of `[!warning]` — "Calendars unreachable" and "All 4 Gmail accounts unreachable". Streams below may or may not have content.

**Diagnostic.**

```bash
cat ~/.hermes/state/last_run.json | jq
# Look at the `streams` object. `true` means the script exited 0.
# That does NOT mean the vault has content — check the actual note.
```

If `streams.brief` is `true` but the Brief looks broken, the issue is inside the composer — most often OAuth (next section).

## OAuth invalid_grant across all accounts

**Symptoms.** Brief opens with `[!warning] Calendars unreachable — events not loaded` followed by four `HTTP 400 — {"error": "invalid_grant", ...}` errors, one per account.

**Diagnostic.**

```bash
stat -c "%y  %n" ~/.hermes/mcp-tokens/*.json | grep -v -E "meta|client"
# When was the most recent successful refresh?
# If the most recent is > 7 days ago, refresh tokens have almost certainly expired.
```

**Root cause.** Google OAuth "Testing mode" apps issue refresh tokens that expire after 7 days. If the OAuth consent screen has never been published, every token dies weekly.

**Fix.**

1. Go to [console.cloud.google.com](https://console.cloud.google.com/) → OAuth consent screen → **Publish**. This removes the 7-day expiry.
2. Re-grant each account:
   ```bash
   for a in gmail_personal gmail_work gmail_iitm gmail_nfsu \
            calendar_personal calendar_work calendar_iitm calendar_nfsu; do
     python3 ~/scripts/oauth-grant.py "$a"
   done
   ```
3. Verify:
   ```bash
   python3 -c "
   import sys, json, urllib.request
   sys.path.insert(0, '/home/USER/scripts')
   from morning import google
   for acct in google.GMAIL_ACCOUNTS:
       try:
           t = google.access_token_for(acct)
           print(f'{acct}: OK ({len(t)} chars)')
       except Exception as e:
           print(f'{acct}: FAIL — {e}')
   "
   ```

## claude -p returns "Not logged in"

**Symptoms.** LLM streams (watchlist, curiosity, weekly) log `LLMError: claude returned no usable output: Not logged in · Please run /login`.

**Diagnostic.**

```bash
claude auth status
# should show loggedIn: true
```

**Fix.**

```bash
claude /login
```

Log in via the browser tab. Verify with the smoke test in [Setup](setup.html#claude-cli-auth).

<div class="callout warn"><div class="callout-title">Don't use --bare</div>
The <code>claude --bare</code> flag skips keychain reads and returns "Not logged in" even for a logged-in user. Only <code>--restricted</code> is safe for scripted use.
</div>

## Reddit 429 storms

**Symptoms.** `tech` stream returns almost no Reddit items. `~/.hermes/state/feed-health.json` shows Reddit URLs with high `consecutive_failures`.

**Root cause.** Reddit aggressively rate-limits the `www.reddit.com` JSON API. Some source IPs get 429s within 3-4 requests per minute.

**Fix.** Already in place since v1.5:

- All Reddit fetches go to `old.reddit.com` (less throttled).
- A browser User-Agent (`Mozilla/5.0 (…) Firefox/128.0`) instead of the old `hermes-morning/1.0` identifier.
- A `time.sleep(1.5)` between subreddit fetches in `tech.py`.

If it's *still* failing after all that, drop the number of configured subs in `~/.hermes/morning-config.yaml` or increase the polite delay:

```python
# In tech.py, `_fetch_reddit` fan-out:
for i, sub in enumerate(SUBREDDITS):
    if i > 0:
        time.sleep(3.0)  # ← increase
```

## Dead RSS feeds

**Symptoms.** A source shows up with high `consecutive_failures` in `feed-health.json`. A specific topic goes empty repeatedly.

**Diagnostic.**

```bash
jq 'to_entries | map(select(.value.consecutive_failures >= 3)) | .[] | {url:.key, fails:.value.consecutive_failures, reason:.value.last_reason}' \
  ~/.hermes/state/feed-health.json
```

**Fix.** Manually verify the URL in a browser. If the feed has moved, update the URL in `morning-config.yaml`. If the outlet has dropped RSS entirely, find an alternative (Bandcamp Daily for Pitchfork, Letterboxd for Criterion, Hyperallergic for Frieze, etc. — see [History](history.html#v15-august-9--failsafes-and-feed-rot-repair) for the replacement pattern).

Reset the health counter after fixing:

```bash
jq --arg url 'https://newurl.example.com/rss' \
   'del(.[$url])' \
   ~/.hermes/state/feed-health.json > /tmp/fh.json && mv /tmp/fh.json ~/.hermes/state/feed-health.json
```

## Ars Technica & other outlets 403

**Symptoms.** A specific outlet (Ars Technica security feed, some Nature Group feeds, occasionally The Verge) returns HTTP 403 with the pipeline's default UA.

**Fix.** Already in place — RSS fetches use a browser UA (`Mozilla/5.0 (…) Firefox/128.0`) since v2.0. If a new outlet 403s despite that, add it to the `primp`-backed browser-impersonation fetch path.

## feed-health.json race condition

**Symptoms.** Sporadic `FileNotFoundError: '/home/USER/.hermes/state/feed-health.tmp' -> '/home/USER/.hermes/state/feed-health.json'` in the log. Happens more often on days with many parallel RSS fetches.

**Root cause.** Two concurrent RSS fetches both write to the same temp file, then race to `Path.replace()`. Whoever loses gets `FileNotFoundError` because the winner's rename already moved the temp file into place.

**Fix.** In place since v2.0. `feed_health._save()` uses a lazy-init module-level `threading.Lock` plus `{pid}.{time_ns()}` suffix on the temp filename. See [Mistakes](mistakes.html#feed-health-race-condition).

If it recurs after v2.0, check that the deployed `feed_health.py` is actually the current version:

```bash
grep "_LOCK\|time_ns" ~/scripts/morning/feed_health.py
# Should show both the lock and the tmp-suffix logic
```

## Watchlist yt-dlp transcript fails

**Symptoms.** A specific video in `08 Summaries/{Creator}/` is missing. Watchlist stream note has `[!warning] transcript unavailable for {video_id}`.

**Root cause.** Not every YouTube video has auto-generated captions. `yt-dlp --skip-download --write-auto-sub` returns nothing.

**Fix.** Nothing to do — the pipeline correctly logs `[!warning]` and moves on. The design decision was: never transcribe audio ourselves (would need Whisper on the LLM host, adding cost and latency); skip the video with a visible warning instead.

If yt-dlp itself is failing (older version, blocked by YouTube's rotating tokens), update:

```bash
~/.hermes/morning-venv/bin/pip install -U yt-dlp
```

## systemd timer drifts past 05:55

**Symptoms.** `journalctl --user -u hermes-morning.timer` shows the next fire past 06:00 or later. Vault updates land late on the phone.

**Diagnostic.**

```bash
systemctl --user list-timers hermes-morning.timer
```

**Fix.** Usually the timer file lacks `Persistent=true`, so a missed fire (laptop sleeping at 05:55) never catches up. Confirm:

```bash
grep Persistent ~/.config/systemd/user/hermes-morning.timer
# Should show: Persistent=true
```

If missing, add it under `[Timer]`, then:

```bash
systemctl --user daemon-reload
systemctl --user restart hermes-morning.timer
```

## Git conflicts when mobile and desktop both edit

**Symptoms.** `git pull --rebase` at the start of the morning run fails with a merge conflict. Vault content differs between phone and desktop.

**Policy.** In the reference deployment: **remote wins for phone-edited paths, local wins for pipeline-generated paths.** Rationale: the pipeline is destructive-idempotent (running again reproduces its output), but manual notes are not.

**Manual recovery.**

```bash
cd ~/vault-ai
git status  # what's conflicting?
# For pipeline-generated paths (01 Updates/, 08 Summaries/), prefer local:
git checkout --ours "01 Updates/📌 Daily Brief.md"
# For manually-edited paths (04 People/, 05 Projects/), prefer remote:
git checkout --theirs "05 Projects/Some Project.md"
git add -A
git rebase --continue
git push
```

## Run log / heartbeat / vault lie about status

**Symptoms.** `~/.hermes/state/last_run.json` says `streams.news: true` but today's Daily News.md has no entry for today.

**Root cause.** `concurrent.futures.ThreadPoolExecutor.future.result(timeout=budget)` raises `TimeoutError` but the underlying thread keeps running and can still write content later. The runner reports failure to the composer even though the stream file eventually got content.

**Fix (not applied as of v2.1).** Have the Brief composer read from the stream files directly rather than trusting `last_run.json`. Planned but not yet implemented.

**Workaround.** Check the actual vault file, not the heartbeat:

```bash
grep -c "^### " "/home/USER/vault-ai/01 Updates/📰 Daily News.md" | head
# Count of day-headings — a today-anchor should be at the top
```

## The diagnostic command index

The commands you actually reach for, in one place:

```bash
# Was the last run successful (in the "script exited 0" sense)?
cat ~/.hermes/state/last_run.json | jq

# Which streams took the longest?
jq '.timings_ms' ~/.hermes/state/last_run.json

# Which feeds are dying?
jq 'to_entries | map(select(.value.consecutive_failures >= 3))' \
  ~/.hermes/state/feed-health.json

# Are OAuth tokens fresh?
stat -c "%y  %n" ~/.hermes/mcp-tokens/*.json | grep -v -E "meta|client"

# Is claude CLI logged in?
claude auth status

# Is the timer scheduled correctly?
systemctl --user list-timers hermes-morning.timer

# What happened in the most recent run?
tail -100 ~/.hermes/logs/morning-run-$(date +%Y-%m-%d).log

# Manually trigger a run (dry-run — no push)?
DRY_RUN=1 ~/scripts/morning-run.sh
```

## Verifying a clean decommission

If you're removing an inference host (or any secondary machine the pipeline used to touch) and want to confirm nothing was left behind, the [History → v2.1 verification sweep](history.html#verification-sweep) has a 14-point checklist that runs entirely from a single SSH command block. It catches systemd units in both scopes, running processes, listening ports, filesystem residue in every plausible location, cron entries, shell rc edits, journal traces, installed packages, WoWLAN kernel state, and disk-freed accounting.

Two edge cases documented from real experience:

- On some Linux WiFi drivers (e.g. Mediatek MT7921), `iw phy0 wowlan show` returns `Operation not supported (-95)` — the driver simply doesn't expose the wowlan interface. That's not a residue; there's nothing to disable. If wake-on-WiFi was ever set up, it was at BIOS level.
- The ex-inference host's `~/.ssh/authorized_keys` will still contain the orchestrator's key. Removing it completes the "no trust relationship" state at the cost of SSH admin access; keeping it preserves manual admin at the cost of a lingering trust link. Decide explicitly rather than by default.

{% include nav.html
  prev="setup" prev_title="Setup"
  next="mistakes" next_title="Mistakes" %}
