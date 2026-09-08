#!/usr/bin/env bash
# ~/scripts/morning-run.sh
# Triggered by hermes-morning.timer at 05:55 IST daily.
#
# Pipeline (single-machine, orchestrator only):
#   1. git pull --rebase the vault
#   2. invoke `python3 -m morning.runner` (uses `claude -p` for LLM calls)
#   3. run post-pass scripts (wikifill, connection-finder, maintenance)
#   4. commit changes
#   5. push to GitHub (skipped if DRY_RUN=1)
#
# Since v2.1 (2026-08-21), the ROG inference host has been decommissioned.
# The LLM layer is the `claude` CLI (Claude Code print mode) authenticated via
# the user's claude.ai Pro subscription — no local llama-server, no ROG wake-up,
# no llama.cpp, no GGUF models.
#
# Env knobs:
#   DRY_RUN=1         vault edits proceed; no git push.
#   HERMES_NO_WRITE=1 orchestrator prints composed brief to stdout only.
#   PREFER_MODEL      passed through to streams as --prefer (primary|fast).

set -euo pipefail

# --- Config -------------------------------------------------------------------
VAULT_ROOT="${VAULT_ROOT:-$HOME/vault-ai}"
MORNING_VENV="${MORNING_VENV:-$HOME/.hermes/morning-venv}"
SCRIPTS_ROOT="${SCRIPTS_ROOT:-$HOME/scripts}"
LOG_FILE="${HOME}/.hermes/logs/morning-run-$(date +%Y-%m-%d).log"
DRY_RUN="${DRY_RUN:-0}"
HERMES_NO_WRITE="${HERMES_NO_WRITE:-0}"

# --- Setup --------------------------------------------------------------------
mkdir -p "$(dirname "$LOG_FILE")"
exec > >(tee -a "$LOG_FILE") 2>&1

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }
log "morning-run starting (DRY_RUN=$DRY_RUN, HERMES_NO_WRITE=$HERMES_NO_WRITE)"

# --- Sanity checks ------------------------------------------------------------
[ -d "$VAULT_ROOT/.git" ]                  || { log "FATAL: $VAULT_ROOT is not a git repo"; exit 1; }
[ -x "$MORNING_VENV/bin/python" ]          || { log "FATAL: morning venv missing at $MORNING_VENV"; exit 1; }
[ -d "$SCRIPTS_ROOT/morning" ]             || { log "FATAL: orchestrator package missing at $SCRIPTS_ROOT/morning"; exit 1; }
command -v claude >/dev/null 2>&1          || log "WARNING: claude CLI not on PATH — LLM streams will fall back to ollama"

cd "$VAULT_ROOT"

# --- Pull latest from GitHub --------------------------------------------------
log "git pull --rebase"
git pull --rebase origin main || log "WARNING: git pull failed; continuing with local state"

# --- Run the Python orchestrator ----------------------------------------------
log "invoking python orchestrator: morning.runner"
PY_ARGS=()
if [ "$HERMES_NO_WRITE" = "1" ]; then
  PY_ARGS+=("--dry-run")
fi

PYTHONPATH="$SCRIPTS_ROOT" "$MORNING_VENV/bin/python" -m morning.runner "${PY_ARGS[@]}" \
  2>&1 | tee -a "$LOG_FILE" || {
  log "WARNING: orchestrator exited non-zero. Continuing to post-pass + commit."
}

# --- Post-run scripts ---------------------------------------------------------
log "running wikifill (today's dangling wikilinks → Wikipedia/DDGS-backed notes)"
PYTHONPATH="$SCRIPTS_ROOT" "$MORNING_VENV/bin/python" -m morning.wikifill \
  --vault "$VAULT_ROOT" --cap 80 --today-only \
  2>&1 | tee -a "$LOG_FILE" || log "WARNING: wikifill failed"

log "running connection-finder.py"
python3 "$SCRIPTS_ROOT/connection-finder.py" --vault "$VAULT_ROOT" --today-only || log "WARNING: connection-finder.py failed"

log "running maintenance pass"
PYTHONPATH="$SCRIPTS_ROOT" "$MORNING_VENV/bin/python" -m morning.maintenance 2>&1 | tee -a "$LOG_FILE" || log "WARNING: maintenance pass failed"

# --- Commit and push ----------------------------------------------------------
log "git add + commit"
git add -A
if git diff --cached --quiet; then
  log "no changes to commit"
else
  git commit -m "morning run $(date -u +%Y-%m-%dT%H:%M:%SZ)" || log "WARNING: commit failed"
  if [ "$DRY_RUN" = "1" ]; then
    log "DRY_RUN: skipping push"
  else
    log "git push"
    git push origin main || log "WARNING: push failed"
  fi
fi

log "morning-run complete"
