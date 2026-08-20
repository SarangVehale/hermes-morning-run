---
created: 2026-06-01
updated: 2026-06-01
regenerated_by: hermes
unread: false
---

> [!prompt]- Agent Instructions for Dashboard regeneration
> Regenerate this file at the end of every morning run, after all stream skills have completed and the Daily Brief has been generated.
>
> Steps:
> 1. **Archive yesterday's dashboard.** Read the current `🏠 Dashboard.md`. Copy to `02 Daily/{prev_year}/{prev_month}/{prev_MM-DD-YY ddd} dashboard.md` if not already archived. (Skip if the existing dashboard is already from today — handles re-runs.)
> 2. **Overwrite this file** with today's dashboard content following the structure below.
>
> Keep this prompt callout at the top — it's the agent's spec for regeneration.
>
> Structure:
>
> ### Top — heatmap and streak
>
> The heatmap-calendar code block (see below) renders the GitHub-style year heatmap. The streak number is computed by reading `02 Daily/` files in reverse chronological order and counting consecutive days where the daily note's `mtime > created` (i.e. the user opened it).
>
> ### Below heatmap — today's date and key stats
>
> One line. Date, day of week, weather one-liner from the Brief.
>
> ### Body — today's brief sections in collapsed callouts
>
> Pull from the Daily Brief (which has already been generated this run). Each section is a collapsed callout, with the most important item or two visible in the title, and a link to the full stream.
>
> ### Footer — open threads
>
> Top 3-5 items from the user's `📋 Tasks.md` that are tagged `#today` or due today.

---

```heatmap-calendar
year: 2026
colors:
  default:
    - '#161b22'
    - '#0e4429'
    - '#006d32'
    - '#26a641'
    - '#39d353'
showCurrentDayBorder: true
defaultEntryIntensity: 1
entries:
  - {date: '2026-01-01', intensity: 1}
```

**Streak:** 0 days · regenerated daily at ~06:15 IST

---

### [[06-01-26 Sun]]

Weather: pending first run.

#### Today's brief

> [!note]- News — top item pending first run
> Placeholder. Real content appears after the first morning run completes.

> [!note]- Watchlist — pending first run
> Placeholder.

> [!paper]- Papers — pending first run
> Placeholder.

> [!tech]- Tech — pending first run
> Placeholder.

> [!note]- Email — pending first run
> Placeholder.

#### Tasks for today

- [ ] First-run dashboard placeholder. Tasks from `📋 Tasks.md` appear here after the next run.

#### Open threads

- Will populate after the first morning run.

---

**Full streams:**
[[📌 Daily Brief]] · [[📰 Daily News]] · [[🎬 Daily Watchlist]] · [[📄 Daily Papers]] · [[🔬 Daily Tech]] · [[🔄 GitHub Releases]] · [[📅 Weekly Recap]]
