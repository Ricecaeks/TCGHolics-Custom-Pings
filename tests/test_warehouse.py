"""The Warehouse: category tiles and product JSON-LD (fixtures trimmed from the live site 2026-10-29)."""

from conftest import load_fixture

from tcgpings.models import Level
from tcgpings.retailers.base import REGISTRY
from tcgpings.retailers.warehouse import TRADING_CARDS, WarehouseAdapter, parse_product, parse_tiles

ID, NAME, CONFIG, _COLOR = WarehouseAdapter.default_retailers[0]
ROW = {"id": ID, "adapter": "warehouse", "name": NAME, "config": CONFIG,
       "requests_per_minute": 12, "proxy_policy": "direct", "color": None}


class Resp:
    def __init__(self, text):
        self.text = text


class FakeHttp:
    browser = None

    def __init__(self, *pages):
        self.pages = list(pages)
        self.urls = []

    async def get(self, policy, url, **kw):
        self.urls.append(url)
        return Resp(self.pages.pop(0) if self.pages else "")


def test_registered():
    assert REGISTRY["warehouse"] is WarehouseAdapter
    assert CONFIG["categories"] == [TRADING_CARDS]


def test_parse_tiles_stock_price_and_marketplace():
    products = parse_tiles(load_fixture("warehouse", "listing.html"))
    assert [(p.sku, p.price_cents, p.online.level) for p in products] == [
        ("R3059372", 1499, Level.IN),
        ("R3068683", 2499, Level.IN),
        ("R3083239", 999, Level.OUT),  # FIND_IN_STORE: in stores, not online
    ]
    pokemon = products[2]
    assert pokemon.title == "Pokemon ME 5 Pitch Black Blisters LIMIT 10 PER CUSTOMER"
    assert pokemon.url == "https://www.thewarehouse.co.nz/p/pokemon-me-5-pitch-black-blisters-limit-10-per-customer/R3083239.html"
    assert pokemon.image.startswith("https://www.thewarehouse.co.nz/dw/image/") and "&amp;" not in pokemon.image
    assert pokemon.atc_url is None
    # third-party marketplace sellers only when asked for
    assert "M37023187" in {p.sku for p in parse_tiles(load_fixture("warehouse", "listing.html"), marketplace=True)}


def test_parse_product_json_ld():
    p = parse_product(load_fixture("warehouse", "product.html"), "R3059372")
    assert (p.sku, p.price_cents, p.online.level) == ("R3059372", 1499, Level.IN)
    assert p.url.endswith("/yu-gi-oh-rarity-collection-v-5-x-card-blister/R3059372.html")
    assert parse_product("<html>Just a moment...</html>", "R1") is None


async def test_discover_pages_newest_first_and_stops_on_short_page():
    a = WarehouseAdapter(ROW, FakeHttp(load_fixture("warehouse", "listing.html")))
    products = await a.discover()
    assert len(products) == 3
    assert a.http.urls == [
        f"https://www.thewarehouse.co.nz/search?cgid={TRADING_CARDS}&srule=newest&start=0&sz=32"
    ]


async def test_search_and_fetch():
    a = WarehouseAdapter(ROW, FakeHttp(load_fixture("warehouse", "listing.html"), load_fixture("warehouse", "product.html")))
    assert len(await a.search("pokemon 30th")) == 3
    assert a.http.urls[0] == "https://www.thewarehouse.co.nz/search?q=pokemon%2030th&srule=newest&start=0&sz=32"
    [p] = await a.fetch_products(["R3059372"])
    assert p.title.startswith("Yu-Gi-Oh!") and a.http.urls[1] == "https://www.thewarehouse.co.nz/p/x/R3059372.html"


def test_parse_ref_and_url_match():
    a = WarehouseAdapter(ROW, FakeHttp())
    assert a.parse_ref("https://www.thewarehouse.co.nz/p/pokemon-me-5/R3083239.html") == "R3083239"
    assert a.matches_url("https://www.thewarehouse.co.nz/p/x/R1.html")
    assert not a.store_stock_enabled
