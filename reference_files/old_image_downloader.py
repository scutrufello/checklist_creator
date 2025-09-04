#!/usr/bin/env python3
import os
import csv
import time
import random
import argparse
import logging
import requests
from pathlib import Path
from tqdm import tqdm
import re

# ─── Configuration ───
INPUT_CSV    = 'master_checklist.csv'
STORAGE_DIR  = Path('/media/scutrufello/storage/phillies_checklist_images')
FAILED_CSV   = 'image_download_failed.csv'
LOG_FILE     = 'image_download_log.txt'
HEADERS      = {'User-Agent': 'Mozilla/5.0'}
RETRY_LIMIT  = 3

# ─── Setup logging ───
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s %(levelname)s:%(message)s'
)

# ─── Helpers ───
def slugify(text: str) -> str:
    s = text.lower()
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"[^a-z0-9\-]", "", s)
    s = re.sub(r"-{2,}", "-", s)
    return s.strip('-')


def try_download(url: str, save_path: Path, image_type: str) -> bool:
    for attempt in range(1, RETRY_LIMIT+1):
        try:
            r = requests.get(url, headers=HEADERS, timeout=10)
            ct = r.headers.get('Content-Type', '')
            if r.status_code == 200 and 'image' in ct and len(r.content) > 1024:
                save_path.write_bytes(r.content)
                logging.info(f"Downloaded {image_type}: {url} -> {save_path}")
                return True
            else:
                logging.warning(f"Unexpected response for {image_type}: {url} (status={r.status_code}, Content-Type={ct})")
        except Exception as e:
            logging.error(f"Attempt {attempt} failed for {image_type} {url}: {e}")
        time.sleep(1 * attempt)
    logging.error(f"Failed to download {image_type} after {RETRY_LIMIT} attempts: {url}")
    return False

# ─── Main ───
def main(retry: bool=False, retry_fails: bool=False):
    # Make sure storage root exists
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)

    # Read master checklist
    with open(INPUT_CSV, newline='', encoding='utf-8') as f:
        reader = list(csv.DictReader(f))

    total_images = len(reader) * 2
    pbar = tqdm(total=total_images, desc='Downloading images', unit='img')
    failures = []

    for row in reader:
        year      = row['year']
        set_name  = row['set']
        tqdm.write(f"🔄 Scraping images for year {year}, set '{set_name}'...")
        number    = row['number']
        full_name = row['fullName']
        front_url = row.get('front_photo_url', '')
        back_url  = row.get('back_photo_url', '')

        # Slugs
        set_slug    = slugify(set_name)
        player_slug = slugify(full_name)

        # Prefix folder: first two chars of number (zfilled)
        numstr = number or ''
        if len(numstr) >= 2:
            prefix = numstr[:2]
        else:
            prefix = numstr.zfill(2)

        # Build directories
        card_dir = STORAGE_DIR / year / set_slug / prefix
        card_dir.mkdir(parents=True, exist_ok=True)

        # Filename base
        fname_base = f"{year}-{set_slug}-{numstr}-{player_slug}"
        front_path = card_dir / f"{fname_base}_front.jpg"
        back_path  = card_dir / f"{fname_base}_back.jpg"

        # Download front
        if front_url and (retry or not front_path.exists()):
            if not try_download(front_url, front_path, 'front'):
                failures.append({
                    **row,
                    'image_type': 'front',
                    'url': front_url
                })
        pbar.update(1)

        # Download back
        if back_url and (retry or not back_path.exists()):
            if not try_download(back_url, back_path, 'back'):
                failures.append({
                    **row,
                    'image_type': 'back',
                    'url': back_url
                })
        pbar.update(1)

        # Throttle
        time.sleep(random.uniform(0.5, 1.5))

    pbar.close()

    # Write failures
    if failures:
        with open(FAILED_CSV, 'w', newline='', encoding='utf-8') as ff:
            fieldnames = list(reader[0].keys()) + ['image_type', 'url']
            writer = csv.DictWriter(ff, fieldnames=fieldnames)
            writer.writeheader()
            for fail in failures:
                writer.writerow(fail)
        print(f"Wrote {len(failures)} failures to {FAILED_CSV}")
    else:
        print('🎉 All images downloaded successfully!')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--retry', action='store_true')
    parser.add_argument('--retry-fails', action='store_true')
    args = parser.parse_args()
    main(args.retry, args.retry_fails)
