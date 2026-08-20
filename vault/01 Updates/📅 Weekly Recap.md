---
created:
updated:
topic: weekly recap
frequency: weekly
schedule: sunday 20:00
ongoing: false
unread: false
---

> [!prompt]- Agent Instructions
> Sunday evening, after the day's morning run has been digested. Reads the past 7 days of daily notes and stream entries, writes one calm recap covering what was learned, what was watched, what's still open.
>
> Run by `hermes-weekly.timer` on Sunday at 20:00 IST.
>
> ## Inputs
>
> - All daily notes from `02 Daily/YYYY/MM/` for the past 7 days (Monday through Sunday).
> - Stream entries (Daily News, Watchlist, Papers, Tech, GitHub Releases) for the same period.
> - The user's tasks file (`📋 Tasks.md`) — for "still open" tracking.
>
> ## Sections
>
> ### 1. Theme of the week
>
> Look across all the week's content. What did the agent surface most often? Was there a cluster around quantum error correction? A run of local-LLM tool launches? Three videos all about cooling? Name the theme in one sentence.
>
> If no clear theme emerged, say so: `Mixed week — no dominant thread across the streams.` Don't manufacture coherence.
>
> ### 2. From the streams
>
> One short paragraph per stream:
>
> - **News:** 2-3 sentences. What were the most consequential items? Wikilink them.
> - **Watchlist:** 2-3 sentences. Which creators dropped substantial content this week? What concepts came up multiple times?
> - **Papers:** 2-3 sentences. Notable papers, especially any that got multiple mentions or had follow-ups. Wikilink.
> - **Tech:** 2-3 sentences. New tools that crossed the threshold this week. Anything the user might actually want to try.
> - **GitHub Releases:** 1 sentence. Anything breaking, anything new worth knowing.
>
> ### 3. Open threads
>
> Things mentioned during the week that didn't resolve:
>
> - Papers the user added wikilinks to but didn't fill out stubs for
> - Tasks in `📋 Tasks.md` that have been there >7 days
> - "Carryover" items that appeared in multiple Daily Briefs without being addressed
> - Email todos in the Brief that didn't get checked off
>
> Format as a flat checklist. The user can copy-paste interesting ones into next week's tasks.
>
> ### 4. Concept stub density check
>
> Count stub files in `07 References/` and `04 People/` created during the week. Note the count and one observation:
>
> - If many stubs are empty (no body content), the user is accumulating dangling references faster than filling them. Mention gently.
> - If stubs are getting filled, mention that as a positive observation.
>
> Avoid scolding. The point is information, not motivation.
>
> ### 5. Heatmap status
>
> Number of days this week the user actually opened the dashboard (mtime > write-time). Format: `Dashboard opened 5/7 days this week. Current streak: 12 days.` If the streak broke this week, note it without judgment.
>
> ## Output format
>
> The note structure:
>
> ```
> ## YYYY-MM
>
> ### [[Week of MM-DD-YY]]
>
> **Theme of the week:** ...
>
> **From the streams:**
>
> News — ...
>
> Watchlist — ...
>
> Papers — ...
>
> Tech — ...
>
> GitHub Releases — ...
>
> **Open threads:**
>
> - [ ] ...
> - [ ] ...
>
> **Stubs created this week:** 23 (15 still empty, 8 filled in by user)
>
> **Heatmap:** Dashboard opened 5/7 days. Current streak: 12 days.
> ```
>
> ## Tone
>
> This is a reflective document. Calmer than the daily streams. No callouts, no `[!note]-` framing — just paragraphs. The user reads it on Sunday evening with whatever they're drinking. It should feel like a quiet summary, not another stream of information.
>
> Length: roughly 400-600 words per week. Long enough to be substantial, short enough to read in one sitting.
>
> ## Date handling
>
> Newest week at top. Group by `## YYYY-MM`. Day heading format `### [[Week of MM-DD-YY]]` using the Monday's date. Collapse previous week into a callout.
>
> Set `unread: true` and update `updated:`.
