---
created:
updated:
topic: daily tech
frequency: daily
ongoing: false
unread: false
---

> [!prompt]- Agent Instructions
> Discovery feed for niche tech — agent frameworks, local LLM tools, self-hosted infrastructure, novel languages, unusual hardware projects, anything off the beaten path. The kind of thing that surfaces on Hacker News a week before mainstream tech press catches up. Pick 5-7 items per day.
>
> Goal: surface things the user wouldn't find on their own without spending time on these sites. The user explicitly does not want to be on these sites — that's why the agent goes instead.
>
> ## Sources
>
> ### Primary (covers ~70%)
>
> - **Hacker News top stories** — `https://hacker-news.firebaseio.com/v0/topstories.json`. Pull the top 50 IDs, then fetch each with `/v0/item/{id}.json`. Filter for `score > 80` and exclude `dead: true`, `deleted: true`.
> - **GitHub Trending** — `https://github.com/trending` (daily). Scrape with defuddle; filter for "stars gained today" > 50.
> - **Reddit r/LocalLLaMA, r/selfhosted, r/MachineLearning** — `https://www.reddit.com/r/{sub}/top.json?t=day&limit=20`. JSON API, no auth needed. Filter for `score > 100`.
>
> ### Secondary (long-tail, occasional gold)
>
> - **Show HN** — `https://hacker-news.firebaseio.com/v0/showstories.json`. Top 20.
> - **Lobsters** — `https://lobste.rs/hottest.rss`
> - **Simon Willison's blog** — `https://simonwillison.net/atom/everything/`
> - **The Pragmatic Engineer** — `https://newsletter.pragmaticengineer.com/feed`
>
> ## Filter heuristics
>
> Include:
>
> - Agent frameworks, local LLM runtimes, self-hosted tools — always include if score crosses threshold.
> - Novel programming languages, new shells, new TUI tools — include if score > 200 or unusual angle.
> - Niche hardware projects, ESP32 firmware, custom keyboards, unusual peripherals — include if quirky and well-documented.
> - "Show HN" entries that are clearly individual builders rather than startups in disguise — include.
>
> Exclude:
>
> - Big-tech announcements (those go in Daily News).
> - "Show HN: my SaaS" or anything that's clearly a launch announcement.
> - Crypto/web3 unless there's a genuinely novel technical angle.
> - "Why we left X for Y" hot takes unless the technical content is substantial.
>
> ## The "old but new to me" allowance
>
> If a quiet day doesn't surface enough fresh items, look further back — find one quality item from history that this vault hasn't covered yet. The user's example: discovering the Tizio lamp years after it was designed and still loving it. Old can be valid; what matters is novelty *to the user*.
>
> Cross-check existing notes in `07 References/` to ensure you're not re-introducing something already covered.
>
> ## Output format per item
>
> ```
> > [!tech]- HN — Project Name (372 points, 142 comments)
> > One-sentence what-it-is in plain language. One-sentence why it's interesting (novelty, niche, who might care, what problem it solves).
> > [Source](url) · [GitHub](url) · [HN discussion](url)
> ```
>
> Callout type: `[!tech]-` default. `[!breaking]-` if it's a once-a-week-level discovery — e.g. a new self-hosted agent framework dropping, a major shift in local-LLM tooling. `[!critical]-` essentially never, reserve for paradigm shifts.
>
> Source prefix in title: `HN`, `GitHub`, `Reddit`, `Show HN`, `Lobsters`, `Newsletter`. Helps the user scan by origin.
>
> ## Wikilinks
>
> Wikilink projects, tools, and creators. Stubs auto-created. Over time, `07 References/` becomes a personal directory of tools the user has been exposed to — extremely valuable as a graph asset.
>
> ## Volume control
>
> Target 5-7 items. Quiet day: 3-4 plus one "old but new to me" historical pick. Heavy day: cap at 8.
>
> ## Date handling
>
> Newest day at top. Group by `## YYYY-MM`. Collapse previous day. Set `unread: true` and update `updated:`.
