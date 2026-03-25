import logging
import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


@dataclass
class ParsedCard:
    sid: int
    cid: str
    set_name: str
    number: str
    player_name: str
    url: str
    tags: list[str] = field(default_factory=list)
    raw_tags_text: str = ""


def parse_team_page(html: str) -> list[ParsedCard]:
    """Parse the TCDB team page and extract all card entries."""
    soup = BeautifulSoup(html, "html.parser")
    cards = []

    # Find all links to ViewCard pages (skip image-only links; use the link that has card text)
    links = soup.find_all("a", href=re.compile(r"/ViewCard\.cfm/sid/\d+/cid/\d+/"))

    for link in links:
        link_text = link.get_text(strip=True)
        if not link_text:
            continue  # Image-only link; same card appears in another cell with text

        href = link.get("href", "")
        match = re.search(r"/ViewCard\.cfm/sid/(\d+)/cid/(\d+)/(.+)", href)
        if not match:
            continue

        sid = int(match.group(1))
        cid = match.group(2)
        slug = match.group(3).rstrip("-")

        set_name, number, player_name = _parse_card_text(link_text, slug)

        raw_tags_text, tag_list = _extract_tags(link)

        url = href if href.startswith("http") else f"https://www.tcdb.com{href}"

        cards.append(ParsedCard(
            sid=sid,
            cid=cid,
            set_name=set_name,
            number=number,
            player_name=player_name,
            url=url,
            tags=tag_list,
            raw_tags_text=raw_tags_text,
        ))

    logger.info("Parsed %d cards from team page", len(cards))
    return cards


def _parse_card_text(link_text: str, slug: str) -> tuple[str, str, str]:
    """
    Parse card text like '1990 Best Reading Phillies #1 David Holdridge'
    into (set_name, number, player_name).
    """
    # Try to split on # first
    hash_match = re.match(r"^(.+?)\s*#(\S+)\s+(.+)$", link_text)
    if hash_match:
        return hash_match.group(1).strip(), hash_match.group(2).strip(), hash_match.group(3).strip()

    # Fallback: try splitting on the last number sequence
    num_match = re.match(r"^(.+?)\s+(\d+\S*)\s+(.+)$", link_text)
    if num_match:
        return num_match.group(1).strip(), num_match.group(2).strip(), num_match.group(3).strip()

    # Last resort: use slug to reconstruct
    return link_text, "", ""


def _extract_tags(link_element) -> tuple[str, list[str]]:
    """
    Extract metadata tags that appear near the card link but outside it.
    Tags like AU, MEM, SN25, RC, etc. appear as text siblings.
    """
    tags = []
    raw_parts = []

    # Check text siblings after the link
    parent = link_element.parent
    if parent is None:
        return "", []

    # Get all text content in the parent that is NOT inside the link
    for child in parent.children:
        if child == link_element:
            continue
        if hasattr(child, "get_text"):
            text = child.get_text(strip=True)
        else:
            text = str(child).strip()

        if text:
            raw_parts.append(text)

    raw_text = " ".join(raw_parts).strip()
    if not raw_text:
        return "", []

    # Tags are typically comma-separated or space-separated short codes
    # Split on commas and whitespace, filter out empties and noise
    candidates = re.split(r"[,\s]+", raw_text)
    for c in candidates:
        c = c.strip().strip(",").strip()
        if c and len(c) <= 12 and re.match(r"^[A-Za-z0-9/]+$", c):
            tags.append(c)

    return raw_text, tags


def parse_years_available(html: str) -> list[int]:
    """Parse available years from a team page with year selector."""
    soup = BeautifulSoup(html, "html.parser")
    years = set()

    # Look for year links in the page
    for link in soup.find_all("a", href=re.compile(r"yea/\d{4}/")):
        href = link.get("href", "")
        match = re.search(r"yea/(\d{4})/", href)
        if match:
            years.add(int(match.group(1)))

    return sorted(years, reverse=True)
