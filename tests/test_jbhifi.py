"""JB Hi-Fi NZ: store stock from the product page JSON (fixture trimmed from the live page 2026-10-29)."""

from conftest import load_fixture

from tcgpings.models import Level
from tcgpings.retailers.base import REGISTRY
from tcgpings.retailers.jbhifi import JBHiFiAdapter, parse_in_stock_store_ids

ID, NAME, CONFIG, _COLOR = JBHiFiAdapter.default_retailers[0]
ROW = {"id": ID, "adapter": "jbhifi", "name": NAME, "config": CONFIG,
       "requests_per_minute": 20, "proxy_policy": "direct", "color": None}
IN_STOCK = ["21", "23", "28", "45", "22", "14", "18", "33", "43", "39", "29", "24", "36", "41"]


class Resp:
    def __init__(self, text):
        self.text = text


class FakeHttp:
    browser = None

    def __init__(self, page):
        self.page = page
        self.urls = []

    async def get(self, policy, url, **kw):
        self.urls.append(url)
        return Resp(self.page)


def test_registered_with_default_retailer():
    assert REGISTRY["jbhifi"] is JBHiFiAdapter
    assert CONFIG["domain"] == "www.jbhifi.co.nz"


def test_parse_in_stock_store_ids():
    assert parse_in_stock_store_ids(load_fixture("jbhifi", "product-page.html")) == IN_STOCK
    # the raw page escapes the JSON inside a string in some templates
    assert parse_in_stock_store_ids('\\"InStockStoreIds\\":[5, 7]') == ["5", "7"]
    assert parse_in_stock_store_ids("<html>no data</html>") is None


async def test_store_stock_marks_known_stores_out_and_learns_new_ones():
    a = JBHiFiAdapter(ROW, FakeHttp(load_fixture("jbhifi", "product-page.html")))
    stock = await a.store_stock("some-handle", ["21", "99"])
    assert stock["21"].level is Level.IN
    assert stock["99"].level is Level.OUT          # known store not in the list
    assert set(IN_STOCK) <= set(stock)             # new in-stock stores reported too
    assert a.http.urls == ["https://www.jbhifi.co.nz/products/some-handle"]
    assert a.store_label("21") == "JB Hi-Fi store #21"


async def test_store_stock_reports_nothing_when_layout_changes():
    a = JBHiFiAdapter(ROW, FakeHttp("<html>redesigned</html>"))
    assert await a.store_stock("x", ["21"]) == {}


def test_cart_link():
    a = JBHiFiAdapter(ROW, FakeHttp(""))
    assert a.cart_url(43210) == "https://www.jbhifi.co.nz/cart/43210:1"
    assert a.store_stock_enabled and a.store_stock_discovers_stores
