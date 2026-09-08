# Setup

This is the summary path. The exhaustive walkthrough — with exact commands, config templates, and troubleshooting — lives in [`SETUP_GUIDE.md`](https://github.com/SarangVehale/hermes-morning-run/blob/main/SETUP_GUIDE.md) at the repo root.

<div class="toc"><div class="toc-title">On this page</div>
<ul>
  <li><a href="#prerequisites">Prerequisites</a></li>
  <li><a href="#one-shot-install">One-shot install</a></li>
  <li><a href="#claude-cli-auth">Claude CLI auth</a></li>
  <li><a href="#configuration">Configuration</a></li>
  <li><a href="#google-oauth-optional">Google OAuth (optional)</a></li>
  <li><a href="#first-run">First run</a></li>
  <li><a href="#mobile-sync">Mobile sync</a></li>
  <li><a href="#uninstall">Uninstall</a></li>
</ul>
</div>

## Prerequisites

- **One Linux host** (Arch / Debian / Fedora family). Since v2.1 the two-machine split is gone — an old laptop is enough.
- **Python 3.11+** on the host.
- **Claude Code CLI** (`claude`) installed and logged in. This is the LLM layer. Free-tier Claude Code works; a Pro / Max subscription is recommended for the usage volume.
- **A GitHub repo for the vault** (private recommended, since it will hold email metadata and personal notes).
- **Obsidian + Obsidian Git plugin** on your mobile devices.

## One-shot install

```bash
git clone https://github.com/SarangVehale/hermes-morning-run.git
cd hermes-morning-run
./setup.sh
```

`setup.sh` will:

1. Create `~/scripts/`, `~/.hermes/`, and copy the pipeline in place.
2. Bootstrap `~/vault-ai/` from the `vault/` template and initialize git.
3. Install a Python virtualenv at `~/.hermes/morning-venv/` with `feedparser`, `defuddle`, `yt-dlp`, `ddgs`, `httpx`, `pyyaml`, and friends.
4. Copy the systemd units to `~/.config/systemd/user/` and enable `hermes-morning.timer`.
5. Print the next steps (edit config, run OAuth grant, first-run smoke test).

## Claude CLI auth

If Claude Code isn't already installed:

```bash
# See https://docs.claude.com/en/docs/claude-code for the current install command.
# Example (subject to change):
curl -fsSL https://claude.com/install.sh | bash
```

Then log in:

```bash
claude /login
```

A browser opens for OAuth. Verify:

```bash
claude auth status
# should show: loggedIn: true, authMethod: claude.ai, subscriptionType: pro (or max, or free)
```

Smoke-test the print-mode path the pipeline uses:

```bash
echo "reply with the single word ok" | claude -p --model sonnet --restricted --output-format text
# → ok
```

Any output that isn't the expected response — especially `Not logged in · Please run /login` — means `llm.py` will fall back to HP-local ollama for every LLM stream. Fix auth before scheduling the timer.

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
  arxiv_categories: [cs.LG, cs.CV, stat.ML]
  max_picks: 8
  max_per_category: 2

tech:
  reddit_subs: [selfhosted, LocalLLaMA, homelab]
  hn_min_score: 100
```

Creator watchlist lives at `~/vault-ai/_watchlist.yaml`:

```yaml
youtube:
  - name: Veritasium
    channel_id: UCHnyfMqiRRG1u-2MsSQLbXA
blogs:
  - name: Simon Willison
    url: https://simonwillison.net
    feed: https://simonwillison.net/atom/everything/
```

GitHub repos to track for releases live at `~/vault-ai/_tools.yaml`.

## Google OAuth (optional)

For the Brief to include Gmail and Calendar:

1. In [Google Cloud Console](https://console.cloud.google.com/), create an OAuth 2.0 Client (Desktop application). Download the JSON.
2. Save it as `~/.hermes/mcp-tokens/{account}.client.json` (e.g. `gmail_personal.client.json`).
3. Run:
   ```bash
   python3 ~/scripts/oauth-grant.py gmail_personal
   ```
   A browser tab opens, you click Allow, tab closes, token lands at `~/.hermes/mcp-tokens/gmail_personal.json`.
4. Repeat for each Gmail and Calendar account you want (up to 4 of each with the reference `google.py`).

<div class="callout warn"><div class="callout-title">Publish the OAuth consent screen</div>
Testing-mode apps expire refresh tokens every 7 days — this is the single most common source of "why does my Brief keep saying my inbox is unreachable" pain. See <a href="troubleshooting.html#oauth-invalid_grant-across-all-accounts">Troubleshooting</a>.
</div>

## First run

```bash
systemctl --user start hermes-morning.service
journalctl --user -u hermes-morning.service -f
```

Expected wall-clock: 5-15 min end-to-end. Watchlist dominates (~1-3 min); RSS streams take under a minute each; LLM stages average ~3s per `claude` call.

## Mobile sync

On your phone / tablet:

1. Install Obsidian.
2. Install the Obsidian Git community plugin.
3. Clone your vault repo into the Obsidian vault directory.
4. Configure "pull on startup" and (optionally) "commit on close".

The `mobile-setup-procedure.md` playbook in `_staging/` has the full walkthrough for iOS and Android, including SSH-key setup on iSH / Termux.

## Uninstall

```bash
systemctl --user disable --now hermes-morning.timer hermes-weekly.timer
rm ~/.config/systemd/user/hermes-*.service ~/.config/systemd/user/hermes-*.timer
systemctl --user daemon-reload

rm -rf ~/scripts/morning ~/scripts/morning-run.sh ~/scripts/oauth-grant.py \
       ~/scripts/concept-stubs.py ~/scripts/connection-finder.py \
       ~/scripts/weekly-recap.sh
rm -rf ~/.hermes/morning-venv ~/.hermes/state ~/.hermes/logs
```

Vault (`~/vault-ai/`) and OAuth tokens (`~/.hermes/mcp-tokens/`) are kept intentionally — remove them manually only if you're sure.

{% include nav.html
  prev="stack" prev_title="Stack"
  next="troubleshooting" next_title="Troubleshooting" %}
