"""Franchise and product-type detection from retailer product titles."""

import re

FRANCHISES: dict[str, re.Pattern] = {
    "pokemon": re.compile(r"pok[eé]mon|\bptcg\b|\bpkm\b", re.I),
    "one_piece": re.compile(r"\bone\s*piece\b", re.I),
    "riftbound": re.compile(r"\briftbound\b", re.I),
    "mtg": re.compile(r"magic:?\s*the\s*gathering|\bmtg\b", re.I),
    "lorcana": re.compile(r"\blorcana\b", re.I),
    "yugioh": re.compile(r"yu-?\s*gi-?\s*oh", re.I),
}

FRANCHISE_NAMES = {
    "pokemon": "Pokémon",
    "one_piece": "One Piece",
    "riftbound": "Riftbound",
    "mtg": "Magic: The Gathering",
    "lorcana": "Lorcana",
    "yugioh": "Yu-Gi-Oh!",
}

# Checked in order: more specific types first.
PRODUCT_TYPES: list[tuple[str, re.Pattern]] = [
    ("booster_bundle", re.compile(r"booster\s*bundle", re.I)),
    ("elite_trainer_box", re.compile(r"elite\s*trainer\s*box|\betb\b", re.I)),
    ("booster_box", re.compile(r"booster\s*(box|display)|\bdisplay\b", re.I)),
    ("premium_collection", re.compile(r"(premium|ultra[-\s]*premium|super[-\s]*premium)\s*collection", re.I)),
    ("collection_box", re.compile(r"collection|box\s*set|gift\s*box", re.I)),
    ("tin", re.compile(r"\btins?\b", re.I)),
    ("blister", re.compile(r"blister|checklane|\b\d\s*-?\s*pack\b", re.I)),
    ("starter_deck", re.compile(r"starter|structure\s*deck|theme\s*deck|battle\s*deck|commander\s*deck|\bdeck\b", re.I)),
    ("booster_pack", re.compile(r"booster|\bpacks?\b|sleeved", re.I)),
    ("accessory", re.compile(r"sleeves|binder|deck\s*box|playmat|portfolio|toploader", re.I)),
]

# Franchise merchandise that isn't sealed card product.
NON_CARD = re.compile(
    r"plush|figure|acrylic|figurine|t-?shirt|hoodie|pyjama|costume|lego|mega\s*construx|puzzle|"
    r"nintendo\s*switch|video\s*game|lunch\s*box|drink\s*bottle|backpack|book\b|annual|"
    r"sticker|colouring|dvd|blu-?ray|squishmallow|cushion|blanket|watch\b",
    re.I,
)


def franchise_of(title: str) -> str | None:
    for key, pattern in FRANCHISES.items():
        if pattern.search(title):
            return key
    return None


def ptype_of(title: str) -> str | None:
    for key, pattern in PRODUCT_TYPES:
        if pattern.search(title):
            return key
    return None


def classify(title: str) -> tuple[str | None, str | None]:
    return franchise_of(title), ptype_of(title)


def is_card_product(title: str, franchise: str | None = None) -> bool:
    """`franchise` lets an adapter vouch for products whose title doesn't name the game (e.g. via tags)."""
    return (franchise or franchise_of(title)) is not None and not NON_CARD.search(title)


def matches_query(text: str, query: str) -> bool:
    """Every whitespace-separated token of the query appears in the text (case-insensitive).

    Tokens are normalised so "pokemon" matches "Pokémon" and "30th" matches "30th".
    """
    haystack = _normalise(text)
    return all(token in haystack for token in _normalise(query).split())


def _normalise(text: str) -> str:
    return text.lower().replace("é", "e").replace("-", " ")
