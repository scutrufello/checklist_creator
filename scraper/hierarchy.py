import logging
import re
from collections import defaultdict

from sqlalchemy.orm import Session

from app.models import CardSet

logger = logging.getLogger(__name__)


def classify_set_type(full_name: str, base_name: str, variant_name: str | None) -> str:
    """Heuristic classification of set type."""
    if not variant_name:
        return "base"

    variant_lower = variant_name.lower()

    # Product-line keywords (insert families). "Chrome" alone must NOT imply parallel —
    # e.g. "Chrome Prospect Autographs" was wrongly classified as parallel because "chrome"
    # was in parallel_keywords, so autograph parallels could not attach to the insert parent.
    insert_keywords = [
        "insert", "subset", "checklist", "award", "highlight",
        "all-star", "league leader", "record breaker", "diamond king",
        "future star", "rated rookie", "rookie card",
        "autograph", "autographs", "memorabilia", "relic", "patch",
        "signature collection", "on-card auto",
        # Named insert products (avoid misclassifying as parallel via color words like gold/black)
        "black gold",
        "silver pack",
        "gold label",
    ]

    # Finish / serial indicators: parallel OF an insert (including autograph lines).
    parallel_finish_keywords = [
        "refractor", "shimmer", "mojo", "xfractor", "foil", "prismatic",
        "die-cut", "die cut", "atomic", "wave", "lava", "speckle", "sparkle",
        "rainbow", "hyper", "crackle", "sapphire", "aqua", "pulsar",
        "mini", "numbered",
    ]
    has_slash_serial = bool(re.search(r"/\d+", variant_lower))
    has_parallel_finish = (
        any(kw in variant_lower for kw in parallel_finish_keywords)
        or has_slash_serial
    )

    autograph_or_mem_line = any(
        kw in variant_lower
        for kw in ("autograph", "autographs", "memorabilia", "relic", "on-card auto")
    )

    # "Chrome Prospect Autographs - Gold Shimmer" → parallel of the autograph insert.
    if autograph_or_mem_line and has_parallel_finish:
        return "parallel"

    if any(kw in variant_lower for kw in insert_keywords):
        return "insert"

    # Serial numbering almost always means a parallel layer.
    if has_slash_serial:
        return "parallel"

    # If variant has "Product Name - Finish", treat finish segment as parallel signal.
    # (e.g. "Topps Black Gold - Blue Wave" — "black/gold" in product name must not imply parallel alone.)
    tail_after_dash: str | None = None
    for sep in (" - ", " — ", " – "):
        if sep in variant_name:
            tail_after_dash = variant_name.split(sep, 1)[1].strip().lower()
            break
    if tail_after_dash:
        if any(kw in tail_after_dash for kw in parallel_finish_keywords):
            return "parallel"
        if re.search(r"/\d+", tail_after_dash):
            return "parallel"
        # Color / metal as parallel suffix only after a dash (not in product title).
        color_parallel_tail = {
            "gold", "silver", "blue", "red", "green", "orange", "purple", "pink",
            "black", "white", "yellow", "platinum", "bronze", "aqua", "sapphire",
        }
        tail_tokens = {t.strip(".,") for t in tail_after_dash.split() if t.strip(".,")}
        if tail_tokens and tail_tokens <= color_parallel_tail:
            return "parallel"

    # Strong parallel keywords — avoid bare gold/silver/blue/black; those appear in insert NAMES.
    parallel_keywords = [
        "refractor", "parallel", "holo", "prismatic", "mojo", "xfractor",
        "shimmer", "rainbow", "die-cut", "die cut", "atomic",
        "mini", "ice",
    ]
    if any(kw in variant_lower for kw in parallel_keywords):
        return "parallel"

    return "insert"


def split_set_name(full_name: str) -> tuple[str, str | None]:
    """
    Split a full set name into base_name and variant_name.
    E.g. '2024 Topps Chrome - Refractor' -> ('2024 Topps Chrome', 'Refractor')
    """
    separators = [" - ", " — ", " – "]
    for sep in separators:
        if sep in full_name:
            parts = full_name.split(sep, 1)
            return parts[0].strip(), parts[1].strip()

    return full_name, None


def build_hierarchy(session: Session, year: int | None = None):
    """
    After cards are scraped, link parallel/insert sets to their parent base set.
    Groups sets by base_name and assigns parent_id.
    """
    query = session.query(CardSet)
    if year:
        query = query.filter(CardSet.year == year)

    sets = query.all()
    logger.info("Building hierarchy for %d sets", len(sets))

    # Group by base_name
    groups: dict[str, list[CardSet]] = defaultdict(list)
    for s in sets:
        groups[s.base_name].append(s)

    for base_name, group_sets in groups.items():
        if len(group_sets) <= 1:
            continue

        # Find the base set (no variant_name, or set_type == 'base')
        base_set = None
        for s in group_sets:
            if s.variant_name is None or s.set_type == "base":
                base_set = s
                break

        # If no clear base, pick the one with no variant
        if base_set is None:
            for s in group_sets:
                if s.variant_name is None:
                    base_set = s
                    break

        # If still no base, use the one with the lowest sid (likely the base)
        if base_set is None:
            base_set = min(group_sets, key=lambda s: s.tcdb_sid)
            base_set.set_type = "base"

        base_set.set_type = "base"

        # Link children to parent
        for s in group_sets:
            if s.id == base_set.id:
                continue
            s.parent_id = base_set.id
            if s.set_type == "base":
                s.set_type = classify_set_type(s.full_name, s.base_name, s.variant_name)

        logger.info("Group '%s': base=%s, children=%d", base_name, base_set.tcdb_sid,
                     len(group_sets) - 1)

    session.commit()
    logger.info("Hierarchy build complete.")
