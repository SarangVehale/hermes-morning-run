# hermes-morning-run

A self-hosted, local-LLM-augmented daily-briefing pipeline. Runs each morning on a home server, aggregates news / papers / videos / tech / GitHub releases / email / tasks from RSS and APIs, and writes the result into an Obsidian vault that syncs across phone, laptop, and tablet over git.

**Repo**: <https://github.com/SarangVehale/hermes-morning-run>

## Documentation

- **[Architecture](architecture.md)** — how the two-machine pipeline is wired together, what each stream does, how the anti-fabrication guarantees hold.
- **[Setup](setup.md)** — installing on a new machine.
- **[Changelog](changelog.md)** — what changed and why.

## What it produces

Every morning, one landing note (`📌 Daily Brief`) plus a set of stream notes in `01 Updates/`. Everything is anchored to the day's date (`### [[08-20-26 Thu]]`) and syncs to your phone through git.

## Design at a glance

- **RSS-first**: publisher-provided title / description / pubDate / image is preferred over LLM re-summarization. The LLM only enters when the source doesn't ship structured metadata (video transcripts, curiosity synthesis).
- **No fabrication**: every rendered item traces back to a real tool call. Failures become `[!warning]` callouts, never invented plausible content.
- **Deterministic selection where possible**: round-robin across categories and sources beats "pick the shiniest" for a daily habit — you see everything eventually.
- **Circuit-breaker feed health**: dead RSS URLs are tracked and skipped after N consecutive failures, retried probe-style every Nth day.
- **Wake-on-LAN**: the inference host stays asleep except during the run window; the orchestrator wakes it, drives it, and powers it back down.

## Two-machine split

```
                       05:55 IST
    ┌───────────────┐   WoL magic packet   ┌─────────────────┐
    │  Orchestrator │ ──────────────────▶  │ Inference host  │
    │  (always on)  │                      │ (asleep→awake)  │
    │               │                      │                 │
    │  morning-run  │ ◀──── llama-server ──│  llama.cpp ×3   │
    │  git push     │                      │  Gemma / Qwen   │
    │               │ ─── power off ─────▶ │                 │
    └───────────────┘                      └─────────────────┘
           │
           │ git push
           ▼
    ┌─────────────────┐
    │  Obsidian sync  │  ── phone, tablet, laptop
    └─────────────────┘
```

## Not for you

This is a personal-use setup, not a product. It expects:

- You're comfortable with Linux, systemd, and reading Python.
- You have (or can get) a machine with a GPU capable of running Gemma-4-26B or similar at usable speeds.
- You want the vault to live in git and don't mind pushing to a private GitHub repo.

If you're looking for a hosted daily-briefing product, this isn't that. If you like the shape but want a different mix — start here, edit `~/.hermes/morning-config.yaml`, and change the code where the shape doesn't fit.
