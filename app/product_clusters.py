"""Product cluster rollups and parallel list helpers."""
from __future__ import annotations

import re

from app.models import CardSet

_TOPPS_FLAGSHIP = re.compile(r"^\d{4} Topps$")
_TOPPS_UPDATE = re.compile(r"^\d{4} Topps Update$")
_TOPPS_TRADED = re.compile(r"^\d{4} Topps Traded\b", re.I)
_TOPPS_CHROME = re.compile(r"^\d{4} Topps Chrome$")
_TOPPS_CHROME_UPDATE = re.compile(r"^\d{4} Topps Chrome Update$")
_TOPPS_CHROME_LOGOFRACTOR = re.compile(r"^\d{4} Topps Chrome Logofractor Edition$")
_TOPPS_CHROME_SAPPHIRE = re.compile(r"^\d{4} Topps Chrome Sapphire Edition$")
_TOPPS_CHROME_UPDATE_SAPPHIRE = re.compile(r"^\d{4} Topps Chrome Update Sapphire Edition$")
_TOPPS_CHROME_TRADED = re.compile(r"^\d{4} Topps Chrome Traded\b", re.I)
_FLEER_FLAGSHIP = re.compile(r"^\d{4} Fleer$")
_FLEER_UPDATE = re.compile(r"^\d{4} Fleer Update$")
_FLEER_FINAL_EDITION = re.compile(r"^\d{4} Fleer Final Edition$")
_FLEER_TRADITION = re.compile(r"^\d{4} Fleer Tradition$")
_FLEER_TRADITION_UPDATE = re.compile(r"^\d{4} Fleer Tradition Update$")
_SCORE_FLAGSHIP = re.compile(r"^\d{4} Score$")
_SCORE_ROOKIE_TRADED = re.compile(r"^\d{4} Score Rookie & Traded$")
_SCORE_ROOKIES = re.compile(r"^\d{4} Score Rookies$")
_DONRUSS_FLAGSHIP = re.compile(r"^\d{4} Donruss$")
_DONRUSS_TRADED = re.compile(r"^\d{4} Donruss Traded$")
_DONRUSS_THE_ROOKIES = re.compile(r"^\d{4} Donruss The Rookies$")
_UPPER_DECK_FLAGSHIP = re.compile(r"^\d{4} Upper Deck$")
_UD_FINAL_EDITION = re.compile(r"^\d{4} Upper Deck Final Edition$")
_ULTRA_FLAGSHIP = re.compile(r"^\d{4} Ultra$")
_ULTRA_UPDATE = re.compile(r"^\d{4} Ultra Update$")
_SELECT_FLAGSHIP = re.compile(r"^\d{4} Select$")
_SELECT_ROOKIE_TRADED = re.compile(r"^\d{4} Select Rookie & Traded$")
_BOWMAN_FLAGSHIP = re.compile(r"^\d{4} Bowman$")
_BOWMAN_SAPPHIRE = re.compile(r"^\d{4} Bowman Sapphire Edition$")
_BOWMAN_CHROME = re.compile(r"^\d{4} Bowman Chrome$")
_BOWMAN_CHROME_SAPPHIRE = re.compile(r"^\d{4} Bowman Chrome Sapphire Edition$")
_BOWMAN_DRAFT = re.compile(r"^\d{4} Bowman Draft$")
_BOWMAN_DRAFT_SAPPHIRE = re.compile(r"^\d{4} Bowman Draft Sapphire Edition$")
_TOPPS_NOW = re.compile(r"^\d{4} Topps Now$")
_TOPPS_NOW_FAMILY = re.compile(r"^\d{4} Topps Now(?: .+)?$")
_TOPPS_BIG_LEAGUE = re.compile(r"^\d{4} Topps Big League$")
_TOPPS_BIG_LEAGUE_WRAPPER = re.compile(
    r"^\d{4} Topps Big League(?: .+)? Wrapper Redemption$",
    re.I,
)

