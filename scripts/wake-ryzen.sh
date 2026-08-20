#!/usr/bin/env bash
# ~/scripts/wake-ryzen.sh
# Standalone Wake-on-LAN for the Ryzen machine. Used by morning-run.sh and
# can be invoked manually any time you want the inference server up.
#
# Usage: ./wake-ryzen.sh [--wait]
#   --wait : block until the model server responds (or timeout after 3 min)

set -euo pipefail

RYZEN_MAC="${RYZEN_MAC:-AA:BB:CC:DD:EE:FF}"
RYZEN_HOSTNAME="${RYZEN_HOSTNAME:-rogflow.local}"
RYZEN_MODEL_PORT="${RYZEN_MODEL_PORT:-8080}"

log() { echo "[$(date +%H:%M:%S)] $*"; }

if [ "$RYZEN_MAC" = "AA:BB:CC:DD:EE:FF" ]; then
  echo "ERROR: edit RYZEN_MAC in this script (or export the env var)" >&2
  exit 1
fi

log "sending magic packet to $RYZEN_MAC"
if command -v wakeonlan >/dev/null 2>&1; then
  wakeonlan "$RYZEN_MAC"
elif command -v etherwake >/dev/null 2>&1; then
  sudo etherwake "$RYZEN_MAC"
else
  echo "ERROR: install wakeonlan or etherwake (sudo pacman -S wol)" >&2
  exit 1
fi

if [ "${1:-}" = "--wait" ]; then
  log "waiting for $RYZEN_HOSTNAME:$RYZEN_MODEL_PORT..."
  for i in {1..36}; do
    if curl -sf --max-time 5 "http://$RYZEN_HOSTNAME:$RYZEN_MODEL_PORT/v1/models" >/dev/null 2>&1; then
      log "model server up (took ${i} attempts, ~$((i*5))s)"
      exit 0
    fi
    sleep 5
  done
  echo "ERROR: model server did not respond within 3 minutes" >&2
  exit 1
fi
