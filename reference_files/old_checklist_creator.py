#!/usr/bin/env python3
import pandas as pd
import cloudscraper
from bs4 import BeautifulSoup
import time
import re
import csv
import os
import argparse
from datetime import datetime
from pathlib import Path
from tqdm import tqdm

# --- Configuration ---
START_YEAR_DEFAULT = 1970
INPUT_CSV = "mlb_year_links.csv"
OUTPUT_CSV = "mlb_checklist.csv"
LOG_CSV = "mlb_scraped_years.csv"
FAILED_CSV = "mlb_failed_years.csv"

# Output columns matching MiLB format
OUTPUT_COLUMNS = [
    "year", "set", "number",
    "fullName", "card", "type",
    "front_photo_url", "back_photo_url"
]

# Cloudflare-bypassing scraper
scraper = cloudscraper.create_scraper()

# CLI args
parser = argparse.ArgumentParser(description="Scrape MLB card checklists from TCDB")
parser.add_argument(
    "--start-year",
    type=int,
    default=START_YEAR_DEFAULT,
    help="Only scrape from this year onward"
)
args = parser.parse_args()
START_YEAR = args.start_year

# Prepare resume log
if not os.path.exists(LOG_CSV) or os.path.getsize(LOG_CSV) == 0:
    with open(LOG_CSV, "w", newline="", encoding="utf-8") as logf:
        csv.writer(logf).writerow(["source", "year", "timestamp"])
done = set()
try:
    df_log = pd.read_csv(LOG_CSV, dtype=str)
    if {"source","year"}.issubset(df_log.columns):
        done = set(zip(df_log.source, df_log.year))
except (pd.errors.EmptyDataError, pd.errors.ParserError, FileNotFoundError):
    done = set()

# Prepare output CSV headers
if not os.path.exists(OUTPUT_CSV) or os.path.getsize(OUTPUT_CSV) == 0:
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(OUTPUT_COLUMNS)

# Load existing for dedupe
df_existing = pd.read_csv(OUTPUT_CSV, dtype=str)
for col in OUTPUT_COLUMNS:
    if col not in df_existing.columns:
        df_existing[col] = ""
df_existing = df_existing[OUTPUT_COLUMNS]
seen = set(
    (row['year'], row['set'], row['number'], row['fullName'])
    for _, row in df_existing.iterrows()
)

# Read year links
df = pd.read_csv(INPUT_CSV, dtype=str).fillna("")
if 'url' not in df.columns:
    raise ValueError("Expected 'url' column in mlb_year_links.csv")

# Main scraping loop
tqdm.write("🔄 Starting MLB checklist scrape...")
for _, row in tqdm(
    df.iterrows(),
    total=len(df),
    desc="Scraping MLB Years",
    unit="year"
):
    url = row['url'].strip()

    # Extract compound year label from URL
    m = re.search(r"/yea/([^/]+)/", url)
    if not m:
        tqdm.write(f"⚠️ Skipping URL with no year: {url}")
        continue
    year_label = m.group(1)

    # Enforce START_YEAR on base year
    base_year = year_label.split('-')[0]
    if not base_year.isdigit() or int(base_year) < START_YEAR:
        tqdm.write(f"⚠️ Skipping MLB {year_label} (before {START_YEAR})")
        continue

    key = ("MLB", year_label)
    if key in done:
        tqdm.write(f"⚠️ Skipping MLB {year_label} (already scraped)")
        continue

    tqdm.write(f"🔍 Scraping MLB {year_label} → {url}")

    # Determine pagination
    try:
        first = scraper.get(url, timeout=10)
        soup = BeautifulSoup(first.text, "html.parser")
        links = soup.select("ul.pagination a[href*='PageIndex']")
        max_page = max(
            int(re.search(r"PageIndex=(\d+)", a['href']).group(1))
            for a in links
        ) if links else 1
    except Exception as e:
        tqdm.write(f"❌ Error determining pages for MLB {year_label}: {e}")
        with open(FAILED_CSV, "a", newline="", encoding="utf-8") as ff:
            csv.writer(ff).writerow([
                "MLB", year_label, "determine_pages", str(e), datetime.now().isoformat()
            ])
        continue

    # Paginated fetch
    page_bar = tqdm(total=max_page, desc=f"Pages {year_label}", unit="page", leave=False)
    with open(OUTPUT_CSV, "a", newline="", encoding="utf-8") as out_f:
        writer = csv.writer(out_f)
        for page in range(1, max_page+1):
            full_url = url if page == 1 else f"{url}&PageIndex={page}"
            tqdm.write(f"📄 Fetching page {page}/{max_page} → {full_url}")
            try:
                res = scraper.get(full_url, timeout=10)
            except Exception as e:
                tqdm.write(f"❌ Error fetching {full_url}: {e}")
                with open(FAILED_CSV, "a", newline="", encoding="utf-8") as ff:
                    csv.writer(ff).writerow([
                        "MLB", year_label, page, full_url, str(e), datetime.now().isoformat()
                    ])
                break
            soup = BeautifulSoup(res.text, "html.parser")
            cards = soup.select("td.vertical")
            tqdm.write(f"🔍 Found {len(cards)} cards on page {page}/{max_page} for MLB {year_label}")
            if not cards:
                break

            for cell in cards:
                a = cell.find("a")
                if not a:
                    continue
                title = (a.get("title", "") or a.text).strip()
                mnum = re.search(r"#(\S+)\s+(.*)", title)
                if not mnum:
                    continue
                number = mnum.group(1).strip()
                fullName = mnum.group(2).strip()
                set_name = title.split(f"#{number}")[0].strip()
                key2 = (year_label, set_name, number, fullName)
                if key2 in seen:
                    continue
                seen.add(key2)

                href = a.get('href', '')
                front = back = ""
                if 'sid/' in href:
                    sid = re.search(r"sid/(\d+)", href).group(1)
                    num_clean = re.sub(r"[^A-Za-z0-9]", "", number)
                    front = f"https://www.tcdb.com/Images/Cards/Baseball/{sid}/{sid}-{num_clean}Fr.jpg"
                    back = f"https://www.tcdb.com/Images/Cards/Baseball/{sid}/{sid}-{num_clean}Bk.jpg"

                # Write row with blank type
                writer.writerow([
                    year_label,
                    set_name,
                    number,
                    fullName,
                    title,
                    "",
                    front,
                    back,
                ])
            page_bar.update(1)
            time.sleep(1.5)
    page_bar.close()

    # Log completion
    with open(LOG_CSV, "a", newline="", encoding="utf-8") as logf:
        csv.writer(logf).writerow(["MLB", year_label, datetime.now().isoformat()])
    done.add(key)
    tqdm.write(f"✅ Completed MLB {year_label}")

print("🎉 Done scraping MLB checklists!")
