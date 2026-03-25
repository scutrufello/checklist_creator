#!/usr/bin/env bash
# Install user systemd timer for twice-daily --recent-years scrape.
# Usage: ./scripts/install-recent-scrape-timer.sh

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
UNIT_DIR="${HOME}/.config/systemd/user"
mkdir -p "$UNIT_DIR"
cp "$ROOT/systemd/phillies-tcdb-recent-scrape.service" "$UNIT_DIR/"
cp "$ROOT/systemd/phillies-tcdb-recent-scrape.timer" "$UNIT_DIR/"
systemctl --user daemon-reload
systemctl --user enable phillies-tcdb-recent-scrape.timer
systemctl --user start phillies-tcdb-recent-scrape.timer
systemctl --user list-timers phillies-tcdb-recent-scrape.timer --no-pager