# kind → flagship regex + supplemental segment keys (order preserved for progress bars)
_CLUSTER_DEFS: tuple[tuple[str, re.Pattern[str], tuple[tuple[str, re.Pattern[str]], ...]], ...] = (
    (
        "topps_paper",
        _TOPPS_FLAGSHIP,
        (
            ("traded", _TOPPS_TRADED),
            ("update", _TOPPS_UPDATE),
        ),
    ),
    (
        "topps_chrome",
        _TOPPS_CHROME,
        (
            ("logofractor", _TOPPS_CHROME_LOGOFRACTOR),
            ("update", _TOPPS_CHROME_UPDATE),
            ("traded", _TOPPS_CHROME_TRADED),
            ("sapphire", _TOPPS_CHROME_SAPPHIRE),
            ("update_sapphire", _TOPPS_CHROME_UPDATE_SAPPHIRE),
        ),
    ),
    (
        "bowman_paper",
        _BOWMAN_FLAGSHIP,
        (
            ("sapphire", _BOWMAN_SAPPHIRE),
        ),
    ),
    (
        "bowman_chrome",
        _BOWMAN_CHROME,
        (
            ("sapphire", _BOWMAN_CHROME_SAPPHIRE),
        ),
    ),
    (
        "bowman_draft",
        _BOWMAN_DRAFT,
        (
            ("sapphire", _BOWMAN_DRAFT_SAPPHIRE),
        ),
    ),
    (
        "topps_now",
        _TOPPS_NOW,
        (),
    ),
    (
        "topps_big_league",
        _TOPPS_BIG_LEAGUE,
        (
            ("wrapper_redemption", _TOPPS_BIG_LEAGUE_WRAPPER),
        ),
    ),
    (
        "fleer_paper",
        _FLEER_FLAGSHIP,
        (
            ("update", _FLEER_UPDATE),
            ("final_edition", _FLEER_FINAL_EDITION),
        ),
    ),
    (
        "fleer_tradition",
        _FLEER_TRADITION,
        (
            ("update", _FLEER_TRADITION_UPDATE),
        ),
    ),
    (
        "score_paper",
        _SCORE_FLAGSHIP,
        (
            ("rookie_traded", _SCORE_ROOKIE_TRADED),
            ("rookies", _SCORE_ROOKIES),
        ),
    ),
    (
        "donruss_paper",
        _DONRUSS_FLAGSHIP,
        (
            ("traded", _DONRUSS_TRADED),
            ("the_rookies", _DONRUSS_THE_ROOKIES),
        ),
    ),
    (
        "upper_deck_paper",
        _UPPER_DECK_FLAGSHIP,
        (
            ("final_edition", _UD_FINAL_EDITION),
        ),
    ),
    (
        "ultra_paper",
        _ULTRA_FLAGSHIP,
        (
            ("update", _ULTRA_UPDATE),
        ),
    ),
    (
        "select_paper",
        _SELECT_FLAGSHIP,
        (
            ("rookie_traded", _SELECT_ROOKIE_TRADED),
        ),
    ),
)

_SERIES_TWO = re.compile(r"\(series\s+(?:two|2|2nd)\)", re.I)
_PROSPECT_NAME = re.compile(r"prospect|scouts", re.I)
_PROSPECT_CARD_PREFIX = re.compile(
    r"^(?:BP|BCP|BTP|BTPA|CPA|BPA|PP|PPA|VIP|RI|RIA|GOTD|GDA)\b",
    re.I,
)
_SERIAL_DENOM = re.compile(r"/(\d+)\b")
_SN_DENOM = re.compile(r"\bSN\s*/?\s*(\d+)\b", re.I)


def _cluster_def(kind: str) -> tuple[re.Pattern[str], tuple[tuple[str, re.Pattern[str]], ...]] | None:
    for cluster_kind, flagship_re, supplementals in _CLUSTER_DEFS:
        if cluster_kind == kind:
            return flagship_re, supplementals
    return None


def cluster_kind_for_base_name(base_name: str) -> str | None:
    name = base_name.strip()
    if _TOPPS_NOW_FAMILY.match(name):
        return "topps_now"
    for kind, flagship_re, supplementals in _CLUSTER_DEFS:
        if flagship_re.match(name):
            return kind
        for _seg_key, supplemental_re in supplementals:
            if supplemental_re.match(name):
                return kind
    return None


