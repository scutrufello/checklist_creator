#!/usr/bin/env python3
"""
One-time backfill of image_scan_status / image_url_checked_at from existing DB + era checkpoints.

Run AFTER bulk era URL backfill completes (or during a planned pause). Safe to run while
era backfill is active only for rows the backfill is not currently updating — prefer waiting.

Usage:
  ./venv/bin/python scripts/migrate_image_scan_status.py
  ./venv/bin/python scripts/migrate_image_scan_status.py --apply
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import get_session, init_db  # noqa: E402
from app.image_scan_status import (  # noqa: E402
    SCAN_NONE,
    infer_scan_status_from_stored_urls,
)
from app.models import Card  # noqa: E402


def _load_checkpoint_processed_ids(data_dir: str) -> dict[int, str | None]:
    """Map card_id -> checkpoint updated_at ISO (or None)."""
    out: dict[int, str | None] = {}
    pattern = os.path.join(data_dir, "image_backfill*_checkpoint.json")
    for path in glob.glob(pattern):
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError):
            continue
        updated = data.get("updated_at")
        for cid in data.get("processed_card_ids") or []:
            out[int(cid)] = updated
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill image scan metadata columns")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write changes (default: dry-run counts only)",
    )
    parser.add_argument(
        "--data-dir",
        default="./data",
        help="Directory containing image_backfill_*_checkpoint.json files",
    )
    args = parser.parse_args()

    init_db()
    session = get_session()
    checkpoint_map = _load_checkpoint_processed_ids(args.data_dir)
    now = datetime.now(timezone.utc).isoformat()

    stats = {
        "from_urls": 0,
        "from_checkpoint_none": 0,
        "already_set": 0,
        "unchanged": 0,
    }

    try:
        cards = session.query(Card).yield_per(500)
        for card in cards:
            if card.image_scan_status and card.image_url_checked_at:
                stats["already_set"] += 1
                continue

            inferred = infer_scan_status_from_stored_urls(card)
            if inferred:
                if not args.apply:
                    stats["from_urls"] += 1
                    continue
                card.image_scan_status = inferred
                if not card.image_url_checked_at:
                    card.image_url_checked_at = now
                stats["from_urls"] += 1
                continue

            if card.id in checkpoint_map and not (card.image_front_url or card.image_back_url):
                if not args.apply:
                    stats["from_checkpoint_none"] += 1
                    continue
                card.image_scan_status = SCAN_NONE
                card.image_url_checked_at = checkpoint_map[card.id] or now
                stats["from_checkpoint_none"] += 1
                continue

            stats["unchanged"] += 1

        if args.apply:
            session.commit()
            print("Applied metadata backfill.")
        else:
            print("Dry run — use --apply to write.")

        print(
            f"from_urls={stats['from_urls']} checkpoint_none={stats['from_checkpoint_none']} "
            f"already_set={stats['already_set']} unchanged={stats['unchanged']} "
            f"(checkpoint ids loaded: {len(checkpoint_map)})"
        )
    finally:
        session.close()


if __name__ == "__main__":
    main()
