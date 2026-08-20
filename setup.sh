#!/usr/bin/env bash
# setup.sh — bootstrap the morning-briefing system on a fresh machine.
#
# Assumptions:
#   - Arch Linux (or any glibc systemd distro; pacman commands need adjusting
#     for Debian/Ubuntu)
#   - SSH keys already configured to clone GitHub
#   - You will edit ~/.hermes/morning-config.yaml afterward to point the LLM
#     URLs at your inference host
#
# Usage:
#   bash setup.sh [--skip-systemd]
#
# Idempotent: re-running is safe. Skips steps already done.

set -euo pipefail

SKIP_SYSTEMD=0
for arg in "$@"; do
  case "$arg" in
    --skip-systemd) SKIP_SYSTEMD=1 ;;
    *) echo "unknown arg: $arg"; exit 2 ;;
  esac
done

HERMES_DIR="$HOME/.hermes"
SCRIPTS_DIR="$HOME/scripts"
VAULT_DIR="$HOME/vault-ai"
BUNDLE_DIR="$HOME/Development/hermes-vault-setup"
VAULT_REPO="git@github.com:YOUR_GH_USER/vault-ai.git"

say()  { echo "  → $*"; }
need() { command -v "$1" >/dev/null 2>&1 || { echo "MISSING: $1"; return 1; }; }

echo "=== hermes-vault-setup bootstrap ==="

# ── 1. System packages ────────────────────────────────────────────────────────
say "[1/8] System packages"
if command -v pacman >/dev/null 2>&1; then
  sudo pacman -S --needed --noconfirm git python python-pip python-virtualenv rsync openssh curl yt-dlp ripgrep || true
elif command -v apt-get >/dev/null 2>&1; then
  sudo apt-get update
  sudo apt-get install -y git python3 python3-pip python3-venv rsync openssh-client curl ripgrep
  # yt-dlp may need to come from pip on Debian
  pip3 install --user yt-dlp || true
fi

# ── 2. Bundle directory ──────────────────────────────────────────────────────
say "[2/8] Bundle directory"
mkdir -p "$BUNDLE_DIR"
if [ ! -d "$BUNDLE_DIR/.git" ]; then
  echo "  Tip: clone the bundle into $BUNDLE_DIR for source-of-truth scripts."
fi

# ── 3. Scripts symlink ────────────────────────────────────────────────────────
say "[3/8] Scripts (symlinking bundle/scripts → ~/scripts)"
mkdir -p "$SCRIPTS_DIR"
for f in "$BUNDLE_DIR"/scripts/*; do
  [ -e "$f" ] || continue
  target="$SCRIPTS_DIR/$(basename "$f")"
  if [ -e "$target" ] && [ ! -L "$target" ]; then
    say "  exists (not symlinked, skipping): $target"
  else
    ln -sf "$f" "$target"
  fi
done
chmod +x "$SCRIPTS_DIR"/*.sh "$SCRIPTS_DIR"/*.py 2>/dev/null || true

# ── 4. Python venv + deps ────────────────────────────────────────────────────
say "[4/8] Python venv at $HERMES_DIR/morning-venv"
mkdir -p "$HERMES_DIR/morning-venv" "$HERMES_DIR/state" "$HERMES_DIR/logs" "$HERMES_DIR/mcp-tokens"
chmod 700 "$HERMES_DIR/mcp-tokens"
if [ ! -f "$HERMES_DIR/morning-venv/bin/python" ]; then
  python3 -m venv "$HERMES_DIR/morning-venv"
fi
"$HERMES_DIR/morning-venv/bin/pip" install --quiet --upgrade pip
"$HERMES_DIR/morning-venv/bin/pip" install --quiet ddgs feedparser requests pyyaml

# ── 5. Vault clone ────────────────────────────────────────────────────────────
say "[5/8] Vault clone at $VAULT_DIR"
if [ ! -d "$VAULT_DIR/.git" ]; then
  git clone "$VAULT_REPO" "$VAULT_DIR"
else
  say "  exists; running git pull"
  (cd "$VAULT_DIR" && git pull --rebase || true)
fi

# ── 6. Default morning-config.yaml ───────────────────────────────────────────
say "[6/8] Default morning-config.yaml"
PYTHONPATH="$SCRIPTS_DIR" "$HERMES_DIR/morning-venv/bin/python" -c "
from morning import config
written = config.write_default_if_missing()
print('  config:', 'created' if written else 'already exists', config.CONFIG_PATH)
"

# ── 7. State restore from latest backup, if present ───────────────────────────
say "[7/8] State restore"
LATEST_TARBALL=$(ls -t "$VAULT_DIR"/.hermes-backups/state-*.tar.gz 2>/dev/null | head -1 || true)
if [ -n "$LATEST_TARBALL" ]; then
  say "  restoring from $(basename "$LATEST_TARBALL")"
  tar xzf "$LATEST_TARBALL" -C "$HERMES_DIR/state/"
  say "  restored. New machine inherits last-seen IDs, cooldown windows, streak counter."
else
  say "  no state tarball in vault. State files will populate on first run."
fi

# ── 8. systemd units ─────────────────────────────────────────────────────────
if [ "$SKIP_SYSTEMD" = "0" ]; then
  say "[8/8] systemd units"
  if [ -d "$BUNDLE_DIR/systemd" ]; then
    say "  installing to /etc/systemd/system (sudo)"
    sudo cp "$BUNDLE_DIR"/systemd/hermes-morning.{service,timer} /etc/systemd/system/
    sudo cp "$BUNDLE_DIR"/systemd/hermes-weekly.{service,timer} /etc/systemd/system/
    sudo systemctl daemon-reload
    say "  enabling timers (NOT starting service — that runs at 05:55 IST)"
    sudo systemctl enable hermes-morning.timer hermes-weekly.timer
    say "  service unit currently has DRY_RUN=1 baked in — remove that line"
    say "  when first scheduled fire is verified. See MIGRATE.md."
  else
    say "  no systemd/ directory in bundle; skipping"
  fi
else
  say "[8/8] systemd: skipped (--skip-systemd)"
fi

echo ""
echo "=== bootstrap complete ==="
echo ""
echo "Verify:"
echo "  PYTHONPATH=$SCRIPTS_DIR $HERMES_DIR/morning-venv/bin/python -m morning.doctor"
echo ""
echo "Dry-run the pipeline (vault edits, no push, no shutdown):"
echo "  DRY_RUN=1 $SCRIPTS_DIR/morning-run.sh"
echo ""
echo "Next:"
echo "  - Edit $HERMES_DIR/morning-config.yaml — point LLM URLs at your inference host"
echo "  - OAuth grants (8 of them) for Gmail + Calendar MCPs:"
echo "      python $SCRIPTS_DIR/oauth-grant.py gmail_personal  (etc)"
echo "  - Mobile: open the GitHub repo in Obsidian Git on each device, sync"
