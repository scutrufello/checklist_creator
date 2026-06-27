#!/usr/bin/env python3
"""Prototype: fetch and preview TCDB card images for a set."""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import textwrap
import time

import cloudscraper

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import get_session  # noqa: E402
from app.models import Card, CardSet  # noqa: E402
from scraper.viewcard_parser import parse_viewcard_images  # noqa: E402

logger = logging.getLogger(__name__)


def _find_set(session, set_query: str) -> CardSet | None:
    if set_query.isdigit():
        return session.get(CardSet, int(set_query))
    return (
        session.query(CardSet)
        .filter(CardSet.full_name.ilike(f"%{set_query}%"))
        .order_by(CardSet.tcdb_sid)
        .first()
    )


def fetch_viewcard_html(scraper, url: str, *, delay: float = 0.0) -> str | None:
    if delay:
        time.sleep(delay)
    try:
        resp = scraper.get(url, timeout=90)
    except Exception as exc:
        logger.error("Fetch failed %s: %s", url, exc)
        return None
    if resp.status_code != 200:
        logger.error("HTTP %s for %s", resp.status_code, url)
        return None
    return resp.text


def try_download_image(scraper, image_url: str, referer: str, dest: str) -> bool:
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    try:
        resp = scraper.get(image_url, headers={"Referer": referer}, timeout=60)
    except Exception as exc:
        logger.warning("Download failed %s: %s", image_url, exc)
        return False
    if resp.status_code != 200 or not resp.content or b"<html" in resp.content[:256].lower():
        logger.warning("Download rejected HTTP %s for %s", resp.status_code, image_url)
        return False
    with open(dest, "wb") as fh:
        fh.write(resp.content)
    return True


def write_preview_html(out_dir: str, set_name: str, rows: list[dict]) -> str:
    cards_html = []
    for row in rows:
        front = row.get("display_front_url") or ""
        back = row.get("back_url") or ""
        cards_html.append(
            textwrap.dedent(
                f"""
                <article class="card">
                  <h2>#{row["number"]} {row["player_name"]}</h2>
                  <p class="meta"><a href="{row["tcdb_url"]}">ViewCard</a></p>
                  <div class="imgs">
                    <figure>
                      <figcaption>Front</figcaption>
                      {"<img src=\"" + front + "\" alt=\"front\" loading=\"lazy\">" if front else "<p class=\"missing\">No front URL</p>"}
                      <code>{front}</code>
                    </figure>
                    <figure>
                      <figcaption>Back</figcaption>
                      {"<img src=\"" + back + "\" alt=\"back\" loading=\"lazy\">" if back else "<p class=\"missing\">No back URL</p>"}
                      <code>{back}</code>
                    </figure>
                  </div>
                </article>
                """
            ).strip()
        )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{set_name} — image prototype</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 1.5rem; background: #f5f0e8; color: #002d72; }}
    h1 {{ margin-bottom: 0.25rem; }}
    .note {{ color: #555; max-width: 52rem; margin-bottom: 1.5rem; }}
    .card {{ background: #fff; border: 1px solid #ddd; border-radius: 8px; padding: 1rem; margin-bottom: 1rem; }}
    .imgs {{ display: flex; flex-wrap: wrap; gap: 1rem; }}
    figure {{ margin: 0; max-width: 280px; }}
    img {{ max-width: 260px; height: auto; border: 1px solid #ccc; background: #eee; }}
    code {{ display: block; font-size: 0.7rem; word-break: break-all; margin-top: 0.35rem; color: #666; }}
    .missing {{ color: #999; font-style: italic; }}
  </style>
</head>
<body>
  <h1>{set_name}</h1>
  <p class="note">Images load directly from TCDB. If they appear broken here, TCDB may be blocking
  hotlinking from this host — URLs are still valid for scrape/download from a residential IP.</p>
  {"".join(cards_html)}
</body>
</html>
"""
    path = os.path.join(out_dir, "index.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(html)
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Prototype TCDB card image fetch for one set")
    parser.add_argument(
        "--set",
        default="1987 Fleer Star Stickers",
        help="Set id or substring of full_name (default: 1987 Fleer Star Stickers)",
    )
    parser.add_argument(
        "--out",
        default="./data/prototype/1987-fleer-star-stickers",
        help="Output directory for JSON, HTML preview, optional downloads",
    )
    parser.add_argument("--download", action="store_true", help="Try saving front images locally")
    parser.add_argument("--delay", type=float, default=2.0, help="Seconds between ViewCard fetches")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    session = get_session()
    try:
        card_set = _find_set(session, args.set)
        if card_set is None:
            raise SystemExit(f"Set not found: {args.set!r}")

        cards = (
            session.query(Card)
            .filter_by(set_id=card_set.id)
            .order_by(Card.sort_number, Card.number, Card.player_name)
            .all()
        )
        if not cards:
            raise SystemExit(f"No cards in set {card_set.full_name}")

        logger.info("Set: %s (sid=%s, %d cards)", card_set.full_name, card_set.tcdb_sid, len(cards))

        scraper = cloudscraper.create_scraper()
        rows: list[dict] = []

        for idx, card in enumerate(cards):
            html = fetch_viewcard_html(scraper, card.tcdb_url, delay=args.delay if idx else 0.0)
            if not html:
                continue
            parsed = parse_viewcard_images(html)
            row = {
                "card_id": card.id,
                "number": card.number,
                "player_name": card.player_name,
                "tcdb_cid": card.tcdb_cid,
                "tcdb_url": card.tcdb_url,
                "front_url": parsed.front_url,
                "back_url": parsed.back_url,
                "large_front_url": parsed.large_front_url,
                "large_back_url": parsed.large_back_url,
                "sample_url": parsed.sample_url,
                "display_front_url": parsed.display_front_url,
                "has_card_scan": parsed.has_card_scan,
            }
            rows.append(row)
            logger.info(
                "%s %s — scan=%s front=%s",
                card.number,
                card.player_name,
                parsed.has_card_scan,
                parsed.front_url,
            )

            if args.download and parsed.display_front_url:
                ext = ".jpg"
                safe = slugify(f"{card.number}-{card.player_name}")
                dest = os.path.join(args.out, "images", f"{safe}{ext}")
                ok = try_download_image(scraper, parsed.display_front_url, card.tcdb_url, dest)
                row["local_front"] = dest if ok else None

        os.makedirs(args.out, exist_ok=True)
        json_path = os.path.join(args.out, "images.json")
        with open(json_path, "w", encoding="utf-8") as fh:
            json.dump(
                {
                    "set_id": card_set.id,
                    "set_name": card_set.full_name,
                    "tcdb_sid": card_set.tcdb_sid,
                    "cards": rows,
                },
                fh,
                indent=2,
            )
        html_path = write_preview_html(args.out, card_set.full_name, rows)

        print(f"\nWrote {json_path}")
        print(f"Preview: {html_path}")
        print(f"Cards with scans: {sum(1 for r in rows if r['has_card_scan'])}/{len(rows)}")
    finally:
        session.close()


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return slug or "card"


if __name__ == "__main__":
    main()
