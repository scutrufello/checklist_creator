#!/usr/bin/env python3
"""
Recurring sync: download JPEGs for cards that have image_*_url but no image_*_local.

DB-driven queue. Do NOT run alongside bulk era download jobs on the same host/VPN.

See docs/IMAGE_SYNC.md.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import get_session, load_config  # noqa: E402
from scraper.card_images import (  # noqa: E402
    PlaywrightImageSession,
    download_existing_card_images_playwright,
    random_delay,
)
from scripts.backfill_card_images import _resolve_image_root  # noqa: E402
from scripts.image_sync_common import (  # noqa: E402
    cards_needing_download,
    count_cards_needing_download,
    load_cursor,
    save_cursor,
    setup_sync_logging,
)

logger = logging.getLogger(__name__)

DEFAULT_CURSOR = "./data/image_sync_downloads_cursor.json"
DEFAULT_LOG = "./data/sync_image_downloads.log"


def main() -> None:
    parser = argparse.ArgumentParser(description="Recurring TCDB image download sync")
    parser.add_argument("--limit", type=int, default=200, help="Max cards this run (default: 200)")
    parser.add_argument("--min-delay", type=float, default=0.8)
    parser.add_argument("--max-delay", type=float, default=1.2)
    parser.add_argument("--settle-seconds", type=float, default=1.0)
    parser.add_argument("--commit-every", type=int, default=25)
    parser.add_argument("--cursor", default=DEFAULT_CURSOR)
    parser.add_argument("--log-file", default=DEFAULT_LOG)
    parser.add_argument("--reset-cursor", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    setup_sync_logging(args.log_file, "sync_image_downloads.log")

    config = load_config()
    image_root = _resolve_image_root(config)
    session = get_session()

    cursor = load_cursor(args.cursor)
    after_id = 0 if args.reset_cursor else int(cursor.get("last_card_id") or 0)

    due_total = count_cards_needing_download(session)
    work = cards_needing_download(session, limit=args.limit, after_id=after_id)

    if not work and after_id > 0:
        logger.info("Cursor at id %d with no rows; wrapping to start", after_id)
        after_id = 0
        cursor["last_card_id"] = 0
        work = cards_needing_download(session, limit=args.limit, after_id=0)

    logger.info(
        "Download sync: %d due globally, %d queued (after_id=%d, delay %.1f–%.1fs)",
        due_total,
        len(work),
        after_id,
        args.min_delay,
        args.max_delay,
    )

    totals = {"cards": 0, "downloaded": 0, "failed": 0}
    pending = 0
    last_id = after_id

    try:
        with PlaywrightImageSession(headless=True, settle_seconds=args.settle_seconds) as pw:
            for card, card_set in work:
                last_id = card.id
                if args.dry_run:
                    logger.info("DRY %s %s", card.number, card.player_name)
                    continue

                random_delay(args.min_delay, args.max_delay)
                results = download_existing_card_images_playwright(
                    card,
                    pw,
                    image_root=image_root,
                    tcdb_sid=card_set.tcdb_sid,
                    skip_existing=True,
                )
                totals["cards"] += 1
                if results["front"] or results["back"]:
                    totals["downloaded"] += 1
                else:
                    totals["failed"] += 1
                    logger.warning("FAIL %s %s (%s)", card.number, card.player_name, card_set.full_name[:40])

                pending += 1
                if pending >= args.commit_every:
                    session.commit()
                    cursor["last_card_id"] = last_id
                    save_cursor(args.cursor, cursor)
                    pending = 0

        if not args.dry_run:
            session.commit()
            cursor["last_card_id"] = last_id
            save_cursor(args.cursor, cursor)

        logger.info(
            "Done: cards=%d downloaded=%d failed=%d (cursor last_id=%d)",
            totals["cards"],
            totals["downloaded"],
            totals["failed"],
            last_id,
        )
    finally:
        session.close()


if __name__ == "__main__":
    main()
