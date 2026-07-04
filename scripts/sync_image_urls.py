#!/usr/bin/env python3
"""
Recurring sync: fetch TCDB ViewCard image URLs for cards still missing image_*_url.

DB-driven queue (not permanent checkpoint skip). Safe to cron after bulk era backfill
finishes — do NOT run alongside era backfill_card_images.py (same TCDB traffic).

See docs/IMAGE_SYNC.md.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

import cloudscraper

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import get_session, load_config  # noqa: E402
from scraper.card_images import backfill_card_image  # noqa: E402
from scraper.vpn_manager import VPNManager  # noqa: E402
from scripts.backfill_card_images import _resolve_image_root  # noqa: E402
from scripts.image_sync_common import (  # noqa: E402
    cards_needing_url_sync,
    count_cards_needing_url_sync,
    load_cursor,
    save_cursor,
    setup_sync_logging,
)

logger = logging.getLogger(__name__)

DEFAULT_CURSOR = "./data/image_sync_urls_cursor.json"
DEFAULT_LOG = "./data/sync_image_urls.log"


def main() -> None:
    parser = argparse.ArgumentParser(description="Recurring TCDB image URL sync")
    parser.add_argument(
        "--limit",
        type=int,
        default=500,
        help="Max cards to process this run (default: 500)",
    )
    parser.add_argument(
        "--recheck-days",
        type=int,
        default=30,
        help="Re-fetch ViewCard for scan_status=none|partial after N days (default: 30)",
    )
    parser.add_argument("--min-delay", type=float, default=1.0)
    parser.add_argument("--max-delay", type=float, default=1.4)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--retries", type=int, default=4)
    parser.add_argument("--commit-every", type=int, default=25)
    parser.add_argument("--cursor", default=DEFAULT_CURSOR)
    parser.add_argument("--log-file", default=DEFAULT_LOG)
    parser.add_argument(
        "--reset-cursor",
        action="store_true",
        help="Start from the beginning of the queue (card id 0)",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-vpn", action="store_true")
    args = parser.parse_args()

    setup_sync_logging(args.log_file, "sync_image_urls.log")

    config = load_config()
    image_root = _resolve_image_root(config)
    session = get_session()
    scraper = cloudscraper.create_scraper()

    vpn = VPNManager(config)
    if args.no_vpn:
        vpn._enabled_config = False
    elif vpn.enabled:
        try:
            vpn.connect()
            logger.info("VPN connected for image URL sync")
        except Exception as exc:
            logger.warning("VPN connect failed (%s); continuing without VPN", exc)
            vpn.enabled = False

    cursor = load_cursor(args.cursor)
    after_id = 0 if args.reset_cursor else int(cursor.get("last_card_id") or 0)

    due_total = count_cards_needing_url_sync(session, recheck_days=args.recheck_days)
    work = cards_needing_url_sync(
        session, limit=args.limit, after_id=after_id, recheck_days=args.recheck_days
    )

    if not work and after_id > 0:
        logger.info("Cursor at id %d with no rows; wrapping to start", after_id)
        after_id = 0
        cursor["last_card_id"] = 0
        work = cards_needing_url_sync(
            session, limit=args.limit, after_id=0, recheck_days=args.recheck_days
        )

    logger.info(
        "URL sync: %d due globally, %d queued this run (after_id=%d, recheck=%dd, delay %.1f–%.1fs)",
        due_total,
        len(work),
        after_id,
        args.recheck_days,
        args.min_delay,
        args.max_delay,
    )

    totals = {"fetched": 0, "new_scan": 0, "still_none": 0, "failed": 0}
    pending = 0
    last_id = after_id

    try:
        for card, card_set in work:
            last_id = card.id
            if args.dry_run:
                logger.info("DRY %s %s (%s)", card.number, card.player_name, card_set.full_name[:40])
                continue

            parsed = backfill_card_image(
                card,
                scraper,
                image_root=image_root,
                tcdb_sid=card_set.tcdb_sid,
                download=False,
                delay_range=(args.min_delay, args.max_delay),
                timeout=args.timeout,
                retries=args.retries,
                vpn=vpn if vpn.enabled else None,
            )

            if parsed is None:
                totals["failed"] += 1
                logger.warning("FAIL %s %s", card.number, card.player_name)
                continue

            totals["fetched"] += 1
            if parsed.has_card_scan:
                totals["new_scan"] += 1
            else:
                totals["still_none"] += 1

            pending += 1
            if pending >= args.commit_every:
                session.commit()
                cursor["last_card_id"] = last_id
                save_cursor(args.cursor, cursor)
                pending = 0
                logger.info(
                    "Progress: fetched=%d new_scan=%d still_none=%d failed=%d last_id=%d",
                    totals["fetched"],
                    totals["new_scan"],
                    totals["still_none"],
                    totals["failed"],
                    last_id,
                )

        if not args.dry_run:
            session.commit()
            cursor["last_card_id"] = last_id
            save_cursor(args.cursor, cursor)

        logger.info(
            "Done: fetched=%d new_scan=%d still_none=%d failed=%d (cursor last_id=%d)",
            totals["fetched"],
            totals["new_scan"],
            totals["still_none"],
            totals["failed"],
            last_id,
        )
    finally:
        session.close()
        if vpn.enabled:
            vpn.cleanup()


if __name__ == "__main__":
    main()
