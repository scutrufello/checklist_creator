#!/usr/bin/env python3
"""Resolve explicit set relationships using checklist overlap."""
import argparse
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import init_db, get_session  # noqa: E402
from app.models import CardSet, Card  # noqa: E402
from scraper.hierarchy import classify_set_type  # noqa: E402


def norm_text(value: str) -> str:
    value = (value or "").lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def norm_number(value: str) -> str:
    value = (value or "").upper().strip().lstrip("#")
    value = re.sub(r"\s+", "", value)
    value = re.sub(r"^0+(\d)", r"\1", value)
    return value


def card_core_key(card: Card) -> str:
    return f"{norm_number(card.number)}|{norm_text(card.player_name)}"


def looks_like_variation(card_set: CardSet, cards: list[Card]) -> bool:
    text = (card_set.full_name or "").lower()
    variation_terms = [
        "variation", "image", "photo", "ssp", "sp", "alternate", "alt", "action", "pose",
    ]
    if any(t in text for t in variation_terms):
        return True
    if not cards:
        return False
    variant_populated = sum(1 for c in cards if (c.variant or "").strip())
    return (variant_populated / len(cards)) >= 0.25


def resolve_group_relationships(group_sets: list[CardSet], cards_by_set_id: dict[int, list[Card]]):
    # Pick root base candidate.
    base_candidates = [s for s in group_sets if s.variant_name is None or s.set_type == "base"]
    if not base_candidates:
        base_candidates = group_sets[:]
    root_base = min(base_candidates, key=lambda s: s.tcdb_sid)

    # Build signatures.
    sig_by_set_id = {}
    for s in group_sets:
        sig_by_set_id[s.id] = {card_core_key(c) for c in cards_by_set_id.get(s.id, [])}

    # Baseline relationship typing (recompute from names; DB set_type can be wrong).
    # Apply classify_set_type before variation heuristics so autograph inserts are not
    # mislabeled as variation when many cards have a populated variant field.
    for s in group_sets:
        s.canonical_parent_set_id = None
        s.relationship_confidence = None
        if s.id == root_base.id:
            s.relationship_type = "base"
            continue

        computed = classify_set_type(s.full_name, s.base_name, s.variant_name)
        if computed == "parallel":
            s.relationship_type = "parallel"
        elif computed == "insert":
            s.relationship_type = "insert"
        elif looks_like_variation(s, cards_by_set_id.get(s.id, [])):
            s.relationship_type = "variation"
        else:
            s.relationship_type = "standalone"

    # Match parallels to best parent by containment.
    parents = [s for s in group_sets if s.relationship_type in {"base", "insert"}]
    for s in group_sets:
        if s.relationship_type != "parallel":
            continue
        child_sig = sig_by_set_id[s.id]
        if not child_sig:
            s.canonical_parent_set_id = root_base.id
            s.relationship_confidence = 0.0
            continue

        best_parent = root_base
        best_score = 0.0
        for p in parents:
            if p.id == s.id:
                continue
            parent_sig = sig_by_set_id[p.id]
            if not parent_sig:
                continue
            overlap = len(child_sig & parent_sig)
            containment = overlap / len(child_sig)
            size_ratio = min(len(child_sig), len(parent_sig)) / max(len(child_sig), len(parent_sig))
            score = (containment * 0.8) + (size_ratio * 0.2)
            if score > best_score:
                best_score = score
                best_parent = p

        s.canonical_parent_set_id = best_parent.id
        s.relationship_confidence = round(best_score, 4)

    # Variations typically derive from base, but avoid being parents by default.
    for s in group_sets:
        if s.relationship_type == "variation":
            s.canonical_parent_set_id = root_base.id
            s.relationship_confidence = 0.6


def main():
    parser = argparse.ArgumentParser(description="Resolve parallel and variation relationships")
    parser.add_argument("--year", type=int, help="Year to process (default: all years)")
    args = parser.parse_args()

    init_db()
    session = get_session()
    try:
        query = session.query(CardSet)
        if args.year:
            query = query.filter(CardSet.year == args.year)
        all_sets = query.all()

        groups = defaultdict(list)
        for s in all_sets:
            key = (s.year, s.base_name)
            groups[key].append(s)

        set_ids = [s.id for s in all_sets]
        cards_by_set_id = defaultdict(list)
        if set_ids:
            cards = session.query(Card).filter(Card.set_id.in_(set_ids)).all()
            for c in cards:
                cards_by_set_id[c.set_id].append(c)

        processed = 0
        for _, group_sets in groups.items():
            if len(group_sets) < 2:
                continue
            resolve_group_relationships(group_sets, cards_by_set_id)
            processed += 1

        session.commit()

        type_counts = defaultdict(int)
        linked_parallel = 0
        low_conf = 0
        for s in all_sets:
            if s.relationship_type:
                type_counts[s.relationship_type] += 1
            if s.relationship_type == "parallel" and s.canonical_parent_set_id:
                linked_parallel += 1
                if (s.relationship_confidence or 0) < 0.85:
                    low_conf += 1

        print(f"Processed groups: {processed}")
        print("Relationship counts:")
        for k in sorted(type_counts):
            print(f"  {k}: {type_counts[k]}")
        print(f"Linked parallels: {linked_parallel}")
        print(f"Low-confidence parallels (<0.85): {low_conf}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
