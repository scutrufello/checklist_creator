import json
import re
from sqlalchemy import Column, Integer, BigInteger, String, Boolean, ForeignKey, UniqueConstraint, Text, Float
from sqlalchemy.orm import relationship
from app.database import Base


def strip_redundant_variant_tag_prose(text: str) -> str:
    """
    TCDB often sends variation prose like 'SP, VAR VAR: Image Variation' while the same
    information lives in structured tags. Strip leading SP,/VAR chains for display (and storage).
    """
    text = (text or "").strip()
    if not text:
        return ""
    while True:
        prev = text
        text = re.sub(r"^SP\s*,\s*", "", text, flags=re.I).strip()
        text = re.sub(r"^VAR\s*,\s*", "", text, flags=re.I).strip()
        text = re.sub(r"^\s*VAR(?:IATION)?\s*[:\-]?\s*", "", text, flags=re.I).strip()
        if text == prev:
            break
    return text


class CardSet(Base):
    __tablename__ = "card_sets"

    id = Column(Integer, primary_key=True)
    # TCDB set id; largest values must stay within 64-bit SQLite integer binding
    tcdb_sid = Column(BigInteger, unique=True, nullable=False, index=True)
    full_name = Column(String, nullable=False)
    base_name = Column(String, nullable=False)
    variant_name = Column(String, nullable=True)
    year = Column(Integer, nullable=False, index=True)
    set_type = Column(String, nullable=False, default="standalone")  # base, parallel, insert, standalone
    parent_id = Column(Integer, ForeignKey("card_sets.id"), nullable=True)
    canonical_parent_set_id = Column(Integer, ForeignKey("card_sets.id"), nullable=True, index=True)
    relationship_type = Column(String, nullable=True, index=True)  # base, insert, parallel, variation, standalone
    relationship_confidence = Column(Float, nullable=True)

    parent = relationship("CardSet", remote_side=[id], foreign_keys=[parent_id], backref="children")
    canonical_parent = relationship("CardSet", remote_side=[id], foreign_keys=[canonical_parent_set_id])
    cards = relationship("Card", back_populates="card_set", order_by="Card.sort_number, Card.number, Card.variant")

    @property
    def display_name(self):
        if self.variant_name:
            return self.variant_name
        return self.full_name

    @property
    def url_slug(self):
        slug = re.sub(r"[^a-z0-9]+", "-", self.full_name.lower()).strip("-")
        return slug or f"set-{self.id}"

    @property
    def total_cards(self):
        return len(self.cards)

    @property
    def owned_cards(self):
        return sum(1 for c in self.cards if c.owned)

    def __repr__(self):
        return f"<CardSet {self.tcdb_sid} '{self.full_name}'>"


class Card(Base):
    __tablename__ = "cards"

    id = Column(Integer, primary_key=True)
    set_id = Column(Integer, ForeignKey("card_sets.id"), nullable=False, index=True)
    number = Column(String, nullable=False)
    variant = Column(String(200), nullable=False, default="")  # e.g. "" for base, "Kevin Hart image variation" for VAR
    sort_number = Column(BigInteger, nullable=True)
    player_name = Column(String, nullable=False)
    tcdb_cid = Column(String, unique=True, nullable=False, index=True)
    tcdb_url = Column(String, nullable=True)
    image_front_url = Column(String, nullable=True)
    image_back_url = Column(String, nullable=True)
    image_front_local = Column(String, nullable=True)
    image_back_local = Column(String, nullable=True)
    raw_tags_text = Column(String, nullable=True)
    tags = Column(Text, nullable=True)  # JSON array stored as text
    owned = Column(Boolean, default=False, nullable=False)

    card_set = relationship("CardSet", back_populates="cards")

    __table_args__ = (
        UniqueConstraint("set_id", "tcdb_cid", name="uq_set_card"),
        UniqueConstraint("set_id", "number", "variant", name="uq_set_number_variant"),
    )

    @property
    def tags_list(self):
        valid_exact = {
            "VAR", "AU", "AUTO", "MEM", "RELIC", "JERSEY", "PATCH",
            "RC", "SP", "SSP", "TC", "PR", "DK", "IP", "GU",
        }

        def _clean(tags):
            out = []
            seen = set()
            for t in tags or []:
                t = (t or "").strip()
                if not t or len(t) > 12:
                    continue
                u = t.upper()
                if re.match(r"^(SN/?\d+|/\d+)$", u):
                    pass
                elif u in valid_exact:
                    pass
                else:
                    continue
                if u not in seen:
                    seen.add(u)
                    out.append(u)
            return sorted(out, key=lambda x: (x != "VAR", x != "TC", x))

        if self.tags:
            try:
                return _clean(json.loads(self.tags))
            except (json.JSONDecodeError, TypeError):
                return []
        return []

    @tags_list.setter
    def tags_list(self, value):
        self.tags = json.dumps(value) if value else None

    @property
    def sort_key(self):
        """Extract numeric portion of card number for sorting."""
        num = ""
        for ch in self.number:
            if ch.isdigit():
                num += ch
        return int(num) if num else 0

    @property
    def variant_display(self):
        """Human-readable variation line without redundant SP/VAR prefix noise."""
        return strip_redundant_variant_tag_prose(self.variant or "")

    def __repr__(self):
        return f"<Card #{self.number} {self.player_name}>"
