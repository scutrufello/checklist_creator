import os
from collections import defaultdict
import re
from urllib.parse import urlencode

from fastapi import FastAPI, Request, Depends, Form, File, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import and_, func, distinct, case, or_
from sqlalchemy.orm import Session, joinedload

from app.database import get_session, init_db, load_config
from app.models import Card, CardSet
from app.user_card_images import (
    CropBox,
    apply_crop_from_original,
    delete_user_photo,
    process_upload,
    user_photos_enabled,
)
from app.product_clusters import (
    attach_parallel_partitions,
    build_segment_keys,
    cluster_kind_for_base_name,
    detect_series_two_split,
    identify_bowman_prospect_set_ids,
    parallel_set_ids_in_section_data,
    pick_cluster_primary_root,
    pick_cluster_supplemental_roots,
    pick_topps_now_supplemental_roots,
    progress_from_sets,
    segment_for_set,
    segment_label,
    serial_denominators_from_card_tags,
    sets_in_segment,
    supplemental_base_names_from_roots,
)
from app.set_metadata import (
    CATEGORY_LABEL_BY_KEY,
    YEAR_LIST_CATEGORIES,
    auto_year_list_category,
    auto_year_list_category_label,
    effective_year_list_category,
    effective_year_list_category_label,
    set_is_hidden,
    year_list_display_name,
)
from scraper.hierarchy import pick_product_root

app = FastAPI(title="Phillies Cards Checklist")

BASE_DIR = os.path.dirname(__file__)
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

_config = load_config()
_image_dir = _config["storage"]["image_path"]
if not os.path.isabs(_image_dir):
    _image_dir = os.path.normpath(os.path.join(os.path.dirname(BASE_DIR), _image_dir))
os.makedirs(_image_dir, exist_ok=True)
app.mount("/card-images", StaticFiles(directory=_image_dir), name="card-images")

_USER_PHOTOS_ENABLED = user_photos_enabled(_config)
_MAX_USER_PHOTO_BYTES = 15 * 1024 * 1024
_ALLOWED_USER_PHOTO_TYPES = {"image/jpeg", "image/png", "image/webp", "image/jpg"}


def _template_globals():
    return {"user_card_photos_enabled": _USER_PHOTOS_ENABLED}


templates.env.globals.update(_template_globals())


def get_db():
    db = get_session()
    try:
        yield db
    finally:
        db.close()



def _organize_year_list_sections(set_groups: list[dict]) -> list[dict]:
    """Split year groups into taxonomy sections (admin overrides respected)."""
    buckets: dict[str, list[dict]] = defaultdict(list)
    for g in set_groups:
        buckets[effective_year_list_category(g["base_set"])].append(g)

    sections: list[dict] = []
    for key, label in YEAR_LIST_CATEGORIES:
        groups = buckets.get(key, [])
        if not groups:
            continue
        groups.sort(
            key=lambda x: (
                x["base_set"].sort_order
                if x["base_set"].sort_order is not None
                else 9999,
                year_list_display_name(x["base_set"]).lower(),
            ),
        )
        sections.append({"key": key, "label": label, "groups": groups})
    return sections


def _completion_card_filter():
    """Cards count only when both card and set are marked required."""
    return and_(
        Card.counts_toward_completion == True,
        CardSet.counts_toward_completion == True,
    )


def _owned_completion_card_filter():
    return and_(
        Card.owned == True,
        Card.counts_toward_completion == True,
        CardSet.counts_toward_completion == True,
    )


@app.on_event("startup")
def startup():
    init_db()


def _search_like_pattern(q: str) -> str:
    """Build a LIKE pattern; strip wildcards from user input to avoid accidental full scans."""
    q = (q or "").strip()
    for ch in ("%", "_"):
        q = q.replace(ch, "")
    return f"%{q}%" if q else ""


def _search_cards(
    db: Session,
    q: str,
    *,
    limit: int,
) -> list[tuple[Card, CardSet]]:
    """Return (Card, CardSet) rows matching player, number, variant, set name, or exact 4-digit year."""
    raw = (q or "").strip()
    if len(raw) < 2:
        return []

    pat = _search_like_pattern(raw)
    clauses = [
        Card.player_name.ilike(pat),
        Card.number.ilike(pat),
        Card.variant.ilike(pat),
        CardSet.full_name.ilike(pat),
        CardSet.base_name.ilike(pat),
    ]
    if raw.isdigit() and len(raw) == 4:
        y = int(raw)
        if 1800 <= y <= 2100:
            clauses.append(CardSet.year == y)

    rows = (
        db.query(Card, CardSet)
        .join(CardSet, Card.set_id == CardSet.id)
        .filter(or_(*clauses))
        .order_by(CardSet.year.desc(), CardSet.full_name, Card.sort_number, Card.number, Card.variant)
        .limit(limit)
        .all()
    )
    return rows


def _build_need_year_summary(db: Session, *, show_hidden: bool = False) -> list[dict]:
    """Years with at least one missing completion-counting card."""
    filters = [Card.owned == False, _completion_card_filter()]
    if not show_hidden:
        filters.append(CardSet.is_hidden == False)

    rows = (
        db.query(
            CardSet.year,
            func.count(Card.id).label("missing_count"),
        )
        .join(Card, Card.set_id == CardSet.id)
        .filter(*filters)
        .group_by(CardSet.year)
        .order_by(CardSet.year.desc())
        .all()
    )
    return [
        {"year": row.year, "missing_count": row.missing_count}
        for row in rows
        if row.missing_count
    ]


def _build_need_groups(
    db: Session,
    *,
    year_from: int,
    year_to: int,
    category: str | None = None,
    q: str = "",
    show_hidden: bool = False,
) -> tuple[list[dict], int]:
    """Missing cards grouped by set for a year range."""
    if year_from > year_to:
        year_from, year_to = year_to, year_from

    filters = [
        Card.owned == False,
        _completion_card_filter(),
        CardSet.year >= year_from,
        CardSet.year <= year_to,
    ]
    if not show_hidden:
        filters.append(CardSet.is_hidden == False)

    q = (q or "").strip()
    if len(q) >= 2:
        pat = _search_like_pattern(q)
        filters.append(
            or_(
                Card.player_name.ilike(pat),
                Card.number.ilike(pat),
                Card.variant.ilike(pat),
                CardSet.full_name.ilike(pat),
            )
        )

    rows = (
        db.query(Card, CardSet)
        .join(CardSet, Card.set_id == CardSet.id)
        .filter(*filters)
        .order_by(
            CardSet.year.desc(),
            CardSet.full_name,
            Card.sort_number,
            Card.number,
            Card.variant,
        )
        .all()
    )

    by_set: dict[int, dict] = {}
    for card, card_set in rows:
        if not show_hidden and set_is_hidden(card_set):
            continue
        if category and effective_year_list_category(card_set) != category:
            continue
        bucket = by_set.get(card_set.id)
        if bucket is None:
            bucket = {"card_set": card_set, "cards": []}
            by_set[card_set.id] = bucket
        bucket["cards"].append(card)

    groups = list(by_set.values())
    groups.sort(key=lambda g: (-g["card_set"].year, g["card_set"].full_name.lower()))
    for group in groups:
        group["missing_count"] = len(group["cards"])

    total = sum(group["missing_count"] for group in groups)
    return groups, total


