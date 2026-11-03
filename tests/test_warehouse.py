"""The Warehouse: category tiles and product JSON-LD (fixtures trimmed from the live site 2026-10-29)."""

from conftest import load_fixture

from tcgpings.models import Level
from tcgpings.net.http import FetchError
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
    assert a.http.urls[0] == f"https://www.thewarehouse.co.nz/search?cgid={TRADING_CARDS}&srule=newest&start=0&sz=32"
    assert "cgid" not in a.http.urls[1] and len(a.http.urls) == 2  # the short page stopped the category


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


class SearchFails(FakeHttp):
    async def get(self, policy, url, **kw):
        if "q=" in url:
            raise FetchError(f"GET {url}: HTTP 429", 429)
        return await super().get(policy, url, **kw)


async def test_discovery_also_reads_a_search_and_keeps_each_product_once():
    listing = load_fixture("warehouse", "listing.html")
    http = FakeHttp(listing, listing)
    products = await WarehouseAdapter(ROW, http).discover()
    assert ["q=pokemon%20tcg" in u for u in http.urls] == [False, True]
    assert len({p.sku for p in products}) == len(products) > 0


async def test_a_failed_discovery_search_keeps_the_category_results():
    assert await WarehouseAdapter(ROW, SearchFails(load_fixture("warehouse", "listing.html"))).discover()


async def test_first_sighting_is_logged_per_listing_after_its_first_read(caplog):
    listing = load_fixture("warehouse", "listing.html")
    a = WarehouseAdapter(ROW, FakeHttp("", "", listing, ""))  # only the second category read has products
    caplog.set_level("INFO", "tcgpings.retailers.warehouse")
    await a.discover()
    assert "first shows" not in caplog.text
    await a.discover()
    assert "category" in caplog.text and "first shows R3083239" in caplog.text and "search" not in caplog.text


def test_in_store_only_tile_says_so():
    products = {p.sku: p for p in parse_tiles(load_fixture("warehouse", "listing.html"))}
    assert products["R3083239"].note == "In stores, not online"
    assert products["R3083239"].online.level is Level.OUT


def test_in_store_tiles_track_stores_nationwide():
    from tcgpings.retailers.warehouse import IN_STORES

    products = {p.sku: p for p in parse_tiles(load_fixture("warehouse", "listing.html"))}
    assert products["R3083239"].stores[IN_STORES].level is Level.IN
    assert all(p.stores is None or IN_STORES in p.stores for p in products.values())


async def test_a_product_that_leaves_the_listings_goes_out_after_several_scans():
    from tcgpings.retailers.warehouse import GONE_AFTER_SCANS, IN_STORES

    listing = load_fixture("warehouse", "listing.html")
    http = FakeHttp(listing, listing)
    a = WarehouseAdapter(ROW, http)
    assert "R3083239" in {p.sku for p in await a.discover()}
    for _ in range(GONE_AFTER_SCANS - 1):
        http.pages = ["", ""]
        assert await a.discover() == []
    http.pages = ["", ""]
    [gone] = await a.discover()
    assert gone.sku == "R3083239" and gone.stores[IN_STORES].level is Level.OUT
    http.pages = ["", ""]
    assert await a.discover() == []


async def test_a_brief_flicker_does_not_count_as_gone():
    listing = load_fixture("warehouse", "listing.html")
    http = FakeHttp(listing, listing)
    a = WarehouseAdapter(ROW, http)
    await a.discover()
    http.pages = ["", ""]
    assert await a.discover() == []
    http.pages = [listing, listing]
    await a.discover()
    assert a._missing == {}


# --- Per-store stock: the browser two-step flow (product page -> widget -> per-region), 2026-11-03 ---


class FakeBrowser:
    """Mimics BrowserFetcher: visit() returns the product-page HTML, fetch_text() serves fixture responses."""

    def __init__(self, product_page, responses):
        self.product_page = product_page
        self.responses = list(responses)
        self.visited = []
        self.fetched = []

    async def visit(self, policy, url, success_js=None, timeout_ms=30_000, settle_ms=500):
        self.visited.append(url)
        return self.product_page

    async def fetch_text(self, policy, origin, url, headers=None, retries=1):
        self.fetched.append(url)
        if not self.responses:
            raise FetchError(f"GET {url}: out of fixture responses")
        text = self.responses.pop(0)
        if isinstance(text, Exception):
            raise text
        return text


