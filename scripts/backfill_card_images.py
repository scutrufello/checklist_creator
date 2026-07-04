#!/usr/bin/env python3
"""Backfill TCDB card image URLs (and optional local cache) by set or year range."""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone

import cloudscraper
from sqlalchemy import func

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import get_session, load_config  # noqa: E402
from app.image_scan_status import infer_scan_status_from_stored_urls  # noqa: E402
from app.models import Card, CardSet  # noqa: E402
from scraper.card_images import backfill_card_image  # noqa: E402
from scraper.vpn_manager import VPNManager  # noqa: E402

logger = logging.getLogger(__name__)

DEFAULT_CHECKPOINT = "./data/image_backfill_checkpoint.json"


def _resolve_image_root(config: dict) -> str:
    image_path = config["storage"]["image_path"]
    if not os.path.isabs(image_path):
        image_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), image_path)
    os.makedirs(image_path, exist_ok=True)
    return image_path


def _find_sets(session, queries: list[str]) -> list[CardSet]:
    found: list[CardSet] = []
    seen: set[int] = set()
    for query in queries:
        if query.isdigit():
            row = session.get(CardSet, int(query))
            matches = [row] if row else []
        else:
            matches = (
                session.query(CardSet)
                .filter(CardSet.full_name.ilike(f"%{query}%"))
                .order_by(CardSet.tcdb_sid)
                .all()
            )
        if not matches:
            logger.warning("No set matched %r", query)
            continue
        for row in matches:
            if row.id not in seen:
                seen.add(row.id)
                found.append(row)
    return found


def _load_checkpoint(path: str) -> dict:
    if not os.path.isfile(path):
        return {"processed_card_ids": [], "failed_card_ids": []}
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    data.setdefault("processed_card_ids", [])
    data.setdefault("failed_card_ids", [])
    return data