def _parse_optional_query_int(value: str | None) -> int | None:
    if value is None:
        return None
    value = str(value).strip()
    if not value:
        return None
    return int(value)


def _parse_need_year_filter(
    year: int | None,
    year_from: int | None,
    year_to: int | None,
) -> tuple[int | None, int | None, bool]:
    if year is not None:
        return year, year, True
    if year_from is not None or year_to is not None:
        y_from = year_from if year_from is not None else year_to
        y_to = year_to if year_to is not None else year_from
        return y_from, y_to, True
    return None, None, False


def _build_year_set_groups(db: Session, year: int) -> list[dict]:
    """Build grouped set data for a year with batched queries."""
    all_sets = (
        db.query(CardSet)
        .filter(CardSet.year == year)
        .order_by(CardSet.full_name)
        .all()
    )

    # Group by TCDB product family (base_name), not parent_id — incremental scrapes often
    # leave parent_id null on new variant rows until hierarchy sync runs.
    by_base_name: dict[str, list[CardSet]] = defaultdict(list)
    for s in all_sets:
        by_base_name[s.base_name].append(s)

    set_stats_rows = (
        db.query(
            Card.set_id,
            func.sum(case((_completion_card_filter(), 1), else_=0)).label("total"),
            func.sum(case((_owned_completion_card_filter(), 1), else_=0)).label("owned"),
        )
        .join(CardSet, Card.set_id == CardSet.id)
        .filter(CardSet.year == year)
        .group_by(Card.set_id)
        .all()
    )
    stats_by_set_id = {
        row.set_id: {"total": row.total or 0, "owned": row.owned or 0}
        for row in set_stats_rows
    }

    set_groups = []
    clustered_kinds: dict[str, list[CardSet]] = defaultdict(list)
    standalone_groups: list[tuple[str, list[CardSet]]] = []

    for base_name, members in by_base_name.items():
        kind = cluster_kind_for_base_name(base_name)
        if kind:
            clustered_kinds[kind].extend(members)
        else:
            standalone_groups.append((base_name, members))

    def _append_group(
        bs: CardSet,
        members: list[CardSet],
        *,
        cluster_kind: str | None,
        supplemental_roots: dict[str, CardSet | None] | None,
        supplemental_labels: dict[str, str] | None = None,
    ) -> None:
        children = sorted(
            (s for s in members if s.id != bs.id),
            key=lambda s: (s.full_name or "").lower(),
        )
        base_stats = stats_by_set_id.get(bs.id, {"total": 0, "owned": 0})
        base_total = base_stats["total"]
        base_owned = base_stats["owned"]
        child_data = []
        group_total = base_total
        group_owned = base_owned
        for child in children:
            child_stats = stats_by_set_id.get(child.id, {"total": 0, "owned": 0})
            ct = child_stats["total"]
            co = child_stats["owned"]
            group_total += ct
            group_owned += co
            child_data.append({"set": child, "total": ct, "owned": co})
        set_groups.append({
            "base_set": bs,
            "base_total": base_total,
            "base_owned": base_owned,
            "children": child_data,
            "group_total": group_total,
            "group_owned": group_owned,
            "cluster_kind": cluster_kind,
            "supplemental_roots": supplemental_roots or {},
            "supplemental_labels": supplemental_labels or {},
            "update_base_set": (supplemental_roots or {}).get("update"),
        })

    for kind, members in clustered_kinds.items():
        try:
            bs = pick_cluster_primary_root(members, kind)
        except ValueError:
            continue
        if kind == "topps_now":
            supplemental_roots, supplemental_labels = pick_topps_now_supplemental_roots(members)
        else:
            supplemental_roots = pick_cluster_supplemental_roots(members, kind)
            supplemental_labels = {}
        _append_group(
            bs,
            members,
            cluster_kind=kind,
            supplemental_roots=supplemental_roots,
            supplemental_labels=supplemental_labels,
        )

    for base_name, members in sorted(standalone_groups, key=lambda x: x[0].lower()):
        bs = pick_product_root(members)
        _append_group(bs, members, cluster_kind=None, supplemental_roots=None, supplemental_labels={})

    set_groups.sort(key=lambda g: (g["base_set"].full_name or "").lower())
    return set_groups


def _find_year_group(set_groups: list[dict], base_set_id: int) -> dict | None:
    for group in set_groups:
        if group["base_set"].id == base_set_id:
            return group
        for supplemental in (group.get("supplemental_roots") or {}).values():
            if supplemental and supplemental.id == base_set_id:
                return group
        update_base = group.get("update_base_set")
        if update_base and update_base.id == base_set_id:
            return group
    return None


def _group_stats_by_set_id(db: Session, group: dict) -> dict[int, dict[str, int]]:
    set_ids = {group["base_set"].id, *(c["set"].id for c in group["children"])}
    for supplemental in (group.get("supplemental_roots") or {}).values():
        if supplemental:
            set_ids.add(supplemental.id)
    rows = (
        db.query(
            Card.set_id,
            func.sum(case((_completion_card_filter(), 1), else_=0)).label("total"),
            func.sum(case((_owned_completion_card_filter(), 1), else_=0)).label("owned"),
        )
        .join(CardSet, Card.set_id == CardSet.id)
        .filter(Card.set_id.in_(set_ids))
        .group_by(Card.set_id)
        .all()
    )
    return {row.set_id: {"total": row.total or 0, "owned": row.owned or 0} for row in rows}


