"""Franchise and product-type detection from retailer product titles."""

import re

FRANCHISES: dict[str, re.Pattern] = {
    # Some card shops title preorders with the set name alone ("Delta Reign Booster Bundle").
    "pokemon": re.compile(
        r"pok[eé]mon|\bptcg\b|\bpkm\b|mega\s*evolution|delta\s*reign|ascended\s*heroes|phantasmal\s*flames|"
        r"perfect\s*order", re.I),
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

# Sleeves, binders, deck boxes...: never "sealed product", even when a deck/box word also matches.
ACCESSORY = re.compile(r"sleeves|binder(?!\s+collection)|deck\s*box|playmat|portfolio|toploader|pocket\s*pages|protector", re.I)

# Checked in order: more specific types first.
PRODUCT_TYPES: list[tuple[str, re.Pattern]] = [
    ("booster_bundle", re.compile(r"booster\s*bundle", re.I)),
    ("elite_trainer_box", re.compile(r"elite\s*trainer\s*box|\betb\b", re.I)),
    ("booster_box", re.compile(r"booster\s*(box|display)|\bdisplay\b", re.I)),
    ("premium_collection", re.compile(r"(premium|ultra[-\s]*premium|super[-\s]*premium)\s*collection|\bprem\.?\s*coll", re.I)),
    ("collection_box", re.compile(r"collection|box\s*set|gift\s*(box|set)|toolkit|trove", re.I)),
    ("tin", re.compile(r"\btins?\b", re.I)),
    ("blister", re.compile(r"blister|checklane|\b\d\s*-?\s*pack\b", re.I)),
    ("starter_deck", re.compile(r"starter|structure\s*deck|theme\s*deck|battle\s*deck|commander\s*deck|\bdeck\b", re.I)),
    ("booster_pack", re.compile(r"booster|\bpacks?\b|sleeved", re.I)),
    ("accessory", ACCESSORY),
]

# Franchise merchandise that isn't sealed card product.
NON_CARD = re.compile(
    r"plush|figure|acrylic(?!.*\bbundle\b)|figurine|t-?shirt|hoodie|pyjama|costume|lego|mega\s*construx|\bmega\s+pok|puzzle|"
    r"model\s*kit|4d\s*build|build\s*(?:&|and)\s*show|clip\W*(?:n|and|&)\W*go|surprise\s*attack|battle\s*game|"
    r"bandolier|monopoly|guess\s*who|trainer\s*guess|"
    r"nintendo\s*switch|video\s*game|lunch\s*box|drink\s*bottle|backpack|book\b|annual|"
    r"sticker|colouring|dvd|blu-?ray|squishmallow|cushion|blanket|watch\b|weekly\s*play|\bdraft\s*-\s*\d|"
    r"socks|trunks|trainers|wrapping|gift\s*bag|\blamp\b|alarm\s*clock|comforter|\bthrow\b|christmas\s*cards|ticket|"
    r"\b\d{1,2}(?::\d{2})?\s*[ap]m\b",  # a store event's start time: "Tournament Wed 12th August 6:30pm"
    re.I,
)

# Single cards: collector numbers "(199/165)" / "199/165" / "065a/167", set codes "[JUSH-EN040]" / "OP09-118" /
# "[VEN - 034/166]" / "- Radiance R04a", and a card shop's trailing set name "Stingcaster Mage [Reality Fracture]".
# Also MTG singles in round brackets: "Tireless Tracker (Extended Art) (308) (Commander: Star Trek) (TRC)",
# "Biorhythm (Surge Foil) (Secret Lair Countdown Kit) (SLC)".
# Sealed titles use short codes ("Vault Bundle [RAD]") or a notice ("[Pre-Order]").
SINGLE_CARD = re.compile(
    r"\b(?i:psa|bgs|cgc)\s*\d|"  # a graded card: "PSA 10 Japanese Pokémon CLL Clefairy"
    r"\(\d{1,4}[a-z]?\)\s*\(|\)\s*\([A-Z0-9]{3,5}\)\s*$|"
    r"\(\s*\d{1,4}\s*/\s*\d{1,4}\s*\)|\b[A-Z]{0,2}\d{1,3}[a-z*]?/\d{2,3}\b|\b[A-Z0-9]{2,5}-[A-Z]{0,2}\d{3}\b|"
    r"\[[A-Z0-9]{2,5}\s*-\s*\d{1,4}[^\]]*\]|\s-\s.*\b[A-Z]\d{2}[a-z]?$|"
    r"\[(?!(?i:pre-?\s*order|limit|sale|new\b))[^\]]*[a-z ][^\]]*\]\s*$"
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


def is_sealed_product(title: str, franchise: str | None = None, ptype: str | None = None) -> bool:
    """Sealed product from one of our games (boxes, bundles, packs, tins, decks, named sets...).

    Discovery and keyword watches use this so singles ("Charizard ex (199/165)") and accessories
    (sleeves, portfolios) don't flood channels. Titles
    with no recognisable type still count ("Disney Lorcana Azurite Sea" is a set release).
    """
    ptype = ptype or ptype_of(title)
    return (is_card_product(title, franchise) and ptype != "accessory" and not ACCESSORY.search(title)
            and not is_single_card(title))


def is_single_card(title: str) -> bool:
    return SINGLE_CARD.search(title) is not None


def matches_query(text: str, query: str) -> bool:
    """Every whitespace-separated token of the query appears in the text (case-insensitive).

    Tokens are normalised so "pokemon" matches "Pokémon" and "30th" matches "30th".
    """
    haystack = _normalise(text)
    return all(token in haystack for token in _normalise(query).split())


def _normalise(text: str) -> str:
    return text.lower().replace("é", "e").replace("-", " ")
