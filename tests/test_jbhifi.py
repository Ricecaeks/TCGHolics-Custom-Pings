"""JB Hi-Fi NZ: store stock from the product page JSON (fixture trimmed from the live page 2026-10-29)."""

from conftest import load_fixture

from tcgpings.models import Level
from tcgpings.net.http import FetchError
from tcgpings.retailers.base import REGISTRY
from tcgpings.retailers.jbhifi import (
    JBHiFiAdapter, load_bundled_stores, parse_in_stock_store_ids, parse_store_locations,
)

ID, NAME, CONFIG, _COLOR = JBHiFiAdapter.default_retailers[0]
ROW = {"id": ID, "adapter": "jbhifi", "name": NAME, "config": CONFIG,
       "requests_per_minute": 20, "proxy_policy": "direct", "color": None}
IN_STOCK = ["21", "23", "28", "45", "22", "14", "18", "33", "43", "39", "29", "24", "36", "41"]


class Resp:
    def __init__(self, text):
        self.text = text


class FakeHttp:
    browser = None

    def __init__(self, page, stores=None):
        self.page = page
        self.stores = stores
        self.urls = []

    async def get(self, policy, url, **kw):
        self.urls.append(url)
        return Resp(self.page)

    async def get_json(self, policy, url, **kw):
        self.urls.append(url)
        self.last_headers = kw.get("headers")
        if isinstance(self.stores, Exception):
            raise self.stores
        return self.stores


def test_registered_with_default_retailer():
    assert REGISTRY["jbhifi"] is JBHiFiAdapter
    assert CONFIG["domain"] == "www.jbhifi.co.nz"


def test_parse_in_stock_store_ids():
    assert parse_in_stock_store_ids(load_fixture("jbhifi", "product-page.html")) == IN_STOCK
    # the raw page escapes the JSON inside a string in some templates
    assert parse_in_stock_store_ids('\\"InStockStoreIds\\":[5, 7]') == ["5", "7"]
    assert parse_in_stock_store_ids("<html>no data</html>") is None


async def test_store_stock_in_and_out_for_retail_stores_only():
    a = JBHiFiAdapter(ROW, FakeHttp(load_fixture("jbhifi", "product-page.html")))
    stock = await a.store_stock("some-handle", ["21", "25"])
    assert stock["21"].level is Level.IN            # Botany, in the list
    assert stock["25"].level is Level.OUT           # Sylvia Park, not in the list
    assert set(stock) == set(IN_STOCK) | {"25"}     # every in-stock id here is a real shop
    assert a.http.urls == ["https://www.jbhifi.co.nz/products/some-handle"]
    assert a.store_label("21") == "Botany" and a.store_label("999") == "JB Hi-Fi store #999"


async def test_store_stock_ignores_warehouses_and_head_office():
    page = '"InStockStoreIds":[1,27,42]'           # head office, retail warehouse, Westgate
    a = JBHiFiAdapter(ROW, FakeHttp(page))
    assert {k: v.level for k, v in (await a.store_stock("x", [])).items()} == {"42": Level.IN}


def test_parse_store_locations_keeps_only_retail_shops():
    stores = parse_store_locations(load_fixture("jbhifi", "store-locations.json"))
    assert [(s["store_id"], s["name"]) for s in stores] == [
        ("14", "Albany"), ("25", "Sylvia Park"), ("32", "Auckland International Airport"), ("42", "Westgate"),
    ]


def test_bundled_store_list():
    stores = load_bundled_stores()
    assert len(stores) == 27
    assert set(IN_STOCK) <= {s["store_id"] for s in stores}


async def test_list_stores_live_then_fallback():
    live = JBHiFiAdapter(ROW, FakeHttp("", load_fixture("jbhifi", "store-locations.json")))
    names = [s.name for s in await live.list_stores()]
    assert names == ["Albany", "Sylvia Park", "Auckland International Airport", "Westgate"]
    assert live.http.urls[-1] == "https://vhbkeahero-dsn.algolia.net/1/indexes/shopify_store_locations/query"
    assert live.http.last_headers["X-Algolia-Application-Id"] == "VHBKEAHERO"
    down = JBHiFiAdapter(ROW, FakeHttp("", FetchError("GET x: HTTP 500")))
    assert len(await down.list_stores()) == 27


async def test_store_stock_reports_nothing_when_layout_changes():
    a = JBHiFiAdapter(ROW, FakeHttp("<html>redesigned</html>"))
    assert await a.store_stock("x", ["21"]) == {}


def test_cart_link():
    a = JBHiFiAdapter(ROW, FakeHttp(""))
    assert a.cart_url(43210) == "https://www.jbhifi.co.nz/cart/43210:1"
    assert a.store_stock_enabled