def _build_cluster_layout(db: Session, group: dict) -> tuple[dict, list[dict]]:
    """Master + sub-release progress and per-segment checklist sections."""
    stats_by_set_id = _group_stats_by_set_id(db, group)
    all_sets = [group["base_set"], *(c["set"] for c in group["children"])]
    members_by_id = {s.id: s for s in all_sets}
    all_ids = set(members_by_id.keys())

    supplemental_roots = group.get("supplemental_roots") or {}
    if not supplemental_roots and group.get("update_base_set"):
        supplemental_roots = {"update": group["update_base_set"]}
    supplemental_labels = group.get("supplemental_labels") or {}
    supplemental_base_names = supplemental_base_names_from_roots(supplemental_roots)
    supplemental_base_name_values = set(supplemental_base_names.values())
    cluster_kind = group.get("cluster_kind")
    base_set_id = group["base_set"].id

    prospect_set_ids: set[int] | None = None
    if cluster_kind == "bowman_paper":
        prospect_set_ids = identify_bowman_prospect_set_ids(db, all_sets)

    flagship_members = [s for s in all_sets if s.base_name not in supplemental_base_name_values]
    split_series_two = detect_series_two_split(flagship_members) if cluster_kind != "bowman_paper" else False
    segment_keys = build_segment_keys(
        supplemental_base_names,
        split_series_two=split_series_two,
        cluster_kind=cluster_kind,
        supplemental_labels=supplemental_labels,
    )

    sub_bars: list[dict] = []
    cluster_flagship_labels = {
        "fleer_paper": "Fleer",
        "fleer_tradition": "Fleer Tradition",
        "score_paper": "Score",
        "donruss_paper": "Donruss",
        "upper_deck_paper": "Upper Deck",
        "ultra_paper": "Ultra",
        "select_paper": "Select",
    }
    for key in segment_keys:
        seg_ids = sets_in_segment(
            all_ids,
            members_by_id,
            stats_by_set_id,
            supplemental_base_names=supplemental_base_names,
            split_series_two=split_series_two,
            segment_key=key,
            cluster_kind=cluster_kind,
            prospect_set_ids=prospect_set_ids,
            base_set_id=base_set_id,
        )
        prog = progress_from_sets(seg_ids, stats_by_set_id)
        label = supplemental_labels.get(key) or segment_label(key)
        if cluster_kind == "topps_now" and key == "flagship":
            label = "Topps NOW"
        if cluster_kind == "topps_big_league" and key == "flagship":
            label = "Big League"
        if key == "flagship" and cluster_kind in cluster_flagship_labels:
            label = cluster_flagship_labels[cluster_kind]
        sub_bars.append({
            "key": key,
            "label": label,
            **prog,
        })

    cluster_progress = {
        "owned": sum(b["owned"] for b in sub_bars),
        "total": sum(b["total"] for b in sub_bars),
        "sub_bars": sub_bars,
    }

    segment_blocks: list[dict] = []
    flagship_base = group["base_set"]
    for bar in sub_bars:
        key = bar["key"]
        supplemental_root = supplemental_roots.get(key)
        if supplemental_root:
            seg_base = supplemental_root
            show_base = True
        elif key in ("series_1", "flagship", "veterans"):
            seg_base = flagship_base
            show_base = True
        elif key == "prospects":
            seg_base = flagship_base
            show_base = False
        else:
            seg_base = flagship_base
            show_base = False

        seg_children = [
            c for c in group["children"]
            if segment_for_set(
                c["set"],
                supplemental_base_names=supplemental_base_names,
                split_series_two=split_series_two,
                cluster_kind=cluster_kind,
                prospect_set_ids=prospect_set_ids,
                members_by_id=members_by_id,
                base_set_id=base_set_id,
            ) == key
            and not (show_base and c["set"].id == seg_base.id)
        ]
        seg_group = {"base_set": seg_base, "children": seg_children}
        section_data = _build_group_sections(db, seg_group)
        base_stats = stats_by_set_id.get(seg_base.id, {"total": 0, "owned": 0}) if show_base else {"total": 0, "owned": 0}
        breakdown = _build_progress_breakdown(
            section_data,
            stats_by_set_id,
            show_base=show_base,
            base_set_id=seg_base.id if show_base else None,
        )
        bar["breakdown"] = breakdown
        segment_blocks.append({
            "key": key,
            "label": bar["label"],
            "owned": bar["owned"],
            "total": bar["total"],
            "show_base": show_base,
            "base_set": seg_base if show_base else None,
            "base_owned": base_stats["owned"],
            "base_total": base_stats["total"],
            "section_data": section_data,
            "breakdown": breakdown,
        })

    return cluster_progress, segment_blocks


def _ui_bucket_for_parallel_child(
    child_set: CardSet,
    base_set: CardSet,
    set_by_id: dict[int, CardSet],
    section_by_parent_id: dict[int, dict],
) -> tuple[str, int | None]:
    """
    Year-group UI only keys ``section_by_parent_id`` off *top-level* rows (insert / base / etc.),
    not other parallels. Nested parallels (parallel of a parallel) must walk
    ``canonical_parent_set_id`` until we hit a top-level insert section or the paper base.
    """
    pid = child_set.canonical_parent_set_id
    seen: set[int] = set()
    while pid is not None and pid not in seen:
        seen.add(pid)
        if pid == base_set.id:
            return "base", None
        if pid in section_by_parent_id:
            return "section", pid
        parent = set_by_id.get(pid)
        if parent is None:
            break
        pid = parent.canonical_parent_set_id
    return "base", None


def _build_group_sections(db: Session, group: dict) -> dict:
    """Group children using explicit canonical parent links when available."""
    children = group["children"]
    base_set = group["base_set"]
    set_by_id: dict[int, CardSet] = {base_set.id: base_set}
    for ch in children:
        set_by_id[ch["set"].id] = ch["set"]

    parallel_children = [
        c for c in children
        if (c["set"].relationship_type or c["set"].set_type) == "parallel"
    ]
    top_level_children = [
        c for c in children
        if (c["set"].relationship_type or c["set"].set_type) != "parallel"
    ]
    top_level_sections = [{"parent": c, "parallels": []} for c in top_level_children]
    section_by_parent_id = {s["parent"]["set"].id: s for s in top_level_sections}
    base_parallels: list[dict] = []

    has_explicit_mapping = any(c["set"].canonical_parent_set_id for c in parallel_children)
    if has_explicit_mapping:
        for child in parallel_children:
            bucket, sid = _ui_bucket_for_parallel_child(
                child["set"], base_set, set_by_id, section_by_parent_id
            )
            if bucket == "section" and sid is not None:
                section_by_parent_id[sid]["parallels"].append(child)
            else:
                base_parallels.append(child)
    else:
        # Fallback to checklist-overlap-based grouping for unmigrated data.
        def normalize_card_key(number: str | None, player_name: str | None) -> tuple[str, str]:
            num = (number or "").strip().upper()
            player = re.sub(r"\s+", " ", (player_name or "").strip().upper())
            return (num, player)

        set_ids = list(set_by_id.keys())
        card_rows = (
            db.query(Card.set_id, Card.number, Card.player_name)
            .filter(Card.set_id.in_(set_ids))
            .all()
        )
        checklist_by_set_id: dict[int, list[tuple[str, str]]] = defaultdict(list)
        for row in card_rows:
            checklist_by_set_id[row.set_id].append(normalize_card_key(row.number, row.player_name))

        signatures: dict[int, set[tuple[str, str]]] = {
            sid: set(checklist_by_set_id.get(sid, [])) for sid in set_ids
        }
        for child in parallel_children:
            child_sig = signatures.get(child["set"].id, set())
            best_parent_id = None
            best_score = 0.0
            for parent in [base_set] + [s["parent"]["set"] for s in top_level_sections]:
                parent_sig = signatures.get(parent.id, set())
                if not child_sig or not parent_sig:
                    continue
                overlap = len(child_sig & parent_sig)
                score = overlap / len(child_sig)
                if score > best_score:
                    best_score = score
                    best_parent_id = parent.id

            if best_parent_id in section_by_parent_id and best_score >= 0.9:
                section_by_parent_id[best_parent_id]["parallels"].append(child)
            else:
                base_parallels.append(child)

    base_parallels = sorted(base_parallels, key=lambda c: c["set"].full_name)
    top_level_sections = sorted(top_level_sections, key=lambda s: s["parent"]["set"].full_name)
    for section in top_level_sections:
        section["parallels"] = sorted(section["parallels"], key=lambda c: c["set"].full_name)

    raw = {"base_parallels": base_parallels, "sections": top_level_sections}
    serial_by_set_id = serial_denominators_from_card_tags(db, parallel_set_ids_in_section_data(raw))
    return attach_parallel_partitions(raw, serial_by_set_id)


