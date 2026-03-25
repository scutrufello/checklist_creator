import os
from collections import defaultdict
import re

from fastapi import FastAPI, Request, Depends, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, distinct, case
from sqlalchemy.orm import Session

from app.database import get_session, init_db
from app.models import Card, CardSet

app = FastAPI(title="Phillies Cards Checklist")

BASE_DIR = os.path.dirname(__file__)
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")


def get_db():
    db = get_session()
    try:
        yield db
    finally:
        db.close()


@app.on_event("startup")
def startup():
    init_db()


def _build_year_set_groups(db: Session, year: int) -> list[dict]:
    """Build grouped set data for a year with batched queries."""
    all_sets = (
        db.query(CardSet)
        .filter(CardSet.year == year)
        .order_by(CardSet.full_name)
        .all()
    )

    base_sets = [s for s in all_sets if s.parent_id is None]
    children_by_parent_id: dict[int, list[CardSet]] = defaultdict(list)
    for s in all_sets:
        if s.parent_id is not None:
            children_by_parent_id[s.parent_id].append(s)

    set_stats_rows = (
        db.query(
            Card.set_id,
            func.count(Card.id).label("total"),
            func.sum(case((Card.owned == True, 1), else_=0)).label("owned"),
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
    for bs in base_sets:
        children = children_by_parent_id.get(bs.id, [])

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
            child_data.append({
                "set": child,
                "total": ct,
                "owned": co,
            })

        set_groups.append({
            "base_set": bs,
            "base_total": base_total,
            "base_owned": base_owned,
            "children": child_data,
            "group_total": group_total,
            "group_owned": group_owned,
        })

    return set_groups


def _build_group_sections(db: Session, group: dict) -> dict:
    """Group children using explicit canonical parent links when available."""
    children = group["children"]
    base_set = group["base_set"]

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
            parent_id = child["set"].canonical_parent_set_id
            if parent_id in section_by_parent_id:
                section_by_parent_id[parent_id]["parallels"].append(child)
            else:
                # Either directly under base, or unresolved mapping.
                base_parallels.append(child)
    else:
        # Fallback to checklist-overlap-based grouping for unmigrated data.
        def normalize_card_key(number: str | None, player_name: str | None) -> tuple[str, str]:
            num = (number or "").strip().upper()
            player = re.sub(r"\s+", " ", (player_name or "").strip().upper())
            return (num, player)

        set_by_id = {base_set.id: base_set, **{c["set"].id: c["set"] for c in children}}
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

    return {"base_parallels": base_parallels, "sections": top_level_sections}


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
def year_view(request: Request, year: int, db: Session = Depends(get_db)):
    """Show grouped sets for a year (one row per set group)."""
    set_groups = _build_year_set_groups(db, year)

    return templates.TemplateResponse("year.html", {
        "request": request,
        "year": year,
        "set_groups": set_groups,
    })


@app.get("/year/{year}/group/{base_set_id}", response_class=HTMLResponse)
def year_group_view_redirect(year: int, base_set_id: int, db: Session = Depends(get_db)):
    """Redirect legacy year group URL to slugged canonical URL."""
    set_groups = _build_year_set_groups(db, year)
    group = next((g for g in set_groups if g["base_set"].id == base_set_id), None)
    if group is None:
        return HTMLResponse("Set group not found", status_code=404)
    return RedirectResponse(
        url=f"/year/{year}/group/{base_set_id}/{group['base_set'].url_slug}",
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
    group = next((g for g in set_groups if g["base_set"].id == base_set_id), None)
    if group is None:
        return HTMLResponse("Set group not found", status_code=404)

    canonical_slug = group["base_set"].url_slug
    if group_slug != canonical_slug:
        return RedirectResponse(
            url=f"/year/{year}/group/{base_set_id}/{canonical_slug}",
            status_code=307,
        )
    if not group["children"]:
        return RedirectResponse(
            url=f"/set/{group['base_set'].id}/{group['base_set'].url_slug}",
            status_code=307,
        )
    section_data = _build_group_sections(db, group)

    return templates.TemplateResponse("year_group.html", {
        "request": request,
        "year": year,
        "group": group,
        "section_data": section_data,
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
def toggle_card(request: Request, card_id: int, db: Session = Depends(get_db)):
    """Toggle owned status of a card. Returns updated card row partial."""
    card = db.query(Card).filter_by(id=card_id).first()
    if not card:
        return HTMLResponse("Card not found", status_code=404)

    card.owned = not card.owned
    db.commit()
    db.refresh(card)

    return templates.TemplateResponse("components/card_row.html", {
        "request": request,
        "card": card,
    })


@app.get("/api/stats/{set_id}", response_class=JSONResponse)
def set_stats(set_id: int, db: Session = Depends(get_db)):
    """Get stats for a set (used for live counter updates)."""
    total = db.query(func.count(Card.id)).filter(Card.set_id == set_id).scalar() or 0
    owned = db.query(func.sum(case((Card.owned == True, 1), else_=0))).filter(Card.set_id == set_id).scalar() or 0
    return {"total": total, "owned": owned}


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
    db: Session = Depends(get_db),
):
    """Review low-confidence or unresolved set relationships."""
    query = db.query(CardSet).filter(
        CardSet.relationship_type == "parallel",
        (CardSet.relationship_confidence.is_(None)) | (CardSet.relationship_confidence < max_conf),
    )
    if year is not None:
        query = query.filter(CardSet.year == year)

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
    })


@app.post("/admin/relationships/update")
def relationships_update(
    set_id: int = Form(...),
    parent_id: int = Form(...),
    relationship_type: str = Form(...),
    year: int | None = Form(None),
    max_conf: float = Form(0.85),
    limit: int = Form(500),
    db: Session = Depends(get_db),
):
    """Apply a manual relationship assignment from review UI."""
    card_set = db.query(CardSet).filter_by(id=set_id).first()
    if not card_set:
        return HTMLResponse("Set not found", status_code=404)

    card_set.relationship_type = relationship_type
    card_set.canonical_parent_set_id = None if parent_id == 0 else parent_id
    card_set.relationship_confidence = 1.0
    db.commit()

    target = f"/admin/relationships?max_conf={max_conf}&limit={limit}"
    if year is not None:
        target += f"&year={year}"
    return RedirectResponse(url=target, status_code=303)
