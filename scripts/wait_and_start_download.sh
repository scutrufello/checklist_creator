#!/usr/bin/env bash
# Wait for a running download_card_images.py era to exit, then start the next era.
#
# Usage:
#   ./scripts/wait_and_start_download.sh WAIT_YEAR_FROM WAIT_YEAR_TO YEAR_FROM YEAR_TO [MIN_DELAY MAX_DELAY]
#
# Example (queue 2001-2010 after 1991-2000 download finishes):
#   nohup ./scripts/wait_and_start_download.sh 1991 2000 2001 2010 >> data/era_download_queue.log 2>&1 &
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

WAIT_YEAR_FROM="${1:?WAIT_YEAR_FROM required}"
WAIT_YEAR_TO="${2:?WAIT_YEAR_TO required}"
YEAR_FROM="${3:?YEAR_FROM required}"
YEAR_TO="${4:?YEAR_TO required}"
MIN_DELAY="${5:-0.5}"
MAX_DELAY="${6:-1.0}"

CHECKPOINT="./data/image_download_${YEAR_FROM}_${YEAR_TO}_checkpoint.json"
LOG="./data/image_download_${YEAR_FROM}_${YEAR_TO}.log"
PIDFILE="./data/image_download_${YEAR_FROM}_${YEAR_TO}.pid"
WAIT_PATTERN="download_card_images.py.*--year-from ${WAIT_YEAR_FROM}.*--year-to ${WAIT_YEAR_TO}"
START_PATTERN="download_card_images.py.*--year-from ${YEAR_FROM}.*--year-to ${YEAR_TO}"

log() {
  echo "$(date '+%Y-%m-%d %H:%M:%S') $*"
}

log "Waiting for download ${WAIT_YEAR_FROM}-${WAIT_YEAR_TO} to finish before starting ${YEAR_FROM}-${YEAR_TO}..."
while pgrep -f "$WAIT_PATTERN" >/dev/null 2>&1; do
  sleep 30
done
sleep 3

if pgrep -f "$START_PATTERN" >/dev/null 2>&1; then
  log "Download ${YEAR_FROM}-${YEAR_TO} already running; skip start."
  exit 0
fi

log "Download ${WAIT_YEAR_FROM}-${WAIT_YEAR_TO} finished; launching ${YEAR_FROM}-${YEAR_TO} (delay ${MIN_DELAY}-${MAX_DELAY}s)"

nohup sg devagent -c "./venv/bin/python scripts/download_card_images.py \
  --year-from ${YEAR_FROM} \
  --year-to ${YEAR_TO} \
  --min-delay ${MIN_DELAY} \
  --max-delay ${MAX_DELAY} \
  --settle-seconds 1.0 \
  --commit-every 25 \
  --checkpoint ${CHECKPOINT} \
  --log-file ${LOG}" >> "$LOG" 2>&1 &

sleep 3
NEW_PID="$(pgrep -f "$START_PATTERN" | head -1 || true)"
if [[ -z "$NEW_PID" ]]; then
  log "ERROR: could not find started download process for ${YEAR_FROM}-${YEAR_TO}"
  exit 1
fi

echo "$NEW_PID" > "$PIDFILE"
log "Started download ${YEAR_FROM}-${YEAR_TO} PID ${NEW_PID} (log ${LOG})"
