"""Fetch TCDB ViewCard scans and optionally cache them locally."""
from __future__ import annotations

import logging
import os
import random
import time
from urllib.parse import urlparse

import cloudscraper

from app.models import Card
from app.image_scan_status import record_image_url_check
from scraper.viewcard_parser import ParsedCardImages, parse_viewcard_images

logger = logging.getLogger(__name__)


def fetch_viewcard_html(
    scraper,
    url: str,
    *,
    timeout: int = 90,
    retries: int = 4,
    vpn=None,
) -> str | None:
    """Fetch a ViewCard page with retries, Cloudflare detection, and optional VPN rotate."""
    last_status = None
    for attempt in range(retries):
        try:
            resp = scraper.get(url, timeout=timeout)
            last_status = resp.status_code
        except Exception as exc:
            logger.warning(
                "ViewCard fetch error (attempt %d/%d) %s: %s",
                attempt + 1,
                retries,
                url,
                exc,
            )
            if attempt < retries - 1:
                _backoff_sleep(attempt, vpn=vpn, reason="fetch error")
            continue

        if resp.status_code == 200:
            content = resp.text
            is_challenge = (
                ("Just a moment" in content or "Checking your browser" in content)
                and "ViewCard.cfm" not in content
            )
            if is_challenge:
                logger.warning(
                    "Cloudflare challenge on ViewCard (attempt %d/%d) %s",
                    attempt + 1,
                    retries,
                    url,
                )
                if attempt < retries - 1:
                    _backoff_sleep(attempt, vpn=vpn, reason="cloudflare")
                continue
            if len(content) < 2500 and "ViewCard.cfm" not in content:
                logger.warning(
                    "Suspicious short ViewCard HTML (%d bytes) attempt %d/%d %s",
                    len(content),
                    attempt + 1,
                    retries,
                    url,
                )
                if attempt < retries - 1:
                    _backoff_sleep(attempt, vpn=vpn, reason="short html")
                continue
            return content

        if resp.status_code in (403, 429, 502, 503):
            hint = {403: "forbidden", 429: "rate limit", 502: "bad gateway", 503: "unavailable"}.get(
                resp.status_code, "error"
            )
            logger.warning(
                "ViewCard HTTP %s (%s) attempt %d/%d %s",
                resp.status_code,
                hint,
                attempt + 1,
                retries,
                url,
            )
            if attempt < retries - 1:
                _backoff_sleep(attempt, vpn=vpn, reason=hint)
            continue

        logger.error("ViewCard HTTP %s for %s", resp.status_code, url)
        return None

    logger.error("ViewCard fetch gave up (last HTTP %s) %s", last_status, url)
    return None


def _backoff_sleep(attempt: int, *, vpn=None, reason: str = "") -> None:
    wait = 5 * (attempt + 1) + random.uniform(1.0, 4.0)
    logger.info("Backing off %.1fs (%s)", wait, reason or "retry")
    time.sleep(wait)
    if vpn is not None and getattr(vpn, "enabled", False):
        try:
            vpn.rotate()
        except Exception as exc:
            logger.warning("VPN rotate failed: %s", exc)


def random_delay(min_delay: float, max_delay: float) -> None:
    if max_delay <= 0:
        return
    lo = max(0.0, min_delay)
    hi = max(lo, max_delay)
    time.sleep(random.uniform(lo, hi))


def _basename_from_url(url: str) -> str:
    path = urlparse(url).path
    name = os.path.basename(path)
    return name or "image.jpg"


def download_tcdb_image(
    scraper,
    image_url: str,
    referer: str,
    dest_path: str,
) -> bool:
    """Save a TCDB image to disk via HTTP client. Returns True on success."""
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    try:
        resp = scraper.get(image_url, headers={"Referer": referer}, timeout=60)
    except Exception as exc:
        logger.warning("Image download failed %s: %s", image_url, exc)
        return False
    if resp.status_code != 200 or len(resp.content) < 256:
        logger.warning("Image download HTTP %s (%s bytes) for %s", resp.status_code, len(resp.content), image_url)
        return False
    content_type = (resp.headers.get("content-type") or "").lower()
    if "html" in content_type:
        logger.warning("Image download returned HTML for %s", image_url)
        return False
    with open(dest_path, "wb") as fh:
        fh.write(resp.content)
    return True


