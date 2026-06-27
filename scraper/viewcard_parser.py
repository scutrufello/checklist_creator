"""Parse TCDB ViewCard pages for card scan URLs."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

TCDB_ORIGIN = "https://www.tcdb.com"

_CARD_FRONT_ALT = re.compile(r"\bfront$", re.I)
_CARD_BACK_ALT = re.compile(r"\bback$", re.I)
_PLACEHOLDER_SRC = re.compile(r"default(?:front|back)\.gif", re.I)


@dataclass
class ParsedCardImages:
    """Image URLs extracted from a TCDB ViewCard page (Cards/ size only)."""

    front_url: str | None = None
    back_url: str | None = None
    sample_url: str | None = None

    @property
    def has_card_scan(self) -> bool:
        return bool(self.front_url or self.back_url)

    @property
    def display_front_url(self) -> str | None:
        return self.front_url


def absolutize_tcdb_path(path: str | None) -> str | None:
    if not path:
        return None
    path = path.strip()
    if not path:
        return None
    if path.startswith("http://") or path.startswith("https://"):
        return path
    if not path.startswith("/"):
        path = "/" + path
    return TCDB_ORIGIN + path


def is_card_scan_path(path: str | None) -> bool:
    """True for real card scans under /Images/Cards/ (not TCDB placeholder GIFs)."""
    if not path:
        return False
    if _PLACEHOLDER_SRC.search(path):
        return False
    return "/Images/Cards/" in path.replace("\\", "/")


def parse_viewcard_images(html: str) -> ParsedCardImages:
    """
    Extract front/back/sample image URLs from a TCDB ViewCard HTML page.

    Uses /Images/Cards/ thumbnails only (not /Images/Large/). TCDB file naming
    varies by era (card number vs cid, Rep prefix), so we read ``<img>`` alt text
    rather than constructing paths.
    """
    soup = BeautifulSoup(html, "html.parser")
    result = ParsedCardImages()

    for img in soup.find_all("img"):
        src = (img.get("src") or img.get("data-src") or "").strip()
        if not src or "Images/" not in src:
            continue
        lower = src.lower()
        if "samplecards" in lower:
            result.sample_url = absolutize_tcdb_path(src)
            continue
        if not is_card_scan_path(src):
            continue
        alt = (img.get("alt") or "").strip()
        if _CARD_FRONT_ALT.search(alt):
            result.front_url = absolutize_tcdb_path(src)
        elif _CARD_BACK_ALT.search(alt):
            result.back_url = absolutize_tcdb_path(src)

    return result
