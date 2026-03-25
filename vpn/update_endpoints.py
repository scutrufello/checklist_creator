#!/usr/bin/env python3
"""
Fetch the latest VyprVPN/Giganews server list and regenerate .ovpn configs.

Run manually:  python vpn/update_endpoints.py
Cron (2x/day): 0 6,18 * * * cd /home/scutrufello/phillies-cards && venv/bin/python vpn/update_endpoints.py
"""
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ENDPOINTS_FILE = os.path.join(SCRIPT_DIR, "endpoints.json")
CONFIGS_DIR = os.path.join(SCRIPT_DIR, "configs")
CA_BLOCK_FILE = os.path.join(SCRIPT_DIR, "ca_block.txt")
GIGANEWS_URL = "https://support.giganews.com/hc/en-us/articles/360039615432"

OVPN_TEMPLATE = """\
client
dev tun
proto udp
remote {hostname} 443
resolv-retry infinite
nobind
persist-key
persist-tun
persist-remote-ip
verify-x509-name {hostname} name
auth-user-pass
comp-lzo
keepalive 10 60
verb 3
auth SHA256
cipher AES-256-CBC
tls-cipher TLS-ECDHE-RSA-WITH-AES-256-GCM-SHA384:TLS-DHE-RSA-WITH-AES-256-CBC-SHA256:TLS-DHE-RSA-WITH-AES-256-CBC-SHA

{ca_block}
"""

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def load_ca_block() -> str:
    with open(CA_BLOCK_FILE) as f:
        return f.read().strip()


def load_current_endpoints() -> dict:
    if os.path.exists(ENDPOINTS_FILE):
        with open(ENDPOINTS_FILE) as f:
            return json.load(f)
    return {"endpoints": []}


def save_endpoints(data: dict):
    with open(ENDPOINTS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def fetch_endpoint_list() -> list[dict] | None:
    """Scrape the Giganews support page for server hostnames."""
    try:
        resp = httpx.get(GIGANEWS_URL, timeout=30, follow_redirects=True)
        resp.raise_for_status()
    except Exception as e:
        logger.error("Failed to fetch endpoint page: %s", e)
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    endpoints = []

    for row in soup.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) != 2:
            continue

        name = cells[0].get_text(strip=True)
        hostname = cells[1].get_text(strip=True)

        if not hostname or "." not in hostname:
            continue

        # Validate it looks like a hostname
        if re.match(r"^[a-z0-9]+\.vpn\.giganews\.com$", hostname):
            endpoints.append({"name": name, "hostname": hostname})

    if not endpoints:
        logger.warning("No endpoints parsed from page — HTML structure may have changed")
        return None

    return endpoints


def generate_ovpn_configs(endpoints: list[dict], region_filter: list[str] | None = None):
    """Generate .ovpn config files from the endpoint list."""
    ca_block = load_ca_block()
    os.makedirs(CONFIGS_DIR, exist_ok=True)

    existing = set(os.listdir(CONFIGS_DIR))
    generated = set()

    for ep in endpoints:
        if region_filter:
            if not any(rf.lower() in ep["name"].lower() for rf in region_filter):
                continue

        safe_name = ep["name"].replace("/", "-")
        filename = f"{safe_name}.ovpn"
        filepath = os.path.join(CONFIGS_DIR, filename)
        generated.add(filename)

        content = OVPN_TEMPLATE.format(
            hostname=ep["hostname"],
            ca_block=ca_block,
        )

        with open(filepath, "w") as f:
            f.write(content)

    # Remove configs for endpoints that no longer exist
    stale = {f for f in existing if f.endswith(".ovpn")} - generated
    for f in stale:
        os.remove(os.path.join(CONFIGS_DIR, f))
        logger.info("Removed stale config: %s", f)

    logger.info("Generated %d .ovpn configs (%d stale removed)", len(generated), len(stale))


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Update VyprVPN endpoint list and configs")
    parser.add_argument(
        "--region", "-r",
        nargs="*",
        default=["U.S.", "Canada"],
        help="Region filter for .ovpn generation (default: U.S. Canada)",
    )
    parser.add_argument(
        "--all-regions",
        action="store_true",
        help="Generate configs for all regions",
    )
    parser.add_argument(
        "--skip-fetch",
        action="store_true",
        help="Skip fetching from Giganews, just regenerate configs from stored endpoints",
    )
    args = parser.parse_args()

    current = load_current_endpoints()

    if not args.skip_fetch:
        logger.info("Fetching endpoint list from %s", GIGANEWS_URL)
        fetched = fetch_endpoint_list()

        if fetched:
            old_hostnames = {ep["hostname"] for ep in current.get("endpoints", [])}
            new_hostnames = {ep["hostname"] for ep in fetched}

            added = new_hostnames - old_hostnames
            removed = old_hostnames - new_hostnames

            if added:
                logger.info("New endpoints: %s", ", ".join(sorted(added)))
            if removed:
                logger.info("Removed endpoints: %s", ", ".join(sorted(removed)))
            if not added and not removed:
                logger.info("No changes to endpoint list (%d endpoints)", len(fetched))

            current = {
                "last_updated": datetime.now(timezone.utc).isoformat(),
                "source": GIGANEWS_URL,
                "endpoints": fetched,
            }
            save_endpoints(current)
        else:
            logger.warning("Fetch failed — using cached endpoint list")

    endpoints = current.get("endpoints", [])
    if not endpoints:
        logger.error("No endpoints available. Exiting.")
        sys.exit(1)

    region_filter = None if args.all_regions else args.region
    generate_ovpn_configs(endpoints, region_filter)
    logger.info("Done. %d total endpoints stored.", len(endpoints))


if __name__ == "__main__":
    main()
