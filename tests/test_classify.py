import pytest

from tcgpings.classify import classify, is_card_product, matches_query


@pytest.mark.parametrize(
    "title, franchise, ptype",
    [
        ("Pokémon TCG: 30th Celebration Booster Bundle", "pokemon", "booster_bundle"),
        ("Pokemon Scarlet & Violet Prismatic Evolutions Elite Trainer Box", "pokemon", "elite_trainer_box"),
        ("One Piece Card Game OP-09 Booster Box", "one_piece", "booster_box"),
        ("Riftbound: League of Legends TCG Origins Booster Display", "riftbound", "booster_box"),
        ("Magic: The Gathering Foundations Commander Deck", "mtg", "starter_deck"),
        ("MTG Duskmourn Play Booster", "mtg", "booster_pack"),
        ("Disney Lorcana Azurite Sea Gift Set Collection", "lorcana", "collection_box"),
        ("Yu-Gi-Oh! Structure Deck: Blue-Eyes White Destiny", "yugioh", "starter_deck"),
        ("Pokemon TCG Paldean Fates Tin", "pokemon", "tin"),
        ("Pokémon TCG Surging Sparks 3-Pack Blister", "pokemon", "blister"),
        ("Pokemon Ultra-Premium Collection Charizard", "pokemon", "premium_collection"),
    ],
)
def test_classify(title, franchise, ptype):
    assert classify(title) == (franchise, ptype)


@pytest.mark.parametrize(
    "title, expected",
    [
        ("Pokémon TCG: 30th Celebration Booster Bundle", True),
        ("Pokemon Pikachu Plush 30cm", False),
        ("Pokemon Legends Z-A Nintendo Switch", False),
        ("LEGO Pokemon set", False),
        ("Barbie Dreamhouse", False),
        ("Yu-Gi-Oh! 25th Anniversary Tin", True),
        ("PKM Elite Trainer Box - Scarlet & Violet", True),
        ("Scale Forge - Crystalguard | Pokémon TCG Elite Trainer Box Acrylic Case", False),
    ],
)
def test_is_card_product(title, expected):
    assert is_card_product(title) is expected


def test_matches_query_is_accent_and_case_insensitive():
    assert matches_query("Pokémon TCG: 30th Celebration Booster Bundle", "pokemon 30th bundle")
    assert not matches_query("Pokémon TCG: 151 Booster Bundle", "pokemon 30th")
    assert matches_query("Yu-Gi-Oh! Rarity Collection", "yu gi oh")


@pytest.mark.parametrize("title, franchise, expected", [
    ("Disney Lorcana Azurite Sea", None, True),                                  # set name only (Farmers)
    ("Disney Lorcana Reign of Jafar Illumineer's Trove", None, True),
    ("Pokemon Trading Card Mega Greninja Ex Prem Coll", None, True),
    ("Pokemon Trading Card Trainer's Toolkit", None, True),
    ("Pokemon Trading Card ME5 Pitch Black Booster Bundle", None, True),
    ("Pokemon Trading Card ME5 Pitch Black Portfolio", None, False),             # accessory
    ("Pokemon Trading Card Pikachu Toploader & Penny Sleeves", None, False),
    ("Mega Zeraora ex (114/084) [Mega Evolution: Pitch Black]", "pokemon", False),  # Shopify single
    ('"A Case for K9" [JUSH-EN040] Super Rare', "yugioh", False),
    ("Monkey.D.Luffy OP09-118 Secret Rare", "one_piece", False),
    ("Cards FIFA 365 Adrenalyn XL 2026 Soccer Tin, Assorted", None, False),     # not one of our games
    # Toyworld's Pokémon collection is mostly toys
    ("Disney Lorcana Series 8 Reign of Jafar Booster Sleeve", None, True),
    ("Disney Lorcana Series 5 Shimmering Skies Deck Box - Aladdin", None, False),  # accessory, not a deck
    ("4D Build Pokémon Model Kit - Eevee", None, False),
    ("Pokemon Clip N Go Chimchar & Repeat Ball", None, False),
    ("Pokemon Surprise Attack Poke Ball Battle Game Larvitar & Scorbunny", None, False),
    ("MEGA Pokémon - Vulpix Evolution Set", None, False),
    ("Pokemon TCG Mega Evolution Elite Trainer Box", None, True),
    ("Pokemon TCG Poke Ball Tin", None, True),
    # Kmart
    ("Pokemon TCG: Ultra Pro 9-Pocket Pages", None, False),
    ("Pokemon Trading Card Game: Mega Evolution Pitch Black Booster Bundle", None, True),
])
def test_is_sealed_product(title, franchise, expected):
    from tcgpings.classify import is_sealed_product

    assert is_sealed_product(title, franchise) is expected
