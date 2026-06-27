#!/usr/bin/env python3
"""Download TCDB card images for one set using URLs already stored in the DB."""
from __future__ import annotations

import argparse
import logging
import os
import sys

import cloudscraper

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import get_session, load_config  # noqa: E402
from app.models import Card  # noqa: E402
from scraper.card_images import (  # noqa: E402
    PlaywrightImageSession,
    _basename_from_url,
    download_existing_card_images,
    download_existing_card_images_playwright,
    random_delay,
)
from scripts.backfill_card_images import _find_sets, _resolve_image_root  # noqa: E402

logger = logging.getLogger(__name__)


def register_existing_card_images(
    card: Card,
    *,
    image_root: str,
    tcdb_sid: int | str,
) -> dict[str, bool]:
    """Point image_*_local at files already present under image_root/{tcdb_sid}/."""
    sid_dir = str(tcdb_sid)
    results = {"front": False, "back": False}

    if card.image_front_url:
        rel = os.path.join(sid_dir, _basename_from_url(card.image_front_url))
        if os.path.isfile(os.path.join(image_root, rel)):
            card.image_front_local = rel
            results["front"] = True

    if card.image_back_url:
        rel = os.path.join(sid_dir, _basename_from_url(card.image_back_url))
        if os.path.isfile(os.path.join(image_root, rel)):
            card.image_back_local = rel
            results["back"] = True

    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download cached TCDB image URLs for one set (no ViewCard re-fetch)",
    )
    parser.add_argument(
        "--set",
        default="1987 Fleer Star Stickers",
        help="Set id or full_name substring (default: 1987 Fleer Star Stickers)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Seconds between cards (default: 1.0)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download even when image_*_local is already set",
    )
    parser.add_argument(
        "--no-vpn",
        action="store_true",
        help="Skip VPN for cloudscraper downloads",
    )
    parser.add_argument(
        "--register-existing",
        action="store_true",
        help="Skip download; set image_*_local from files already on disk",
    )
    parser.add_argument(
        "--playwright",
        action="store_true",
        help="Download via Playwright browser session (required on VM for TCDB images)",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Run Playwright with a visible browser (debug only)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    config = load_config()
    image_root = _resolve_image_root(config)
    session = get_session()

    use_playwright = args.playwright and not args.register_existing
    scraper = None if args.register_existing or use_playwright else cloudscraper.create_scraper()

    vpn = None
    if not args.register_existing and not use_playwright and not args.no_vpn and config.get("vpn", {}).get("enabled", False):
        from scraper.vpn_manager import VPNManager

        vpn = VPNManager(config)
        try:
            vpn.connect()
            logger.info("VPN connected")
        except Exception as exc:
            logger.warning("VPN connect failed (%s); continuing without VPN", exc)
            vpn = None

    try:
        card_sets = _find_sets(session, [args.set])
        if not card_sets:
            raise SystemExit(f"Set not found: {args.set!r}")

        totals = {"cards": 0, "front_ok": 0, "back_ok": 0, "failed": 0}

        if use_playwright:
            with PlaywrightImageSession(headless=not args.headed) as pw_session:
                _run_sets(session, card_sets, args, image_root, totals, pw_session=pw_session)
        else:
            _run_sets(session, card_sets, args, image_root, totals, scraper=scraper)

        action = "registered" if args.register_existing else "saved"
        logger.info(
            "Done: %d cards, %d fronts, %d backs %s under %s",
            totals["cards"],
            totals["front_ok"],
            totals["back_ok"],
            action,
            image_root,
        )
    finally:
        session.close()
        if vpn is not None:
            try:
                vpn.disconnect()
            except Exception:
                pass


def _run_sets(session, card_sets, args, image_root, totals, *, scraper=None, pw_session=None) -> None:
    use_playwright = pw_session is not None
    for card_set in card_sets:
        cards = (
            session.query(Card)
            .filter_by(set_id=card_set.id)
            .order_by(Card.sort_number, Card.number, Card.player_name)
            .all()
        )
        logger.info(
            "Set: %s (sid=%s, %d cards) → %s%s",
            card_set.full_name,
            card_set.tcdb_sid,
            len(cards),
            image_root,
            " [playwright]" if use_playwright else "",
        )

        for idx, card in enumerate(cards):
            if not card.image_front_url and not card.image_back_url:
                logger.warning("SKIP %s %s — no image URLs in DB", card.number, card.player_name)
                totals["failed"] += 1
                continue

            if idx and not args.register_existing:
                random_delay(args.delay, args.delay)

            totals["cards"] += 1
            if args.register_existing:
                results = register_existing_card_images(
                    card,
                    image_root=image_root,
                    tcdb_sid=card_set.tcdb_sid,
                )
            elif use_playwright:
                results = download_existing_card_images_playwright(
                    card,
                    pw_session,
                    image_root=image_root,
                    tcdb_sid=card_set.tcdb_sid,
                    skip_existing=not args.force,
                )
            else:
                results = download_existing_card_images(
                    card,
                    scraper,
                    image_root=image_root,
                    tcdb_sid=card_set.tcdb_sid,
                    skip_existing=not args.force,
                )
            if results["front"]:
                totals["front_ok"] += 1
            if results["back"]:
                totals["back_ok"] += 1

            logger.info(
                "OK #%s %s — front=%s back=%s local_front=%s",
                card.number,
                card.player_name,
                results["front"] or bool(card.image_front_local),
                results["back"] or bool(card.image_back_local),
                card.image_front_local,
            )
            session.commit()


if __name__ == "__main__":
    main()
