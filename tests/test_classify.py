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
    ("Pokemon Clip And Go Jigglypuff with Moon Ball", None, False),
    ("Pokemon Surprise Attack Poke Ball Battle Game Larvitar & Scorbunny", None, False),
    ("MEGA Pokémon - Vulpix Evolution Set", None, False),
    ("Pokemon TCG Mega Evolution Elite Trainer Box", None, True),
    ("Pokemon TCG Poke Ball Tin", None, True),
    # Kmart
    ("Pokemon TCG: Ultra Pro 9-Pocket Pages", None, False),
    ("Pokemon Trading Card Game: Mega Evolution Pitch Black Booster Bundle", None, True),
    # Collectors Guild titles Delta Reign preorders by the set name alone, some with an acrylic case
    ("Delta Reign Booster Bundle & 3 Pack Blister Bundle (Limit 1, Pick-Up, Pre-Order)", None, True),
    ("Delta Reign Booster Box & Guilded Acrylic Case Bundle (Limit 1, Pick-Up, Pre-Order)", None, True),
    ("Pokemon Acrylic Display Case", None, False),
    ("Pokemon Acrylic Stand - Pikachu", None, False),
])
def test_is_sealed_product(title, franchise, expected):
    from tcgpings.classify import is_sealed_product

    assert is_sealed_product(title, franchise) is expected


@pytest.mark.parametrize(
    "title, single",
    [
        ("Stingcaster Mage [Reality Fracture]", True),
        ("PSA 10 Japanese Pokémon CLL Clefairy", True),
        ("Pokemon TCG Mega Evolution Elite Trainer Box - Mega Lucario ex", False),
        ("Q, Stacking the Deck (Showcase) (Surge Foil) [Star Trek]", True),
        ("Traveling Chocobo (Borderless) (Chocobo Track Foil) [FINAL FANTASY]", True),
        ("Resonating Strike [VEN - 034/166]", True),
        ("Emissary Escort (EOE Bundle) [UMP - 399]", True),
        ("Seraphine Not Alone (Alternate Art) - Radiance 138a/167", True),
        ("Kai'Sa Rebel - Radiance SP4/005", True),
        ("Body Rune (Alternate Art) - Radiance R04a", True),
        ("Radiance - Vault Bundle [RAD]", False),
        ("Attack of the Vine! Collection Starter Set - Rapunzel Edition [13]", False),
        ("Pokemon 30th Celebration Booster Bundle [Pre-Order]", False),
        ("**PRE-ORDER** MTG Play Booster Box - Star Trek", False),
        ("Pokemon TCG 30th Celebration Booster Bundle - 2 per Customer", False),
        ("Pokemon Trading Card Game: 30th Celebration Pokemon ex Box - Assorted", False),
        ("Tireless Tracker (Extended Art) (308) (Commander: Star Trek) (TRC)", True),
        ("Mountain (0566) (Surge Foil) (566) (Star Trek) (TRK)", True),
        ("Biorhythm (Surge Foil) (Secret Lair Countdown Kit) (SLC)", True),
        ("Star Trek Collector Booster Box (TRK)", False),
        ("Delta Reign Booster Bundle & 3 Pack Blister Bundle (Limit 1, Pick-Up, Pre-Order)", False),
    ],
)
def test_is_single_card(title, single):
    from tcgpings.classify import is_single_card

    assert is_single_card(title) is single


@pytest.mark.parametrize("title", [
    "One Piece Weekly Play - 19 Nov 2026", "Riftbound - Radiance Draft - 22 Nov 2026",
    "One Piece Tournament Wed 12th August 6:30pm", "Delta Reign Pre-Release Thursday Oct 29 2026 @ 6:30PM Mt Roskill",
])
def test_store_events_are_not_card_products(title):
    from tcgpings.classify import is_card_product

    assert not is_card_product(title)


def test_binder_collection_is_sealed_but_a_binder_is_not():
    from tcgpings.classify import is_sealed_product

    assert is_sealed_product("Pokemon TCG: 30th Celebration Binder Collection")
    assert not is_sealed_product("Pokemon TCG: Ultra Pro 9-Pocket Binder")


@pytest.mark.parametrize("title", [
    "Pokemon Boys' Crew Socks 2 Pack", "Pokemon Christmas Wrapping Paper", "Teknofun Pokemon Happy Pikachu 25cm LED Lamp",
    "Pokemon Throw 127cm x 152cm", "Pokemon - Delta Reign Pre-Release Ticket",
])
def test_merchandise_and_event_tickets_are_not_card_products(title):
    assert not is_card_product(title)


