#!/usr/bin/env python3
"""
Merge duplicate cards: one row per (set_id, number).
Keeps the first row (min id), merges tags and raw_tags_text from all duplicates, deletes the rest.
Run once after scraping to fix variation duplicates (e.g. 2024 Topps #126 base + VAR).
"""
import json
import sys

from sqlalchemy import func

# Add project root
sys.path.insert(0, ".")

from app.database import get_session, init_db
from app.models import Card


def normalize_tags(tags: list) -> list:
    if not tags:
        return []
    seen = set()
    out = []
    noise = {"image", "variation", "kevin", "hart"}
    for t in tags:
        t = (t or "").strip() if isinstance(t, str) else str(t).strip()
        if not t or len(t) > 12:
            continue
        if t.lower() in noise:
            continue
        key = t.upper()
        if key not in seen:
            seen.add(key)
            out.append(t)
    return sorted(out, key=lambda x: (x.upper() != "VAR", x.upper() != "TC", x))


def main():
    init_db()
    db = get_session()

    # Find (set_id, number) with more than one row
    dupes = (
        db.query(Card.set_id, Card.number, func.count(Card.id).label("cnt"))
        .group_by(Card.set_id, Card.number)
        .having(func.count(Card.id) > 1)
        .all()
    )
    print(f"Found {len(dupes)} (set_id, number) groups with duplicates")

    merged_count = 0
    deleted_count = 0

    for set_id, number, cnt in dupes:
        rows = (
            db.query(Card)
            .filter(Card.set_id == set_id, Card.number == number)
            .order_by(Card.id)
            .all()
        )
        if len(rows) <= 1:
            continue
        keep = rows[0]
        # Prefer row that has owned=True if any
        for r in rows:
            if r.owned:
                keep = r
                break
        # Merge tags and raw_tags from all
        all_tags = []
        all_raw = []
        for r in rows:
            if r.tags:
                try:
                    all_tags.extend(json.loads(r.tags))
                except (TypeError, json.JSONDecodeError):
                    pass
            if r.raw_tags_text:
                all_raw.append(r.raw_tags_text)
        keep.tags = json.dumps(normalize_tags(all_tags)) if all_tags else None
        keep.raw_tags_text = " ".join(all_raw).strip() or None
        # Keep first cid/url; already have keep's
        ids_to_delete = [r.id for r in rows if r.id != keep.id]
        db.query(Card).filter(Card.id.in_(ids_to_delete)).delete(synchronize_session=False)
        merged_count += 1
        deleted_count += len(ids_to_delete)

    db.commit()
    print(f"Merged {merged_count} groups, removed {deleted_count} duplicate rows")
    db.close()


if __name__ == "__main__":
    main()