def cluster_base_names_for_year(year: int, kind: str) -> list[str]:
    prefix = str(year)
    if kind == "topps_paper":
        return [f"{prefix} Topps", f"{prefix} Topps Update", f"{prefix} Topps Traded"]
    if kind == "topps_chrome":
        return [
            f"{prefix} Topps Chrome",
            f"{prefix} Topps Chrome Logofractor Edition",
            f"{prefix} Topps Chrome Update",
            f"{prefix} Topps Chrome Traded and Rookies",
            f"{prefix} Topps Chrome Sapphire Edition",
            f"{prefix} Topps Chrome Update Sapphire Edition",
        ]
    if kind == "bowman_paper":
        return [f"{prefix} Bowman", f"{prefix} Bowman Sapphire Edition"]
    if kind == "bowman_chrome":
        return [f"{prefix} Bowman Chrome", f"{prefix} Bowman Chrome Sapphire Edition"]
    if kind == "bowman_draft":
        return [f"{prefix} Bowman Draft", f"{prefix} Bowman Draft Sapphire Edition"]
    if kind == "topps_now":
        return [f"{prefix} Topps Now"]
    if kind == "topps_big_league":
        return [f"{prefix} Topps Big League"]
    if kind == "fleer_paper":
        return [f"{prefix} Fleer", f"{prefix} Fleer Update", f"{prefix} Fleer Final Edition"]
    if kind == "fleer_tradition":
        return [f"{prefix} Fleer Tradition", f"{prefix} Fleer Tradition Update"]
    if kind == "score_paper":
        return [
            f"{prefix} Score",
            f"{prefix} Score Rookie & Traded",
            f"{prefix} Score Rookies",
        ]
    if kind == "donruss_paper":
        return [f"{prefix} Donruss", f"{prefix} Donruss Traded", f"{prefix} Donruss The Rookies"]
    if kind == "upper_deck_paper":
        return [f"{prefix} Upper Deck", f"{prefix} Upper Deck Final Edition"]
    if kind == "ultra_paper":
        return [f"{prefix} Ultra", f"{prefix} Ultra Update"]
    if kind == "select_paper":
        return [f"{prefix} Select", f"{prefix} Select Rookie & Traded"]
    return []


def _topps_now_suffix(base_name: str) -> str | None:
    m = re.match(r"^\d{4} Topps Now(?: (.+))?$", (base_name or "").strip())
    if not m:
        return None
    return m.group(1)


