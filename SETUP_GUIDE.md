# Setup Guide

The complete walkthrough. Read it through once before executing anything.

## Overview

Two machines, one workflow:

- **HP EliteBook G1** (Arch Linux, always on) — Hermes Agent, Obsidian vault, git, MCP servers, scheduled automations. Never runs inference.
- **ROG Flow X13** (Arch Linux, woken on schedule) — llama.cpp serving Hermes models. Started by Wake-on-LAN at 05:55, suspended after the morning run.

The HP cannot run a useful local model (Haswell + DDR3 + integrated graphics). The ROG Flow can run real models because of the RTX 4050 and DDR5. Distributed setup is not optional — it's the only way this works.

## Section 1 — Hardware checklist

Before starting, confirm:

- HP can ssh into the ROG Flow without a password prompt (key-based auth). If not, set this up first.
- Both machines are on the same LAN.
- The ROG Flow's NIC supports Wake-on-LAN. Check with `sudo ethtool eth0 | grep Wake-on` — should show `Wake-on: g` or be able to be set to `g`.
- The HP has either `wakeonlan` or `etherwake` available (`pacman -S wol`).
- You know the ROG Flow's MAC address. Find it with `ip link show eth0`.

## Section 2 — Vault directory layout

Vault location: `~/vault-ai/` on the HP. Final structure after setup:

```
~/vault-ai/
├── HERMES.md                 (agent reads this on every run)
├── 🏠 Dashboard.md            (regenerated every morning)
├── 📋 Tasks.md                (user-maintained, plain markdown)
├── _watchlist.yaml           (creator feeds)
├── _tools.yaml               (GitHub release watch list)
├── .gitignore
├── .obsidian/                (created when Obsidian opens the folder)
├── 01 Updates/               (the seven daily/weekly stream notes)
├── 02 Daily/YYYY/MM/         (daily notes accumulate forever)
│   └── (archived dashboards land here as MM-DD-YY ddd dashboard.md)
├── 03 Meetings/
├── 04 People/                (auto-stubs created from wikilinks)
├── 05 Projects/
├── 06 Research/              (paper stubs)
├── 07 References/            (concept stubs)
├── 08 Summaries/             (long-form summaries from the summarize skill)
├── _Templates/
└── _Attachments/
```

Folder numbering reflects the original zip's convention. Keep it.

## Section 3 — Git and GitHub

After creating the vault directory and copying this bundle's `vault/` contents into it:

```bash
cd ~/vault-ai
git init
git branch -M main
echo '.obsidian/workspace*.json' > .gitignore
echo '.obsidian/cache' >> .gitignore
echo '.trash/' >> .gitignore
echo '.DS_Store' >> .gitignore
git add .
git commit -m "initial vault"
```

Create a **private** GitHub repo called `vault-ai` (do not make it public — the dashboard contains email and personal data). Then:

```bash
git remote add origin git@github.com:USERNAME/vault-ai.git
git push -u origin main
```

If using `gh` CLI:

```bash
gh repo create vault-ai --private --source=. --remote=origin --push
```

## Section 4 — Obsidian setup

Open `~/vault-ai/` once in Obsidian on the HP (or any machine) to create the `.obsidian/` directory. This is what makes Obsidian recognize the folder as a vault.

Install these community plugins from inside Obsidian's Community Plugins browser:

| Plugin | Purpose |
|---|---|
| Obsidian Git | Auto-pull on startup, auto-push periodic. Required for cross-device sync. |
| Obsidian Heatmap Calendar | GitHub-style year heatmap. Reads `02 Daily/` for the streak data. |
| Templater | Frontmatter date logic. Optional but useful. |

The original zip also includes two plugins not in the community store:

| Plugin | Source | Purpose |
|---|---|---|
| flashcards-obsidian | `ai-life-skills-main/obsidian-plugins/flashcards-obsidian/` | Spaced repetition, export to Anki |
| unread-dot | `ai-life-skills-main/obsidian-plugins/unread-dot/` | Shows dots next to files with `unread: true` |

Install these by copying the plugin folder into `~/vault-ai/.obsidian/plugins/`, then enable them in Settings → Community Plugins.

### Obsidian Git config

Settings → Obsidian Git:

- Vault backup interval: `0` (disabled — let the morning script handle commits on the HP)
- Pull updates on startup: enabled
- Disable push: false
- Sync method: rebase
- Commit message: `vault sync: {{date:YYYY-MM-DD HH:mm}}`

On mobile (Android + iPad), enable: pull on startup, auto-push every 10 minutes, auto-commit every 10 minutes. Mobile devices commit local edits (notes you write on your phone) and pull the morning run's output.

### Heatmap Calendar config

Add this block to `🏠 Dashboard.md` (already in the template):

