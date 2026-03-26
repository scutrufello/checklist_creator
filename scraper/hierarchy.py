import logging
import re
from collections import defaultdict

from sqlalchemy.orm import Session

from app.models import CardSet

logger = logging.getLogger(__name__)

# Crystal/Laser + color: parallel of an autograph/mem line (e.g. Leaf "Base Autographs Crystal Black …").
_CRYSTAL_LASER_COLOR = re.compile(
    r"\b(crystal|laser)\s+"
    r"(black|blue|red|green|gold|orange|purple|pink|silver|platinum|white|yellow|aqua)\b",
    re.I,
)

# Standalone color word as the entire variant (e.g. "… - Gold" for a minors parallel).
_COLOR_ONLY_ONE_WORD = frozenset({
    "gold", "silver", "blue", "red", "green", "orange", "purple", "pink",
    "black", "white", "yellow", "platinum", "bronze", "aqua", "sapphire",
})

# Topps-style "… Black (Series One)" paper parallels (no Refractor / Autographs in name).
_TRAILING_COLOR_SERIES = re.compile(
    r"\b(black|blue|red|green|gold|orange|purple|pink|silver|platinum|white|yellow|aqua)\s+"
    r"\(series\s+(one|two|1|2)\)",
    re.I,
)


def _single_token_color_parallel(variant_name: str) -> bool:
    if not variant_name:
        return False
    stripped = variant_name.strip()
    if "(" in stripped:
        stripped = stripped.split("(", 1)[0].strip()
    parts = stripped.lower().split()
    if len(parts) != 1:
        return False
    return parts[0].rstrip(".,") in _COLOR_ONLY_ONE_WORD


def _autograph_plus_color_parallel(variant_lower: str) -> bool:
    """e.g. '35th Anniversary Autographs Black (Series One)' — parallel of the auto insert."""
    if "autograph" not in variant_lower:
        return False
    idx = variant_lower.rfind("autograph")
    tail = variant_lower[idx:]
    return bool(
        re.search(
            r"\bautographs?\s+(?:\([^)]*\)\s*)*"
            r"(black|blue|red|green|gold|orange|purple|pink|silver|platinum|white|yellow|aqua)\b",
            tail,
        )
    )


def _die_cut_autograph_insert_only(variant_lower: str) -> bool:
    """
    '… Die Cut Autographs' is an insert product name (die-cut shape), not a parallel finish.
    Returns True when the name is only that product line with no trailing foil / color parallel.
    """
    if not re.search(r"\bdie[-\s]?cut\s+autographs?\b", variant_lower):
        return False
    tail = re.split(r"\bautographs?\b", variant_lower, maxsplit=1)[-1]
    if re.search(
        r"\b(black|blue|red|green|gold|orange|purple|pink|silver|platinum|white|yellow|aqua|"
        r"foil|refractor|wave|sparkle|shimmer|prismatic|mojo|xfractor)\b",
        tail,
    ):
        return False
    return True


def classify_set_type(full_name: str, base_name: str, variant_name: str | None) -> str:
    """Heuristic classification of set type."""
    if not variant_name:
        return "base"

    variant_lower = variant_name.lower()

    # Unambiguous parallel signals (run before insert_keywords so "autograph" does not
    # force an auto-*parallel* line to be typed as insert).
    if _single_token_color_parallel(variant_name):
        return "parallel"
    if _TRAILING_COLOR_SERIES.search(variant_lower):
        return "parallel"
    if _autograph_plus_color_parallel(variant_lower):
        return "parallel"

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
    # Do not add bare "crystal" here — it appears in insert names like "Crystal Map".
    parallel_finish_keywords = [
        "refractor", "shimmer", "mojo", "xfractor", "foil", "prismatic",
        "die-cut", "die cut", "atomic", "wave", "lava", "speckle", "sparkle",
        "rainbow", "hyper", "crackle", "sapphire", "aqua", "pulsar",
        "mini", "numbered", "mega", "superfractor",
    ]
    has_slash_serial = bool(re.search(r"/\d+", variant_lower))
    has_parallel_finish = (
        any(kw in variant_lower for kw in parallel_finish_keywords)
        or has_slash_serial
        or bool(_CRYSTAL_LASER_COLOR.search(variant_lower))
    )

    autograph_or_mem_line = any(
        kw in variant_lower
        for kw in ("autograph", "autographs", "memorabilia", "relic", "on-card auto")
    )

    # "Chrome Prospect Autographs - Gold Shimmer" → parallel of the autograph insert.
    if autograph_or_mem_line and has_parallel_finish:
        if not _die_cut_autograph_insert_only(variant_lower):
            return "parallel"

    if any(kw in variant_lower for kw in insert_keywords):
        return "insert"

    # Finish layers without autograph/mem in the variant (e.g. "Black Foil", "FoilFractors"
    # on "2025 Greatest Hits"). insert_keywords run first so named lines like "black gold" stay insert.
    if has_parallel_finish:
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

        # True product base: stored with no variant_name (e.g. "2026 Topps").
        # Do not use set_type == 'base' here — it can be stale and match a parallel row first.
        base_set = None
        for s in group_sets:
            if s.variant_name is None:
                base_set = s
                break

        # If still no base, prefer a true "insert" anchor (shortest variant_name first),
        # so TCDB sid ordering does not promote a parallel row (e.g. Leaf) to group root.
        if base_set is None:
            insert_anchors = [
                s for s in group_sets
                if classify_set_type(s.full_name, s.base_name, s.variant_name) == "insert"
            ]
            if insert_anchors:
                base_set = min(
                    insert_anchors,
                    key=lambda s: (len(s.variant_name or ""), s.tcdb_sid),
                )
            else:
                base_set = min(group_sets, key=lambda s: s.tcdb_sid)
            base_set.set_type = "base"

        base_set.set_type = "base"
        base_set.parent_id = None

        # Link children to parent
        for s in group_sets:
            if s.id == base_set.id:
                continue
            s.parent_id = base_set.id
            s.set_type = classify_set_type(s.full_name, s.base_name, s.variant_name)

        logger.info("Group '%s': base=%s, children=%d", base_name, base_set.tcdb_sid,
                     len(group_sets) - 1)

    session.commit()
    logger.info("Hierarchy build complete.")
