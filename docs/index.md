# hermes-morning-run

A self-hosted daily-briefing pipeline built over three months of live use. Runs each morning on a single machine, aggregates news / papers / videos / tech / GitHub releases / email / tasks from RSS and APIs, and writes the result into an Obsidian vault that syncs across phone, laptop, and tablet over git.

**Repo**: <https://github.com/SarangVehale/hermes-morning-run>

## Read in order

If you're new here, read these pages in this order — each one builds on the last:

1. **[History](history.html)** — where the project started (June 2026), what it looked like in v1.0, and every version through the v2.1 ROG decommission today. Chronological, with the reasoning for each change.
2. **[Architecture](architecture.html)** — the shape of the pipeline today. Single-machine, per-stream design, anti-fabrication guarantees, with file:line references into the code.
3. **[Stack](stack.html)** — what libraries we use (`feedparser`, `ddgs`, `httpx`, `claude` CLI) and what we deliberately don't (LangChain, LangGraph, LlamaIndex) and why. Explains the "just fetch it" philosophy.
4. **[Setup](setup.html)** — installing on a fresh machine. Python venv, claude.ai auth wiring, systemd timer, mobile sync.
5. **[Troubleshooting](troubleshooting.html)** — the runbook. OAuth `invalid_grant`, Reddit 429 storms, dead RSS feeds, `claude -p` not authenticated, systemd timer drift.
6. **[Mistakes](mistakes.html)** — a catalog of what went wrong. URL mangling by the LLM, papers biased to three categories, heartbeat lies, race conditions in feed-health persistence, the two-month OAuth outage nobody noticed, the two-machine architecture that turned out to be overkill. Every one is a real war story from the last three months.
7. **[Changelog](changelog.html)** — version-by-version summary. Points back to [Mistakes](mistakes.html) for the "why".

## Architecture at a glance (v2.1)

```
                 ┌─────────────────────────────────────────┐
                 │                Orchestrator             │
                 │           (always-on, no GPU)           │
                 │                                         │
    05:55 IST ──►│  morning-run.sh                         │
                 │    ├─ git pull                          │
                 │    ├─ RSS/API fan-out (deterministic)   │
                 │    │   news · papers · tech · watchlist │
                 │    │   releases · curiosity             │
                 │    ├─ Brief composer                    │
                 │    │   ↑ Gmail + Calendar (OAuth)       │
                 │    ├─ LLM calls (`claude -p sonnet`)    │──► claude.ai (Pro)
                 │    ├─ concept-stubs, wikifill           │
                 │    ├─ git commit + push                 │──► github.com (private vault)
                 │    └─ maintenance pass                  │
                 └─────────────────────────────────────────┘
                                     │
                                     ▼
                            phone / tablet / laptop
                            (Obsidian + Git plugin)
```

## The one-paragraph summary

Every morning at 05:55 IST the orchestrator pulls the vault repo, dispatches ~9 streams (news / papers / tech / watchlist / curiosity / releases / weather / on-this-day / brief). Each stream fetches from RSS or APIs and writes callouts into its corresponding note in the Obsidian vault. LLM-augmented streams (watchlist summaries, curiosity synthesis) shell out to the `claude` CLI in print mode using the user's claude.ai Pro subscription — no API key, no local GPU inference. The Brief composer reads the stream notes plus four Gmail accounts, four Calendar accounts, and today's tasks, produces a one-page landing note, then the orchestrator commits everything and pushes to GitHub. On the phone, Obsidian Git pulls the changes on next open. Total wall-clock: 5-15 minutes.

## What makes this different

- **Runs on one modest machine** — an old laptop is enough. No GPU. No wake-on-LAN. No inference host to babysit.
- **Auth via Claude Code, not API key** — LLM calls shell out to `claude -p --model sonnet` and inherit the user's claude.ai OAuth session. Pro subscription covers the traffic (no per-token billing on top).
- **Raw HTTP everywhere else** — no LangChain, no LangGraph, no LlamaIndex. Every RSS fetch is `feedparser.parse(url)`, every HTTP call is stdlib `urllib` or `httpx`. See [Stack](stack.html) for the deliberate reasoning.
- **RSS-first, not LLM-first** — publisher-provided title / description / pubDate / image is preferred over LLM re-summarization. The LLM only enters when the source doesn't ship structured metadata (video transcripts, curiosity synthesis).
- **No fabrication** — every rendered item traces back to a real tool call. Failures become `[!warning]` callouts, never invented plausible content. Structural, not prompted.

## Not for you

This is a personal-use setup, not a product. It expects:

- Comfort with Linux, systemd, OAuth PKCE flows, and reading Python.
- A Claude Code / claude.ai Pro or Max subscription (for the LLM stages), or willingness to fall back to a local ollama endpoint.
- A (private) GitHub repo for the vault.

If you want a hosted daily-briefing product, this isn't it. If you like the shape but want a different mix — start here, edit `~/.hermes/morning-config.yaml`, and change the code where the shape doesn't fit.

{% include nav.html
  next="history"
  next_title="History" %}