````
```heatmap-calendar
year: 2026
colors:
  default:
    - '#161b22'
    - '#0e4429'
    - '#006d32'
    - '#26a641'
    - '#39d353'
entries:
  - {date: '2026-01-01', intensity: 1}
```
````

The morning script regenerates the `entries` array each day based on which daily notes in `02 Daily/` have mtime > write-time (i.e. you opened and at least scrolled them).

## Section 5 — Hermes Agent on the HP

Install:

```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
```

Initial config: run `hermes setup`. **Skip** the `--portal` flag — that connects to Nous's paid hosted models, which is not what we want. Configure manually instead:

`~/.hermes/config.yaml`:

```yaml
# Primary LLM provider — llama.cpp on the Ryzen machine
llm:
  provider: openai_compatible
  base_url: http://RYZEN_HOSTNAME:8080/v1
  api_key: not-needed
  model: hermes-4-35b-a3b
  context_window: 32768

# Fallback when primary unreachable
llm_fallback:
  provider: openai_compatible
  base_url: http://localhost:11434/v1   # HP-local Ollama
  api_key: not-needed
  model: hermes3:8b

# Vault root — Hermes reads HERMES.md from here as context
context_file: ~/vault-ai/HERMES.md
working_directory: ~/vault-ai

# Skills directory
skills_dir: ~/.hermes/skills

# Memory — Hermes' own state, separate from the vault
memory_db: ~/.hermes/memory.db

# Logging
log_file: ~/.hermes/logs/hermes.log
log_level: info
```

Replace `RYZEN_HOSTNAME` with whatever the ROG Flow resolves to on your LAN. `rogflow.local` works if mDNS/avahi is running; otherwise use the IP.

Copy skills:

```bash
mkdir -p ~/.hermes/skills
cp -r /path/to/hermes-vault-setup/skills/summarize ~/.hermes/skills/
cp -r /path/to/hermes-vault-setup/skills/summarize-call ~/.hermes/skills/
```

Apply the patches described in each skill's `PATCH.md` file.

### HP-local fallback model

When the ROG Flow is unreachable (traveling, etc.), Hermes falls back to a tiny model on the HP. Install Ollama:

```bash
curl -fsSL https://ollama.com/install.sh | sh
sudo systemctl enable --now ollama
ollama pull hermes3:8b
```

Quality will be noticeably worse on the fallback — that's expected. The morning run completes anyway, with shorter and flatter summaries. Acceptable for travel days.

## Section 6 — Inference server on the ROG Flow

SSH into the ROG Flow. Then:

### 6a. Build llama.cpp with CUDA

```bash
sudo pacman -S --needed base-devel cmake git cuda
git clone https://github.com/ggerganov/llama.cpp ~/llama.cpp
cd ~/llama.cpp
cmake -B build -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=89   # 89 = Ada Lovelace, RTX 4050
cmake --build build --config Release -j$(nproc)
```

Binaries land in `~/llama.cpp/build/bin/`. The one we care about is `llama-server`.

### 6b. Download models

```bash
mkdir -p ~/models
cd ~/models

# Primary: Hermes 4 35B A3B Q4_K_M (~22GB)
huggingface-cli download NousResearch/Hermes-4-35B-A3B-GGUF \
  --include "Hermes-4-35B-A3B-Q4_K_M.gguf" \
  --local-dir ~/models/hermes-4-35b-a3b

# Heavy-lift: Hermes 4.3 36B Q4_K_M (~21GB)
huggingface-cli download NousResearch/Hermes-4.3-36B-GGUF \
  --include "Hermes-4.3-36B-Q4_K_M.gguf" \
  --local-dir ~/models/hermes-4.3-36b

# Fallback: Hermes 4 14B Q4_K_M (~9GB)
huggingface-cli download NousResearch/Hermes-4-14B-GGUF \
  --include "Hermes-4-14B-Q4_K_M.gguf" \
  --local-dir ~/models/hermes-4-14b
```

Verify integrity: `sha256sum` each file against the published checksums on HuggingFace.

### 6c. llama-server flags — tuned per model

The systemd units in `systemd/` use these parameters. Brief explanation of each:

**Primary — Hermes 4 35B A3B (port 8080):**

```bash
llama-server \
  --model ~/models/hermes-4-35b-a3b/Hermes-4-35B-A3B-Q4_K_M.gguf \
  --n-gpu-layers 22 \
  --ctx-size 32768 \
  --threads 8 \
  --threads-batch 8 \
  --batch-size 512 \
  --flash-attn \
  --host 0.0.0.0 \
  --port 8080
```