def _save_checkpoint(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    os.replace(tmp, path)


def _cards_for_year_range(session, year_from: int, year_to: int, force: bool):
    q = (
        session.query(Card, CardSet)
        .join(CardSet, Card.set_id == CardSet.id)
        .filter(
            CardSet.year >= year_from,
            CardSet.year <= year_to,
            Card.tcdb_url.isnot(None),
            Card.tcdb_url != "",
        )
        .order_by(CardSet.year, CardSet.id, Card.sort_number, Card.number, Card.id)
    )
    rows = q.all()
    if force:
        return rows
    return [
        (card, card_set)
        for card, card_set in rows
        if card.image_front_url is None and card.image_back_url is None
    ]


def _setup_logging(log_file: str | None) -> None:
    handlers: list[logging.Handler] = []
    if log_file:
        os.makedirs(os.path.dirname(log_file) or ".", exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    else:
        handlers.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
        force=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill TCDB card image URLs")
    parser.add_argument(
        "--set",
        action="append",
        dest="sets",
        help="Set id or full_name substring (repeatable)",
    )
    parser.add_argument(
        "--year-from",
        type=int,
        help="Include sets from this year (inclusive)",
    )
    parser.add_argument(
        "--year-to",
        type=int,
        help="Include sets through this year (inclusive)",
    )
    parser.add_argument("--download", action="store_true", help="Cache image files under storage.image_path")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-fetch even when image URLs are already set",
    )
    parser.add_argument(
        "--min-delay",
        type=float,
        default=None,
        help="Min seconds between ViewCard requests (default: scraper.min_delay)",
    )
    parser.add_argument(
        "--max-delay",
        type=float,
        default=None,
        help="Max seconds between ViewCard requests (default: scraper.max_delay)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=None,
        help="HTTP timeout seconds (default: scraper.request_timeout)",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=4,
        help="Retries per ViewCard fetch",
    )
    parser.add_argument(
        "--commit-every",
        type=int,
        default=25,
        help="Commit DB and checkpoint every N cards",
    )
    parser.add_argument(
        "--checkpoint",
        default=DEFAULT_CHECKPOINT,
        help=f"Checkpoint JSON path (default: {DEFAULT_CHECKPOINT})",
    )
    parser.add_argument(
        "--log-file",
        default=None,
        help="Also append logs to this file",
    )
    parser.add_argument("--dry-run", action="store_true", help="Fetch/parse only; do not write DB")
    parser.add_argument(
        "--no-vpn",
        action="store_true",
        help="Disable VPN even if enabled in config.yaml",
    )
    args = parser.parse_args()

    if not args.sets and args.year_to is None and args.year_from is None:
        parser.error("Provide --set and/or --year-from/--year-to")

    config = load_config()
    scfg = config.get("scraper", {})
    min_delay = args.min_delay if args.min_delay is not None else float(scfg.get("min_delay", 8))
    max_delay = args.max_delay if args.max_delay is not None else float(scfg.get("max_delay", 15))
    timeout = args.timeout if args.timeout is not None else int(scfg.get("request_timeout", 120))

    log_file = args.log_file
    if log_file is None and args.year_to is not None:
        log_file = "./data/image_backfill.log"
    _setup_logging(log_file)

    image_root = _resolve_image_root(config)
    session = get_session()
    scraper = cloudscraper.create_scraper()

    vpn = VPNManager(config)
    if args.no_vpn:
        vpn._enabled_config = False
    if vpn.enabled:
        try:
            vpn.connect()
            logger.info("VPN connected for image backfill")
        except Exception as exc:
            logger.warning("VPN connect failed (%s); continuing without VPN", exc)
            vpn.enabled = False

    checkpoint = _load_checkpoint(args.checkpoint)
    processed_ids = set(checkpoint.get("processed_card_ids", []))
    failed_ids = set(checkpoint.get("failed_card_ids", []))

    totals = {
        "cards": 0,
        "fetched": 0,
        "with_scan": 0,
        "downloaded": 0,
        "skipped_done": 0,
        "skipped_checkpoint": 0,
        "failed": 0,
    }
    pending_since_commit = 0

    try:
        work: list[tuple[Card, CardSet]] = []

        if args.year_from is not None or args.year_to is not None:
            year_from = args.year_from
            if year_from is None:
                year_from = session.query(func.min(CardSet.year)).scalar() or 0
            year_to = args.year_to if args.year_to is not None else year_from
            if year_from > year_to:
                raise SystemExit(f"year-from ({year_from}) > year-to ({year_to})")
            work.extend(_cards_for_year_range(session, year_from, year_to, args.force))
            logger.info(
                "Year range %d–%d: %d cards queued (force=%s)",
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
                    if card.tcdb_url:
                        work.append((card, card_set))

        if not work:
            raise SystemExit("No cards to process.")

        # De-dupe while preserving order
        seen_card_ids: set[int] = set()
        unique_work: list[tuple[Card, CardSet]] = []
        for card, card_set in work:
            if card.id in seen_card_ids:
                continue
            seen_card_ids.add(card.id)
            unique_work.append((card, card_set))
        work = unique_work
        totals["cards"] = len(work)

        logger.info(
            "Starting backfill: %d cards, delay %.1f–%.1fs, commit every %d",
            len(work),
            min_delay,
            max_delay,
            args.commit_every,
        )

        current_year = None
        for card, card_set in work:
            if card.id in processed_ids:
                totals["skipped_checkpoint"] += 1
                continue
            if not args.force and (card.image_front_url or card.image_back_url):
                if card.image_scan_status is None:
                    inferred = infer_scan_status_from_stored_urls(card)
                    if inferred:
                        card.image_scan_status = inferred
                        if card.image_url_checked_at is None:
                            card.image_url_checked_at = datetime.now(timezone.utc).isoformat()
                totals["skipped_done"] += 1
                processed_ids.add(card.id)
                continue

            if card_set.year != current_year:
                current_year = card_set.year
                logger.info("--- Year %d ---", current_year)

            if args.dry_run:
                from scraper.card_images import fetch_viewcard_html, random_delay
                from scraper.viewcard_parser import parse_viewcard_images

                random_delay(min_delay, max_delay)
                html = fetch_viewcard_html(
                    scraper,
                    card.tcdb_url,
                    timeout=timeout,
                    retries=args.retries,
                    vpn=vpn if vpn.enabled else None,
                )
                parsed = parse_viewcard_images(html) if html else None
            else:
                parsed = backfill_card_image(
                    card,
                    scraper,
                    image_root=image_root,
                    tcdb_sid=card_set.tcdb_sid,
                    download=args.download,
                    delay_range=(min_delay, max_delay),
                    timeout=timeout,
                    retries=args.retries,
                    vpn=vpn if vpn.enabled else None,
                )

            if parsed is None:
                totals["failed"] += 1
                failed_ids.add(card.id)
                logger.warning(
                    "FAIL %s %s | %s",
                    card.number,
                    card.player_name,
                    card.tcdb_url,
                )
                continue

            totals["fetched"] += 1
            if parsed.has_card_scan:
                totals["with_scan"] += 1
            if card.image_front_local:
                totals["downloaded"] += 1

            processed_ids.add(card.id)
            failed_ids.discard(card.id)
            pending_since_commit += 1

            if totals["fetched"] % 10 == 0 or parsed.has_card_scan:
                logger.info(
                    "OK %s %s (%s) scan=%s",
                    card.number,
                    card.player_name,
                    card_set.full_name[:40],
                    parsed.has_card_scan,
                )

            if not args.dry_run and pending_since_commit >= args.commit_every:
                session.commit()
                checkpoint["processed_card_ids"] = sorted(processed_ids)
                checkpoint["failed_card_ids"] = sorted(failed_ids)
                _save_checkpoint(args.checkpoint, checkpoint)
                pending_since_commit = 0
                logger.info(
                    "Checkpoint saved (%d processed, %d failed, %d with scans so far)",
                    len(processed_ids),
                    len(failed_ids),
                    totals["with_scan"],
                )

        if not args.dry_run:
            session.commit()
            checkpoint["processed_card_ids"] = sorted(processed_ids)
            checkpoint["failed_card_ids"] = sorted(failed_ids)
            _save_checkpoint(args.checkpoint, checkpoint)

        logger.info(
            "Done: fetched=%d with_scans=%d downloaded=%d failed=%d "
            "skipped_checkpoint=%d skipped_done=%d (queued=%d)",
            totals["fetched"],
            totals["with_scan"],
            totals["downloaded"],
            totals["failed"],
            totals["skipped_checkpoint"],
            totals["skipped_done"],
            totals["cards"],
        )
    finally:
        session.close()
        if vpn.enabled:
            vpn.cleanup()


if __name__ == "__main__":
    main()
