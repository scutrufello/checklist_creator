# systemd units — Phillies checklist

Units in this folder run the **web app** on boot and keep the **twice-daily TCDB scrape timer** enabled.

Paths and `User=` assume the repo lives at `/home/scutrufello/phillies-cards`. Change those if your install differs.

## Install (recommended: system units, survives reboot without user login)

Run from the repo (uses `sudo`):

```bash
cd /home/scutrufello/phillies-cards/systemd
sudo ./install.sh
```

This copies the unit files into `/etc/systemd/system/`, reloads systemd, enables and starts:

- `phillies-checklist-web.service` — FastAPI on `0.0.0.0:8000` (logs: `data/webapp.log`)
- `phillies-tcdb-recent-scrape.timer` — scrape current + prior year at 00:01 and 12:01

It also enables `phillies-cards.target` as a convenience group.

## Manual commands

```bash
sudo systemctl status phillies-checklist-web.service
sudo systemctl restart phillies-checklist-web.service
sudo journalctl -u phillies-checklist-web.service -f
```

Timer:

```bash
sudo systemctl list-timers phillies-tcdb-recent-scrape.timer
```

## Notes

- `run.py` uses `reload=True` for local dev. The service runs **production-style** `uvicorn` without reload.
- The scraper unit may require VPN credentials and `sudo` for OpenVPN if `vpn.enabled` is true in `config.yaml`; adjust permissions or config as needed for unattended runs.