def download_tcdb_image_playwright(
    context,
    image_url: str,
    referer: str,
    dest_path: str,
) -> bool:
    """Save a TCDB image using a Playwright browser context (cookies/TLS)."""
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    try:
        resp = context.request.get(image_url, headers={"Referer": referer}, timeout=60_000)
    except Exception as exc:
        logger.warning("Playwright image download failed %s: %s", image_url, exc)
        return False
    if resp.status not in (200,):
        logger.warning("Playwright image HTTP %s for %s", resp.status, image_url)
        return False
    body = resp.body()
    if len(body) < 256:
        logger.warning("Playwright image too small (%s bytes) for %s", len(body), image_url)
        return False
    content_type = (resp.headers.get("content-type") or "").lower()
    if "html" in content_type or body[:15].lower().startswith(b"<!doctype"):
        logger.warning("Playwright image returned HTML for %s", image_url)
        return False
    with open(dest_path, "wb") as fh:
        fh.write(body)
    return True


class PlaywrightImageSession:
    """Reuse one Chromium instance for many card image downloads."""

    _USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )

    def __init__(self, *, headless: bool = True, settle_seconds: float = 1.5):
        self.headless = headless
        self.settle_seconds = settle_seconds
        self._playwright = None
        self._browser = None
        self.context = None
        self._page = None

    def __enter__(self) -> "PlaywrightImageSession":
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=self.headless)
        self.context = self._browser.new_context(
            user_agent=self._USER_AGENT,
            locale="en-US",
        )
        self._page = self.context.new_page()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._browser is not None:
            self._browser.close()
        if self._playwright is not None:
            self._playwright.stop()

    def prime_viewcard(self, viewcard_url: str) -> bool:
        """Load ViewCard so image CDN requests inherit session cookies."""
        if not viewcard_url or self._page is None:
            return False
        try:
            self._page.goto(viewcard_url, wait_until="domcontentloaded", timeout=90_000)
        except Exception as exc:
            logger.warning("Playwright ViewCard load failed %s: %s", viewcard_url, exc)
            return False
        if self.settle_seconds > 0:
            time.sleep(self.settle_seconds)
        return True

    def download_image(self, image_url: str, referer: str, dest_path: str) -> bool:
        if self.context is None:
            return False
        return download_tcdb_image_playwright(self.context, image_url, referer, dest_path)


def apply_card_images(
    card: Card,
    parsed: ParsedCardImages,
    *,
    image_root: str,
    tcdb_sid: int | str,
    download: bool,
    scraper=None,
) -> dict[str, str | None]:
    """
    Update card image URL columns (and optional local cache paths).

    New URLs are merged per side — existing front/back URLs are not cleared when
    ViewCard omits that side (important for partial-scan rechecks).

    Returns a summary dict for logging.
    """
    if parsed.front_url:
        card.image_front_url = parsed.front_url
    if parsed.back_url:
        card.image_back_url = parsed.back_url

    if not download or scraper is None:
        return {
            "front_url": card.image_front_url,
            "back_url": card.image_back_url,
            "front_local": card.image_front_local,
            "back_local": card.image_back_local,
        }

    referer = card.tcdb_url or ""
    sid_dir = str(tcdb_sid)

    front_local = card.image_front_local
    back_local = card.image_back_local
    if card.image_front_url and not card.image_front_local:
        dest = os.path.join(image_root, sid_dir, _basename_from_url(card.image_front_url))
        if download_tcdb_image(scraper, card.image_front_url, referer, dest):
            front_local = os.path.join(sid_dir, _basename_from_url(card.image_front_url))
            card.image_front_local = front_local

    if card.image_back_url and not card.image_back_local:
        dest = os.path.join(image_root, sid_dir, _basename_from_url(card.image_back_url))
        if download_tcdb_image(scraper, card.image_back_url, referer, dest):
            back_local = os.path.join(sid_dir, _basename_from_url(card.image_back_url))
            card.image_back_local = back_local

    return {
        "front_url": card.image_front_url,
        "back_url": card.image_back_url,
        "front_local": front_local,
        "back_local": back_local,
    }


