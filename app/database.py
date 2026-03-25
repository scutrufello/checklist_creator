import os
import sqlite3
from sqlalchemy import create_engine
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
        _engine = create_engine(f"sqlite:///{db_path}", echo=False)
    return _engine

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