Notes:
- `--n-gpu-layers 22` — start here, watch `nvidia-smi`, push higher if VRAM allows. Target: ~5.7 GB used. Each layer is ~270 MB.
- `--ctx-size 32768` — 32k context fits comfortably with flash-attn enabled. Plenty for the morning workflow.
- `--threads 8` — physical cores only, not 16 (hyperthreads). Memory-bound workload doesn't benefit from SMT.
- No `--mlock`. With ~22 GB model on 22 GB total system memory, mlock is an OOM trap.
- No `--numa distribute`. Single-socket consumer CPU; this flag is for multi-socket servers.

**Heavy-lift — Hermes 4.3 36B (port 8081):**

```bash
llama-server \
  --model ~/models/hermes-4.3-36b/Hermes-4.3-36B-Q4_K_M.gguf \
  --n-gpu-layers 18 \
  --ctx-size 16384 \
  --threads 8 \
  --threads-batch 8 \
  --batch-size 256 \
  --flash-attn \
  --host 0.0.0.0 \
  --port 8081
```

Smaller context, smaller batch, fewer GPU layers — this model is denser so each layer costs more. Don't run primary and heavy-lift simultaneously; they'd OOM together.

**Fallback — Hermes 4 14B (port 8082):**

```bash
llama-server \
  --model ~/models/hermes-4-14b/Hermes-4-14B-Q4_K_M.gguf \
  --n-gpu-layers 999 \
  --ctx-size 32768 \
  --threads 8 \
  --threads-batch 8 \
  --batch-size 512 \
  --flash-attn \
  --host 0.0.0.0 \
  --port 8082
```

`999` means "all layers on GPU." The 14B at Q4_K_M is ~9 GB, doesn't quite fit in 6 GB VRAM — llama.cpp will silently page the rest to CPU. Speed: 25-35 tok/s.

### 6d. systemd units

Copy from this bundle's `systemd/llama-server-*.service` files to `/etc/systemd/system/` on the ROG Flow. Edit paths if your home directory differs from the unit files' default. Then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable llama-server-primary.service
# Do NOT enable heavy/fallback — those start manually when needed
sudo systemctl start llama-server-primary.service
sudo systemctl status llama-server-primary.service
```

Test from the HP:

```bash
curl http://RYZEN_HOSTNAME:8080/v1/models
```

Should return a JSON list with the model name.

### 6e. Wake-on-LAN

On the ROG Flow:

```bash
sudo ethtool -s eth0 wol g
```

Make this persistent. Create `/etc/systemd/network/50-wol.link`:

```ini
[Match]
OriginalName=eth0

