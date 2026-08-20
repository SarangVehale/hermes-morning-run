# hermes-morning-run

A self-hosted, local-LLM-augmented daily-briefing pipeline. Runs each morning on a home server, aggregates news / papers / videos / tech / GitHub releases / email / tasks from RSS and APIs, and writes the result into an Obsidian vault that syncs across phone, laptop, and tablet over git.

Designed for a two-machine split:

- **Orchestrator** (always-on laptop / small server) — runs the pipeline, holds the vault, pushes to git.
- **Inference host** (bigger GPU, woken on schedule) — serves `llama.cpp` for the LLM-augmented stages.

📖 **Documentation**: <https://SarangVehale.github.io/hermes-morning-run/>
📝 **Changelog**: [CHANGELOG.md](CHANGELOG.md)

## What it does

Every morning it produces one landing note (`📌 Daily Brief.md`) plus a set of stream notes:

| Stream | Source | Selection |
|---|---|---|
| 📰 Daily News | Publisher RSS across 20 configured topics, DDGS fallback | Deterministic: recency + per-domain dedupe |
| 📄 Daily Papers | arXiv RSS across configured categories + journal RSS (Nature Physics, PRL, bioRxiv, Quanta) | Round-robin — every category with candidates picked before any gets a second |
| 🔬 Daily Tech | Hacker News, Show HN, Lobsters, Reddit tech subs | Deterministic with per-source diversity cap |
| 🎬 Daily Watchlist | Configured YouTube channels + blog feeds, transcript→summary via LLM | New-since-last-run per creator |
| 🪅 Daily Curiosity | Wikipedia crawl seeded from previous curiosities | LLM curator (small model) |
| 🔄 GitHub Releases | Repos in `_tools.yaml` | New releases since last run |
| 📌 Daily Brief | Reads the above + Gmail + Calendar | One-page morning summary with weather, schedule, inbox, headline items |

## Design principles

- **RSS-first**: publisher-provided title / description / pubDate / image is preferred over LLM re-summarization. The LLM only enters when the source doesn't ship structured metadata (transcripts, curiosity synthesis).
- **No fabrication**: every rendered item traces back to a real tool call. Failures become `[!warning]` callouts, never invented content.
- **Deterministic selection where possible**: round-robin across categories and sources beats "pick the shiniest" for a daily habit — you see everything eventually.
- **Circuit-breaker feed health**: dead RSS URLs are tracked and skipped after N consecutive failures, retried probe-style every Nth day.
- **Wake-on-LAN**: the inference host stays asleep except during the run window; the orchestrator wakes it, drives it, and powers it back down.

## Requirements

- Two Arch/Debian/Fedora-family Linux machines (or one, if you don't need the GPU split).
- Python 3.11+ on the orchestrator.
- `llama.cpp` on the inference host (or any OpenAI-compatible endpoint).
- Obsidian on your mobile/tablet with the [Obsidian Git](https://github.com/Vinzent03/obsidian-git) plugin.
- A GitHub repo for the vault (recommended private).
- Optional: Google OAuth credentials if you want the Brief to include Gmail + Calendar.

## Quick start

1. Clone this repo.
2. Read [`SETUP_GUIDE.md`](SETUP_GUIDE.md) — the full walkthrough with exact commands.
3. Copy `scripts/` to `~/scripts/` on the orchestrator, `systemd/` units to `/etc/systemd/system/`.
4. Edit `~/.hermes/morning-config.yaml` with your topics, subreddits, watchlist, and API keys.
5. `systemctl --user enable --now hermes-morning.timer`.

For the full architecture, see [`docs/architecture.md`](docs/architecture.md).

## Repo layout

```
├── scripts/
│   ├── morning/            # the pipeline package (news.py, papers.py, tech.py, …)
│   ├── morning-run.sh      # entry point: wake ROG, run pipeline, push, sleep ROG
│   ├── oauth-grant.py      # one-shot Google OAuth PKCE helper
│   ├── weekly-recap.sh     # weekly aggregator
│   └── concept-stubs.py    # post-run: create stubs for [[wikilinked]] concepts
├── systemd/                # timer + service units for orchestrator and inference host
├── skills/                 # Hermes Agent skills (summarize, summarize-call)
├── vault/                  # starter Obsidian vault template
├── _staging/               # operational playbooks (maintenance, dry-run, mobile setup)
├── docs/                   # GitHub Pages site
├── rog-setup.sh            # one-shot bootstrap for the inference host
├── setup.sh                # one-shot bootstrap for the orchestrator
├── SETUP_GUIDE.md          # detailed walkthrough
├── HANDOFF.md              # notes to a fresh setup session
├── MIGRATE.md              # notes when moving hosts
└── CHANGELOG.md
```

## License

MIT. See [LICENSE](LICENSE).

## Attribution

The pipeline was iterated on over months of live use. The RSS-first architecture landed in v2.0 after the LLM-curation path proved unreliable — see the [changelog](CHANGELOG.md) for the story.