def download_existing_card_images(
    card: Card,
    scraper,
    *,
    image_root: str,
    tcdb_sid: int | str,
    skip_existing: bool = True,
) -> dict[str, bool]:
    """Download front/back JPEGs when image_*_url is already set on the card."""
    referer = card.tcdb_url or ""
    sid_dir = str(tcdb_sid)
    results = {"front": False, "back": False}

    if card.image_front_url and not (skip_existing and card.image_front_local):
        dest = os.path.join(image_root, sid_dir, _basename_from_url(card.image_front_url))
        if download_tcdb_image(scraper, card.image_front_url, referer, dest):
            card.image_front_local = os.path.join(sid_dir, _basename_from_url(card.image_front_url))
            results["front"] = True

    if card.image_back_url and not (skip_existing and card.image_back_local):
        dest = os.path.join(image_root, sid_dir, _basename_from_url(card.image_back_url))
        if download_tcdb_image(scraper, card.image_back_url, referer, dest):
            card.image_back_local = os.path.join(sid_dir, _basename_from_url(card.image_back_url))
            results["back"] = True

    return results


def download_existing_card_images_playwright(
    card: Card,
    pw_session: PlaywrightImageSession,
    *,
    image_root: str,
    tcdb_sid: int | str,
    skip_existing: bool = True,
) -> dict[str, bool]:
    """Download front/back via Playwright after priming the ViewCard session."""
    referer = card.tcdb_url or ""
    sid_dir = str(tcdb_sid)
    results = {"front": False, "back": False}

    need_front = bool(card.image_front_url) and not (skip_existing and card.image_front_local)
    need_back = bool(card.image_back_url) and not (skip_existing and card.image_back_local)
    if not need_front and not need_back:
        results["front"] = bool(card.image_front_local)
        results["back"] = bool(card.image_back_local)
        return results

    if not pw_session.prime_viewcard(referer):
        return results

    if need_front and card.image_front_url:
        dest = os.path.join(image_root, sid_dir, _basename_from_url(card.image_front_url))
        if pw_session.download_image(card.image_front_url, referer, dest):
            card.image_front_local = os.path.join(sid_dir, _basename_from_url(card.image_front_url))
            results["front"] = True

    if need_back and card.image_back_url:
        dest = os.path.join(image_root, sid_dir, _basename_from_url(card.image_back_url))
        if pw_session.download_image(card.image_back_url, referer, dest):
            card.image_back_local = os.path.join(sid_dir, _basename_from_url(card.image_back_url))
            results["back"] = True

    return results


def backfill_card_image(
    card: Card,
    scraper,
    *,
    image_root: str,
    tcdb_sid: int | str,
    download: bool,
    delay_range: tuple[float, float] = (0.0, 0.0),
    timeout: int = 90,
    retries: int = 4,
    vpn=None,
) -> ParsedCardImages | None:
    random_delay(*delay_range)
    if not card.tcdb_url:
        return None
    html = fetch_viewcard_html(scraper, card.tcdb_url, timeout=timeout, retries=retries, vpn=vpn)
    if not html:
        return None
    parsed = parse_viewcard_images(html)
    apply_card_images(
        card,
        parsed,
        image_root=image_root,
        tcdb_sid=tcdb_sid,
        download=download,
        scraper=scraper,
    )
    record_image_url_check(card, parsed)
    return parsed
