"""Paper Plus: category tiles and product JSON-LD (fixtures trimmed from the live site 2026-11-04)."""

from conftest import load_fixture

from tcgpings.models import Level
from tcgpings.retailers.base import REGISTRY
from tcgpings.retailers.paperplus import (
    GONE_AFTER_SCANS, TRADING_CARDS, PaperPlusAdapter, parse_product, parse_tiles,
)

ID, NAME, CONFIG, _COLOR = PaperPlusAdapter.default_retailers[0]
ROW = {"id": ID, "adapter": "paperplus", "name": NAME, "config": CONFIG,
       "requests_per_minute": 12, "proxy_policy": "direct", "color": None}
PITCH_BLACK = f"{TRADING_CARDS}/pokemon-tcg-mega-evolutions-5-pitch-black-booster"


class Resp:
    def __init__(self, text):
        self.text = text


class FakeHttp:
    def __init__(self, *pages):
        self.pages = list(pages)
        self.urls = []

    async def get(self, policy, url, **kw):
        self.urls.append(url)
        return Resp(self.pages.pop(0) if self.pages else "")


def test_registered():
    assert REGISTRY["paperplus"] is PaperPlusAdapter
    assert CONFIG["categories"] == [TRADING_CARDS]


def test_tiles():
    products = {p.sku: p for p in parse_tiles(load_fixture("paperplus", "category.html"))}
    assert len(products) == 10  # not the binder pages or the Trainer Guess game
    assert not any("Ultra Pro" in p.title or "Sinnoh" in p.title for p in products.values())
    p = products[PITCH_BLACK]
    assert p.title == "Pokemon TCG Mega Evolutions 5 Pitch Black Booster" and p.price_cents == 1099
    assert p.url == f"https://www.paperplus.co.nz/shop/{PITCH_BLACK}" and p.online.level is Level.IN
    assert p.image == "https://static-ppimages.freetls.fastly.net/product/2000079546841-1.jpg"


def test_product_page_json_ld():
    p = parse_product(load_fixture("paperplus", "product.html"), "x")
    assert (p.sku, p.price_cents, p.online.level) == (PITCH_BLACK, 1099, Level.IN)
    assert parse_product("<html></html>", "x") is None


async def test_a_product_that_leaves_the_listing_goes_out_after_several_scans():
    listing = load_fixture("paperplus", "category.html")
    without = listing.replace("pokemon-tcg-mega-evolutions-5-pitch-black-booster", "gone")
    http = FakeHttp(listing)
    a = PaperPlusAdapter(ROW, http)
    assert PITCH_BLACK in {p.sku for p in await a.discover()}
    for _ in range(GONE_AFTER_SCANS - 1):
        http.pages = [without]
        assert PITCH_BLACK not in {p.sku for p in await a.discover()}
    http.pages = [without]
    gone = [p for p in await a.discover() if p.sku == PITCH_BLACK]
    assert len(gone) == 1 and gone[0].online.level is Level.OUT
    http.pages = [without]
    assert PITCH_BLACK not in {p.sku for p in await a.discover()}


async def test_an_empty_page_is_not_a_sell_out():
    http = FakeHttp(load_fixture("paperplus", "category.html"))
    a = PaperPlusAdapter(ROW, http)
    await a.discover()
    for _ in range(GONE_AFTER_SCANS + 1):
        http.pages = ["<html>maintenance</html>"]
        assert await a.discover() == []
    assert a._missing == {}


async def test_fetch_and_parse_ref():
    http = FakeHttp(load_fixture("paperplus", "product.html"))
    a = PaperPlusAdapter(ROW, http)
    [p] = await a.fetch_products([PITCH_BLACK])
    assert http.urls == [f"https://www.paperplus.co.nz/shop/{PITCH_BLACK}"] and p.online.level is Level.IN
    assert a.parse_ref(f"https://www.paperplus.co.nz/shop/{PITCH_BLACK}?x=1") == PITCH_BLACK
    assert a.matches_url("https://www.paperplus.co.nz/shop/x")


def test_books_and_plush_are_not_card_products():
    tile = ('<article data-url="/shop/{path}" data-category="{category}">'
            '<span class="hidden js-product-data" data-name="{name}" data-price="29.99"></span></article>')
    page = "".join(tile.format(path=f"x/{i}", category=c, name=n) for i, (c, n) in enumerate([
        ("Pokemon", "Pokemon Select 30th Anniversary 8 Inch Plush"),
        ("Books", "Pokemon Encyclopedia"),
        ("Pokemon", "Pokemon TCG 30th Celebration Booster Bundle"),
        ("Trading Cards", "Disney Lorcana Starter Deck"),
    ]))
    assert [p.title for p in parse_tiles(page)] == [
        "Pokemon TCG 30th Celebration Booster Bundle", "Disney Lorcana Starter Deck"]
