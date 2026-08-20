# Dry-run review checklist

What to look at the moment a `DRY_RUN=1 ~/scripts/morning-run.sh` finishes, before deciding to push + enable the timer.

## Step 0 — did the script complete cleanly

```
grep -E 'WARNING|FATAL|complete' ~/.hermes/logs/morning-run-$(date +%Y-%m-%d).log | tail -10
```

You should see one `morning-run complete` line and ideally no `FATAL`. `WARNING:` lines are OK (the script presses through), but read each one — they tell you what skipped.

## Step 1 — confirm the agent didn't fabricate

This is the #1 failure mode. Read the agent's final summary message in the log:

```
sed -n '/invoking hermes morning workflow/,/concept-stubs/p' \
  ~/.hermes/logs/morning-run-$(date +%Y-%m-%d).log | head -100
```

**Smoking gun phrases to watch for** (any of these = hallucination, do NOT push):

- "simulated fetches"
- "available data"
- "structurally complete digest"
- "subagent timeout" followed by content still being written
- "due to" + "manually" + "completed"

If you see any, the dry run failed regardless of whether files got written.

## Step 2 — spot-check each note for plausibility

```
cd ~/vault-ai
git show HEAD --stat
```

Then for each touched file, look at today's section:

```
git show HEAD:"01 Updates/📰 Daily News.md" | head -50
git show HEAD:"01 Updates/🎬 Daily Watchlist.md" | head -30
git show HEAD:"01 Updates/📄 Daily Papers.md" | head -30
git show HEAD:"01 Updates/🔬 Daily Tech.md" | head -30
git show HEAD:"01 Updates/🔄 GitHub Releases.md" | head -20
git show HEAD:"01 Updates/📌 Daily Brief.md" | head -50
git show HEAD:"01 Updates/📥 Email Triage.md" | head -30
git show HEAD:"🏠 Dashboard.md" | head -30
```

**Red flags per stream:**

| Stream | Red flag |
|---|---|
| News | URLs ending in `.../12345`, `lorem-ipsum-`, no real outlet name in slug, dates that don't match today |
| Watchlist | Creator names from the example block (Veritasium, Alex Ziskind) WITHOUT a real YouTube video URL containing a 11-char video ID like `dQw4w9WgXcQ` |
| Papers | arXiv IDs from the example block (`2505.18234`), or any arXiv ID with `v2`/`v3` suffix the agent guessed without fetching |
| Tech | "Show HN: my SaaS" or anything that reads like a startup launch from the agent's training data instead of a real HN top-50 |
| GitHub Releases | Release tags that don't actually exist on GitHub (browse to `github.com/<repo>/releases` to check) |
| Brief — Email | Senders "Prof. Joshi", "Anjali", "Rohan Mehta", subjects like "Quantum-ECC chapter draft" — all from the example block |
| Brief — Scheduled today | Event "Research Sync" or attendee "Rohan Mehta" — example-block values |
| Brief — Tasks | "Submit ECC draft" or "Implement noise model simulation" — these come from the example block, never from `📋 Tasks.md` which today contains only first-run placeholders |
| Brief — Carryover/Open threads | "Finish reading [[arXiv 2505.18234]]" — example value |
| Dashboard | Any of the above (Dashboard pulls from Brief) |

**Green flags** (good signs the agent did real work):

- News articles have URLs you can paste into a browser and they load real articles, dated today (or close)
- Watchlist items link to summary files in `08 Summaries/` and those summaries reference real, fetched transcripts (search a phrase from the summary against the actual video to verify)
- Tasks section says "Nothing due today." because `📋 Tasks.md` is mostly placeholders — that's HONEST, not a failure
- Brief's email section is empty or has 1-5 real entries that you can find in your actual Gmail
- Scheduled today shows real meetings/events from your real calendar — cross-check with calendar.google.com

## Step 3 — markdown rendering check

Open `~/vault-ai/🏠 Dashboard.md` in Obsidian. The Brief and the stream notes should render as designed. Things to check visually:

- Heatmap renders (not just a code block of text)
- Streak count shows a number (not "0 days" if dashboard has been opened before)
- Scheduled today / Email / Tasks / Open threads are inline visible (NOT collapsed)
- News / Watchlist / Papers / Tech / GitHub Releases callouts are COLLAPSED — single line each with `▶` triangle
- Each section heading has the small `↗` arrow next to it as a clickable wikilink
- Tap each `↗` — should navigate to the source note

Common Obsidian-rendering bugs from the agent:

- Callouts that should be `> [!note]-` but the agent wrote `[!note]-` (missing the leading `> `) — render as plain text
- Wikilinks with broken syntax (`[[ ` instead of `[[`)
- Frontmatter with bad YAML (would make Obsidian show a parse error)
- Strikethrough using `--` instead of `~~`

## Step 4 — concept stubs

```
ls ~/vault-ai/04\ People/*.md 2>/dev/null | wc -l
ls ~/vault-ai/07\ References/*.md 2>/dev/null | wc -l
ls ~/vault-ai/06\ Research/*.md 2>/dev/null | wc -l
```

Should have a non-trivial number of new stub files (the concept-stubs.py post-run pass creates them from dangling wikilinks). Each stub file should contain:
- Frontmatter only (no AI-generated body)
- Fields: `created`, `updated`, `unread: true`, `stub: true`, optional `first_referenced_in`
- NO summary, biography, or descriptive text — the rule is bodies stay empty until you fill them.

If you find stub files with bodies, that's a hallucination — concept-stubs.py should never write content beyond frontmatter.

## Step 5 — decide

- All green: `git push origin main` then `sudo systemctl enable --now hermes-morning.timer hermes-weekly.timer`. Tomorrow morning at 05:55 IST you get a real run.
- Mixed (mostly real but one stream hallucinated): revert the dry-run commit (`git reset --hard HEAD~1`), iterate on that stream's prompt callout (add stricter "never invent" wording, list specific tools to call), re-run.
- All hallucinated: revert, hard look at why the agent isn't reaching its tools (timeout? wrong subagent config? network?), fix, re-run.

## Step 6 — if pushing, mobile clones

After push succeeds:
- On Android Obsidian Git: Command palette → "Obsidian Git: Clone an existing remote repo" → wait for clone to finish.
- On iPad: same, or via Working Copy.
- Confirm sync works both directions with a test edit (see `mobile-setup-procedure.md` Step 3 for the verify steps).