@pytest.mark.parametrize("title, franchise", [
    # Titles from Game Roost, Card Masters, Otakumart, HobbiXchange and Retrospace (November 2026).
    ("Gundam Card Game: Booster Pack - Dual Impact GD02", "gundam"),
    ("PRE ORDER - Gundam Card Game: Booster Display –   [GD06]", "gundam"),
    ("Gundam Card Game: Gundam Assemble – Premium Collection:  Iron Blooded Orphans PC01A", "gundam"),
    ("Dragon Ball Super Card Game Fusion World Starter Deck Vegeta Mini [FS07]", "dragonball"),
    ("Dragon Ball Super Card Game - Fusion World FB-11 Boosters", "dragonball"),
    ("Dragon Ball Z Super The Dark Invasion Starter Deck Series 3 Cross Worlds", "dragonball"),
    ("FB05 New Adventure Booster Pack Dragon Ball Super Sealed", "dragonball"),  # title + Shopify type
])
def test_gundam_and_dragon_ball_card_games(title, franchise):
    from tcgpings.classify import franchise_of, is_sealed_product

    assert franchise_of(title) == franchise and is_sealed_product(title)


@pytest.mark.parametrize("title", [
    "RG 1/144 UNICORN GUNDAM Model Kit", "MGSD Wing Gundam Zero EW Model Kit",
    "GUNDAM - MASTER GRADE SD (MGSD) GUNDAM BARBATOS (On Sale)", "GUNDAM MOBILE SUIT ENSEMBLE -  Blind Box",
    "Funko Pop! Plus Mobile Suit Gundam - Gundam Deathscythe Vinyl Figure",
    "Dragon Ball Z - Cell (First Form) Bitty Pop! 4 Pack", "Funko Pop! Dragon Ball Z - Frieza Vinyl Figure",
    "BANDAI - DRAGON BALL DAIMA MODEL KIT SON GOKU (MINI) & VEGETA (MINI)",
    "Dragon Shield Halloween 2026 - Brushed Art Sleeves",
    "Gundam Barbatos Lupus (GD03-050) - Steel Requiem Holofoil Gundam Card Game Single",  # a single
])
def test_gunpla_figures_and_singles_are_not_sealed_card_games(title):
    from tcgpings.classify import is_sealed_product

    assert not is_sealed_product(title)


def test_retrospace_titles():
    from tcgpings.classify import is_sealed_product

    assert is_sealed_product("Pokemon Mega Evolution Pitch Black Zarude 2-Pack Blister [2 Booster Packs & Coin]")
    assert not is_sealed_product("Yu-Gi-Oh! Jaden & Yubel Card Case")
    assert not is_sealed_product("Yu-Gi-Oh! Jaden & Yubel Game Mat")
    assert not is_sealed_product("Stingcaster Mage [Reality Fracture]")  # still a single


@pytest.mark.parametrize("title", [
    "Gundam Card Game GD06 Stardust Trails Release Event - SEALED - 31 Oct 2026",
    "Gundam Card Game Newtype Challenge 2026 - MISSION 5 (December) - 5 Dec 2026",
    "GUNDAM CARD GAME 1st Anniversary Event Mt Roskill, Sunday October 18, 2026 2:30 p.m",
    "One Piece Card Game EB05 HEROINES BATTLE Release Event! - 07 Nov - 7 Nov 2026",
    "Magic the Gathering Pre-Release Event: Star Trek",
    "Pokemon - Delta Reign Pre-Release (MONDAY)",
    "Riftbound: League of Legends TCG – Pre-Rift Vendetta Mt Roskill",
])
def test_store_event_entries_are_not_products(title):
    from tcgpings.classify import is_sealed_product

    assert not is_sealed_product(title)


@pytest.mark.parametrize("title", [
    "MTG Prerelease Kit - The Hobbit", "Magic The Gathering - Reality Fracture Prerelease Pack",
    "Riftbound: League of Legends TCG Vendetta Pre-Rift Kit", "Pokemon TCG - Iono Premium Tournament Collection",
])
def test_prerelease_kits_are_still_sealed(title):
    from tcgpings.classify import is_sealed_product

    assert is_sealed_product(title)


def test_a_bracketed_deck_code_is_not_a_card_number():
    from tcgpings.classify import is_sealed_product, is_single_card

    assert is_sealed_product("One Piece TCG - Learn Together Deck [LT-01]")
    assert is_single_card("Ultra Rare [VEN - 034/166]")
