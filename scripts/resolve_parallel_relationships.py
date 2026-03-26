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
    """
    One checklist slot per (card number, player). Variation rows (SP/VAR, different
    variant text) still map to the same key, so they share a slot with the base #/name.

    That matches how most parallels work: chrome/refractor lines mirror the flagship
    checklist counts, not every image-variation row. Overlap scores therefore compare
    parallel checklists to the shared “base roster”, not to a 1:1 expansion of every VAR.
    """
    return f"{norm_number(card.number)}|{norm_text(card.player_name)}"


_SERIES_PAREN_SUFFIX_RE = re.compile(
    r"\s*\(\s*series\s+(one|two|1|2)\s*\)\s*$",
    re.I,
)

_CHAIN_AUTOGRAPH_WORD = re.compile(r"\bautographs?\b", re.I)


def _norm_chain_title(t: str) -> str:
    """Lowercase, collapse whitespace, and fold autograph/autographs for title chaining."""
    t = (t or "").strip().lower()
    t = re.sub(r"\s+", " ", t)
    return _CHAIN_AUTOGRAPH_WORD.sub("autograph", t)


# TCDB sometimes titles the parallel "Real Ones Relics …" while the parent insert is "Real One Relics".
_REAL_ONES_RELICS_TYPO = re.compile(r"\breal ones relics\b", re.I)


def _norm_title_for_parallel_chain(t: str) -> str:
    """Like `_norm_chain_title` plus known product-title typos that break strict prefix matching."""
    t = _norm_chain_title(t)
    t = _REAL_ONES_RELICS_TYPO.sub("real one relics", t)
    return t


def _full_title_parallel_extension(parent: CardSet, child: CardSet) -> bool:
    """
    Child extends parent as ``… - Extra`` or ``… Extra`` (single space).
    Covers ``… Die Cut Autographs`` + `` FoilFractors`` (TCDB often omits `` - `` before the parallel token).
    Folds autograph/autographs so a singular base title still matches.
    """
    pf = (parent.full_name or "").strip()
    cf = (child.full_name or "").strip()
    if len(cf) <= len(pf):
        return False
    pn = _norm_title_for_parallel_chain(pf)
    cn = _norm_title_for_parallel_chain(cf)
    if cn.startswith(pn + " - "):
        return bool(cn[len(pn) + 3 :].strip())
    if cn.startswith(pn + " "):
        return bool(cn[len(pn) :].strip())
    return False


def _split_variant_series_core(v: str | None) -> tuple[str, str | None]:
    """Strip trailing '(Series One)' / '(Series 1)' style suffix; return (core, normalized suffix)."""
    v = (v or "").strip()
    if not v:
        return "", None
    m = _SERIES_PAREN_SUFFIX_RE.search(v)
    if not m:
        return v, None
    core = v[: m.start()].rstrip()
    series_norm = re.sub(r"\s+", " ", m.group(0).strip().lower())
    return core, series_norm


def _variant_mid_name_parallel_extension(parent: CardSet, child: CardSet) -> bool:
    """
    Same checklist family with parallel wording inserted before a shared '(Series …)' tail, e.g.
    '… 35th Anniversary (Series One)' vs '… 35th Anniversary Koi Fish (Series One)'.
    (full_name prefix 'Parent - Child' does not apply because TCDB inserts the extra tokens mid-title.)
    """
    if parent.base_name != child.base_name:
        return False
    pv = parent.variant_name
    cv = child.variant_name
    if not pv or not cv:
        return False
    p_core, p_suf = _split_variant_series_core(pv)
    c_core, c_suf = _split_variant_series_core(cv)
    if p_suf and c_suf and p_suf != c_suf:
        return False
    p_n = _norm_title_for_parallel_chain(p_core)
    c_n = _norm_title_for_parallel_chain(c_core)
    if not c_n.startswith(p_n) or c_n == p_n:
        return False
    extra = c_n[len(p_n) :].strip()
    return bool(extra)


def _reconcile_identical_checklist_lines(
    group_sets: list[CardSet],
    sig_by_set_id: dict[int, set[str]],
) -> None:
    """
    Team-filtered checklists often share the same small player/number set across unrelated
    products, so we must NOT merge on signature alone.

    When signatures are identical AND the child's name extends the parent's (``full_name``
    chain with `` - `` or a single space, OR mid-variant extension before ``(Series …)``),
    treat the longer line as a parallel of the nearest shorter name (same print family).
    """
    eligible = [
        s for s in group_sets
        if sig_by_set_id.get(s.id)
        and s.variant_name is not None
        and s.relationship_type in {"insert", "parallel", "standalone"}
    ]
    buckets: dict[frozenset[str], list[CardSet]] = defaultdict(list)
    for s in eligible:
        buckets[frozenset(sig_by_set_id[s.id])].append(s)

    for members in buckets.values():
        if len(members) < 2:
            continue
        ordered = sorted(members, key=lambda s: (len(s.full_name or ""), s.tcdb_sid))
        child_to_parent: dict[int, int] = {}
        for o in ordered:
            parents = [
                p for p in ordered
                if p.id != o.id
                and len(p.full_name or "") < len(o.full_name or "")
                and (
                    _full_title_parallel_extension(p, o)
                    or _variant_mid_name_parallel_extension(p, o)
                )
            ]
            if not parents:
                continue
            immediate = max(parents, key=lambda p: len(p.full_name or ""))
            child_to_parent[o.id] = immediate.id

        for s in members:
            pid = child_to_parent.get(s.id)
            if pid is not None:
                s.relationship_type = "parallel"
                s.canonical_parent_set_id = pid
                s.relationship_confidence = 1.0


