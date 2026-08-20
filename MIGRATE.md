# Migrating hermes-vault to new hardware

Runbook for moving the morning-briefing system to a different always-on
machine. Tested on Arch Linux; instructions for Debian/Ubuntu noted inline.

## What you're moving

| Component | Where it lives now | Notes |
|---|---|---|
| Vault content | GitHub (`YOUR_GH_USER/vault-ai`) | Single source of truth; clone from anywhere |
| Stream state | `~/.hermes/state/*.json` | Last-seen IDs, cooldowns, streak. Snapshotted into vault under `.hermes-backups/state-*.tar.gz` daily |
| OAuth tokens | `~/.hermes/mcp-tokens/*.json` | **NOT in backup.** Must re-grant on the new machine |
| Inference (LLM) | ROG Flow X13 at `rog:8080` | Stays on ROG; new machine just needs to reach it |
| Scripts + Python deps | `~/scripts` + `~/.hermes/morning-venv/` | Re-created by `setup.sh` |
| systemd units | `/etc/systemd/system/hermes-*.{timer,service}` | Re-installed by `setup.sh` |

## Procedure

### 1. On the OLD machine — capture latest state

```bash
# Force a state snapshot into the vault before migration
python -m morning.maintenance

# Push everything that's local-only
cd ~/vault-ai && git add -A && git commit -m "pre-migration snapshot" && git push
```

You're capturing the per-stream cooldowns and last-seen IDs so the new
machine doesn't re-surface the last 30 days of news on first run.

### 2. On the NEW machine — bootstrap

```bash
# Ensure git + SSH keys are configured for GitHub
ssh -T git@github.com  # should print "Hi YOUR_GH_USER!"

# Clone the bundle source-of-truth
git clone <bundle-repo> ~/Development/hermes-vault-setup
cd ~/Development/hermes-vault-setup

# Run the bootstrap. Add --skip-systemd if you don't want timers yet.
bash setup.sh
```

`setup.sh` is idempotent and does:

1. Install system packages (git, python, rsync, openssh, curl, yt-dlp, ripgrep)
2. Symlink `~/scripts/*` from the bundle
3. Create the Python venv at `~/.hermes/morning-venv/` and install pip deps
4. Clone the vault from GitHub to `~/vault-ai`
5. Write a default `~/.hermes/morning-config.yaml` if missing
6. Restore state from the most recent `.hermes-backups/state-*.tar.gz` in the vault
7. Install + enable systemd units (timer enabled, service has `DRY_RUN=1` baked in)

### 3. Configure for your inference host

Edit `~/.hermes/morning-config.yaml`:

```yaml
llm:
  primary_url: http://<your-rog-ip>:8080/v1/chat/completions
  fast_url:    http://<your-rog-ip>:8081/v1/chat/completions
  hp_ollama_url: http://localhost:11434/v1/chat/completions  # if you run ollama on the new HP
```

If the new machine IS the inference host, point at `http://localhost:8080`.

### 4. OAuth re-grants

Tokens don't migrate (security). Re-run for each:

```bash
python ~/scripts/oauth-grant.py gmail_personal
python ~/scripts/oauth-grant.py gmail_work
python ~/scripts/oauth-grant.py gmail_iitm
python ~/scripts/oauth-grant.py gmail_nfsu
python ~/scripts/oauth-grant.py calendar_personal
python ~/scripts/oauth-grant.py calendar_work
python ~/scripts/oauth-grant.py calendar_iitm
python ~/scripts/oauth-grant.py calendar_nfsu
```

Each opens a browser tab. If on a headless machine, see "Remote OAuth"
section in the bundle's `_staging/oauth-procedure.md`.

### 5. Verify

```bash
# Comprehensive health check — exits 0/1/2 for clean/warn/fail
PYTHONPATH=~/scripts ~/.hermes/morning-venv/bin/python -m morning.doctor

# Dry-run the pipeline (vault edits proceed, no push, no shutdown)
DRY_RUN=1 ~/scripts/morning-run.sh
```

Expected duration: 25-35 minutes on first run (no state cache → most streams
process up to their per-creator/per-topic limits).

### 6. Go live

After the first scheduled fire succeeds:

```bash
# Edit the service unit to remove DRY_RUN=1
sudo $EDITOR /etc/systemd/system/hermes-morning.service
# Delete the line: Environment="DRY_RUN=1"
sudo systemctl daemon-reload
```

The next 05:55 IST fire will push to GitHub and SSH-shutdown the ROG.

### 7. Mobile devices

If switching infrastructure changes the GitHub repo URL or branch, update
Obsidian Git settings on each phone/iPad. Otherwise nothing changes — they
pull from GitHub same as before.

## Rollback

The old machine still has working state. If migration fails, disable the
new timer and re-enable the old one:

```bash
# On new machine
sudo systemctl disable --now hermes-morning.timer hermes-weekly.timer

# On old machine
sudo systemctl enable --now hermes-morning.timer hermes-weekly.timer
```

State on the old machine is unchanged.

## Disaster recovery (vault loss)

If GitHub is unavailable AND your vault is gone:

```bash
# rsync backup is the second copy
cp -r ~/backups/vault-ai/latest/ ~/vault-ai-restored/
cd ~/vault-ai-restored
git init && git add -A && git commit -m "restored from rsync backup"
# Push to a new GitHub repo, point Obsidian Git at it
```

The rsync backup excludes `.git/`, so you'll need to re-create the GitHub
history. Content is preserved.

## What's NOT in the migration

- `~/.hermes/mcp-tokens/` — security-sensitive, re-grant manually
- `~/.hermes/logs/` — disposable; old logs stay on the old machine
- `~/Development/hermes-vault-setup/` — clone fresh from your bundle repo
- Plugin downloads in `.obsidian/plugins/` other than what's tracked in git
  (Dataview is tracked; mobile may need Browse → Install)
