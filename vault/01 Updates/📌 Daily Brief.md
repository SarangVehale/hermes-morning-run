---
created:
updated:
topic: daily brief
frequency: daily
ongoing: true
unread: false
---

> [!prompt]- Agent Instructions
> The Daily Brief is the user's morning landing note. It reads the other stream notes (Daily News, Daily Watchlist, Daily Papers, Daily Tech, GitHub Releases), picks the most important 1-2 items from each, adds email triage and task priorities, and writes one calm digest for the day.
>
> Run this skill **after** all the other stream skills have completed for the day. The Brief reads their output, doesn't duplicate their work.
>
> ## Sections
>
> 1. **Weather** — Pimpri-Chinchwad. One line: high/low °C, conditions, what to wear if relevant. Pull from any free weather API or a simple web search.
> 2. **Calendar** — today's events. If a calendar MCP server is configured, read from there. Otherwise read from `📅 Calendar.md` at vault root if it exists. If neither, write `Nothing scheduled.`
> 3. **Top from streams** — 1-2 items each, picked by importance:
>    - News (top 1 from Daily News' today entry)
>    - Watchlist (1-2 from Daily Watchlist's today entry — pick the ones with the most new-to-vault concepts)
>    - Papers (top 1 from Daily Papers' today entry — usually the highest-impact experimental result, or a survey that's relevant to current research)
>    - Tech (top 1 from Daily Tech's today entry)
>    - GitHub Releases (only if there's something with breaking changes for tools the user actually uses daily)
> 4. **Email** — todo list of seemingly important emails. Use the Gmail MCP. Heuristics for "important":
>    - Sender's name appears in `04 People/` already, OR
>    - Subject/body mentions a deadline within 7 days, OR
>    - User's name is in the body (not just To: line), OR
>    - Explicit urgency markers ("urgent", "asap", "tomorrow", "EOD")
>    - Output format: one bullet per email — `[ ] From [[Name]] — short subject. Action: <what they want>`
>    - Cap at 5. If more would qualify, list the rest as `Others (N more): brief sender names`
>    - No suggested replies. No drafts. Just the todo list.
> 5. **Tasks** — read `📋 Tasks.md` at vault root. Filter for: due today, overdue, tagged `#today` or `#urgent`. List as plain checkbox items. Cap at 7.
> 6. **Carryover** — read yesterday's daily note (`02 Daily/YYYY/MM/MM-DD-YY ddd.md` for yesterday's date). If there's a `## TODO for next session` section, paste its contents here.
>
> ## Section rules
>
> If a section is empty, still include the heading with one line: `Nothing today.` Do not omit sections silently.
>
> Use plain prose. No emoji in body text. No motivational language. Specific names and numbers over generic descriptions.
>
> ## Top of note
>
> The note's structure each day:
>
> ```
> ## YYYY-MM
>
> ### [[MM-DD-YY ddd]]
>
> Weather: 24-32°C, partly cloudy, low chance of rain.
>
> Calendar:
> - 10:00 — standup
> - 14:30 — review meeting with [[Prof. Joshi]]
>
> #### From the streams
>
> > [!note]- News: PCMC announces metro extension to Hinjewadi (Pune Mirror)
> > Brief 1-2 sentence framing, taken from the News stream's full entry. [Source](url)
>
> > [!note]- Watchlist: [[Veritasium]] on the Vera Rubin Observatory
> > 1-2 sentences from the summary, emphasizing new concepts. Detail: [[Veritasium - 2026-06-01 - Vera Rubin Observatory]]
>
> > [!paper]- Papers: arXiv:2505.18234 — Logical qubit lifetime exceeding physical on neutral-atom processor
> > 1-2 sentence framing of why this matters. Detail: [[06 Research/arXiv 2505.18234]]
>
> > [!tech]- Tech: NetworkChuck released a homelab-AI guide using Hermes 4
> > 1-2 sentence framing. [Source](url)
>
> #### Email — needs attention today
>
> - [ ] From [[Anjali Sharma]] — quantum-ECC chapter draft due Monday. Action: send revised draft.
> - [ ] From [[Rohan]] — confirms Wednesday meeting. Action: send agenda.
>
> #### Tasks
>
> - [ ] Submit ECC chapter draft (Monday)
> - [ ] Implement noise model simulation
>
> #### Carryover from yesterday
>
> - Finish reading [[arXiv 2505.18234]]
> ```
>
> ## Date handling
>
> Newest day at the top, after this prompt callout. Group by `## YYYY-MM`. When a new day is added, collapse the previous day's entry into a `> [!note]- [[MM-DD-YY ddd]]` callout (prefix every line of the previous entry with `> `).
>
> Set `unread: true` and update `updated:` in frontmatter.
