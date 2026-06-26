"""Year-list taxonomy, display overrides, and completion helpers for CardSet rows."""
from __future__ import annotations

import re

from app.models import CardSet

YEAR_LIST_CATEGORIES: tuple[tuple[str, str], ...] = (
    ("major_licensed", "Major Licensed Releases"),
    ("major_unlicensed", "Major Unlicensed Releases"),
    ("minor_licensed", "Minor Licensed Releases"),
    ("minor_unlicensed", "Minor Unlicensed Releases"),
    ("minor_league", "Minor League Releases"),
    ("oddball_regional", "Oddball & Regional"),
    ("promo_team", "Promos, Giveaways, & Team Issues"),
)

CATEGORY_LABEL_BY_KEY = dict(YEAR_LIST_CATEGORIES)
CATEGORY_KEYS = tuple(CATEGORY_LABEL_BY_KEY.keys())

_YEAR_PROMO_TEAM_RE = re.compile(
    r"(?i)"
    r"(\bpromo\b|"
    r"stadium giveaway|"
    r"team issue|"
    r"\bteam set\b|"
    r"kids club|"
    r"club 215|"
    r"bobblehead|"
    r"wrapper redemption|"
    r"industry conference|"
    r"\bnscc\b|"
    r"national sports collectors convention|"
    r"\bsga\b|"
    r"rip night|"
    r"fan appreciation|"
    r"fan fest|"
    r"\bfest autograph\b|"
    r"\bphoto day\b|"
    r"military appreciation|"
    r"first pitch|"
    r"ticket giveaway|"
    r"luncheon|"
    r"meet\s+and\s+greet|"
    r"vip\s+event|"
    r"photocards?|"
    r"\bcard show\b)",
)

_YEAR_MILB_RE = re.compile(
    r"(?i)"
    r"\b(milb|minor\s+league|"
    r"class\s*[ad]\b|single[-\s]?a|double[-\s]?a|triple[-\s]?a|"
    r"threshers|blueclaws|ironpigs|fightin\b|fightin'? phils|"
    r"lehigh valley|jersey shore|clearwater|lakewood|"
    r"clearwater threshers|jersey shore blueclaws|"
    r"\breading phillies\b|\breading fightin\b|"
    r"affiliate|"
    r"rise to the show|"
    r"\bprospect team\b|"
    r"\bstate league\b|\bfsl\b|\bcarolina league\b|\bmidwest league\b|"
    r"\bsouth atlantic\b|\bflorida state\b|\beastern league\b|\bpacific coast\b|"
    r"\binternational league\b|\btriple[-\s]?a\b|\bdouble[-\s]?a\b|\bsingle[-\s]?a\b)",
)

_YEAR_MAJOR_UNLICENSED_RE = re.compile(
    r"(?i)"
    r"\(unlicensed\)|"
    r"\bpanini\b|\bdonruss\b|\bleaf\b|\bonyx\b|\bsage\b|\bchoice\b|"
    r"\bwild card\b|historic autographs|\bpress pass\b|\bfutera\b|\brazor\b|"
    r"\btristar\b",
)

_YEAR_MAJOR_LICENSED_RE = re.compile(
    r"(?i)"
    r"\b("
    r"topps|bowman|bowman'?s|stadium club|upper deck|\bfleer\b|\bscore\b|"
    r"finest|heritage|archives|gypsy queen|big league|pro debut|"
    r"museum collection|tribute|tier one|sterling|five star|diamond icons|"
    r"gilded|pristine|dynasty|lucent|black.?white|brooklyn collection|"
    r"chrome|cosmic chrome|"
    r"allen\s*&\s*ginter|allen.{0,5}ginter"
    r")\b",
)

_YEAR_MINOR_LICENSED_RE = re.compile(
    r"(?i)\b(pacific|pinnacle|skybox|classic|action packed|pro cards|studio)\b",
)

_YEAR_MINOR_UNLICENSED_RE = re.compile(
    r"(?i)\b(impel|star pics|midland|grandstand)\b",
)


def _is_bowmans_best_product(text: str) -> bool:
    return bool(re.search(r"(?i)bowman'?s?\s+best\b", text))


def _is_best_brand_product(text: str) -> bool:
    """Best / Best Cards (e.g. 1990 Best Reading Phillies), not Bowman's Best."""
    if _is_bowmans_best_product(text):
        return False
    return bool(re.search(r"(?i)\bbest\b", text))


def auto_year_list_category(card_set: CardSet) -> str:
    text = f"{card_set.full_name} {card_set.base_name}"
    if _YEAR_PROMO_TEAM_RE.search(text):
        return "promo_team"
    if _YEAR_MILB_RE.search(text):
        return "minor_league"
    if _is_bowmans_best_product(text):
        return "major_licensed"
    if _YEAR_MAJOR_UNLICENSED_RE.search(text):
        return "major_unlicensed"
    if _is_best_brand_product(text):
        return "minor_unlicensed"
    if _YEAR_MINOR_UNLICENSED_RE.search(text):
        return "minor_unlicensed"
    if _YEAR_MINOR_LICENSED_RE.search(text):
        return "minor_licensed"
    if _YEAR_MAJOR_LICENSED_RE.search(text):
        return "major_licensed"
    return "oddball_regional"


def effective_year_list_category(card_set: CardSet) -> str:
    if getattr(card_set, "category_source", "auto") == "manual" and card_set.year_list_category:
        return card_set.year_list_category
    return auto_year_list_category(card_set)


def auto_year_list_category_label(card_set: CardSet) -> str:
    return CATEGORY_LABEL_BY_KEY[auto_year_list_category(card_set)]


def effective_year_list_category_label(card_set: CardSet) -> str:
    return CATEGORY_LABEL_BY_KEY[effective_year_list_category(card_set)]


def year_list_display_name(card_set: CardSet) -> str:
    override = getattr(card_set, "display_name_override", None)
    if override and str(override).strip():
        return str(override).strip()
    return card_set.full_name


def set_is_hidden(card_set: CardSet) -> bool:
    return bool(getattr(card_set, "is_hidden", False))


def set_counts_toward_completion(card_set: CardSet) -> bool:
    return bool(getattr(card_set, "counts_toward_completion", True))


def card_counts_toward_completion(card_set: CardSet, card) -> bool:
    return set_counts_toward_completion(card_set) and bool(card.counts_toward_completion)
