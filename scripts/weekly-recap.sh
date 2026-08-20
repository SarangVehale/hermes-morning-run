#!/usr/bin/env bash
# ~/scripts/weekly-recap.sh
# Triggered by hermes-weekly.timer on Sundays at 20:00 IST.
#
# Pipeline:
#   1. git pull --rebase the vault
#   2. probe the ROG llama-server (best effort)
#   3. invoke `python3 -m morning.weekly` to compose the recap
#   4. commit + push (unless DRY_RUN=1)
#
# Env knobs:
#   DRY_RUN=1         vault edits proceed; no git push.
#   HERMES_NO_WRITE=1 print the composed recap to stdout, no vault writes.

set -euo pipefail

RYZEN_HOST="${RYZEN_HOST:-rog}"
RYZEN_MODEL_PORT="${RYZEN_MODEL_PORT:-8080}"
VAULT_ROOT="${VAULT_ROOT:-$HOME/vault-ai}"
MORNING_VENV="${MORNING_VENV:-$HOME/.hermes/morning-venv}"
SCRIPTS_ROOT="${SCRIPTS_ROOT:-$HOME/scripts}"
LOG_FILE="${HOME}/.hermes/logs/weekly-recap-$(date +%Y-%m-%d).log"
DRY_RUN="${DRY_RUN:-0}"
HERMES_NO_WRITE="${HERMES_NO_WRITE:-0}"

mkdir -p "$(dirname "$LOG_FILE")"
exec > >(tee -a "$LOG_FILE") 2>&1

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }
log "weekly-recap starting (DRY_RUN=$DRY_RUN, HERMES_NO_WRITE=$HERMES_NO_WRITE)"

[ -d "$VAULT_ROOT/.git" ]                  || { log "FATAL: $VAULT_ROOT not a git repo"; exit 1; }
[ -x "$MORNING_VENV/bin/python" ]          || { log "FATAL: morning venv missing"; exit 1; }
[ -d "$SCRIPTS_ROOT/morning" ]             || { log "FATAL: morning package missing"; exit 1; }

cd "$VAULT_ROOT"

log "git pull --rebase"
git pull --rebase origin main || log "WARNING: git pull failed; continuing"

log "probing model server at ${RYZEN_HOST}:${RYZEN_MODEL_PORT}"
if curl -sf --max-time 5 "http://${RYZEN_HOST}:${RYZEN_MODEL_PORT}/v1/models" >/dev/null 2>&1; then
  log "model server up"
else
  log "WARNING: ROG model server unreachable; falling back per llm.py chain"
fi

log "invoking python weekly recap"
PY_ARGS=()
[ "$HERMES_NO_WRITE" = "1" ] && PY_ARGS+=("--dry-run")

PYTHONPATH="$SCRIPTS_ROOT" "$MORNING_VENV/bin/python" -m morning.weekly "${PY_ARGS[@]}" \
  2>&1 | tee -a "$LOG_FILE" || log "WARNING: weekly recap exited non-zero"

log "git add + commit"
git add -A
if git diff --cached --quiet; then
  log "no changes to commit"
else
  git commit -m "weekly recap $(date -u +%Y-%m-%d)" || log "WARNING: commit failed"
  if [ "$DRY_RUN" = "1" ]; then
    log "DRY_RUN: skipping push"
  else
    log "git push"
    git push origin main || log "WARNING: push failed"
  fi
fi

log "weekly-recap complete"
