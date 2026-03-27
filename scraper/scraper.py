import json
import logging
import os
import random
import re
import sys
import time

import cloudscraper
import requests

from app.database import get_session, init_db, load_config
from app.models import Card, CardSet, strip_redundant_variant_tag_prose
from scraper.hierarchy import build_hierarchy, classify_set_type, split_set_name
from scraper.page_parser import ParsedCard, parse_team_page, parse_years_available
from scraper.vpn_manager import VPNManager

logger = logging.getLogger(__name__)

CHECKPOINT_FILE = "./data/scrape_checkpoint.json"


def discover_team_years(config: dict) -> list[int]:
    """
    Fetch one team page and parse all years linked from the year selector.
    Returns years ascending (oldest first) for stable scrape order.
    """
    scraper = TCDBScraper(config)
    scfg = config["scraper"]
    seed = scfg["year"]
    seed_year = max(seed) if isinstance(seed, list) else int(seed)

    if scraper.vpn.enabled:
        try:
            scraper.vpn.connect()
        except Exception as e:
            logger.warning("VPN connection failed during year discovery (%s), continuing without VPN", e)

    try:
        url = scraper._team_url(seed_year, 1)
        logger.info("Discovering years from %s", url)
        html = scraper._fetch_page(url)
        if not html:
            raise RuntimeError("Could not fetch team page to discover years (see logs)")
        years = parse_years_available(html)
        if not years:
            raise RuntimeError("No years found in page HTML; TCDB layout may have changed")
        years_sorted = sorted(years)
        logger.info("Discovered %d years: %d … %d", len(years_sorted), years_sorted[0], years_sorted[-1])
        return years_sorted
    finally:
        scraper.vpn.cleanup()