def _heritage_identical_roster_parallels_to_flagship(
    group_sets: list[CardSet],
    root_base: CardSet,
    sig_by_set_id: dict[int, set[str]],
) -> None:
    """
    Heritage paper parallels (borders, flip stock, deckle, color-of-the-year, etc.) use the
    same team roster as the flagship but often lack 'foil'/'refractor' in the name, so name
    heuristics label them insert. If (number, player) keys match the bare Heritage base exactly,
    treat them as parallels of that flagship.

    Scoped to *Heritage* products only — flagship Topps has many unrelated inserts that reuse
    the same small team checklist and must not use this rule.
    """
    if "heritage" not in (root_base.base_name or "").lower():
        return
    if root_base.variant_name is not None:
        return
    base_sig = sig_by_set_id.get(root_base.id)
    if not base_sig:
        return
    for s in group_sets:
        if s.id == root_base.id:
            continue
        if sig_by_set_id.get(s.id) != base_sig:
            continue
        s.relationship_type = "parallel"
        s.canonical_parent_set_id = root_base.id
        s.relationship_confidence = 1.0


# Bare flagship only (not "Topps Chrome", "Topps Update", etc.)
_TOPPS_FLAGSHIP_BASE_NAME = re.compile(r"^\d{4} Topps$")

def _topps_flagship_identical_roster_parallels(
    group_sets: list[CardSet],
    root_base: CardSet,
    sig_by_set_id: dict[int, set[str]],
) -> None:
    """
    For ``YYYY Topps`` (paper flagship), many stock parallels (borders, sandglitter, plates,
    holiday stock, etc.) reuse the exact same team checklist as the base set but lack
    ``foil``/``refractor`` in the name, so heuristics leave them as insert.

    If (number, player) keys match the flagship exactly, treat as parallels.

    Confetti / Confetti *: TCDB often uses different ``player_name`` text on league-leader
    rows vs the flagship, so ``card_core_key`` never matches even though it is the same
    stock parallel family — force those lines to the flagship as well.
    """
    if root_base.variant_name is not None:
        return
    if not _TOPPS_FLAGSHIP_BASE_NAME.match((root_base.base_name or "").strip()):
        return
    base_sig = sig_by_set_id.get(root_base.id)
    if not base_sig:
        return
    for s in group_sets:
        if s.id == root_base.id:
            continue
        v = (s.variant_name or "").strip().lower()
        if v == "confetti" or v.startswith("confetti "):
            s.relationship_type = "parallel"
            s.canonical_parent_set_id = root_base.id
            s.relationship_confidence = 1.0
            continue
        if sig_by_set_id.get(s.id) != base_sig:
            continue
        s.relationship_type = "parallel"
        s.canonical_parent_set_id = root_base.id
        s.relationship_confidence = 1.0


def _heritage_chrome_parallels_to_flagship(group_sets: list[CardSet], root_base: CardSet) -> None:
    """
    For Heritage products, the Chrome checklist mirrors the paper base; Chrome refractors
    mirror the same roster. Attach ``Chrome`` and every ``Chrome …`` line to the flagship
    Heritage row instead of nesting under an intermediate Chrome insert.
    """
    if "heritage" not in (root_base.base_name or "").lower():
        return
    for s in group_sets:
        if s.id == root_base.id:
            continue
        if s.base_name != root_base.base_name:
            continue
        vn = (s.variant_name or "").strip()
        if not vn:
            continue
        if vn != "Chrome" and not vn.startswith("Chrome "):
            continue
        s.relationship_type = "parallel"
        s.canonical_parent_set_id = root_base.id
        s.relationship_confidence = 1.0


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

    # Same checklist ⇒ same print run family: collapse duplicate insert lines to one parent.
    _reconcile_identical_checklist_lines(group_sets, sig_by_set_id)

    # Heritage: same roster as paper flagship ⇒ parallel stock (borders, flip, deckle, chrome, …).
    _heritage_identical_roster_parallels_to_flagship(group_sets, root_base, sig_by_set_id)

    # Topps Heritage: Chrome is a parallel product of the paper flagship; refractors / sparkles
    # are parallels of that flagship too (not nested under a synthetic "Chrome" insert).
    _heritage_chrome_parallels_to_flagship(group_sets, root_base)

    # ``YYYY Topps`` paper: identical roster as flagship ⇒ parallel (borders, sandglitter, …).
    _topps_flagship_identical_roster_parallels(group_sets, root_base, sig_by_set_id)

    # Keep set_type aligned with resolver output (UI and build_hierarchy name heuristics often
    # still say "insert" for lines we proved are parallels, e.g. "8 Bit Ballers Black").
    for s in group_sets:
        rt = s.relationship_type
        if rt in ("base", "insert", "parallel", "variation", "standalone"):
            s.set_type = rt


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
