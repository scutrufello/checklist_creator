"""Helpers for TCDB image URL scan state on Card rows."""
from __future__ import annotations

from datetime import datetime, timezone

from scraper.viewcard_parser import ParsedCardImages

# Stored in cards.image_scan_status (NULL = never classified via ViewCard).
SCAN_NONE = "none"
SCAN_PARTIAL = "partial"
SCAN_FULL = "full"


def scan_status_from_urls(front_url: str | None, back_url: str | None) -> str:
    if front_url and back_url:
        return SCAN_FULL
    if front_url or back_url:
        return SCAN_PARTIAL
    return SCAN_NONE


def scan_status_from_parsed(parsed: ParsedCardImages) -> str:
    if not parsed.has_card_scan:
        return SCAN_NONE
    return scan_status_from_urls(parsed.front_url, parsed.back_url)


def record_image_url_check(
    card,
    parsed: ParsedCardImages | None,
    *,
    checked_at: datetime | None = None,
) -> None:
    """Persist ViewCard check time and scan classification on a Card."""
    ts = checked_at or datetime.now(timezone.utc)
    card.image_url_checked_at = ts.isoformat()
    if parsed is None:
        return
    # Classify from merged card URLs (apply may keep an existing side).
    card.image_scan_status = scan_status_from_urls(
        card.image_front_url, card.image_back_url
    )


def infer_scan_status_from_stored_urls(card) -> str | None:
    """Derive status from image_*_url columns when metadata was never written."""
    if card.image_front_url or card.image_back_url:
        return scan_status_from_urls(card.image_front_url, card.image_back_url)
    return None
