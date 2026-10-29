import pytest

from tcgpings.engine.keywords import KeywordFilter

TITLES = {
    "bundle30": "Pokémon TCG: 30th Celebration Booster Bundle",
    "etb": "Pokemon Scarlet & Violet Prismatic Evolutions Elite Trainer Box",
    "upc": "Pokemon TCG Mega Charizard X ex Ultra-Premium Collection",
    "sleeves": "Pokemon Trading Card Pikachu Toploader & Penny Sleeves",
    "bundle151": "PKM 151 Booster Bundle",
    "mtg": "Magic The Gathering Trading Card Game: Reality Fracture - Bundle",
}


def passing(expr):
    f = KeywordFilter.parse(expr)
    return sorted(k for k, t in TITLES.items() if f.matches(t))


def test_alternatives_and_all_words():
    assert passing("30th booster bundle, elite trainer box") == ["bundle30", "etb"]


def test_word_order_and_accents_do_not_matter():
    assert passing("bundle 30th pokemon") == ["bundle30"]


def test_excludes_win():
    assert passing("pokemon, -sleeves") == ["bundle151", "bundle30", "etb", "upc"]
    assert passing("pokemon -sleeves -etb") == ["bundle151", "bundle30", "upc"]


def test_shorthands_both_ways():
    assert passing("etb") == ["etb"]
    assert passing("upc") == ["upc"]              # "Ultra-Premium Collection" with a hyphen
    assert passing("bb") == ["bundle151", "bundle30"]
    assert passing("pokemon booster bundle") == ["bundle151", "bundle30"]  # PKM -> pokemon
    assert passing("mtg bundle") == ["mtg"]


def test_empty_and_exclude_only_filters():
    assert KeywordFilter.parse("").empty
    assert passing("") == sorted(TITLES)
    assert passing("-sleeves, -magic") == ["bundle151", "bundle30", "etb", "upc"]


def test_word_prefix_matching_not_substrings():
    f = KeywordFilter.parse("box")
    assert f.matches("Booster Boxes") and not f.matches("Toolbox")


@pytest.mark.parametrize("expr, text", [
    ("30th booster bundle, elite trainer box, -sleeves", "30th + booster + bundle OR elite + trainer + box — excluding sleeves"),
    ("", "everything"),
])
def test_describe(expr, text):
    assert KeywordFilter.parse(expr).describe() == text


def test_newlines_and_semicolons_separate_too():
    assert passing("30th\nelite trainer box; upc") == ["bundle30", "etb", "upc"]