def _topps_now_segment_key(suffix: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", suffix.lower()).strip("_")
    return slug or "other"


def _topps_now_segment_label(suffix: str) -> str:
    label = re.sub(r"\s+Philadelphia Phillies\s*$", "", suffix, flags=re.I).strip()
    return label or suffix


def _topps_now_segment_sort_key(label: str) -> tuple[int, str]:
    ll = label.lower()
    if ll.startswith("road to opening day") and "bonus" not in ll:
        return (0, label.lower())
    if "road to opening day" in ll and "bonus" in ll:
        return (1, label.lower())
    return (2, label.lower())


def pick_topps_now_supplemental_roots(
    members: list[CardSet],
) -> tuple[dict[str, CardSet | None], dict[str, str]]:
    """One segment per distinct ``YYYY Topps Now …`` sub-product (Road to Opening Day, etc.)."""
    by_base_name: dict[str, list[CardSet]] = {}
    for s in members:
        by_base_name.setdefault(s.base_name, []).append(s)

    roots: dict[str, CardSet | None] = {}
    labels: dict[str, str] = {}
    for base_name, group_sets in by_base_name.items():
        if _TOPPS_NOW.match(base_name.strip()):
            continue
        suffix = _topps_now_suffix(base_name)
        if not suffix:
            continue
        seg_key = _topps_now_segment_key(suffix)
        if seg_key in roots:
            continue
        candidates = [s for s in group_sets if s.variant_name is None]
        if candidates:
            root = min(candidates, key=lambda s: s.tcdb_sid)
        else:
            from scraper.hierarchy import pick_product_root

            root = pick_product_root(group_sets)
        roots[seg_key] = root
        labels[seg_key] = _topps_now_segment_label(suffix)
    return roots, labels


def topps_now_segment_order(supplemental_labels: dict[str, str]) -> tuple[str, ...]:
    return tuple(
        sorted(
            supplemental_labels.keys(),
            key=lambda k: _topps_now_segment_sort_key(supplemental_labels.get(k, k)),
        )
    )


def pick_cluster_primary_root(members: list[CardSet], kind: str) -> CardSet:
    """Flagship row (exact YYYY Topps / YYYY Topps Chrome, variant_name is None)."""
    if kind == "topps_now":
        candidates = [
            s for s in members
            if _TOPPS_NOW.match((s.base_name or "").strip()) and s.variant_name is None
        ]
        if candidates:
            return min(candidates, key=lambda s: s.tcdb_sid)
        raise ValueError("No primary root for cluster topps_now")
    cluster = _cluster_def(kind)
    if cluster is None:
        raise ValueError(f"Unknown cluster kind {kind}")
    flagship_re, _ = cluster
    candidates = [
        s for s in members
        if flagship_re.match((s.base_name or "").strip()) and s.variant_name is None
    ]
    if candidates:
        return min(candidates, key=lambda s: s.tcdb_sid)
    raise ValueError(f"No primary root for cluster {kind}")


def pick_cluster_supplemental_roots(
    members: list[CardSet],
    kind: str,
) -> dict[str, CardSet | None]:
    """Root row per supplemental release (Update, Traded, …)."""
    cluster = _cluster_def(kind)
    if cluster is None:
        return {}
    _flagship_re, supplementals = cluster
    roots: dict[str, CardSet | None] = {}
    for seg_key, supplemental_re in supplementals:
        candidates = [
            s for s in members
            if supplemental_re.match((s.base_name or "").strip()) and s.variant_name is None
        ]
        roots[seg_key] = min(candidates, key=lambda s: s.tcdb_sid) if candidates else None
    return roots


def pick_cluster_update_root(members: list[CardSet], kind: str) -> CardSet | None:
    """Backward-compatible helper for Update-only callers."""
    return pick_cluster_supplemental_roots(members, kind).get("update")


def supplemental_base_names_from_roots(roots: dict[str, CardSet | None]) -> dict[str, str]:
    return {key: card_set.base_name for key, card_set in roots.items() if card_set}


def supplemental_segment_order(kind: str, supplemental_labels: dict[str, str] | None = None) -> tuple[str, ...]:
    if kind == "topps_now" and supplemental_labels:
        return topps_now_segment_order(supplemental_labels)
    cluster = _cluster_def(kind)
    if cluster is None:
        return ()
    _flagship_re, supplementals = cluster
    return tuple(seg_key for seg_key, _ in supplementals)


def build_segment_keys(
    supplemental_base_names: dict[str, str],
    *,
    split_series_two: bool,
    cluster_kind: str | None = None,
    supplemental_labels: dict[str, str] | None = None,
) -> list[str]:
    if cluster_kind == "bowman_paper":
        keys = ["veterans", "prospects"]
        for seg_key in supplemental_segment_order("bowman_paper"):
            if seg_key in supplemental_base_names:
                keys.append(seg_key)
        return keys
    if cluster_kind == "topps_now":
        keys = ["flagship"]
        for seg_key in supplemental_segment_order("topps_now", supplemental_labels):
            if seg_key in supplemental_base_names:
                keys.append(seg_key)
        return keys
    keys: list[str] = []
    if split_series_two:
        keys.extend(["series_1", "series_2"])
    else:
        keys.append("flagship")
    for seg_key in supplemental_segment_order(cluster_kind or "", supplemental_labels):
        if seg_key in supplemental_base_names:
            keys.append(seg_key)
    return keys


def is_bowman_prospect_by_name(card_set: CardSet) -> bool:
    text = f"{card_set.variant_name or ''} {card_set.full_name or ''}"
    return bool(_PROSPECT_NAME.search(text))


def prospect_set_ids_from_card_numbers(db, set_ids: set[int] | list[int]) -> set[int]:
    """Flag insert sets whose checklist uses Bowman prospect card-number prefixes."""
    if not set_ids:
        return set()
    from app.models import Card

    rows = (
        db.query(Card.set_id, Card.number)
        .filter(Card.set_id.in_(set_ids))
        .order_by(Card.set_id, Card.id)
        .all()
    )
    prospect_ids: set[int] = set()
    seen: set[int] = set()
    for set_id, number in rows:
        if set_id in seen:
            continue
        seen.add(set_id)
        if number and _PROSPECT_CARD_PREFIX.match(number.strip()):
            prospect_ids.add(set_id)
    return prospect_ids


def identify_bowman_prospect_set_ids(db, members: list[CardSet]) -> set[int]:
    prospect_ids = {s.id for s in members if is_bowman_prospect_by_name(s)}
    remaining = [s.id for s in members if s.id not in prospect_ids]
    prospect_ids |= prospect_set_ids_from_card_numbers(db, remaining)
    return prospect_ids


def bowman_segment_for_set(
    card_set: CardSet,
    prospect_set_ids: set[int],
    members_by_id: dict[int, CardSet],
    base_set_id: int,
) -> str:
    if card_set.id in prospect_set_ids:
        return "prospects"
    pid = card_set.canonical_parent_set_id
    seen: set[int] = set()
    while pid is not None and pid not in seen:
        seen.add(pid)
        if pid in prospect_set_ids:
            return "prospects"
        if pid == base_set_id:
            return "veterans"
        parent = members_by_id.get(pid)
        if parent is None:
            break
        if parent.id in prospect_set_ids:
            return "prospects"
        pid = parent.canonical_parent_set_id
    return "veterans"


def has_series_two_marker(card_set: CardSet) -> bool:
    text = f"{card_set.variant_name or ''} {card_set.full_name or ''}"
    return bool(_SERIES_TWO.search(text))


def detect_series_two_split(flagship_members: list[CardSet]) -> bool:
    """True when any flagship-family row uses an explicit (Series Two) marker."""
    return any(has_series_two_marker(s) for s in flagship_members)


def segment_for_set(
    card_set: CardSet,
    *,
    supplemental_base_names: dict[str, str],
    split_series_two: bool,
    cluster_kind: str | None = None,
    prospect_set_ids: set[int] | None = None,
    members_by_id: dict[int, CardSet] | None = None,
    base_set_id: int | None = None,
) -> str:
    base_name = card_set.base_name
    for seg_key, supplemental_base in supplemental_base_names.items():
        if base_name == supplemental_base:
            return seg_key
    if cluster_kind == "bowman_paper":
        return bowman_segment_for_set(
            card_set,
            prospect_set_ids or set(),
            members_by_id or {},
            base_set_id or 0,
        )
    if not split_series_two:
        return "flagship"
    if has_series_two_marker(card_set):
        return "series_2"
    return "series_1"


def segment_label(key: str) -> str:
    return {
        "flagship": "Flagship",
        "series_1": "Series 1",
        "series_2": "Series 2",
        "traded": "Traded",
        "logofractor": "Logofractor",
        "update": "Update",
        "sapphire": "Sapphire",
        "update_sapphire": "Update Sapphire",
        "veterans": "Veterans",
        "prospects": "Prospects",
        "wrapper_redemption": "Wrapper Redemption",
        "final_edition": "Final Edition",
        "rookie_traded": "Rookie & Traded",
        "the_rookies": "The Rookies",
        "rookies": "Rookies",
    }.get(key, key.replace("_", " ").title())


def parse_serial_denominator(text: str | None) -> int | None:
    """Extract print-run denominator from /NNN or SN### patterns (in names or card tags)."""
    if not text:
        return None
    matches = [int(m.group(1)) for m in _SERIAL_DENOM.finditer(text)]
    matches.extend(int(m.group(1)) for m in _SN_DENOM.finditer(text))
    return max(matches) if matches else None


def serial_denominator_for_parallel(
    card_set: CardSet,
    serial_by_set_id: dict[int, int] | None = None,
) -> int | None:
    for field in (card_set.variant_name, card_set.full_name):
        denom = parse_serial_denominator(field)
        if denom is not None:
            return denom
    if serial_by_set_id:
        return serial_by_set_id.get(card_set.id)
    return None


def serial_denominators_from_card_tags(db, set_ids: set[int] | list[int]) -> dict[int, int]:
    """Batch lookup SN### print runs from card tags (TCDB stores these separately from set names)."""
    if not set_ids:
        return {}
    from app.models import Card

    rows = (
        db.query(Card.set_id, Card.raw_tags_text)
        .filter(Card.set_id.in_(set_ids))
        .filter(Card.raw_tags_text.isnot(None))
        .filter(Card.raw_tags_text != "")
        .order_by(Card.set_id, Card.id)
        .all()
    )
    result: dict[int, int] = {}
    for set_id, raw_tags in rows:
        if set_id in result:
            continue
        denom = parse_serial_denominator(raw_tags)
        if denom is not None:
            result[set_id] = denom
    return result


def partition_numbered_unnumbered(
    parallels: list[dict],
    serial_by_set_id: dict[int, int] | None = None,
) -> dict[str, list[dict]]:
    numbered: list[tuple[int, dict]] = []
    unnumbered: list[dict] = []
    for row in parallels:
        cs = row["set"]
        denom = serial_denominator_for_parallel(cs, serial_by_set_id)
        if denom is not None:
            numbered.append((denom, row))
        else:
            unnumbered.append(row)
    numbered.sort(key=lambda item: (-item[0], (item[1]["set"].display_name or "").lower()))
    unnumbered.sort(key=lambda row: (row["set"].display_name or "").lower())
    return {
        "numbered": [row for _, row in numbered],
        "unnumbered": unnumbered,
    }


def parallel_set_ids_in_section_data(section_data: dict) -> set[int]:
    ids: set[int] = set()
    for row in section_data.get("base_parallels", []):
        ids.add(row["set"].id)
    for sec in section_data.get("sections", []):
        for row in sec.get("parallels", []):
            ids.add(row["set"].id)
    return ids


def attach_parallel_partitions(
    section_data: dict,
    serial_by_set_id: dict[int, int] | None = None,
) -> dict:
    """Add numbered/unnumbered lists alongside raw parallel lists."""
    out = {
        "base_parallels": section_data.get("base_parallels", []),
        "base_parallels_partitioned": partition_numbered_unnumbered(
            section_data.get("base_parallels", []),
            serial_by_set_id,
        ),
        "sections": [],
    }
    for sec in section_data.get("sections", []):
        partitioned = partition_numbered_unnumbered(sec.get("parallels", []), serial_by_set_id)
        out["sections"].append({**sec, "parallels_partitioned": partitioned})
    return out


def progress_from_sets(set_ids: list[int], stats_by_set_id: dict[int, dict[str, int]]) -> dict[str, int]:
    total = owned = 0
    for sid in set_ids:
        st = stats_by_set_id.get(sid, {"total": 0, "owned": 0})
        total += st["total"]
        owned += st["owned"]
    return {"total": total, "owned": owned}


def sets_in_segment(
    all_member_ids: set[int],
    members_by_id: dict[int, CardSet],
    stats_by_set_id: dict[int, dict[str, int]],
    *,
    supplemental_base_names: dict[str, str],
    split_series_two: bool,
    segment_key: str,
    cluster_kind: str | None = None,
    prospect_set_ids: set[int] | None = None,
    base_set_id: int | None = None,
) -> list[int]:
    ids: list[int] = []
    for sid in all_member_ids:
        cs = members_by_id[sid]
        if segment_for_set(
            cs,
            supplemental_base_names=supplemental_base_names,
            split_series_two=split_series_two,
            cluster_kind=cluster_kind,
            prospect_set_ids=prospect_set_ids,
            members_by_id=members_by_id,
            base_set_id=base_set_id,
        ) == segment_key:
            if stats_by_set_id.get(sid, {}).get("total", 0) >= 0:
                ids.append(sid)
    return ids