_INSERT_AUTO_NAME = re.compile(r"autograph", re.I)
_INSERT_RELIC_NAME = re.compile(r"relic|memorabilia|patch|jersey|material", re.I)


def _insert_hit_bucket(full_name: str) -> str:
    """Bucket insert families for optional typed progress rows."""
    is_auto = bool(_INSERT_AUTO_NAME.search(full_name or ""))
    is_relic = bool(_INSERT_RELIC_NAME.search(full_name or ""))
    if is_auto and is_relic:
        return "relic_auto"
    if is_auto:
        return "autograph"
    if is_relic:
        return "relic"
    return "other"


def _progress_pair_row(
    left_label: str,
    left_ids: list[int],
    right_label: str,
    right_ids: list[int],
    stats_by_set_id: dict[int, dict[str, int]],
) -> dict | None:
    left = progress_from_sets(left_ids, stats_by_set_id)
    right = progress_from_sets(right_ids, stats_by_set_id)
    if left["total"] == 0 and right["total"] == 0:
        return None
    return {
        "left_label": left_label,
        "left": left,
        "right_label": right_label,
        "right": right,
    }


def _build_progress_breakdown(
    section_data: dict,
    stats_by_set_id: dict[int, dict[str, int]],
    *,
    show_base: bool,
    base_set_id: int | None,
) -> dict:
    """Paired progress rows for base/insert checklists vs their parallels."""
    base_ids = [base_set_id] if show_base and base_set_id else []
    base_par_ids = [c["set"].id for c in section_data.get("base_parallels", [])]

    insert_ids: list[int] = []
    insert_par_ids: list[int] = []
    typed_ids: dict[str, tuple[list[int], list[int]]] = {
        "autograph": ([], []),
        "relic": ([], []),
        "relic_auto": ([], []),
        "other": ([], []),
    }
    for section in section_data.get("sections", []):
        parent_id = section["parent"]["set"].id
        parallel_ids = [child["set"].id for child in section.get("parallels", [])]
        insert_ids.append(parent_id)
        insert_par_ids.extend(parallel_ids)
        bucket = _insert_hit_bucket(section["parent"]["set"].full_name or "")
        typed_ids[bucket][0].append(parent_id)
        typed_ids[bucket][1].extend(parallel_ids)

    summary_pairs = [
        row
        for row in [
            _progress_pair_row(
                "Base cards",
                base_ids,
                "Base parallels",
                base_par_ids,
                stats_by_set_id,
            ),
            _progress_pair_row(
                "Inserts",
                insert_ids,
                "Insert parallels",
                insert_par_ids,
                stats_by_set_id,
            ),
        ]
        if row is not None
    ]

    typed_labels = {
        "autograph": ("Autographs", "Autograph parallels"),
        "relic": ("Relics", "Relic parallels"),
        "relic_auto": ("Relic autos", "Relic auto parallels"),
        "other": ("Other inserts", "Other insert parallels"),
    }
    detail_pairs = [
        row
        for key in ("autograph", "relic", "relic_auto", "other")
        for row in [
            _progress_pair_row(
                typed_labels[key][0],
                typed_ids[key][0],
                typed_labels[key][1],
                typed_ids[key][1],
                stats_by_set_id,
            )
        ]
        if row is not None
    ]

    return {
        "summary_pairs": summary_pairs,
        "detail_pairs": detail_pairs,
        "has_content": bool(summary_pairs or detail_pairs),
    }


def _normalize_section_data(section_data: dict | None, db: Session | None = None) -> dict | None:
    """Ensure numbered/unnumbered parallel keys exist (templates require them)."""
    if section_data is None:
        return None
    if "base_parallels_partitioned" in section_data:
        return section_data
    serial_by_set_id = (
        serial_denominators_from_card_tags(db, parallel_set_ids_in_section_data(section_data))
        if db is not None
        else {}
    )
    return attach_parallel_partitions(section_data, serial_by_set_id)


@app.get("/partials/search", response_class=HTMLResponse)
def search_dropdown(request: Request, q: str = "", db: Session = Depends(get_db)):
    """HTMX fragment: quick search results for the nav dropdown."""
    q = (q or "").strip()
    results: list[tuple[Card, CardSet]] = []
    if len(q) >= 2:
        results = _search_cards(db, q, limit=12)
    search_url = f"/search?{urlencode({'q': q})}" if q else "/search"
    return templates.TemplateResponse("components/search_dropdown.html", {
        "request": request,
        "query": q,
        "results": results,
        "search_url": search_url,
    })


@app.get("/search", response_class=HTMLResponse)
def search_page(request: Request, q: str = "", db: Session = Depends(get_db)):
    """Full search results page (linked from the nav dropdown)."""
    q = (q or "").strip()
    results: list[tuple[Card, CardSet]] = []
    if len(q) >= 2:
        results = _search_cards(db, q, limit=200)
    return templates.TemplateResponse("search.html", {
        "request": request,
        "query": q,
        "results": results,
    })


@app.get("/need", response_class=HTMLResponse)
def need_list(
    request: Request,
    category: str | None = None,
    q: str = "",
    show_hidden: bool = False,
    db: Session = Depends(get_db),
):
    """Cross-set view of unowned cards, grouped by set (card-show friendly)."""
    params = request.query_params
    year = _parse_optional_query_int(params.get("year"))
    year_from = _parse_optional_query_int(params.get("year_from"))
    year_to = _parse_optional_query_int(params.get("year_to"))

    q = (q or "").strip()
    if category and category not in CATEGORY_LABEL_BY_KEY:
        category = None

    year_summary = _build_need_year_summary(db, show_hidden=show_hidden)
    y_from, y_to, has_year_filter = _parse_need_year_filter(year, year_from, year_to)

    need_groups: list[dict] = []
    total_missing = 0
    if has_year_filter and y_from is not None and y_to is not None:
        need_groups, total_missing = _build_need_groups(
            db,
            year_from=y_from,
            year_to=y_to,
            category=category,
            q=q,
            show_hidden=show_hidden,
        )

    return templates.TemplateResponse("need.html", {
        "request": request,
        "year_summary": year_summary,
        "need_groups": need_groups,
        "total_missing": total_missing,
        "has_year_filter": has_year_filter,
        "year": year,
        "year_from": y_from,
        "year_to": y_to,
        "category": category,
        "query": q,
        "show_hidden": show_hidden,
        "categories": YEAR_LIST_CATEGORIES,
        "category_labels": CATEGORY_LABEL_BY_KEY,
    })


