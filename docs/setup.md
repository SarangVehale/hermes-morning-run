# Setup

This is the summary path. The exhaustive walkthrough — with exact commands, config templates, and troubleshooting — lives in [`SETUP_GUIDE.md`](https://github.com/SarangVehale/hermes-morning-run/blob/main/SETUP_GUIDE.md) at the repo root.

## Prerequisites

- Two Linux hosts (Arch / Debian / Fedora family). One-host deployments work too — just skip the WoL wiring.
- Python 3.11+ on the orchestrator.
- `llama.cpp` on the inference host, or any OpenAI-compatible endpoint.
- A GitHub repo for the vault (private recommended, since it will hold email metadata and personal notes).
- Obsidian + Obsidian Git plugin on your mobile devices.

## Orchestrator setup (5 minutes)

```bash
git clone https://github.com/SarangVehale/hermes-morning-run.git
cd hermes-morning-run
./setup.sh
```

`setup.sh` will:

1. Create `~/scripts/`, `~/.hermes/`, and copy the pipeline in place.
2. Bootstrap `~/vault-ai/` from the `vault/` template and initialize git.
3. Install a Python virtualenv at `~/.hermes/morning-venv/` with `feedparser`, `defuddle`, `yt-dlp`, `duckduckgo-search`, and friends.
4. Copy the systemd units to `~/.config/systemd/user/` and enable `hermes-morning.timer`.
5. Print the next steps (edit config, run OAuth grant, first-run smoke test).

## Inference host setup (15 minutes)

On the second machine:

```bash
git clone https://github.com/SarangVehale/hermes-morning-run.git
cd hermes-morning-run
./rog-setup.sh
```

`rog-setup.sh` will:

1. Install `llama.cpp` (build from source with your GPU flags — CUDA / ROCm / Metal / Vulkan).
2. Download the reference model set (or your preferred models — edit the script first).
3. Install the three `llama-server-*.service` units bound to `0.0.0.0` on ports 8080 / 8081 / 8082.
4. Configure WoWLAN via `wowlan-enable.service` so the host can be woken from suspend over WiFi.

## Wiring the two together

On the orchestrator, edit `~/scripts/morning-run.sh`:

```bash
RYZEN_MAC="${RYZEN_MAC:-AA:BB:CC:DD:EE:FF}"    # inference host's MAC
RYZEN_IP="${RYZEN_IP:-192.168.1.42}"           # inference host's LAN IP
```

Send a wake test:

```bash
wakeonlan "$RYZEN_MAC"
# host wakes; poll llama-server
curl -s "http://$RYZEN_IP:8080/health"
```

## Configuration

Edit `~/.hermes/morning-config.yaml`. The defaults are opinionated (Pune-centric news topics, quantum-heavy paper categories, a specific tech-YouTube watchlist). Replace them with your own:

```yaml
news:
  topics:
    - name: "Local"
      site_hints: ["your-local-paper.com"]
      queries: ["your city news today"]
    - name: "Your beat"
      # ...

papers:
  arxiv_categories: [cs.LG, cs.CV, stat.ML]  # or whatever
  max_picks: 8
  max_per_category: 2

tech:
  reddit_subs: [selfhosted, LocalLLaMA, homelab]
  hn_min_score: 100

watchlist:
  # or edit ~/vault-ai/_watchlist.yaml directly
```

## Google OAuth (optional — for Gmail / Calendar in the Brief)

For each account you want the Brief to see:

1. In [Google Cloud Console](https://console.cloud.google.com/), create an OAuth 2.0 Client (Desktop application). Download the JSON.
2. Save it as `~/.hermes/mcp-tokens/{account}.client.json` (e.g. `gmail_personal.client.json`).
3. Run:
   ```bash
   python3 ~/scripts/oauth-grant.py gmail_personal
   ```
   A browser tab opens, you click Allow, tab closes, token lands at `~/.hermes/mcp-tokens/gmail_personal.json`.
4. Repeat for `gmail_work`, `gmail_iitm`, `gmail_nfsu`, and their `calendar_*` counterparts.

**Publish the OAuth consent screen.** Testing-mode apps expire refresh tokens every 7 days — this is the single most common source of "why does my Brief keep saying my inbox is unreachable" pain.

## First run

```bash
systemctl --user start hermes-morning.service
journalctl --user -u hermes-morning.service -f
```

Expected wall-clock: 15–25 min end-to-end (watchlist dominates; RSS streams take under a minute each).

## Mobile setup

On your phone / tablet:

1. Install Obsidian.
2. Install the Obsidian Git community plugin.
3. Clone your vault repo into the Obsidian vault directory.
4. Configure "pull on startup" and (optionally) "commit on close".

The `mobile-setup-procedure.md` playbook in `_staging/` has the full walkthrough for iOS and Android including SSH-key setup on iSH / Termux.

## Troubleshooting

See [`_staging/maintenance-playbook.md`](https://github.com/SarangVehale/hermes-morning-run/blob/main/_staging/maintenance-playbook.md) for the operational runbook (dead feeds, OAuth recovery, git conflict resolution, WoL debugging).
