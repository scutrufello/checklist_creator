#!/usr/bin/env python3
"""Add variant column to cards and create unique index (set_id, number, variant)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import load_config

def main():
    config = load_config()
    db_path = config["storage"]["db_path"]
    if not os.path.isabs(db_path):
        db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), db_path)

    import sqlite3
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Check if column exists
    cur.execute("PRAGMA table_info(cards)")
    columns = [row[1] for row in cur.fetchall()]
    if "variant" not in columns:
        cur.execute("ALTER TABLE cards ADD COLUMN variant VARCHAR(200) NOT NULL DEFAULT ''")
        conn.commit()
        print("Added column variant")
    else:
        print("Column variant already exists")

    # Backfill empty string where null (shouldn't happen with default)
    cur.execute("UPDATE cards SET variant = '' WHERE variant IS NULL")
    conn.commit()

    # Create unique index if not exists
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name='uq_set_number_variant'"
    )
    if cur.fetchone() is None:
        cur.execute(
            "CREATE UNIQUE INDEX uq_set_number_variant ON cards(set_id, number, variant)"
        )
        conn.commit()
        print("Created unique index uq_set_number_variant")
    else:
        print("Index uq_set_number_variant already exists")

    conn.close()


if __name__ == "__main__":
    main()
