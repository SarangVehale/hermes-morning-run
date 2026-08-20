#!/usr/bin/env bash
# ~/scripts/morning-run.sh
# Triggered by hermes-morning.timer at 05:55 IST daily.
#
# Pipeline (Path A — Python orchestrator):
#   1. git pull --rebase the vault
#   2. probe the ROG llama-server (no WoL — ROG stays awake overnight)
#   3. invoke `python3 -m morning.runner` (replaces the old `hermes -z` prompt)
#   4. run post-pass scripts (concept-stubs, connection-finder)
#   5. commit changes
#   6. push to GitHub (skipped if DRY_RUN=1)
#   7. send ssh shutdown to ROG (skipped if DRY_RUN=1)
#
# Env knobs:
#   DRY_RUN=1         vault edits proceed; no git push, no ROG shutdown.
#   HERMES_NO_WRITE=1 orchestrator prints composed brief to stdout only.
#   PREFER_MODEL      passed through to streams as --prefer (primary|fast).

set -euo pipefail

# --- Config -------------------------------------------------------------------
RYZEN_HOST="${RYZEN_HOST:-rog}"
RYZEN_SSH_HOST="${RYZEN_SSH_HOST:-rog}"
RYZEN_MODEL_PORT="${RYZEN_MODEL_PORT:-8080}"
VAULT_ROOT="${VAULT_ROOT:-$HOME/vault-ai}"
MORNING_VENV="${MORNING_VENV:-$HOME/.hermes/morning-venv}"
SCRIPTS_ROOT="${SCRIPTS_ROOT:-$HOME/scripts}"
LOG_FILE="${HOME}/.hermes/logs/morning-run-$(date +%Y-%m-%d).log"
DRY_RUN="${DRY_RUN:-0}"
HERMES_NO_WRITE="${HERMES_NO_WRITE:-0}"
SKIP_ROG_SHUTDOWN="${SKIP_ROG_SHUTDOWN:-0}"

# --- Setup --------------------------------------------------------------------
mkdir -p "$(dirname "$LOG_FILE")"
exec > >(tee -a "$LOG_FILE") 2>&1

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }
log "morning-run starting (DRY_RUN=$DRY_RUN, HERMES_NO_WRITE=$HERMES_NO_WRITE)"

# --- Sanity checks ------------------------------------------------------------
[ -d "$VAULT_ROOT/.git" ]                  || { log "FATAL: $VAULT_ROOT is not a git repo"; exit 1; }
[ -x "$MORNING_VENV/bin/python" ]          || { log "FATAL: morning venv missing at $MORNING_VENV"; exit 1; }
[ -d "$SCRIPTS_ROOT/morning" ]             || { log "FATAL: orchestrator package missing at $SCRIPTS_ROOT/morning"; exit 1; }

cd "$VAULT_ROOT"

# --- Pull latest from GitHub --------------------------------------------------
log "git pull --rebase"
git pull --rebase origin main || log "WARNING: git pull failed; continuing with local state"

# --- Probe the ROG model server (no WoL — ROG stays on overnight) -------------
log "probing model server at ${RYZEN_HOST}:${RYZEN_MODEL_PORT}"
MODEL_READY=0
for i in $(seq 1 12); do
  if curl -sf --max-time 5 "http://${RYZEN_HOST}:${RYZEN_MODEL_PORT}/v1/models" >/dev/null 2>&1; then
    log "model server up after ${i} attempts"
    MODEL_READY=1
    break
  fi
  sleep 5
done

if [ "$MODEL_READY" = "0" ]; then
  log "WARNING: ROG model server unreachable. Orchestrator will fall back to FAST/HP_OLLAMA per llm.py chain."
fi

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
# concept-stubs.py disabled — it generated 479 body-empty stubs that polluted
# the random-note widget and the graph view. Wikilinks to nonexistent notes
# now stay as dangling refs in Obsidian's graph (visually distinct as grey
# nodes). Re-enable below if you want stub creation back.
# log "running concept-stubs.py"
# python3 "$SCRIPTS_ROOT/concept-stubs.py" --vault "$VAULT_ROOT" || log "WARNING: concept-stubs.py failed"

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

# --- Shutdown the ROG ---------------------------------------------------------
if [ "$DRY_RUN" = "1" ] || [ "$SKIP_ROG_SHUTDOWN" = "1" ]; then
  log "skipping ROG shutdown (DRY_RUN=$DRY_RUN, SKIP_ROG_SHUTDOWN=$SKIP_ROG_SHUTDOWN)"
else
  log "sending shutdown signal to ROG"
  ssh -o ConnectTimeout=5 "$RYZEN_SSH_HOST" "sudo systemctl poweroff" || log "WARNING: ssh shutdown failed (may have already died, may be a sudoers issue)"
fi

log "morning-run complete"
