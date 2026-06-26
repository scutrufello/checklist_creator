#!/usr/bin/env bash
set -euo pipefail

# Install Phillies checklist systemd units (system-wide, start on boot).
# Usage: sudo ./install.sh
# Custom tree: INSTALL_ROOT=/path/to/phillies-cards sudo -E ./install.sh

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run with sudo: sudo $0" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
INSTALL_ROOT="${INSTALL_ROOT:-$REPO_ROOT}"
SYSTEMD_DIR="/etc/systemd/system"

if [[ ! -d "$INSTALL_ROOT/venv" ]]; then
  echo "No venv at $INSTALL_ROOT/venv — create it before installing." >&2
  exit 1
fi

CHOWN_USER="${SUDO_USER:-scutrufello}"
if [[ -z "$CHOWN_USER" ]] || ! id "$CHOWN_USER" &>/dev/null; then
  CHOWN_USER="$(stat -c '%U' "$REPO_ROOT" 2>/dev/null || true)"
fi
if [[ -z "${CHOWN_USER:-}" ]] || ! id "$CHOWN_USER" &>/dev/null; then
  echo "Could not determine Unix user for the app; set SUDO_USER or edit unit files." >&2
  exit 1
fi
CHOWN_GROUP="$(id -gn "$CHOWN_USER")"

WORKDIR="$INSTALL_ROOT"
VENV_BIN="$INSTALL_ROOT/venv/bin"
LOG_FILE="$INSTALL_ROOT/data/webapp.log"
mkdir -p "$INSTALL_ROOT/data"
touch "$LOG_FILE"
chown "$CHOWN_USER:$CHOWN_GROUP" "$LOG_FILE" || true

render_unit() {
  local src="$1" dest="$2"
  sed \
    -e "s|/home/scutrufello/phillies-cards|$WORKDIR|g" \
    -e "s|^User=scutrufello|User=$CHOWN_USER|g" \
    -e "s|^Group=scutrufello|Group=$CHOWN_GROUP|g" \
    -e "s|/home/scutrufello/phillies-cards/venv/bin|$VENV_BIN|g" \
    "$src" > "$dest"
  chmod 0644 "$dest"
}

for unit in \
  phillies-checklist-web.service \
  phillies-tcdb-recent-scrape.service \
  phillies-tcdb-recent-scrape.timer \
  phillies-cards.target; do
  render_unit "$SCRIPT_DIR/$unit" "$SYSTEMD_DIR/$unit"
done

systemctl daemon-reload

systemctl enable phillies-checklist-web.service
systemctl enable phillies-tcdb-recent-scrape.timer
systemctl enable phillies-cards.target

systemctl restart phillies-checklist-web.service
systemctl start phillies-tcdb-recent-scrape.timer

echo "Installed and enabled:"
echo "  - $SYSTEMD_DIR/phillies-checklist-web.service (http://0.0.0.0:8000)"
echo "  - $SYSTEMD_DIR/phillies-tcdb-recent-scrape.timer"
echo "  - $SYSTEMD_DIR/phillies-cards.target"
echo "Check: systemctl status phillies-checklist-web.service"