class TCDBScraper:
    def __init__(self, config: dict):
        self.config = config
        scfg = config["scraper"]
        self.min_delay = scfg["min_delay"]
        self.max_delay = scfg["max_delay"]
        self.year = scfg["year"]
        self.team_id = scfg["team_id"]
        self.team_name = scfg["team_name"]
        self.base_url = scfg["base_url"]
        self.resume = scfg.get("resume", True)
        self.request_timeout = scfg.get("request_timeout", 90)
        self.use_playwright_fallback = scfg.get("use_playwright_fallback", True)
        self.vpn = VPNManager(config)
        self.page_count = 0
        self.scraper = cloudscraper.create_scraper()

    def _delay(self):
        wait = random.uniform(self.min_delay, self.max_delay)
        logger.debug("Sleeping %.1fs", wait)
        time.sleep(wait)

    def _team_url(self, year: int, page: int = 1) -> str:
        url = (
            f"{self.base_url}/Team.cfm/tid/{self.team_id}/col/1"
            f"/yea/{year}/{self.team_name}"
        )
        if page > 1:
            url += f"?PageIndex={page}"
        return url

    def _load_checkpoint(self) -> dict:
        if self.resume and os.path.exists(CHECKPOINT_FILE):
            with open(CHECKPOINT_FILE) as f:
                return json.load(f)
        return {}

    def _save_checkpoint(self, data: dict):
        os.makedirs(os.path.dirname(CHECKPOINT_FILE), exist_ok=True)
        with open(CHECKPOINT_FILE, "w") as f:
            json.dump(data, f)

    def run(self, years: list[int] | None = None, bypass_checkpoint: bool = False):
        if years is None:
            years = [self.year]

        init_db()
        checkpoint = self._load_checkpoint()

        if self.vpn.enabled:
            try:
                self.vpn.connect()
            except Exception as e:
                logger.warning("VPN connection failed (%s), continuing without VPN", e)

        logger.info(
            "Run settings | vpn_enabled=%s | rotate_every=%d successful pages | log_public_ip_every=%d | delay=%.1f-%.1fs | timeout=%ds",
            self.vpn.enabled,
            self.vpn.rotate_every,
            self.vpn.log_public_ip_every_n_requests,
            self.min_delay,
            self.max_delay,
            self.request_timeout,
        )

        try:
            for year in years:
                ck_key = str(year)
                if not bypass_checkpoint and checkpoint.get(ck_key) == "done":
                    logger.info("Year %d already scraped (checkpoint). Skipping.", year)
                    continue

                logger.info("=== Scraping year %d ===", year)
                self._scrape_year(year)

                checkpoint[ck_key] = "done"
                self._save_checkpoint(checkpoint)
        finally:
            self.vpn.cleanup()

        # Build set hierarchy after all scraping
        session = get_session()
        try:
            for year in years:
                build_hierarchy(session, year)
        finally:
            session.close()

        logger.info("Scraping complete!")

    def _scrape_year(self, year: int):
        page_num = 1
        total_cards = 0

        while True:
            url = self._team_url(year, page_num)
            logger.info("Fetching page %d: %s", page_num, url)

            html = self._fetch_page(url)
            if html is None:
                logger.error(
                    "Failed to fetch page %d for year %d — stopping this year (check logs above for HTTP block / Cloudflare / timeout)",
                    page_num,
                    year,
                )
                break

            parsed_cards = parse_team_page(html)
            if not parsed_cards:
                if page_num == 1:
                    logger.warning("No cards found for year %d", year)
                break

            self._store_cards(parsed_cards, year)
            total_cards += len(parsed_cards)
            logger.info("Page %d: %d cards (total: %d)", page_num, len(parsed_cards), total_cards)

            # Count every successful page toward rotate_every + periodic IP logs
            self.vpn.tick()

            # Check for next page
            if not self._has_next_page(html, page_num):
                break

            page_num += 1
            self._delay()

        logger.info("Year %d complete: %d cards total", year, total_cards)

    def _egress_log_suffix(self) -> str:
        if not self.vpn.enabled:
            return "vpn=off"
        return "public_ip=%s endpoint=%s" % (
            self.vpn.current_public_ip or "?",
            self.vpn.current_endpoint_name or "?",
        )

    def _fetch_page(self, url: str, retries: int = 3) -> str | None:
        html = None
        for attempt in range(retries):
            try:
                response = self.scraper.get(url, timeout=self.request_timeout)
                response.raise_for_status()
                content = response.text

                # Only treat as Cloudflare challenge when we don't have real content.
                # (Normal TCDB pages can include "challenge-platform" in script URLs.)
                is_challenge = (
                    ("Just a moment" in content or "Checking your browser" in content)
                    and "ViewCard.cfm" not in content
                )
                if is_challenge:
                    logger.warning(
                        "[CLOUDFLARE] challenge page (no card links) | %s | url=%s | attempt %d/%d",
                        self._egress_log_suffix(),
                        url,
                        attempt + 1,
                        retries,
                    )
                    if attempt == 0 and self.use_playwright_fallback:
                        fallback_html = self._fetch_page_playwright(url)
                        if fallback_html:
                            self.page_count += 1
                            return fallback_html
                    if self.vpn.enabled:
                        logger.info("[CLOUDFLARE] rotating VPN and retrying...")
                        self.vpn.rotate()
                        time.sleep(3)
                        continue
                    return None

                # 200 but suspicious: tiny HTML with no cards might mean soft block / error page
                if len(content) < 5000 and "ViewCard.cfm" not in content:
                    logger.warning(
                        "[SUSPICIOUS RESPONSE] short HTML (%d bytes) and no ViewCard links | %s | url=%s",
                        len(content),
                        self._egress_log_suffix(),
                        url,
                    )

                self.page_count += 1
                html = content
                return html
            except requests.HTTPError as e:
                resp = e.response
                status = resp.status_code if resp is not None else None
                snippet = ""
                if resp is not None and resp.text:
                    snippet = resp.text[:240].replace("\n", " ").replace("\r", "")
                hint = ""
                if status == 403:
                    hint = " | likely FORBIDDEN / IP or bot block"
                elif status == 429:
                    hint = " | likely RATE LIMITED"
                elif status in (503, 502):
                    hint = " | server busy or protection upstream"
                logger.error(
                    "[HTTP %s] TCDB request failed%s | %s | url=%s | attempt %d/%d | body_prefix=%r",
                    status,
                    hint,
                    self._egress_log_suffix(),
                    url,
                    attempt + 1,
                    retries,
                    snippet,
                )
                if attempt < retries - 1:
                    time.sleep(5 * (attempt + 1))
                    if self.vpn.enabled:
                        logger.info("[HTTP ERROR] rotating VPN before retry...")
                        self.vpn.rotate()
            except Exception as e:
                err_msg = f"{type(e).__name__}: {e}"
                if "timeout" in type(e).__name__.lower() or "timed out" in str(e).lower():
                    logger.warning(
                        "[TIMEOUT] attempt %d/%d (timeout=%ds) | %s | %s",
                        attempt + 1,
                        retries,
                        self.request_timeout,
                        self._egress_log_suffix(),
                        err_msg,
                    )
                else:
                    logger.warning(
                        "[FETCH ERROR] attempt %d/%d | %s | %s",
                        attempt + 1,
                        retries,
                        self._egress_log_suffix(),
                        err_msg,
                    )
                if attempt < retries - 1:
                    time.sleep(5 * (attempt + 1))
                    if self.vpn.enabled:
                        logger.info("[FETCH ERROR] rotating VPN before retry...")
                        self.vpn.rotate()

        logger.error(
            "[FETCH GAVE UP] all retries exhausted | %s | url=%s",
            self._egress_log_suffix(),
            url,
        )
        # Optional: try Playwright once (headed or headless) when cloudscraper failed
        if html is None and self.use_playwright_fallback:
            html = self._fetch_page_playwright(url)
        return html

    def _has_next_page(self, html: str, current_page: int) -> bool:
        next_pattern = rf"PageIndex={current_page + 1}"
        return next_pattern in html

    def _fetch_page_playwright(self, url: str) -> str | None:
        """Fallback: use headless (or headed) browser when cloudscraper hits Cloudflare."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.warning("Playwright not installed; skip browser fallback")
            return None

        headless = self.config.get("scraper", {}).get("playwright_headless", True)
        logger.info("Trying Playwright fallback (headless=%s)", headless)

        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=headless)
                context = browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                    )
                )
                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                for _ in range(12):
                    content = page.content()
                    if "Just a moment" in content or "challenge-platform" in content:
                        time.sleep(5)
                        continue
                    try:
                        page.wait_for_selector("a[href*='ViewCard.cfm']", timeout=10000)
                    except Exception:
                        pass
                    content = page.content()
                    if "ViewCard.cfm" in content:
                        self.page_count += 1
                        browser.close()
                        return content
                    time.sleep(2)
                browser.close()
                logger.warning(
                    "[PLAYWRIGHT] still no card content after waits | %s | url=%s",
                    self._egress_log_suffix(),
                    url,
                )
                return None
        except Exception as e:
            logger.warning(
                "Playwright fallback failed: %s | %s | url=%s",
                e,
                self._egress_log_suffix(),
                url,
            )
            return None

    def _store_cards(self, parsed_cards: list[ParsedCard], year: int):
        session = get_session()
        try:
            for pc in parsed_cards:
                if not _safe_tcdb_sid(pc.sid):
                    logger.warning("Skipping card: invalid tcdb_sid %s | %s", pc.sid, pc.url)
                    continue
                # Upsert CardSet
                card_set = session.query(CardSet).filter_by(tcdb_sid=pc.sid).first()
                if card_set is None:
                    base_name, variant_name = split_set_name(pc.set_name)
                    set_type = classify_set_type(pc.set_name, base_name, variant_name)

                    card_set = CardSet(
                        tcdb_sid=pc.sid,
                        full_name=pc.set_name,
                        base_name=base_name,
                        variant_name=variant_name,
                        year=year,
                        set_type=set_type,
                    )
                    session.add(card_set)
                    session.flush()

                # One row per TCDB card id inside a set. Using tcdb_cid avoids collisions on
                # products where every card is "NNO" (e.g. 2025 Topps T205).
                variant_label = _variant_label(pc)
                existing = session.query(Card).filter_by(
                    set_id=card_set.id, tcdb_cid=pc.cid
                ).first()
                if existing is None:
                    sort_num = _extract_sort_number(pc.number)
                    card = Card(
                        set_id=card_set.id,
                        number=pc.number,
                        variant=variant_label,
                        sort_number=sort_num,
                        player_name=pc.player_name,
                        tcdb_cid=pc.cid,
                        tcdb_url=pc.url,
                        raw_tags_text=pc.raw_tags_text,
                        tags=json.dumps(_normalize_tags(pc.tags)) if pc.tags else None,
                        owned=False,
                    )
                    session.add(card)
                else:
                    # Same tcdb_cid seen again (e.g. duplicate link cell); refresh mutable fields and merge tags.
                    existing.number = pc.number
                    existing.variant = variant_label
                    existing.sort_number = _extract_sort_number(pc.number)
                    existing.player_name = pc.player_name
                    existing.tcdb_url = pc.url
                    existing.raw_tags_text = pc.raw_tags_text
                    merged_tags = list({t for t in (existing.tags_list + pc.tags) if t and len(t) <= 12})
                    existing.tags = json.dumps(_normalize_tags(merged_tags)) if merged_tags else None

            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


# SQLite / Python sqlite3 bind limit for INTEGER
_SQLITE_MAX_INT = 2**63 - 1
# Sane ceiling for card “#” sorting (guards garbage / accidental huge digit runs)
_MAX_SORT_NUMBER = 999_999_999


def _extract_sort_number(number_str: str) -> int | None:
    """
    Extract a stable sortable number from card labels.
    Uses the first numeric token only (see checklist-style numbers with many slashes).
    Caps so we never overflow SQLite integer binds from a bogus all-digit “number”.
    """
    match = re.search(r"\d+", number_str or "")
    if not match:
        return None
    token = match.group(0)
    if len(token) > 12:
        return None
    try:
        val = int(token)
    except ValueError:
        return None
    if val < 0 or val > _MAX_SORT_NUMBER:
        return None
    return val


def _safe_tcdb_sid(sid: int) -> bool:
    return isinstance(sid, int) and 0 < sid <= _SQLITE_MAX_INT


def _variant_label(pc: "ParsedCard") -> str:
    """Return variant string for (set, number, variant) uniqueness. '' = base card."""
    raw = (pc.raw_tags_text or "").strip()
    tags_upper = [t.upper() for t in (pc.tags or [])]
    is_variation = "VAR" in tags_upper or "variation" in raw.lower()
    if not is_variation or not raw:
        return ""
    label = strip_redundant_variant_tag_prose(raw)
    # If nothing meaningful remains, keep raw as fallback.
    if not label:
        label = raw
    if len(label) > 200:
        label = label[:197] + "..."
    return label


def _normalize_tags(tags: list[str]) -> list[str]:
    """Keep canonical indicator tags only (VAR, AU, MEM, SNxx, RC, etc.)."""
    if not tags:
        return []
    seen = set()
    out = []
    valid_exact = {
        "VAR", "AU", "AUTO", "MEM", "RELIC", "JERSEY", "PATCH",
        "RC", "SP", "SSP", "TC", "PR", "DK", "IP", "GU",
    }
    for t in tags:
        t = (t or "").strip()
        if not t or len(t) > 12:
            continue
        u = t.upper()
        # Serialized indicators (SN25, SN/25, /25) should be retained.
        if re.match(r"^(SN/?\d+|/\d+)$", u):
            pass
        elif u in valid_exact:
            pass
        else:
            continue
        if u not in seen:
            seen.add(u)
            out.append(u)
    return sorted(out, key=lambda x: (x.upper() != "VAR", x.upper() != "TC", x))


def main(
    years: list[int] | None = None,
    fresh: bool = False,
    bypass_checkpoint: bool = False,
):
    log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    root = logging.getLogger()
    if not root.handlers:
        os.makedirs(os.path.dirname("./data/scraper.log") or ".", exist_ok=True)
        logging.basicConfig(
            level=logging.INFO,
            format=log_format,
            handlers=[
                logging.StreamHandler(sys.stdout),
                logging.FileHandler("./data/scraper.log"),
            ],
        )
    else:
        # scrape.py may have configured stdout only; ensure file log too
        has_file = any(isinstance(h, logging.FileHandler) for h in root.handlers)
        if not has_file:
            os.makedirs(os.path.dirname("./data/scraper.log") or ".", exist_ok=True)
            fh = logging.FileHandler("./data/scraper.log")
            fh.setFormatter(logging.Formatter(log_format))
            root.addHandler(fh)

    config = load_config()

    if years is None:
        year_arg = config["scraper"]["year"]
        years = [year_arg] if isinstance(year_arg, int) else year_arg

    if fresh and os.path.exists(CHECKPOINT_FILE):
        os.remove(CHECKPOINT_FILE)
        logger.info("Removed checkpoint file for fresh run: %s", CHECKPOINT_FILE)

    scraper = TCDBScraper(config)
    scraper.run(years, bypass_checkpoint=bypass_checkpoint)


if __name__ == "__main__":
    main()
