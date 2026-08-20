# HANDOFF — for Claude Code

You are Claude Code running on Sarang's HP EliteBook G1 (Arch Linux). Your job is to install and configure a personal daily-briefing workflow that has been designed and specified across this bundle. Read this entire file before touching anything. Then read `SETUP_GUIDE.md` in full. Then begin execution phase by phase, asking for "go" between major phases.

## Context you need

Sarang is in Pimpri-Chinchwad, India. He has three machines:

- **HP EliteBook G1** (the one you are on) — Arch, i5 Haswell, 16GB DDR3, integrated graphics. Always on. Role: orchestration only. Runs Hermes Agent, the Obsidian vault, git, MCP servers, scheduled automations.
- **ROG Flow X13** — Arch, Ryzen 9 7940HS (or similar Phoenix-series chip), RTX 4050 6GB VRAM, 16GB DDR5. Role: inference server. Reachable over LAN. Hostname to be confirmed during setup — ask Sarang for `RYZEN_IP` / `RYZEN_HOSTNAME` / `RYZEN_MAC` early.
- **Lenovo IdeaPad** — Windows, i5 11th gen. Out of scope. Mention only if asked.

The system runs once each morning at ~06:00 IST. The HP wakes the ROG Flow over LAN, the ROG Flow's llama-server starts via systemd, Hermes Agent on the HP runs the morning workflow (multiple skills writing into the Obsidian vault), then git-pushes everything to GitHub. Sarang's phone (Obsidian + Git) and iPad pull on open. He reads the dashboard at his leisure.

## Constraints you must respect

These are not negotiable:

1. **No Anthropic API.** Sarang reserves his Claude credits for other work. All inference must go through the local model on the ROG Flow, or the small fallback on the HP. You yourself, during setup, are using Anthropic credentials — that's fine, but the *runtime workflow* must not.
2. **No paid APIs at all.** Free and open-source only. ElevenLabs is out. OpenAI is out. The only paid line item Sarang accepts is the GitHub private repo for the vault, which is free for personal use anyway.
3. **Calm tone, minimal emoji in note content.** Filenames keep their emoji (📌, 📰, 🎬, 📄, 🔬, 🔄, 📅, 🏠). Inside notes, write plain prose. No exclamation points, no rah-rah, no "let's go!" energy. Sarang is building this stack to *reduce* stimulation, not add to it.
4. **The vault structure and conventions in `vault/HERMES.md` are authoritative.** Every skill, every callout, every script must respect them. No `# Heading` at top of notes (Obsidian uses filename). Wikilink everything. Set `unread: true` on edited files. Update the daily note at the end of every session.
5. **Ask before destructive operations.** Anything that deletes, force-pushes, or modifies system services should be confirmed first. Anything that downloads >5GB should be confirmed. Anything that touches `/etc/` should be confirmed.

## Phases — execute in this order, ask for "go" between each

### Phase 1 — Pre-flight on the HP

- Verify you are on Arch (`cat /etc/os-release`).
- Verify you can ssh into the Ryzen machine. If not, help Sarang set up the SSH key.
- Get from Sarang: `RYZEN_IP`, `RYZEN_HOSTNAME`, `RYZEN_MAC`, `GITHUB_USERNAME`, `GMAIL_ADDRESS`, primary creator/blog URLs to add to the watchlist (he has a list — ask him to paste it).
- Confirm wakeonlan is supported on both machines (ethtool on the ROG Flow, wakeonlan/etherwake installed on the HP).

### Phase 2 — Vault scaffold and git init

- Create `~/vault-ai/` and copy the contents of this bundle's `vault/` directory into it.
- `cd ~/vault-ai && git init`.
- Help Sarang create a **private** repo on GitHub called `vault-ai` (he authorizes; you cannot create it for him without `gh` CLI being configured — check first).
- Add remote, initial commit, push.
- Open the vault in Obsidian once (Sarang does this part) to create `.obsidian/`. Then update `.gitignore` to exclude `.obsidian/workspace*.json`, `.trash/`, `.DS_Store`.

### Phase 3 — Obsidian plugins

Sarang installs these from the Community Plugins browser inside Obsidian. List them for him explicitly:

- Obsidian Git
- Obsidian Heatmap Calendar
- flashcards-obsidian (from this bundle if not in the community store; copy the folder from the original zip)
- unread-dot (same, copy from the original zip)

For Obsidian Git, the config is in SETUP_GUIDE.md section 4.

### Phase 4 — Hermes Agent installation on the HP

```
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
```

Then walk through `hermes setup` — answer prompts. **Skip** `hermes setup --portal` (paid, not needed). Configure the LLM provider to point at `http://RYZEN_IP:8080` (llama.cpp) when reachable, and an HP-local Ollama fallback otherwise. Exact config in SETUP_GUIDE.md section 5.

Copy `skills/summarize/` and `skills/summarize-call/` from this bundle into `~/.hermes/skills/`. Apply the YouTube-auto-subs-only patch described in the summarize skill folder's `PATCH.md`.

Copy `vault/HERMES.md` is already in the vault; tell Hermes to read it on every run as the vault context file.

### Phase 5 — Inference server on the ROG Flow

SSH into the ROG Flow. Install llama.cpp with CUDA, build, download Hermes 4 35B A3B Q4_K_M as primary + Hermes 4 14B Q4_K_M as fallback + Hermes 4.3 36B Q4_K_M as heavy-lift. Configure three systemd units, one per model, that bind to different ports (8080, 8081, 8082). Enable only the primary by default.