def _pdp(sku):
    # Both the plain widget and the edit=true variant exist; the flow must pick the non-edit one.
    return (
        "<html><body>"
        f'<gep-container-store-availability pid="{sku}" url="/products/stores?pid={sku}&amp;verify=TOKEN1">'
        f'<gep-container-store-availability pid="{sku}" url="/products/stores?pid={sku}&amp;edit=true&amp;verify=TOKENEDIT">'
        "</body></html>"
    )


def test_widget_store_url_picks_the_non_edit_element_for_that_product():
    from tcgpings.retailers.warehouse import widget_store_url

    page = _pdp("R3098657")
    assert widget_store_url(page, "R3098657") == "/products/stores?pid=R3098657&verify=TOKEN1"
    assert widget_store_url(page, "R999") is None  # another product's widget isn't used


def test_parse_store_regions_lists_15_regions_with_their_own_tokens():
    from tcgpings.retailers.warehouse import parse_store_regions

    regions = parse_store_regions(load_fixture("warehouse", "widget.json"))
    assert len(regions) == 15
    url = regions["NZ-AUK"]
    assert url.startswith("/products/stores/region?")
    assert "region=NZ-AUK&verify=" in url and "&amp;" not in url


def test_parse_store_levels_reads_stock_by_store_id():
    from tcgpings.retailers.warehouse import parse_store_levels

    levels = parse_store_levels(load_fixture("warehouse", "region-auckland.json"))
    assert len(levels) == 22
    assert levels["196"].level is Level.IN   # Warkworth
    assert levels["221"].level is Level.OUT  # Auckland Central


async def test_store_stock_visits_once_fires_the_widget_then_only_the_needed_regions():
    import json as _json

    from tcgpings.retailers.warehouse import IN_STORES

    widget_text = _json.dumps(load_fixture("warehouse", "widget.json"))
    region_text = _json.dumps(load_fixture("warehouse", "region-auckland.json"))
    browser = FakeBrowser(_pdp("R3098657"), [widget_text, region_text])
    http = FakeHttp()
    http.browser = browser
    a = WarehouseAdapter(ROW, http)
    assert a.store_stock_enabled

    stock = await a.store_stock("R3098657", ["221", "196", IN_STORES])  # only Auckland stores
    assert stock["196"].level is Level.IN    # Warkworth
    assert stock["221"].level is Level.OUT   # Auckland Central
    assert browser.visited == ["https://www.thewarehouse.co.nz/p/x/R3098657.html"]
    assert len(browser.fetched) == 2         # widget + the one Auckland region
    assert all("stores/region" in u for u in browser.fetched[1:])


async def test_store_stock_ignores_store_ids_outside_the_bundle():
    import json as _json

    widget_text = _json.dumps(load_fixture("warehouse", "widget.json"))
    region_text = _json.dumps(load_fixture("warehouse", "region-auckland.json"))
    browser = FakeBrowser(_pdp("R3098657"), [widget_text, region_text])
    http = FakeHttp()
    http.browser = browser
    a = WarehouseAdapter(ROW, http)

    stock = await a.store_stock("R3098657", ["221", "999"])  # 999 isn't in the 76-store bundle
    assert set(stock) == {"221"}
    assert len(browser.fetched) == 2


async def test_list_stores_is_the_real_76_plus_the_nationwide_pseudo_store():
    from tcgpings.retailers.warehouse import IN_STORES, IN_STORES_NAME

    stores = await WarehouseAdapter(ROW, FakeHttp()).list_stores()
    assert len(stores) == 77  # 76 real + 1 nationwide
    auk = next(s for s in stores if s.name == "Auckland Central")
    assert auk.store_id == "221" and auk.region == "NZ-AUK"
    assert stores[-1].store_id == IN_STORES and stores[-1].name == IN_STORES_NAME
