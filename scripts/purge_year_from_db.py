#!/usr/bin/env python3
"""Remove all card_sets (and cards) for a given year from the local DB."""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import get_session, load_config  # noqa: E402
from app.models import Card, CardSet  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Purge checklist data for one or more years")
    parser.add_argument(
        "years",
        nargs="+",
        type=int,
        help="Years to remove (e.g. 2024)",
    )
    parser.add_argument(
        "--checkpoint",
        action="store_true",
        help="Also remove these years from data/scrape_checkpoint.json",
    )
    args = parser.parse_args()

    session = get_session()
    try:
        for year in args.years:
            set_ids = [row[0] for row in session.query(CardSet.id).filter(CardSet.year == year).all()]
            if not set_ids:
                print(f"Year {year}: no sets found")
                continue
            n_cards = session.query(Card).filter(Card.set_id.in_(set_ids)).delete(synchronize_session=False)
            n_sets = session.query(CardSet).filter(CardSet.year == year).delete(synchronize_session=False)
            session.commit()
            print(f"Year {year}: deleted {n_sets} sets, {n_cards} cards")
    finally:
        session.close()

    if args.checkpoint:
        config = load_config()
        ck_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "data",
            "scrape_checkpoint.json",
        )
        if os.path.isfile(ck_path):
            with open(ck_path) as f:
                ck = json.load(f)
            for y in args.years:
                ck.pop(str(y), None)
            with open(ck_path, "w") as f:
                json.dump(ck, f)
            print(f"Updated checkpoint: {ck_path}")


if __name__ == "__main__":
    main()