Exact build commands, model download URLs, and systemd unit files in SETUP_GUIDE.md section 6 and in `systemd/`. Tune `--n-gpu-layers` per model — guidance in SETUP_GUIDE.md.

Configure Wake-on-LAN on the ROG Flow (ethtool).

### Phase 6 — Scheduled automations

On the HP, install the systemd units in `systemd/`:

- `hermes-morning.timer` + `.service` — fires at 05:55 daily, runs `scripts/morning-run.sh`
- `hermes-weekly.timer` + `.service` — fires Sundays at 20:00, runs `scripts/weekly-recap.sh`

The morning-run script sends WoL, waits for the model server, then triggers Hermes via its API.

### Phase 7 — MCP servers

Install the Gmail MCP server on the HP. Walk Sarang through the Google OAuth consent screen — he clicks "Allow" in a browser. Register the server with Hermes.

### Phase 8 — Watchlist + tools auto-discovery

Read `vault/_watchlist.yaml` and `vault/_tools.yaml`. For each YouTube creator with only a name (no channel_id), search and resolve the channel ID. For each blog URL, probe `/feed`, `/feed.xml`, `/atom.xml`, `/rss.xml`, `/index.xml` for a valid feed. Update the YAML files with what you find. Show Sarang the result before saving.

### Phase 9 — Mobile setup

Walk Sarang through installing Obsidian + Obsidian Git on Android and iPad. Provide the exact GitHub personal access token scope to create (`Contents: read+write` on `vault-ai` repo only, fine-grained PAT).

### Phase 10 — First dry run

Run `scripts/morning-run.sh` manually with a `DRY_RUN=1` flag. Verify each section runs, output looks sensible, git commit happens but no push. Show Sarang the resulting dashboard. Iterate on prompt callouts if anything's off.

Then enable the timer for real and let it run the next morning.

## File map of this bundle

```
hermes-vault-setup/
├── HANDOFF.md                          (this file)
├── SETUP_GUIDE.md                      (detailed setup walkthrough)
├── README.md                           (brief overview)
├── vault/
│   ├── HERMES.md                       (vault conventions — agent reads on every run)
│   ├── 🏠 Dashboard.md                  (template, overwritten daily)
│   ├── 📋 Tasks.md                      (user-maintained task list)
│   ├── _watchlist.yaml                 (creator feed list — fill in IDs at setup)
│   ├── _tools.yaml                     (GitHub release watch list)
│   ├── 01 Updates/
│   │   ├── 📌 Daily Brief.md
│   │   ├── 📰 Daily News.md
│   │   ├── 🎬 Daily Watchlist.md
│   │   ├── 📄 Daily Papers.md
│   │   ├── 🔬 Daily Tech.md
│   │   ├── 🔄 GitHub Releases.md
│   │   └── 📅 Weekly Recap.md
│   ├── _Templates/
│   │   ├── new person template.md
│   │   └── new person template (minimal).md
│   └── (02 Daily, 03 Meetings, ... 08 Summaries, _Attachments)   empty dirs
├── scripts/
│   ├── morning-run.sh
│   ├── weekly-recap.sh
│   ├── wake-ryzen.sh
│   ├── concept-stubs.py
│   └── connection-finder.py
├── systemd/
│   ├── llama-server-primary.service     (Ryzen — Hermes 4 35B A3B)
│   ├── llama-server-heavy.service       (Ryzen — Hermes 4.3 36B, manual start)
│   ├── llama-server-fallback.service    (Ryzen — Hermes 4 14B, manual start)
│   ├── hermes-morning.service           (HP)
│   ├── hermes-morning.timer             (HP)
│   ├── hermes-weekly.service            (HP)
│   └── hermes-weekly.timer              (HP)
└── skills/
    ├── summarize/
    │   ├── SKILL.md                    (original, from zip)
    │   └── PATCH.md                    (instructions for the no-GPU patch)
    └── summarize-call/
        ├── SKILL.md                    (original, from zip)
        └── PATCH.md                    (instructions for the whisper.cpp swap)
```

## Things to not do

- Do not write any AI-generated content into concept stub files in `07 References/` or `04 People/`. Stubs are frontmatter-only. Sarang fills the bodies himself from real sources. Hallucination risk is the reason.
- Do not auto-install Obsidian community plugins via script. Sarang installs them through Obsidian's UI so he can read what permissions they ask for.
- Do not run the workflow against real Gmail until Sarang has reviewed the Daily Brief skill's exact instructions. Show him the prompt callout before the first email-fetching dry run.
- Do not push to GitHub during dry runs. Commit yes, push no, until he confirms output quality.
- Do not add features that aren't in this bundle. If Sarang asks for something new mid-setup, complete the current phase first, then implement the new thing as a discrete addition — don't bolt it on while half-done.

## Tone

Match the style of the bundle's docs: technical, specific, no oversell. If something is uncertain (Hermes Agent config syntax may have shifted between this bundle's writing and now), say so — don't fake confidence. When you hit a real choice point that isn't covered in the docs, ask. Don't guess and proceed.

If Hermes Agent's exact YAML/config format has changed from what's in this bundle, follow current Hermes documentation at https://hermes-agent.nousresearch.com/docs and adapt. The intent of each config file is documented in comments — preserve intent, update syntax.

## When you finish

Confirm the morning run will fire tomorrow at 05:55. Tell Sarang what time he'll see his first dashboard. Wish him a calm morning. That's it.
