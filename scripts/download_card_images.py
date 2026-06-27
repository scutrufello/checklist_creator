#!/usr/bin/env python3
"""Download TCDB card images (Playwright) for cards that already have image URLs in the DB."""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone

from sqlalchemy import func, or_

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import get_session, load_config  # noqa: E402
from app.models import Card, CardSet  # noqa: E402
from scraper.card_images import (  # noqa: E402
    PlaywrightImageSession,
    download_existing_card_images_playwright,
    random_delay,
)
from scripts.backfill_card_images import (  # noqa: E402
    _find_sets,
    _load_checkpoint,
    _resolve_image_root,
    _save_checkpoint,
    _setup_logging,
)

logger = logging.getLogger(__name__)

DEFAULT_CHECKPOINT = "./data/image_download_checkpoint.json"


def _needs_download(card: Card, *, force: bool) -> bool:
    if not card.image_front_url and not card.image_back_url:
        return False
    if force:
        return True
    need_front = bool(card.image_front_url) and not card.image_front_local
    need_back = bool(card.image_back_url) and not card.image_back_local
    return need_front or need_back


def _cards_for_download(
    session,
    *,
    year_from: int | None,
    year_to: int | None,
    force: bool,
) -> list[tuple[Card, CardSet]]:
    q = (
        session.query(Card, CardSet)
        .join(CardSet, Card.set_id == CardSet.id)
        .filter(
            Card.tcdb_url.isnot(None),
            Card.tcdb_url != "",
            or_(Card.image_front_url.isnot(None), Card.image_back_url.isnot(None)),
        )
        .order_by(CardSet.year, CardSet.id, Card.sort_number, Card.number, Card.id)
    )
    if year_from is not None:
        q = q.filter(CardSet.year >= year_from)
    if year_to is not None:
        q = q.filter(CardSet.year <= year_to)
    return [(card, card_set) for card, card_set in q.all() if _needs_download(card, force=force)]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download TCDB card JPEGs for rows that already have image_*_url",
    )
    parser.add_argument("--set", action="append", dest="sets", help="Set id or name substring")
    parser.add_argument("--year-from", type=int, help="Include sets from this year (inclusive)")
    parser.add_argument("--year-to", type=int, help="Include sets through this year (inclusive)")
    parser.add_argument("--force", action="store_true", help="Re-download even when image_*_local is set")
    parser.add_argument(
        "--min-delay",
        type=float,
        default=0.5,
        help="Min seconds between cards (default: 0.5)",
    )
    parser.add_argument(
        "--max-delay",
        type=float,
        default=1.0,
        help="Max seconds between cards (default: 1.0)",
    )
    parser.add_argument(
        "--settle-seconds",
        type=float,
        default=1.0,
        help="Playwright pause after ViewCard load (default: 1.0)",
    )
    parser.add_argument(
        "--commit-every",
        type=int,
        default=25,
        help="Commit DB and checkpoint every N cards",
    )
    parser.add_argument("--checkpoint", default=DEFAULT_CHECKPOINT)
    parser.add_argument("--log-file", default=None)
    parser.add_argument(
        "--vpn",
        action="store_true",
        help="Connect VPN at start (avoid while URL backfill is running on the same VM)",
    )
    parser.add_argument(
        "--vpn-start-index",
        type=int,
        default=None,
        help="Initial .ovpn index when --vpn is set (e.g. 1 for Austin)",
    )
    args = parser.parse_args()

    if not args.sets and args.year_from is None and args.year_to is None:
        parser.error("Provide --set and/or --year-from/--year-to")

    config = load_config()
    log_file = args.log_file or "./data/image_download.log"
    _setup_logging(log_file)

    image_root = _resolve_image_root(config)
    session = get_session()

    vpn = None
    if args.vpn:
        from scraper.vpn_manager import VPNManager

        vpn = VPNManager(config, start_index=args.vpn_start_index)
        try:
            vpn.connect()
            logger.info("VPN connected for image download")
        except Exception as exc:
            logger.warning("VPN connect failed (%s); continuing without VPN", exc)
            vpn = None
    else:
        logger.info("Using system routing only (no VPN connect/disconnect)")

    checkpoint = _load_checkpoint(args.checkpoint)
    processed_ids = set(checkpoint.get("processed_card_ids", []))
    failed_ids = set(checkpoint.get("failed_card_ids", []))

    totals = {
        "cards": 0,
        "downloaded": 0,
        "skipped_checkpoint": 0,
        "skipped_done": 0,
        "failed": 0,
        "front_ok": 0,
        "back_ok": 0,
    }
    pending_since_commit = 0

    try:
        work: list[tuple[Card, CardSet]] = []

        if args.year_from is not None or args.year_to is not None:
            year_from = args.year_from
            if year_from is None:
                year_from = session.query(func.min(CardSet.year)).scalar() or 0
            year_to = args.year_to if args.year_to is not None else year_from
            work.extend(_cards_for_download(session, year_from=year_from, year_to=year_to, force=args.force))
            logger.info(
                "Year range %d–%d: %d cards need download (force=%s)",
                year_from,
                year_to,
                len(work),
                args.force,
            )
            checkpoint["year_from"] = year_from
            checkpoint["year_to"] = year_to

        if args.sets:
            for card_set in _find_sets(session, args.sets):
                cards = (
                    session.query(Card)
                    .filter_by(set_id=card_set.id)
                    .order_by(Card.sort_number, Card.number, Card.player_name)
                    .all()
                )
                for card in cards:
                    if _needs_download(card, force=args.force):
                        work.append((card, card_set))

        if not work:
            raise SystemExit("No cards to download.")

        seen: set[int] = set()
        unique_work: list[tuple[Card, CardSet]] = []
        for card, card_set in work:
            if card.id in seen:
                continue
            seen.add(card.id)
            unique_work.append((card, card_set))
        work = unique_work
        totals["cards"] = len(work)

        logger.info(
            "Starting download: %d cards, delay %.1f–%.1fs, settle %.1fs, root %s",
            len(work),
            args.min_delay,
            args.max_delay,
            args.settle_seconds,
            image_root,
        )

        current_year = None
        with PlaywrightImageSession(headless=True, settle_seconds=args.settle_seconds) as pw:
            for card, card_set in work:
                if card.id in processed_ids:
                    totals["skipped_checkpoint"] += 1
                    continue
                if not _needs_download(card, force=args.force):
                    totals["skipped_done"] += 1
                    processed_ids.add(card.id)
                    continue

                if card_set.year != current_year:
                    current_year = card_set.year
                    logger.info("--- Year %d ---", current_year)

                random_delay(args.min_delay, args.max_delay)
                results = download_existing_card_images_playwright(
                    card,
                    pw,
                    image_root=image_root,
                    tcdb_sid=card_set.tcdb_sid,
                    skip_existing=not args.force,
                )

                got_any = results["front"] or results["back"]
                if results["front"]:
                    totals["front_ok"] += 1
                if results["back"]:
                    totals["back_ok"] += 1

                if got_any:
                    totals["downloaded"] += 1
                    processed_ids.add(card.id)
                    failed_ids.discard(card.id)
                    logger.info(
                        "OK %s %s (%s) front=%s back=%s",
                        card.number,
                        card.player_name,
                        card_set.full_name[:40],
                        results["front"] or bool(card.image_front_local),
                        results["back"] or bool(card.image_back_local),
                    )
                else:
                    totals["failed"] += 1
                    failed_ids.add(card.id)
                    logger.warning(
                        "FAIL %s %s (%s)",
                        card.number,
                        card.player_name,
                        card_set.full_name[:40],
                    )

                pending_since_commit += 1
                if pending_since_commit >= args.commit_every:
                    session.commit()
                    checkpoint["processed_card_ids"] = sorted(processed_ids)
                    checkpoint["failed_card_ids"] = sorted(failed_ids)
                    _save_checkpoint(args.checkpoint, checkpoint)
                    pending_since_commit = 0
                    logger.info(
                        "Checkpoint saved (%d processed, %d failed, %d downloaded)",
                        len(processed_ids),
                        len(failed_ids),
                        totals["downloaded"],
                    )

        session.commit()
        checkpoint["processed_card_ids"] = sorted(processed_ids)
        checkpoint["failed_card_ids"] = sorted(failed_ids)
        _save_checkpoint(args.checkpoint, checkpoint)

        logger.info(
            "Done: downloaded=%d front_ok=%d back_ok=%d failed=%d "
            "skipped_checkpoint=%d skipped_done=%d (queued=%d)",
            totals["downloaded"],
            totals["front_ok"],
            totals["back_ok"],
            totals["failed"],
            totals["skipped_checkpoint"],
            totals["skipped_done"],
            totals["cards"],
        )
    finally:
        session.close()
        if vpn is not None and vpn.enabled:
            vpn.cleanup()


if __name__ == "__main__":
    main()
