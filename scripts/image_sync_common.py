"""Shared helpers for recurring image URL and download sync scripts."""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, case, or_

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.image_scan_status import SCAN_NONE, SCAN_PARTIAL  # noqa: E402
from app.models import Card, CardSet  # noqa: E402

logger = logging.getLogger(__name__)

_ONE_SIDED_URL = or_(
    and_(Card.image_front_url.isnot(None), Card.image_back_url.is_(None)),
    and_(Card.image_front_url.is_(None), Card.image_back_url.isnot(None)),
)


def _url_sync_cutoff(recheck_days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=recheck_days)).isoformat()


def url_sync_due_filter(recheck_days: int):
    """Cards that should be re-fetched on ViewCard for image URL discovery."""
    cutoff = _url_sync_cutoff(recheck_days)
    return and_(
        Card.tcdb_url.isnot(None),
        Card.tcdb_url != "",
        or_(
            Card.image_url_checked_at.is_(None),
            and_(
                Card.image_scan_status == SCAN_NONE,
                Card.image_front_url.is_(None),
                Card.image_back_url.is_(None),
                Card.image_url_checked_at < cutoff,
            ),
            and_(
                Card.image_scan_status == SCAN_PARTIAL,
                Card.image_url_checked_at < cutoff,
            ),
            and_(
                _ONE_SIDED_URL,
                Card.image_url_checked_at < cutoff,
            ),
        ),
    )


def setup_sync_logging(log_file: str | None, default_name: str) -> None:
    path = log_file or os.path.join("data", default_name)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.FileHandler(path, encoding="utf-8"), logging.StreamHandler(sys.stdout)],
        force=True,
    )


def load_cursor(path: str) -> dict:
    if not os.path.isfile(path):
        return {"last_card_id": 0}
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    data.setdefault("last_card_id", 0)
    return data


def save_cursor(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    os.replace(tmp, path)


def cards_needing_url_sync(session, *, limit: int, after_id: int, recheck_days: int) -> list[tuple[Card, CardSet]]:
    """
    Cards due for a ViewCard fetch to discover image URLs.

    Includes never-checked rows, confirmed-no-scan rows older than recheck_days,
    and partial / one-sided scans (TCDB may add the missing side later).
    """
    q = (
        session.query(Card, CardSet)
        .join(CardSet, Card.set_id == CardSet.id)
        .filter(Card.id > after_id, url_sync_due_filter(recheck_days))
        .order_by(
            case((Card.image_url_checked_at.is_(None), 0), else_=1),
            case((Card.image_scan_status == SCAN_PARTIAL, 0), else_=1),
            Card.image_url_checked_at.asc(),
            Card.id.asc(),
        )
        .limit(limit)
    )
    return q.all()


def count_cards_needing_url_sync(session, *, recheck_days: int) -> int:
    return session.query(Card.id).filter(url_sync_due_filter(recheck_days)).count()


def cards_needing_download(session, *, limit: int, after_id: int) -> list[tuple[Card, CardSet]]:
    """Cards with remote image URLs but missing local cache files."""
    q = (
        session.query(Card, CardSet)
        .join(CardSet, Card.set_id == CardSet.id)
        .filter(
            Card.id > after_id,
            Card.tcdb_url.isnot(None),
            Card.tcdb_url != "",
            or_(
                and_(Card.image_front_url.isnot(None), Card.image_front_local.is_(None)),
                and_(Card.image_back_url.isnot(None), Card.image_back_local.is_(None)),
            ),
        )
        .order_by(Card.id.asc())
        .limit(limit)
    )
    return q.all()


def count_cards_needing_download(session) -> int:
    return (
        session.query(Card.id)
        .filter(
            Card.tcdb_url.isnot(None),
            Card.tcdb_url != "",
            or_(
                and_(Card.image_front_url.isnot(None), Card.image_front_local.is_(None)),
                and_(Card.image_back_url.isnot(None), Card.image_back_local.is_(None)),
            ),
        )
        .count()
    )
