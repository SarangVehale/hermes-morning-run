---
title: Vault conventions for Hermes Agent
audience: any AI agent operating on this vault
authoritative: true
---

# Vault Conventions

This file is read by Hermes Agent at the start of every run. Conventions below are not suggestions; they are the contract between the agent and the vault. If a skill's instructions conflict with this file, this file wins unless the skill explicitly says otherwise.

## Folder layout

| Folder | Purpose |
|---|---|
| `01 Updates/` | The seven daily/weekly stream notes (Brief, News, Watchlist, Papers, Tech, GitHub Releases, Weekly Recap) — each has a prompt callout at the top |
| `02 Daily/YYYY/MM/` | Daily notes, filename format `MM-DD-YY ddd.md` (e.g. `06-01-26 Sun.md`). Yesterday's dashboard is archived here as `MM-DD-YY ddd dashboard.md` |
| `03 Meetings/` | Meeting notes |
| `04 People/` | One file per person referenced anywhere in the vault. Stubs auto-created from wikilinks |
| `05 Projects/` | Project notes |
| `06 Research/` | Paper stubs, research-specific reference notes |
| `07 References/` | Concept stubs — technical terms, companies, products, places, tools |
| `08 Summaries/` | Long-form summaries produced by the `summarize` skill |
| `_Templates/` | Note templates used by the agent when creating stubs |
| `_Attachments/` | Images and other binaries referenced from notes |

Root-level files:

- `🏠 Dashboard.md` — regenerated each morning. Archived to `02 Daily/` first.
- `📋 Tasks.md` — user-maintained plain markdown task list. Brief skill reads from here.
- `_watchlist.yaml` — creator feed list for the Watchlist skill.
- `_tools.yaml` — GitHub release watch list.

## Note structure

Every note has frontmatter. Required fields:

```yaml
---
created: 2026-06-01
updated: 2026-06-01
unread: true
---
```

Optional fields per note type — see the prompt callouts for specifics.

After frontmatter, do not write a `# Heading` for the note's title. Obsidian uses the filename as the title; a top-level heading duplicates it. Start with content.

## Wikilinks

Wikilink everything that could plausibly be its own note: people, companies, places, technical concepts, tools, papers, products. Use the natural reading form: `[[Veritasium]]`, not `[[04 People/Veritasium]]`. Obsidian resolves the link regardless of folder.

For people the agent encounters for the first time (mentioned in a news article, paper, or video), the wikilink is still written. A separate post-run step (`scripts/concept-stubs.py`) creates empty stub files for dangling links so they appear in graph view.

Do not write AI-generated content into stub files. Stubs contain only frontmatter (`created`, `unread: true`, `first_referenced_in: [[source note]]`). The user fills bodies from real sources when and if they want to.

## Callout types

Markdown callouts are how status and severity are encoded. Use these consistently:

| Callout | When to use |
|---|---|
| `[!note]-` | Default. Anything informational. Most content. |
| `[!breaking]-` | Genuinely major — once-a-week-or-less items in a given stream. |
| `[!critical]-` | Field-moving or paradigm-shifting. Once-a-month at most. |
| `[!paper]-` | Used in Daily Papers for paper entries. |
| `[!tech]-` | Used in Daily Tech for individual tool/project items. |
| `[!summary]-` | Used in 08 Summaries for the summarize skill's output. |
| `[!warning]` | When the agent itself has uncertainty or a non-blocking issue to flag. |

The dash suffix (`-`) makes the callout collapsed by default. Use the dash on every callout except active warnings.

## Daily note update

At the end of every run (morning or weekly), update the day's daily note at `02 Daily/YYYY/MM/MM-DD-YY ddd.md`. If it doesn't exist, create it.

The format of the daily note is a simple log of what was touched:

```yaml
---
created: 2026-06-01
updated: 2026-06-01T06:18:00+05:30
unread: true
---

## Updates

- Dashboard regenerated
- [[📰 Daily News]] — 4 new items
- [[🎬 Daily Watchlist]] — 2 new summaries: [[Veritasium - 2026-06-01 - Vera Rubin Observatory]], [[Alex Ziskind - 2026-06-01 - Strix Halo LLM Bench]]
- [[📄 Daily Papers]] — 3 papers
- [[🔬 Daily Tech]] — 5 items
- [[🔄 GitHub Releases]] — 2 release notes
- [[📌 Daily Brief]] — generated
- 7 concept stubs created in `07 References/`
- 2 connection suggestions appended to today's notes
```

Daily notes accumulate forever. They are not regenerated, only appended to.

## Unread tracking

When the agent edits any note, set `unread: true` in that note's frontmatter (creating the field if missing) and update `updated:` to the current ISO 8601 timestamp.

The `unread-dot` Obsidian plugin reads this field and renders a visual indicator in the file explorer. The user clears it manually by toggling the field to `false` (or there's a plugin command for it).

## Linking convention for the dashboard

The Dashboard.md is a view, not a record. Everything on it is a link to a source. Format:

- Items from streams link to that stream's note (e.g. `[[📰 Daily News]]`)
- Watchlist items link to their detail summary file in `08 Summaries/`
- Papers link to either the stub in `06 Research/` or directly to the source URL, depending on whether a stub was created
- Tasks link to specific lines/sections in `📋 Tasks.md` using block references where possible

## Language and tone

When writing into the vault on behalf of the agent:

- Plain prose. No exclamation points. No emoji in body text. Emoji in filenames is fine.
- No hedging boilerplate. Don't write "It's worth noting that..." or "It's important to remember..." — say the thing.
- No motivational framing. Don't tell the user they're crushing it or what a productive day this is. The vault is for information, not encouragement.
- Be specific. "The team announced a result" is worse than "Bluvstein et al. announced a 2.1×10⁻³ logical error rate." Always prefer the specific.
- Quotation: under 15 words per quoted span, one quote per source maximum. Paraphrase everything else. This applies regardless of source.

## When in doubt

If a skill's instructions are unclear, write a minimal version and add a `[!warning]` callout at the bottom of the note explaining what was unclear. Do not invent content to fill gaps. Do not skip a section silently — say it was skipped and why.

If a tool call fails (web search down, MCP server unreachable, RSS feed 404), the agent records the failure in the relevant section and moves on. The morning run never blocks on a single source.