@app.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    """Home page showing available years with card counts."""
    year_stats = (
        db.query(
            CardSet.year,
            func.count(distinct(CardSet.id)).label("set_count"),
            func.count(Card.id).label("card_count"),
            func.sum(case((Card.owned == True, 1), else_=0)).label("owned_count"),
        )
        .join(Card, Card.set_id == CardSet.id)
        .group_by(CardSet.year)
        .order_by(CardSet.year.desc())
        .all()
    )

    years = []
    for row in year_stats:
        years.append({
            "year": row.year,
            "set_count": row.set_count,
            "card_count": row.card_count,
            "owned_count": row.owned_count or 0,
        })

    return templates.TemplateResponse("index.html", {"request": request, "years": years})


@app.get("/year/{year}", response_class=HTMLResponse)
def year_view(
    request: Request,
    year: int,
    show_hidden: bool = False,
    db: Session = Depends(get_db),
):
    """Show grouped sets for a year (one row per set group)."""
    set_groups = _build_year_set_groups(db, year)
    hidden_count = sum(1 for g in set_groups if set_is_hidden(g["base_set"]))
    visible_groups = [
        g for g in set_groups
        if show_hidden or not set_is_hidden(g["base_set"])
    ]
    year_sections = _organize_year_list_sections(visible_groups)
    year_owned = sum(g["group_owned"] for g in visible_groups)
    year_total = sum(g["group_total"] for g in visible_groups)

    return templates.TemplateResponse("year.html", {
        "request": request,
        "year": year,
        "set_groups": visible_groups,
        "year_sections": year_sections,
        "show_hidden": show_hidden,
        "hidden_count": hidden_count,
        "year_owned": year_owned,
        "year_total": year_total,
    })


@app.get("/year/{year}/group/{base_set_id}", response_class=HTMLResponse)
def year_group_view_redirect(year: int, base_set_id: int, db: Session = Depends(get_db)):
    """Redirect legacy year group URL to slugged canonical URL."""
    set_groups = _build_year_set_groups(db, year)
    group = _find_year_group(set_groups, base_set_id)
    if group is None:
        return HTMLResponse("Set group not found", status_code=404)
    canonical_id = group["base_set"].id
    return RedirectResponse(
        url=f"/year/{year}/group/{canonical_id}/{group['base_set'].url_slug}",
        status_code=307,
    )


@app.get("/year/{year}/group/{base_set_id}/{group_slug}", response_class=HTMLResponse)
def year_group_view(
    request: Request,
    year: int,
    base_set_id: int,
    group_slug: str,
    db: Session = Depends(get_db),
):
    """Show one set group page (base set + variants) for a year."""
    set_groups = _build_year_set_groups(db, year)
    group = _find_year_group(set_groups, base_set_id)
    if group is None:
        return HTMLResponse("Set group not found", status_code=404)

    canonical_slug = group["base_set"].url_slug
    canonical_id = group["base_set"].id
    if base_set_id != canonical_id or group_slug != canonical_slug:
        return RedirectResponse(
            url=f"/year/{year}/group/{canonical_id}/{canonical_slug}",
            status_code=307,
        )
    if not group["children"]:
        return RedirectResponse(
            url=f"/set/{group['base_set'].id}/{group['base_set'].url_slug}",
            status_code=307,
        )

    cluster_progress = None
    segment_blocks = None
    section_data = None
    progress_breakdown = None
    if group.get("cluster_kind"):
        cluster_progress, segment_blocks = _build_cluster_layout(db, group)
        segment_blocks = [
            {**block, "section_data": _normalize_section_data(block["section_data"], db)}
            for block in segment_blocks
        ]
    else:
        section_data = _normalize_section_data(_build_group_sections(db, group), db)
        progress_breakdown = _build_progress_breakdown(
            section_data,
            _group_stats_by_set_id(db, group),
            show_base=True,
            base_set_id=group["base_set"].id,
        )

    return templates.TemplateResponse("year_group.html", {
        "request": request,
        "year": year,
        "group": group,
        "section_data": section_data,
        "cluster_progress": cluster_progress,
        "segment_blocks": segment_blocks,
        "progress_breakdown": progress_breakdown,
    })


@app.get("/set/{set_id}", response_class=HTMLResponse)
def set_view_redirect(set_id: int, db: Session = Depends(get_db)):
    """Redirect legacy set URL to slugged canonical URL."""
    card_set = db.query(CardSet).filter_by(id=set_id).first()
    if not card_set:
        return HTMLResponse("Set not found", status_code=404)
    return RedirectResponse(url=f"/set/{card_set.id}/{card_set.url_slug}", status_code=307)


@app.get("/set/{set_id}/{set_slug}", response_class=HTMLResponse)
def set_view(request: Request, set_id: int, set_slug: str, db: Session = Depends(get_db)):
    """Show all cards in a set."""
    card_set = db.query(CardSet).filter_by(id=set_id).first()
    if not card_set:
        return HTMLResponse("Set not found", status_code=404)

    canonical_slug = card_set.url_slug
    if set_slug != canonical_slug:
        return RedirectResponse(url=f"/set/{card_set.id}/{canonical_slug}", status_code=307)

    cards = (
        db.query(Card)
        .filter(Card.set_id == set_id)
        .order_by(Card.sort_number, Card.number, Card.variant)
        .all()
    )

    parent = card_set.parent if card_set.parent_id else None
    siblings = []
    if parent:
        siblings = (
            db.query(CardSet)
            .filter(CardSet.parent_id == parent.id, CardSet.id != card_set.id)
            .order_by(CardSet.full_name)
            .all()
        )

    total = len(cards)
    owned = sum(1 for c in cards if c.owned)

    return templates.TemplateResponse("set.html", {
        "request": request,
        "card_set": card_set,
        "cards": cards,
        "parent": parent,
        "siblings": siblings,
        "total": total,
        "owned": owned,
    })


@app.post("/api/card/{card_id}/toggle", response_class=HTMLResponse)
def toggle_card(
    request: Request,
    card_id: int,
    context: str = "",
    db: Session = Depends(get_db),
):
    """Toggle owned status of a card. Returns updated card row partial."""
    card = db.query(Card).options(joinedload(Card.card_set)).filter_by(id=card_id).first()
    if not card:
        return HTMLResponse("Card not found", status_code=404)

    card.owned = not card.owned
    if card.owned:
        card.on_the_way = False
    else:
        card.wants_upgrade = False
    db.commit()
    db.refresh(card)

    if context == "need" and card.owned:
        return HTMLResponse(content="")

    return templates.TemplateResponse("components/card_toggle_sync.html", {
        "request": request,
        "card": card,
    })


@app.post("/api/card/{card_id}/toggle-upgrade", response_class=HTMLResponse)
def toggle_card_upgrade(request: Request, card_id: int, db: Session = Depends(get_db)):
    """Toggle condition-upgrade flag (only when card is owned). Returns updated card row."""
    card = db.query(Card).options(joinedload(Card.card_set)).filter_by(id=card_id).first()
    if not card:
        return HTMLResponse("Card not found", status_code=404)

    if not card.owned:
        card.wants_upgrade = False
    else:
        card.wants_upgrade = not card.wants_upgrade
    db.commit()
    db.refresh(card)

    return templates.TemplateResponse("components/card_toggle_sync.html", {
        "request": request,
        "card": card,
    })