[Link]
WakeOnLan=magic
```

For wired Ethernet, this just works. For Wi-Fi only, WoL is much less reliable — recommend keeping the ROG Flow on Ethernet during normal sleep. If only Wi-Fi, the alternative is to not suspend the ROG Flow at all between morning runs.

Test WoL: from the HP, suspend the ROG Flow (`sudo systemctl suspend` on the ROG Flow), then wait 30 seconds, then from the HP:

```bash
wakeonlan AA:BB:CC:DD:EE:FF   # the ROG Flow's MAC
# OR
sudo etherwake AA:BB:CC:DD:EE:FF
```

It should wake. If not, BIOS settings on the ROG Flow may need adjustment (look for "Wake on LAN" in power options).

## Section 7 — Scheduled automation

The morning run fires from the HP. The HP wakes the ROG Flow, waits for the model server, runs Hermes, commits and pushes.

Copy from this bundle:

- `scripts/morning-run.sh` → `~/scripts/morning-run.sh`
- `scripts/weekly-recap.sh` → `~/scripts/weekly-recap.sh`
- `scripts/wake-ryzen.sh` → `~/scripts/wake-ryzen.sh`
- `scripts/concept-stubs.py` → `~/scripts/concept-stubs.py`
- `scripts/connection-finder.py` → `~/scripts/connection-finder.py`

Make them executable:

```bash
chmod +x ~/scripts/*.sh
```

Edit `~/scripts/morning-run.sh` to set `RYZEN_HOSTNAME` and `RYZEN_MAC` at the top.

Copy systemd units to the HP's `/etc/systemd/system/`:

- `hermes-morning.service`
- `hermes-morning.timer`
- `hermes-weekly.service`
- `hermes-weekly.timer`

Edit unit files to set the correct `User=` and `WorkingDirectory=`. Then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now hermes-morning.timer
sudo systemctl enable --now hermes-weekly.timer
sudo systemctl list-timers | grep hermes
```

Should show both timers with next-run times.

## Section 8 — Gmail MCP server

Install:

```bash
npm install -g @gongrzhe/server-gmail-autoauth-mcp
```

Run once interactively to do the OAuth flow:

```bash
npx @gongrzhe/server-gmail-autoauth-mcp
```

A browser opens. Allow access. Credentials cache to `~/.gmail-server/credentials.json`.

Register with Hermes by adding to `~/.hermes/config.yaml`:

```yaml
mcp_servers:
  gmail:
    command: npx
    args: ["-y", "@gongrzhe/server-gmail-autoauth-mcp"]
    auto_start: true
```

Restart Hermes (`hermes restart` or the equivalent command in current docs).

## Section 9 — Watchlist setup

Edit `~/vault-ai/_watchlist.yaml`. The bundle ships with the creators Sarang named, but most have `channel_id: null` — those need resolving. Two ways:

**Manual:** for each, visit the channel's YouTube page, view source, find `"channelId":"UC...."`. Paste it into the YAML.

**Automated:** Run this from Claude Code on the HP, with Sarang present (in case any need disambiguation):

```
For each entry in ~/vault-ai/_watchlist.yaml with channel_id: null, search YouTube
for the creator's main channel, find the channel_id, and update the file. For
ambiguous names (e.g. multiple creators share a name), ask before picking.
```

For blogs with `url:` but `feed:` missing, probe these paths in order: `/feed`, `/feed.xml`, `/atom.xml`, `/rss.xml`, `/index.xml`. First one that returns valid XML wins.

## Section 10 — Mobile sync

**Android:** Install Obsidian from Play Store. Tap "Open existing vault," create new vault folder on device, then in Obsidian Git plugin settings: set the GitHub clone URL with PAT embedded: `https://USERNAME:PAT@github.com/USERNAME/vault-ai.git`. Enable pull on startup, auto-commit every 10 min, auto-push after commit.

**iPad:** Same as Android. iPad version of Obsidian Git works identically. Alternative if you hit issues: install Working Copy, clone the repo there, "Link to file provider," then open the folder as an Obsidian vault.

**GitHub PAT:** Create a fine-grained personal access token at github.com → Settings → Developer settings → Personal access tokens → Fine-grained. Scope: only the `vault-ai` repo, `Contents: read+write`. Copy once, paste into both mobile clients. The PAT is stored on each device — never in the repo.

## Section 11 — First dry run

Before enabling the timer for live runs, do a manual dry run:

```bash
cd ~/vault-ai
DRY_RUN=1 ~/scripts/morning-run.sh
```

Dry run mode:
- Skips the git push
- Logs everything to stdout in addition to the log file
- Still commits locally (so you can see the diff)

Inspect:

```bash
git log --oneline -5
git show HEAD --stat
```

If the dashboard looks reasonable, the streams have content, and nothing failed:

```bash
git push origin main
sudo systemctl enable --now hermes-morning.timer
```

If anything's off, iterate on the prompt callouts in `01 Updates/` and re-run.

## Section 12 — Things that will go wrong (a non-exhaustive list)

- **Wake-on-LAN fails after kernel update.** ROG Flow's WoL state can reset after firmware/driver updates. Re-run `sudo ethtool -s eth0 wol g` if morning runs start using the HP-local fallback unexpectedly.
- **OAuth token expires.** Gmail refresh tokens last ~6 months under normal use. When the Brief skill's email section starts coming up empty, re-run the OAuth flow.
- **OOM on the Ryzen.** Most common cause: heavy-lift and primary both started by accident. Verify only one llama-server is running with `systemctl status llama-server-*`. Or you opened a browser on the ROG Flow during the morning run. Solution: don't.
- **Merge conflict on Dashboard.md.** Happens if you edit on phone and morning run runs simultaneously. The dashboard is always overwritten so conflicts are spurious — script does `git pull --rebase` first; if it fails, manual intervention required. Realistically rare given the time-of-day separation.
- **Hermes Agent config syntax changes.** Hermes is young software (released February 2026). Config keys and skill APIs may shift. When in doubt, current docs at hermes-agent.nousresearch.com/docs override this guide.
- **arXiv rate limits.** Don't run the morning script more than once per hour. Daily is fine.

## Section 13 — Day-to-day operation, after setup

Normal use is: nothing. Wake up, your phone has pulled the new dashboard, you read it.

When you want to:

- **Add a creator to the watchlist:** edit `_watchlist.yaml` on your phone, commit, push. Tomorrow's run picks them up.
- **Add a tool to the GitHub release watcher:** same, edit `_tools.yaml`.
- **Add a task:** edit `📋 Tasks.md`. Brief skill reads from there.
- **Call summarize ad-hoc:** open Hermes' chat interface (CLI on the HP, or whatever messaging interface you've wired up), say "summarize https://example.com/article".
- **Skip a morning run:** `systemctl stop hermes-morning.timer`. Re-enable when you're back.

That's it. The system is supposed to be quiet.
