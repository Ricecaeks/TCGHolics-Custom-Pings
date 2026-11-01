"""Toyworld store stock through Stock In Store. Fixtures are trimmed copies of the live responses."""

from conftest import load_fixture

from tcgpings.models import Level
from tcgpings.net.http import FetchError
from tcgpings.retailers.toyworld import ToyworldAdapter, parse_store_list, parse_store_levels

ROW = {
    "id": "toyworld", "adapter": "toyworld", "name": "Toyworld", "config": ToyworldAdapter.default_retailers[0][2],
    "requests_per_minute": 60, "proxy_policy": "direct", "color": None,
}
JS = "https://www.toyworld.co.nz/products/booster.js"


class FakeResponse:
    def __init__(self, data):
        self.data = data

    def json(self):
        return self.data


class FakeHttp:
    def __init__(self, products=None, stock=None):
        self.products = products or {}
        self.stock = stock if stock is not None else load_fixture("toyworld", "stock.json")
        self.posts = []

    async def get_json(self, policy, url, **kw):
        if url not in self.products:
            raise FetchError(f"GET {url}: HTTP 404", 404)
        return self.products[url]

    async def request(self, policy, method, url, data=None, **kw):
        self.posts.append((method, url, data))
        if url.endswith("getStoresForWidget"):
            return FakeResponse(load_fixture("toyworld", "stores.json"))
        return FakeResponse(self.stock(data) if callable(self.stock) else self.stock)


def adapter(http):
    return ToyworldAdapter(ROW, http)


def test_parse_store_list_drops_the_brand_from_names():
    stores = parse_store_list(load_fixture("toyworld", "stores.json"))
    assert stores[0] == {"store_id": "1120", "name": "Waihi", "region": "Waikato"}


def level_row(code, label):
    return {"code": code, "stock": "1", "threshold": {"threshold_type_by": label}}


def test_parse_levels_uses_the_displayed_threshold_and_skips_unknown_ones():
    assert parse_store_levels({"response": [
        level_row("A", "in-stock"), level_row("B", "low-stock"), level_row("C", "out-of-stock"),
        level_row("D", "something-new"), {"code": "E", "stock": "1"},
    ]}) == {"A": Level.IN, "B": Level.LOW, "C": Level.OUT}


async def test_list_stores():
    stores = await adapter(FakeHttp()).list_stores()
    assert stores[0].store_id == "1120" and stores[0].name == "Waihi" and stores[0].region == "Waikato"


async def test_store_stock_reads_levels_by_barcode():
    http = FakeHttp({JS: {"variants": [{"barcode": "4050368984227"}]}})
    stock = await adapter(http).store_stock("booster", ["1065", "1073", "1120"])
    assert {k: (v.level, v.qty) for k, v in stock.items()} == {
        "1065": (Level.IN, None), "1073": (Level.LOW, None), "1120": (Level.OUT, None),
    }
    method, url, form = http.posts[0]
    assert (method, url) == ("POST", "https://stockinstore.net/stores/getStoresStock")
    assert form["pid"] == "4050368984227" and form["storeids"] == "1065,1073,1120" and form["site"] == "10044"


async def test_assorted_products_take_the_best_level_across_barcodes():
    def stock(form):
        return {"response": [level_row("A", "out-of-stock" if form["pid"] == "111" else "low-stock")]}

    http = FakeHttp({JS: {"variants": [{"barcode": "111"}, {"barcode": "222"}, {"barcode": ""}]}}, stock)
    assert (await adapter(http).store_stock("booster", ["A"]))["A"].level is Level.LOW
    assert len(http.posts) == 2


async def test_unlisted_product_reports_nothing_rather_than_all_out():
    http = FakeHttp()
    assert await adapter(http).store_stock("booster", ["A"]) == {}
    assert http.posts == []


async def test_empty_answer_reports_nothing_rather_than_all_out():
    http = FakeHttp({JS: {"variants": [{"barcode": "111"}]}}, {"response": []})
    assert await adapter(http).store_stock("booster", ["A"]) == {}
