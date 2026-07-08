import os
import sqlite3
import time
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, DeclarativeBase

import yaml

def load_config():
    config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.yaml")
    with open(config_path) as f:
        return yaml.safe_load(f)

class Base(DeclarativeBase):
    pass

_engine = None
_SessionLocal = None

def get_engine():
    global _engine
    if _engine is None:
        config = load_config()
        db_path = config["storage"]["db_path"]
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        _engine = create_engine(
            f"sqlite:///{db_path}",
            echo=False,
            connect_args={"timeout": 60},
        )
        _configure_sqlite(_engine)
    return _engine


def _configure_sqlite(engine) -> None:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=60000")
        cursor.close()

def get_session():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine())
    return _SessionLocal()

def init_db():
    from app.models import CardSet, Card  # noqa: F401
    engine = get_engine()
    Base.metadata.create_all(engine)
    _ensure_card_set_columns()
    _ensure_card_columns()
    _ensure_card_image_indexes()
    _ensure_cards_indexes()


def _ensure_card_set_columns():
    """Lightweight SQLite migration for new card_sets relationship columns."""
    config = load_config()
    db_path = config["storage"]["db_path"]
    if not os.path.isabs(db_path):
        db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), db_path)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(card_sets)")
    existing_columns = {row[1] for row in cur.fetchall()}

    if "canonical_parent_set_id" not in existing_columns:
        cur.execute("ALTER TABLE card_sets ADD COLUMN canonical_parent_set_id INTEGER")
    if "relationship_type" not in existing_columns:
        cur.execute("ALTER TABLE card_sets ADD COLUMN relationship_type VARCHAR")
    if "relationship_confidence" not in existing_columns:
        cur.execute("ALTER TABLE card_sets ADD COLUMN relationship_confidence FLOAT")

    admin_columns = {
        "year_list_category": "VARCHAR",
        "display_name_override": "VARCHAR",
        "is_hidden": "BOOLEAN NOT NULL DEFAULT 0",
        "sort_order": "INTEGER",
        "counts_toward_completion": "BOOLEAN NOT NULL DEFAULT 1",
        "admin_notes": "TEXT",
        "category_source": "VARCHAR NOT NULL DEFAULT 'auto'",
        "relationship_source": "VARCHAR NOT NULL DEFAULT 'auto'",
        "completion_source": "VARCHAR NOT NULL DEFAULT 'auto'",
    }
    for col, ddl in admin_columns.items():
        if col not in existing_columns:
            cur.execute(f"ALTER TABLE card_sets ADD COLUMN {col} {ddl}")

    cur.execute(
        "CREATE INDEX IF NOT EXISTS ix_card_sets_year_list_category "
        "ON card_sets(year_list_category)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS ix_card_sets_canonical_parent_set_id "
        "ON card_sets(canonical_parent_set_id)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS ix_card_sets_relationship_type "
        "ON card_sets(relationship_type)"
    )
    conn.commit()
    conn.close()


def _ensure_card_columns():
    """Lightweight SQLite migration for checklist completion rules."""
    config = load_config()
    db_path = config["storage"]["db_path"]
    if not os.path.isabs(db_path):
        db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), db_path)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(cards)")
    existing_columns = {row[1] for row in cur.fetchall()}

    if "counts_toward_completion" not in existing_columns:
        cur.execute(
            "ALTER TABLE cards ADD COLUMN counts_toward_completion BOOLEAN NOT NULL DEFAULT 1"
        )

    if "wants_upgrade" not in existing_columns:
        for attempt in range(12):
            try:
                cur.execute(
                    "ALTER TABLE cards ADD COLUMN wants_upgrade BOOLEAN NOT NULL DEFAULT 0"
                )
                break
            except sqlite3.OperationalError as exc:
                if "locked" not in str(exc).lower() or attempt >= 11:
                    raise
                time.sleep(2)
                conn.rollback()
                cur = conn.cursor()
                cur.execute("PRAGMA table_info(cards)")
                existing_columns = {row[1] for row in cur.fetchall()}
                if "wants_upgrade" in existing_columns:
                    break

    if "on_the_way" not in existing_columns:
        for attempt in range(12):
            try:
                cur.execute(
                    "ALTER TABLE cards ADD COLUMN on_the_way BOOLEAN NOT NULL DEFAULT 0"
                )
                break
            except sqlite3.OperationalError as exc:
                if "locked" not in str(exc).lower() or attempt >= 11:
                    raise
                time.sleep(2)
                conn.rollback()
                cur = conn.cursor()
                cur.execute("PRAGMA table_info(cards)")
                existing_columns = {row[1] for row in cur.fetchall()}
                if "on_the_way" in existing_columns:
                    break

    image_columns = {
        "image_scan_status": "VARCHAR",
        "image_url_checked_at": "VARCHAR",
        "user_image_front_local": "VARCHAR",
        "user_image_back_local": "VARCHAR",
    }
    for col, ddl in image_columns.items():
        if col not in existing_columns:
            for attempt in range(12):
                try:
                    cur.execute(f"ALTER TABLE cards ADD COLUMN {col} {ddl}")
                    break
                except sqlite3.OperationalError as exc:
                    if "locked" not in str(exc).lower() or attempt >= 11:
                        raise
                    time.sleep(2)
                    conn.rollback()
                    cur = conn.cursor()
                    cur.execute("PRAGMA table_info(cards)")
                    existing_columns = {row[1] for row in cur.fetchall()}
                    if col in existing_columns:
                        break

    conn.commit()
    conn.close()


def _ensure_card_image_indexes():
    """Indexes for recurring image URL / download sync queries."""
    config = load_config()
    db_path = config["storage"]["db_path"]
    if not os.path.isabs(db_path):
        db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), db_path)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "CREATE INDEX IF NOT EXISTS ix_cards_image_url_checked_at "
        "ON cards(image_url_checked_at)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS ix_cards_image_scan_status "
        "ON cards(image_scan_status)"
    )
    conn.commit()
    conn.close()


def _ensure_cards_indexes():
    """
    Drop legacy uniqueness on (set_id, number, variant).

    That index collapses checklist rows for products with repeated labels like "NNO"
    and prevents storing distinct cards that differ only by tcdb_cid/player.
    """
    config = load_config()
    db_path = config["storage"]["db_path"]
    if not os.path.isabs(db_path):
        db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), db_path)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name='uq_set_number_variant'"
    )
    if cur.fetchone():
        cur.execute("DROP INDEX uq_set_number_variant")
    conn.commit()
    conn.close()
