"""Retrospace: listing tiles, stock labels and product pages (fixtures from the live site 2026-11-04)."""

from conftest import load_fixture

from tcgpings.models import Level
from tcgpings.retailers.base import REGISTRY
from tcgpings.retailers.retrospace import (
    CATEGORIES, GONE_AFTER_SCANS, NEWEST, RetrospaceAdapter, is_card_path, parse_product, parse_stock, parse_tiles,
)

ID, NAME, CONFIG, _COLOR = RetrospaceAdapter.default_retailers[0]
ROW = {"id": ID, "adapter": "retrospace", "name": NAME, "config": CONFIG,
       "requests_per_minute": 10, "proxy_policy": "direct", "color": None}
ZARUDE = "games/pokemon-cards/pokemon-mega-evolution-pitch-black-zarude"
BOOSTERS = "games/pokemon-cards/pokemon-tcg-mega-evolution-pitch-black-boosters"
TIN = "games/yu-gi-oh-cards/yu-gi-oh-2022-tin-of-the-pharaohs-gods-mega"


class Resp:
    def __init__(self, text):
        self.text = text


class FakeHttp:
    """Answers a category "load more" request with `category`, the newest listing with `newest`."""

    def __init__(self, category="", newest="", page=""):
        self.category, self.newest, self.page = category, newest, page
        self.calls = []

    async def get(self, policy, url, **kw):
        self.calls.append((url, kw.get("params")))
        if url.endswith(f"/{NEWEST}/more/"):
            return Resp(self.newest)
        if url.endswith("/more/"):
            return Resp(self.category if url.endswith("/pokemon-cards/more/") else "")
        return Resp(self.page)


def test_registered():
    assert REGISTRY["retrospace"] is RetrospaceAdapter
    assert CONFIG["categories"] == CATEGORIES


def test_stock_labels():
    assert parse_stock("2 in stock")[0] == parse_stock("2 IN STOCK")[0]
    assert (parse_stock("2 in stock")[0].level, parse_stock("2 in stock")[0].qty) == (Level.IN, 2)
    assert parse_stock("in stock") == (parse_stock("in stock")[0], None) and parse_stock("in stock")[0].level is Level.IN
    stock, note = parse_stock("Pre-Order April 2027")
    assert stock.level is Level.IN and note == "Pre-Order April 2027"
    assert parse_stock("Special Order (Ships in 2 weeks)")[0].level is Level.OUT  # ordered in, not stock
    assert parse_stock("Special Order (Ships in 5-6 Weeks)")[0].level is Level.OUT
    assert parse_stock("Coming soon")[0].level is Level.UNKNOWN


def test_category_tiles():
    products = {p.sku: p for p in parse_tiles(load_fixture("retrospace", "category.html"))}
    assert set(products) >= {ZARUDE, BOOSTERS}
    z = products[ZARUDE]
    assert z.title == "Pokemon Mega Evolution Pitch Black Zarude 2-Pack Blister [2 Booster Packs & Coin]"
    assert (z.online.level, z.online.qty, z.price_cents) == (Level.IN, 2, 3499)
    assert z.url == f"https://www.retrospace.co.nz/{ZARUDE}/"
    assert z.image.startswith("https://www.retrospace.co.nz/assets/resized/") and "?k=" in z.image
    assert products[BOOSTERS].online.qty is None and products[BOOSTERS].online.level is Level.IN


def test_newest_listing_keeps_card_games_only():
    products = {p.sku: p for p in parse_tiles(load_fixture("retrospace", "newest.html"))}
    assert "cards/dragonball-z-cards/dragon-ball-super-card-game-fusion-world" in products
    assert not any("binder" in p.title.lower() or "sleeves" in p.title.lower() for p in products.values())


def test_search_skips_category_tiles_and_merchandise():
    products = parse_tiles(load_fixture("retrospace", "search.html"))
    assert products and all(is_card_path(p.sku) for p in products)
    assert not any(p.title in ("Pokemon Cards", "Pokemon - Mugs") for p in products)


def test_card_paths():
    assert is_card_path(ZARUDE) and is_card_path("cards/dragonball-z-cards/x")
    assert is_card_path("in-stock/tcg-collector-cards-in-stock/riftbound-league-of-legends-tcg-in-stock/x")
    assert not is_card_path("games/card-accessories/card-sleeves/card-sleeves-ultra-pro/x")
    assert not is_card_path("other-memorabilia/mugs/pokemon-mugs/x")


def test_product_pages():
    p = parse_product(load_fixture("retrospace", "product.html"), ZARUDE)
    assert (p.online.level, p.online.qty, p.price_cents) == (Level.IN, 2, 3499)
    assert p.title.startswith("Pokemon Mega Evolution Pitch Black Zarude")
    assert p.image.startswith("https://www.retrospace.co.nz/assets/")
    tin = parse_product(load_fixture("retrospace", "product_special.html"), TIN)
    assert tin.title == "Yu-Gi-Oh! - 2022 Tin of the Pharaoh's Gods Mega Pack"
    assert (tin.online.level, tin.price_cents) == (Level.OUT, 1299)  # Special Order; related items are in stock
    assert parse_product("<html></html>", "x") is None


async def test_discover_reads_whole_categories_and_the_newest_cards():
    http = FakeHttp(load_fixture("retrospace", "category.html"), load_fixture("retrospace", "newest.html"))
    products = {p.sku for p in await RetrospaceAdapter(ROW, http).discover()}
    assert {ZARUDE, BOOSTERS, "cards/dragonball-z-cards/dragon-ball-super-card-game-fusion-world"} <= products
    urls = [u for u, _ in http.calls]
    assert urls == [f"https://www.retrospace.co.nz/{c}/more/" for c in CATEGORIES] + [
        f"https://www.retrospace.co.nz/{NEWEST}/more/"]
    assert http.calls[0][1] == {"start": 0, "howMany": 500}


async def test_a_product_that_leaves_its_category_goes_out_after_several_scans():
    listing = load_fixture("retrospace", "category.html")
    without = listing.replace("pokemon-mega-evolution-pitch-black-zarude", "gone")
    http = FakeHttp(listing)
    a = RetrospaceAdapter(ROW, http)
    assert ZARUDE in {p.sku for p in await a.discover()}
    http.category = without
    for _ in range(GONE_AFTER_SCANS - 1):
        assert ZARUDE not in {p.sku for p in await a.discover()}
    gone = [p for p in await a.discover() if p.sku == ZARUDE]
    assert len(gone) == 1 and gone[0].online.level is Level.OUT
    assert ZARUDE not in {p.sku for p in await a.discover()}


async def test_empty_categories_are_not_a_sell_out():
    http = FakeHttp(load_fixture("retrospace", "category.html"))
    a = RetrospaceAdapter(ROW, http)
    await a.discover()
    http.category = "<html>maintenance</html>"
    for _ in range(GONE_AFTER_SCANS + 1):
        assert await a.discover() == []
    assert a._missing == {}


async def test_fetch_and_parse_ref():
    http = FakeHttp(page=load_fixture("retrospace", "product.html"))
    a = RetrospaceAdapter(ROW, http)
    [p] = await a.fetch_products([ZARUDE])
    assert http.calls[0][0] == f"https://www.retrospace.co.nz/{ZARUDE}/" and p.online.qty == 2
    assert a.parse_ref(f"https://www.retrospace.co.nz/{ZARUDE}/?x=1") == ZARUDE
    assert a.parse_ref(f"/{ZARUDE}/") == ZARUDE and a.parse_ref(ZARUDE) == ZARUDE
    assert a.matches_url("https://www.retrospace.co.nz/games/x/")