@app.post("/api/card/{card_id}/toggle-on-the-way", response_class=HTMLResponse)
def toggle_card_on_the_way(request: Request, card_id: int, db: Session = Depends(get_db)):
    """Toggle purchased/in-transit flag (only when card is not owned)."""
    card = db.query(Card).options(joinedload(Card.card_set)).filter_by(id=card_id).first()
    if not card:
        return HTMLResponse("Card not found", status_code=404)

    if card.owned:
        card.on_the_way = False
    else:
        card.on_the_way = not card.on_the_way
    db.commit()
    db.refresh(card)

    return templates.TemplateResponse("components/card_toggle_sync.html", {
        "request": request,
        "card": card,
    })


def _require_user_photos():
    if not _USER_PHOTOS_ENABLED:
        raise HTTPException(status_code=404, detail="User card photos are disabled")


def _parse_photo_side(side: str) -> str:
    s = (side or "front").strip().lower()
    if s not in ("front", "back"):
        raise HTTPException(status_code=400, detail="side must be 'front' or 'back'")
    return s


def _card_toggle_response(request: Request, card: Card):
    return templates.TemplateResponse("components/card_toggle_sync.html", {
        "request": request,
        "card": card,
    })


@app.post("/api/card/{card_id}/user-photo/upload")
async def upload_user_card_photo(
    request: Request,
    card_id: int,
    file: UploadFile = File(...),
    side: str = Form("front"),
    db: Session = Depends(get_db),
):
    """Stage a photo, auto-detect card edges, return crop preview."""
    _require_user_photos()
    photo_side = _parse_photo_side(side)
    card = (
        db.query(Card)
        .options(joinedload(Card.card_set))
        .filter_by(id=card_id)
        .first()
    )
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")

    content_type = (file.content_type or "").lower()
    if content_type and content_type not in _ALLOWED_USER_PHOTO_TYPES:
        raise HTTPException(status_code=400, detail="Use JPEG, PNG, or WebP")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(data) > _MAX_USER_PHOTO_BYTES:
        raise HTTPException(status_code=400, detail="File too large (max 15 MB)")

    try:
        result = process_upload(
            data, _image_dir, card.card_set.tcdb_sid, card.id, photo_side
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Could not save image: {exc}") from exc

    return {
        "ok": True,
        "side": photo_side,
        "preview_url": f"/card-images/{result.preview_rel}",
        "original_url": f"/card-images/{result.original_rel}",
        "auto_detected": result.auto_detected,
        "crop": result.suggested_crop.as_dict(),
    }


@app.post("/api/card/{card_id}/user-photo/confirm", response_class=HTMLResponse)
def confirm_user_card_photo(
    request: Request,
    card_id: int,
    crop_x: float = Form(...),
    crop_y: float = Form(...),
    crop_width: float = Form(...),
    crop_height: float = Form(...),
    side: str = Form("front"),
    db: Session = Depends(get_db),
):
    """Apply manual crop and save as the card's user photo."""
    _require_user_photos()
    photo_side = _parse_photo_side(side)
    card = (
        db.query(Card)
        .options(joinedload(Card.card_set))
        .filter_by(id=card_id)
        .first()
    )
    if not card:
        return HTMLResponse("Card not found", status_code=404)

    crop = CropBox(
        x=int(round(crop_x)),
        y=int(round(crop_y)),
        width=max(1, int(round(crop_width))),
        height=max(1, int(round(crop_height))),
    )
    try:
        rel_path = apply_crop_from_original(
            _image_dir, card.card_set.tcdb_sid, card.id, crop, photo_side
        )
    except (FileNotFoundError, ValueError) as exc:
        return HTMLResponse(str(exc), status_code=400)
    except OSError as exc:
        return HTMLResponse(f"Could not save image: {exc}", status_code=500)

    if photo_side == "back":
        card.user_image_back_local = rel_path
    else:
        card.user_image_front_local = rel_path
    db.commit()
    db.refresh(card)
    return _card_toggle_response(request, card)


@app.delete("/api/card/{card_id}/user-photo", response_class=HTMLResponse)
def remove_user_card_photo(
    request: Request,
    card_id: int,
    side: str = "front",
    db: Session = Depends(get_db),
):
    """Remove user photo; TCDB scan shows again if present."""
    _require_user_photos()
    photo_side = _parse_photo_side(side)
    card = (
        db.query(Card)
        .options(joinedload(Card.card_set))
        .filter_by(id=card_id)
        .first()
    )
    if not card:
        return HTMLResponse("Card not found", status_code=404)

    delete_user_photo(_image_dir, card.card_set.tcdb_sid, card.id, photo_side)
    if photo_side == "back":
        card.user_image_back_local = None
    else:
        card.user_image_front_local = None
    db.commit()
    db.refresh(card)
    return _card_toggle_response(request, card)


@app.get("/api/stats/{set_id}")
def set_stats(set_id: int, db: Session = Depends(get_db)):
    """Get stats for a set (used for live counter updates)."""
    total = (
        db.query(func.count(Card.id))
        .join(CardSet, Card.set_id == CardSet.id)
        .filter(Card.set_id == set_id, _completion_card_filter())
        .scalar()
        or 0
    )
    owned = (
        db.query(func.sum(case((_owned_completion_card_filter(), 1), else_=0)))
        .join(CardSet, Card.set_id == CardSet.id)
        .filter(Card.set_id == set_id)
        .scalar()
        or 0
    )
    return {"total": total, "owned": owned}


def _admin_group_for_set(db: Session, year: int, set_id: int) -> dict | None:
    set_groups = _build_year_set_groups(db, year)
    return _find_year_group(set_groups, set_id)


def _admin_parent_options(db: Session, card_set: CardSet) -> list[CardSet]:
    return (
        db.query(CardSet)
        .filter(
            CardSet.year == card_set.year,
            CardSet.base_name == card_set.base_name,
            CardSet.id != card_set.id,
            CardSet.relationship_type != "parallel",
        )
        .order_by(CardSet.full_name)
        .all()
    )


def _effective_relationship_type(card_set: CardSet) -> str:
    return card_set.relationship_type or card_set.set_type or "standalone"


def _parallel_numbering_label(card_set: CardSet) -> str:
    if card_set.parallel_is_numbered is True:
        if card_set.parallel_numbered_to:
            return f"/{card_set.parallel_numbered_to}"
        return "numbered"
    if card_set.parallel_is_numbered is False:
        return "unnumbered"
    return "unknown"


ADMIN_RELATIONSHIP_TYPES = ("parallel", "insert", "variation", "standalone", "base")


def _relationship_type_sql_filter(rel_type: str):
    """Match effective relationship type (relationship_type with set_type fallback)."""
    return or_(
        CardSet.relationship_type == rel_type,
        and_(CardSet.relationship_type.is_(None), CardSet.set_type == rel_type),
    )


def _admin_set_name_search_filter(q: str):
    pat = _search_like_pattern(q)
    if not pat:
        return None
    return or_(
        CardSet.full_name.ilike(pat),
        CardSet.base_name.ilike(pat),
        CardSet.variant_name.ilike(pat),
        CardSet.display_name_override.ilike(pat),
    )


def _stats_by_set_ids(db: Session, set_ids: list[int]) -> dict[int, dict[str, int]]:
    if not set_ids:
        return {}
    rows = (
        db.query(
            Card.set_id,
            func.count(Card.id).label("total"),
            func.sum(case((Card.owned == True, 1), else_=0)).label("owned"),
        )
        .filter(Card.set_id.in_(set_ids))
        .group_by(Card.set_id)
        .all()
    )
    return {row.set_id: {"total": row.total or 0, "owned": row.owned or 0} for row in rows}


@app.get("/admin", response_class=HTMLResponse)
def admin_index(request: Request, db: Session = Depends(get_db)):
    years = [row[0] for row in db.query(distinct(CardSet.year)).order_by(CardSet.year.desc()).all()]
    return templates.TemplateResponse("admin_index.html", {"request": request, "years": years})


@app.get("/admin/year/{year}", response_class=HTMLResponse)
def admin_year(request: Request, year: int, db: Session = Depends(get_db)):
    set_groups = _build_year_set_groups(db, year)
    rows = []
    for group in sorted(set_groups, key=lambda g: year_list_display_name(g["base_set"]).lower()):
        bs = group["base_set"]
        rows.append({
            "group": group,
            "display_name": year_list_display_name(bs),
            "category_label": effective_year_list_category_label(bs),
            "auto_category_label": auto_year_list_category_label(bs),
            "hidden": set_is_hidden(bs),
        })
    return templates.TemplateResponse("admin_year.html", {
        "request": request,
        "year": year,
        "rows": rows,
    })


@app.get("/admin/year/{year}/sets", response_class=HTMLResponse)
def admin_year_sets(
    request: Request,
    year: int,
    q: str = "",
    rel_type: str = "",
    product: str = "",
    limit: int = 500,
    db: Session = Depends(get_db),
):
    """Browse inserts, parallels, and other child sets for a year with text/type filters."""
    rel_type = (rel_type or "").strip().lower()
    if rel_type and rel_type not in ADMIN_RELATIONSHIP_TYPES:
        rel_type = ""

    query = db.query(CardSet).filter(CardSet.year == year)
    if rel_type:
        query = query.filter(_relationship_type_sql_filter(rel_type))
    else:
        query = query.filter(
            or_(
                _relationship_type_sql_filter("parallel"),
                _relationship_type_sql_filter("insert"),
                _relationship_type_sql_filter("variation"),
                _relationship_type_sql_filter("standalone"),
            )
        )

    product = (product or "").strip()
    if product:
        query = query.filter(CardSet.base_name == product)

    name_filter = _admin_set_name_search_filter(q)
    if name_filter is not None:
        query = query.filter(name_filter)

    limit = max(1, min(limit, 2000))
    sets = query.order_by(CardSet.base_name, CardSet.full_name).limit(limit).all()

    set_ids = [s.id for s in sets]
    stats_by_id = _stats_by_set_ids(db, set_ids)

    parent_ids = {s.canonical_parent_set_id for s in sets if s.canonical_parent_set_id}
    parents_by_id = {}
    if parent_ids:
        parents_by_id = {p.id: p for p in db.query(CardSet).filter(CardSet.id.in_(parent_ids)).all()}

    rows = []
    for s in sets:
        st = stats_by_id.get(s.id, {"total": 0, "owned": 0})
        parent = parents_by_id.get(s.canonical_parent_set_id)
        rows.append({
            "set": s,
            "relationship": _effective_relationship_type(s),
            "parallel_numbering": _parallel_numbering_label(s),
            "owned": st["owned"],
            "total": st["total"],
            "parent": parent,
        })

    return templates.TemplateResponse("admin_year_sets.html", {
        "request": request,
        "year": year,
        "rows": rows,
        "q": (q or "").strip(),
        "rel_type": rel_type,
        "product": product,
        "limit": limit,
        "relationship_types": ADMIN_RELATIONSHIP_TYPES,
    })


@app.get("/admin/year/{year}/set/{set_id}", response_class=HTMLResponse)
def admin_set_view(request: Request, year: int, set_id: int, db: Session = Depends(get_db)):
    card_set = db.query(CardSet).filter_by(id=set_id, year=year).first()
    if not card_set:
        return HTMLResponse("Set not found", status_code=404)

    group = _admin_group_for_set(db, year, set_id)
    product_root = group["base_set"] if group else card_set
    is_product_root = product_root.id == card_set.id
    effective_relationship = _effective_relationship_type(card_set)
    show_year_page_settings = is_product_root and effective_relationship == "base"
    show_relationship_editor = not show_year_page_settings

    tree_rows = []
    if group and show_year_page_settings:
        for child in sorted(group["children"], key=lambda c: (c["set"].full_name or "").lower()):
            cs = child["set"]
            tree_rows.append({
                "set": cs,
                "owned": child["owned"],
                "total": child["total"],
                "relationship": cs.relationship_type or cs.set_type,
            })

    cards = (
        db.query(Card)
        .filter(Card.set_id == card_set.id)
        .order_by(Card.sort_number, Card.number, Card.variant)
        .limit(500)
        .all()
    )
    parent_options = _admin_parent_options(db, card_set) if show_relationship_editor else []

    return templates.TemplateResponse("admin_set.html", {
        "request": request,
        "year": year,
        "card_set": card_set,
        "product_root": product_root,
        "is_product_root": is_product_root,
        "show_year_page_settings": show_year_page_settings,
        "show_relationship_editor": show_relationship_editor,
        "group": group,
        "tree_rows": tree_rows,
        "cards": cards,
        "parent_options": parent_options,
        "categories": YEAR_LIST_CATEGORIES,
        "auto_category_label": auto_year_list_category_label(product_root),
        "effective_category_label": effective_year_list_category_label(product_root),
        "effective_category_key": effective_year_list_category(product_root),
    })


@app.post("/admin/year/{year}/set/{set_id}/update")
def admin_set_update(
    year: int,
    set_id: int,
    db: Session = Depends(get_db),
    # Product root fields
    year_list_category: str = Form(""),
    category_manual: str = Form(""),
    display_name_override: str = Form(""),
    is_hidden: str = Form(""),
    sort_order: str = Form(""),
    # Set-level completion
    counts_toward_completion: str = Form("off"),
    completion_manual: str = Form(""),
    cascade_completion_to_cards: str = Form(""),
    admin_notes: str = Form(""),
    # Relationship fields (insert/parallel)
    relationship_type: str = Form(""),
    parent_id: int = Form(0),
    parallel_numbering: str = Form("unknown"),
    parallel_numbered_to: str = Form(""),
    relationship_manual: str = Form(""),
):
    card_set = db.query(CardSet).filter_by(id=set_id, year=year).first()
    if not card_set:
        return HTMLResponse("Set not found", status_code=404)

    group = _admin_group_for_set(db, year, set_id)
    product_root = group["base_set"] if group else card_set
    is_product_root = product_root.id == card_set.id
    effective_relationship = _effective_relationship_type(card_set)
    show_year_page_settings = is_product_root and effective_relationship == "base"
    show_relationship_editor = not show_year_page_settings

    if show_year_page_settings:
        auto_category = auto_year_list_category(card_set)
        chosen_category = year_list_category.strip() if year_list_category else ""
        wants_manual = (
            category_manual == "on"
            or (chosen_category and chosen_category != auto_category)
        )
        if wants_manual and chosen_category:
            card_set.category_source = "manual"
            card_set.year_list_category = chosen_category
        else:
            card_set.category_source = "auto"
            card_set.year_list_category = None
        card_set.display_name_override = display_name_override.strip() or None
        card_set.is_hidden = is_hidden == "on"
        card_set.sort_order = int(sort_order) if sort_order.strip().isdigit() else None

    card_set.counts_toward_completion = counts_toward_completion == "on"
    if completion_manual == "on":
        card_set.completion_source = "manual"
    else:
        card_set.completion_source = "auto"

    card_set.admin_notes = admin_notes.strip() or None

    if show_relationship_editor and relationship_type:
        card_set.relationship_type = relationship_type
        card_set.canonical_parent_set_id = None if parent_id == 0 else parent_id
        if relationship_type == "parallel":
            if parallel_numbering == "numbered":
                card_set.parallel_is_numbered = True
                card_set.parallel_numbered_to = (
                    int(parallel_numbered_to.strip())
                    if parallel_numbered_to.strip().isdigit()
                    else None
                )
            elif parallel_numbering == "unnumbered":
                card_set.parallel_is_numbered = False
                card_set.parallel_numbered_to = None
            else:
                card_set.parallel_is_numbered = None
                card_set.parallel_numbered_to = None
        else:
            card_set.parallel_is_numbered = None
            card_set.parallel_numbered_to = None
        if relationship_manual == "on":
            card_set.relationship_source = "manual"
            card_set.relationship_confidence = 1.0
        else:
            card_set.relationship_source = "auto"

    if cascade_completion_to_cards == "on":
        db.query(Card).filter(Card.set_id == card_set.id).update(
            {"counts_toward_completion": card_set.counts_toward_completion},
            synchronize_session=False,
        )

    db.commit()
    return RedirectResponse(url=f"/admin/year/{year}/set/{set_id}", status_code=303)


@app.post("/admin/year/{year}/set/{set_id}/card/{card_id}/completion")
def admin_card_completion(
    year: int,
    set_id: int,
    card_id: int,
    required: str = Form("on"),
    db: Session = Depends(get_db),
):
    card = db.query(Card).filter_by(id=card_id, set_id=set_id).first()
    if not card:
        return HTMLResponse("Card not found", status_code=404)
    card.counts_toward_completion = required == "on"
    db.commit()
    return RedirectResponse(url=f"/admin/year/{year}/set/{set_id}#cards", status_code=303)


@app.get("/partials/set/{set_id}/cards", response_class=HTMLResponse)
def set_cards_partial(request: Request, set_id: int, db: Session = Depends(get_db)):
    """Render a card list partial for accordion sections."""
    card_set = db.query(CardSet).filter_by(id=set_id).first()
    if not card_set:
        return HTMLResponse("Set not found", status_code=404)

    cards = (
        db.query(Card)
        .filter(Card.set_id == set_id)
        .order_by(Card.sort_number, Card.number, Card.variant)
        .all()
    )

    return templates.TemplateResponse("components/set_cards_table.html", {
        "request": request,
        "card_set": card_set,
        "cards": cards,
    })


@app.get("/admin/relationships", response_class=HTMLResponse)
def relationships_review(
    request: Request,
    year: int | None = None,
    max_conf: float = 0.85,
    limit: int = 500,
    q: str = "",
    rel_type: str = "",
    db: Session = Depends(get_db),
):
    """Review low-confidence or unresolved set relationships."""
    rel_type = (rel_type or "").strip().lower()
    if rel_type and rel_type not in ADMIN_RELATIONSHIP_TYPES:
        rel_type = ""

    query = db.query(CardSet)
    if year is not None:
        query = query.filter(CardSet.year == year)

    if rel_type:
        query = query.filter(_relationship_type_sql_filter(rel_type))
    else:
        query = query.filter(
            CardSet.relationship_type == "parallel",
            (CardSet.relationship_confidence.is_(None)) | (CardSet.relationship_confidence < max_conf),
        )

    name_filter = _admin_set_name_search_filter(q)
    if name_filter is not None:
        query = query.filter(name_filter)

    limit = max(1, min(limit, 2000))
    rows = query.order_by(CardSet.year.desc(), CardSet.base_name, CardSet.full_name).limit(limit).all()
    reviews = []

    for s in rows:
        parent_options = (
            db.query(CardSet)
            .filter(
                CardSet.year == s.year,
                CardSet.base_name == s.base_name,
                CardSet.id != s.id,
                CardSet.relationship_type != "parallel",
            )
            .order_by(CardSet.full_name)
            .all()
        )
        current_parent = next((p for p in parent_options if p.id == s.canonical_parent_set_id), None)
        reviews.append({
            "set": s,
            "current_parent": current_parent,
            "parent_options": parent_options,
        })

    return templates.TemplateResponse("admin_relationships.html", {
        "request": request,
        "year": year,
        "max_conf": max_conf,
        "limit": limit,
        "reviews": reviews,
        "q": (q or "").strip(),
        "rel_type": rel_type,
        "relationship_types": ADMIN_RELATIONSHIP_TYPES,
    })


@app.post("/admin/relationships/update")
def relationships_update(
    set_id: int = Form(...),
    parent_id: int = Form(...),
    relationship_type: str = Form(...),
    year: int | None = Form(None),
    max_conf: float = Form(0.85),
    limit: int = Form(500),
    q: str = Form(""),
    rel_type: str = Form(""),
    db: Session = Depends(get_db),
):
    """Apply a manual relationship assignment from review UI."""
    card_set = db.query(CardSet).filter_by(id=set_id).first()
    if not card_set:
        return HTMLResponse("Set not found", status_code=404)

    card_set.relationship_type = relationship_type
    card_set.canonical_parent_set_id = None if parent_id == 0 else parent_id
    card_set.relationship_confidence = 1.0
    card_set.relationship_source = "manual"
    db.commit()

    params: dict[str, str | int | float] = {"max_conf": max_conf, "limit": limit}
    if year is not None:
        params["year"] = year
    if q.strip():
        params["q"] = q.strip()
    if rel_type.strip():
        params["rel_type"] = rel_type.strip()
    return RedirectResponse(url=f"/admin/relationships?{urlencode(params)}", status_code=303)
