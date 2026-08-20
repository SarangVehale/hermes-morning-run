#!/usr/bin/env bash
# ~/scripts/morning-run.sh
# Triggered by hermes-morning.timer at 05:55 IST daily.
#
# Pipeline (Path A — Python orchestrator):
#   1. git pull --rebase the vault
#   2. START the ROG llama-servers via systemctl --user (user-scoped, no sudo)
#   3. wait for both /v1/models endpoints to be reachable
#   4. invoke `python3 -m morning.runner`
#   5. run post-pass scripts (wikifill, connection-finder, maintenance)
#   6. commit changes
#   7. push to GitHub (skipped if DRY_RUN=1)
#   8. STOP the ROG llama-servers so they leave no RAM/CPU residue on ROG
#      (ROG is the user's daily-driver; llama-servers only run during the
#      morning window)
#
# Env knobs:
#   DRY_RUN=1         vault edits proceed; no git push, llama-servers still
#                     stopped after (that's the whole point).
#   HERMES_NO_WRITE=1 orchestrator prints composed brief to stdout only.
#   SKIP_ROG_STOP=1   leave llama-servers running after the run (dev only).
#   SKIP_ROG_START=1  don't try to start them (assume already up).
#   PREFER_MODEL      passed through to streams as --prefer (primary|fast).

set -euo pipefail

# --- Config -------------------------------------------------------------------
RYZEN_HOST="${RYZEN_HOST:-rog}"
RYZEN_SSH_HOST="${RYZEN_SSH_HOST:-rog}"
RYZEN_MAC="${RYZEN_MAC:-AA:BB:CC:DD:EE:FF}"    # ROG's wlan0 MAC — used for WoL
RYZEN_MODEL_PORT="${RYZEN_MODEL_PORT:-8080}"
RYZEN_FAST_PORT="${RYZEN_FAST_PORT:-8081}"
VAULT_ROOT="${VAULT_ROOT:-$HOME/vault-ai}"
MORNING_VENV="${MORNING_VENV:-$HOME/.hermes/morning-venv}"
SCRIPTS_ROOT="${SCRIPTS_ROOT:-$HOME/scripts}"
LOG_FILE="${HOME}/.hermes/logs/morning-run-$(date +%Y-%m-%d).log"
DRY_RUN="${DRY_RUN:-0}"
HERMES_NO_WRITE="${HERMES_NO_WRITE:-0}"
SKIP_ROG_START="${SKIP_ROG_START:-0}"
SKIP_ROG_STOP="${SKIP_ROG_STOP:-0}"
# Legacy compat: SKIP_ROG_SHUTDOWN used to mean "don't poweroff ROG". We no
# longer poweroff; SKIP_ROG_STOP is the new knob. Old callers keep working.
if [ "${SKIP_ROG_SHUTDOWN:-0}" = "1" ]; then SKIP_ROG_STOP=1; fi

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

# --- Wake ROG if it's suspended (Wake-on-WLAN magic packet) -------------------
# ROG frequently suspends overnight. When suspended its WiFi radio drops
# ARP responses, so ssh times out with "No route to host". Send a magic
# packet FIRST, then wait for the ARP entry to come back before we try ssh.
if [ "$SKIP_ROG_START" = "1" ]; then
  log "SKIP_ROG_START=1 — skipping WoL + llama-server start"
else
  # Send 3 packets over 6 sec — WiFi packet loss makes single-packet unreliable.
  log "sending WoL magic packet to ROG ($RYZEN_MAC)"
  for i in 1 2 3; do
    /usr/bin/wol "$RYZEN_MAC" >/dev/null 2>&1 || true
    sleep 2
  done

  log "waiting for ROG to come up"
  ROG_UP=0
  for i in $(seq 1 20); do
    if ping -c 1 -W 2 "$RYZEN_HOST" >/dev/null 2>&1; then
      log "ROG responded to ping after ${i} attempts"
      ROG_UP=1
      break
    fi
    # Resend WoL every 5 attempts in case WiFi missed the first burst.
    if [ $((i % 5)) = 0 ]; then
      /usr/bin/wol "$RYZEN_MAC" >/dev/null 2>&1 || true
    fi
    sleep 3
  done

  if [ "$ROG_UP" = "0" ]; then
    log "WARNING: ROG did not respond to WoL. Proceeding — will fall back to HP-local ollama."
  else
    # Give ROG's networking + sshd another moment after ARP comes back.
    sleep 3
    log "starting ROG llama-servers via systemctl --user"
    ssh -o ConnectTimeout=5 "$RYZEN_SSH_HOST" \
      'XDG_RUNTIME_DIR=/run/user/$(id -u) systemctl --user start llama-server-primary llama-server-fast' \
      || log "WARNING: could not start llama-servers on ROG"
  fi
fi

# --- Probe both endpoints until healthy ---------------------------------------
log "probing model server at ${RYZEN_HOST}:${RYZEN_MODEL_PORT}"
MODEL_READY=0
for i in $(seq 1 30); do
  # Primary model is a 26B — cold start can take up to ~2 min to load weights.
  if curl -sf --max-time 5 "http://${RYZEN_HOST}:${RYZEN_MODEL_PORT}/v1/models" >/dev/null 2>&1; then
    log "primary model server up after ${i} attempts"
    MODEL_READY=1
    break
  fi
  sleep 5
done
if [ "$MODEL_READY" = "0" ]; then
  log "WARNING: ROG primary model server unreachable. Orchestrator will fall back to FAST/HP_OLLAMA."
fi

# Fast sidecar (Qwen 3B) — loads in seconds, cheap to wait on.
FAST_READY=0
for i in $(seq 1 6); do
  if curl -sf --max-time 5 "http://${RYZEN_HOST}:${RYZEN_FAST_PORT}/v1/models" >/dev/null 2>&1; then
    log "fast sidecar up after ${i} attempts"
    FAST_READY=1
    break
  fi
  sleep 5
done
if [ "$FAST_READY" = "0" ]; then
  log "WARNING: ROG fast sidecar unreachable."
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

# --- Stop ROG llama-servers, then power ROG off -------------------------------
# ROG runs 24+ hours as the user's daily driver and needs rest — power it off
# after the pipeline so it can get 4-5 hours of sleep before whenever the
# user picks it back up. The llama-server stop is technically redundant when
# followed by poweroff but it's cheap insurance for the case where poweroff
# fails (sudoers change, network drop, whatever) — we still want zero residue.
if [ "$SKIP_ROG_STOP" = "1" ]; then
  log "SKIP_ROG_STOP=1 — leaving llama-servers running and ROG powered on"
else
  log "stopping ROG llama-servers"
  ssh -o ConnectTimeout=5 "$RYZEN_SSH_HOST" \
    'XDG_RUNTIME_DIR=/run/user/$(id -u) systemctl --user stop llama-server-primary llama-server-fast' \
    || log "WARNING: could not stop llama-servers on ROG"

  log "powering off ROG"
  # ssh exits with 255 when the remote session is killed by shutdown;
  # that's the expected happy path, not a failure. Ignore non-zero.
  ssh -o ConnectTimeout=5 "$RYZEN_SSH_HOST" 'sudo -n systemctl poweroff' 2>&1 | \
    grep -vE "Connection.*closed|Connection reset" | \
    sed 's/^/  ssh: /' || true
fi

log "morning-run complete"
