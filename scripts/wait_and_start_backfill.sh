#!/usr/bin/env bash
# Wait for a running backfill_card_images.py process to exit, then start the next era.
#
# Usage:
#   ./scripts/wait_and_start_backfill.sh WAIT_PID YEAR_FROM YEAR_TO [MIN_DELAY MAX_DELAY]
#
# Example (queue 2001-2010 after PID 66041 finishes):
#   nohup ./scripts/wait_and_start_backfill.sh 66041 2001 2010 >> data/era_backfill_queue.log 2>&1 &
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

WAIT_PID="${1:?WAIT_PID required}"
YEAR_FROM="${2:?YEAR_FROM required}"
YEAR_TO="${3:?YEAR_TO required}"
MIN_DELAY="${4:-1.0}"
MAX_DELAY="${5:-1.4}"

CHECKPOINT="./data/image_backfill_${YEAR_FROM}_${YEAR_TO}_checkpoint.json"
LOG="./data/image_backfill_${YEAR_FROM}_${YEAR_TO}.log"
PIDFILE="./data/image_backfill_${YEAR_FROM}_${YEAR_TO}.pid"
QUEUE_LOG="./data/era_backfill_queue.log"

log() {
  echo "$(date '+%Y-%m-%d %H:%M:%S') $*"
}

log "Waiting for backfill PID ${WAIT_PID} before starting ${YEAR_FROM}-${YEAR_TO}..."
while kill -0 "$WAIT_PID" 2>/dev/null; do
  sleep 30
done
sleep 3

if pgrep -f "backfill_card_images.py.*--year-from ${YEAR_FROM}.*--year-to ${YEAR_TO}" >/dev/null 2>&1; then
  log "Backfill ${YEAR_FROM}-${YEAR_TO} already running; skip start."
  exit 0
fi

log "PID ${WAIT_PID} gone; launching ${YEAR_FROM}-${YEAR_TO} (delay ${MIN_DELAY}-${MAX_DELAY}s)"

nohup ./venv/bin/python scripts/backfill_card_images.py \
  --year-from "$YEAR_FROM" \
  --year-to "$YEAR_TO" \
  --min-delay "$MIN_DELAY" \
  --max-delay "$MAX_DELAY" \
  --checkpoint "$CHECKPOINT" \
  --log-file "$LOG" >> "$LOG" 2>&1 &

NEW_PID=$!
echo "$NEW_PID" > "$PIDFILE"
log "Started backfill ${YEAR_FROM}-${YEAR_TO} PID ${NEW_PID} (log ${LOG})"
