# Image URL & download sync

Recurring jobs to keep TCDB image URLs and local JPEG cache up to date after the initial
era backfill finishes.

## Problem

| Situation | Old behavior |
|-----------|----------------|
| New set scraped | Cards get `tcdb_url` only; no ViewCard pass |
| TCDB adds scan later | Era checkpoint marks card "done" → never rechecked |
| URL exists, no local file | Only picked up if download job runs for that era |

## DB columns (cards)

| Column | Meaning |
|--------|---------|
| `image_url_checked_at` | ISO timestamp of last successful ViewCard parse |
| `image_scan_status` | `none` \| `partial` \| `full` (NULL = never checked) |

Set automatically by `backfill_card_image()` / era backfill **once deployed and restarted**.
Existing era processes keep running old code in memory until they exit.

## Scripts

### `scripts/sync_image_urls.py`

Fetches ViewCard when:

- Never checked (`image_url_checked_at IS NULL`), or
- Confirmed no scan (`image_scan_status = none`, no URLs) and last check older than `--recheck-days` (default 30), or
- **Partial scan** (`scan_status = partial`) or **one-sided URL only** — recheck after `--recheck-days` in case TCDB added the missing side

URL updates **merge per side** (existing front/back URLs are not wiped when ViewCard returns only one side).

```bash
# Dry run (no TCDB)
./venv/bin/python scripts/sync_image_urls.py --dry-run --limit 20

# Production batch (after era backfill done)
./venv/bin/python scripts/sync_image_urls.py \
  --limit 500 \
  --min-delay 1.0 --max-delay 1.4 \
  --recheck-days 30
```

Cursor: `data/image_sync_urls_cursor.json` (resume within queue, wraps at end).

Log: `data/sync_image_urls.log`

### `scripts/sync_image_downloads.py`

Downloads JPEGs when URL exists but `image_*_local` is missing.

```bash
sg devagent -c './venv/bin/python scripts/sync_image_downloads.py \
  --limit 200 \
  --min-delay 0.8 --max-delay 1.2'
```

Cursor: `data/image_sync_downloads_cursor.json`  
Log: `data/sync_image_downloads.log`

Run as `devagent` when writing to `/mnt/phillies-images`.

### `scripts/migrate_image_scan_status.py`

One-time metadata backfill **after era URL backfill completes**:

1. Cards with URLs → infer `partial` / `full`
2. Cards in era checkpoint with no URLs → `none` + checkpoint timestamp

```bash
./venv/bin/python scripts/migrate_image_scan_status.py          # dry run
./venv/bin/python scripts/migrate_image_scan_status.py --apply
```

## When to run what

| Phase | Action |
|-------|--------|
| **Now (era backfill running)** | Schema migrates on app/`init_db` startup only. **Do not** start sync scripts. |
| **After era URL backfill** | Run `migrate_image_scan_status.py --apply`, then enable cron for `sync_image_urls.py` |
| **After most URLs exist** | Cron `sync_image_downloads.py` (avoid parallel with URL sync on same VPN) |

## Suggested cron (example)

Installed on this host (user crontab):

```cron
# Phillies image URL recheck (Sundays 3am, ~40 min)
0 3 * * 0 cd /home/scutrufello/phillies-cards && ./venv/bin/python scripts/sync_image_urls.py --limit 2000 >> data/sync_image_urls.log 2>&1
# Phillies image download catch-up (daily 4am, ~17 min)
0 4 * * * cd /home/scutrufello/phillies-cards && sg devagent -c './venv/bin/python scripts/sync_image_downloads.py --limit 500 >> data/sync_image_downloads.log 2>&1'
```

## Do not run in parallel

- `sync_image_urls.py` + era `backfill_card_images.py` → duplicate ViewCard traffic, 429s
- `sync_image_downloads.py` + bulk Playwright download → same
- One TCDB-scraping job per VM/VPN tunnel

## Future: new set scrape hook

When the team scraper finishes a set, either:

1. Leave new cards with `image_url_checked_at = NULL` → picked up by nightly URL sync, or
2. Call ViewCard for that `set_id` immediately (small sets only)

No scraper hook is wired yet; URL sync covers new cards via NULL `checked_at`.
