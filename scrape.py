#!/usr/bin/env python3
"""Run the TCDB scraper for Phillies cards."""
import argparse
import logging
import sys
from datetime import date

from scraper.scraper import discover_team_years, main as scraper_main


def main():
    parser = argparse.ArgumentParser(description="Scrape TCDB for Phillies cards")
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument(
        "--year", "-y",
        type=int,
        help="Year to scrape (overrides config.yaml)",
    )
    scope.add_argument(
        "--all-years",
        action="store_true",
        help="Discover all years from TCDB team page and scrape each (uses config team_id / team_name)",
    )
    scope.add_argument(
        "--recent-years",
        action="store_true",
        help=(
            "Scrape the current calendar year and the previous year (local date), "
            "re-fetching even if the checkpoint marks them done (for scheduled refreshes)"
        ),
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Delete scrape checkpoint so years are not skipped as already done",
    )
    args = parser.parse_args()

    # Year discovery logs before scraper_main() configures file logging.
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
    )

    years = None
    bypass_checkpoint = False
    if args.all_years:
        from app.database import load_config

        years = discover_team_years(load_config())
    elif args.year:
        years = [args.year]
    elif args.recent_years:
        y = date.today().year
        years = [y, y - 1]
        bypass_checkpoint = True

    scraper_main(years=years, fresh=args.fresh, bypass_checkpoint=bypass_checkpoint)


if __name__ == "__main__":
    main()
