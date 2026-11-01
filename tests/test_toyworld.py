"""Toyworld store stock through Stock In Store. Fixtures are trimmed copies of the live responses."""

from conftest import load_fixture

from tcgpings.discord.embeds import build_embed
from tcgpings.models import Event, EventType, Level
from tcgpings.net.http import FetchError
from tcgpings.retailers.toyworld import ToyworldAdapter, parse_store_list, parse_store_quantities

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


def test_parse_quantities_skips_unreadable_rows():
    assert parse_store_quantities({"response": [
        {"code": "A", "stock": "3"}, {"code": "B", "stock": "-1"}, {"code": "C", "stock": None}, {"stock": "1"},
    ]}) == {"A": 3, "B": 0}


async def test_list_stores():
    stores = await adapter(FakeHttp()).list_stores()
    assert stores[0].store_id == "1120" and stores[0].name == "Waihi" and stores[0].region == "Waikato"


async def test_store_stock_reads_quantities_by_barcode():
    http = FakeHttp({JS: {"variants": [{"barcode": "4050368984227"}]}})
    stock = await adapter(http).store_stock("booster", ["1065", "1120", "NPL1"])
    assert {k: (v.level, v.qty) for k, v in stock.items()} == {
        "1065": (Level.IN, 1), "1120": (Level.OUT, 0), "NPL1": (Level.OUT, 0),
    }
    method, url, form = http.posts[0]
    assert (method, url) == ("POST", "https://stockinstore.net/stores/getStoresStock")
    assert form["pid"] == "4050368984227" and form["storeids"] == "1065,1120,NPL1" and form["site"] == "10044"


async def test_assorted_products_add_up_across_barcodes():
    def stock(form):
        return {"response": [{"code": "A", "stock": "2" if form["pid"] == "111" else "3"}]}

    http = FakeHttp({JS: {"variants": [{"barcode": "111"}, {"barcode": "222"}, {"barcode": ""}]}}, stock)
    assert (await adapter(http).store_stock("booster", ["A"]))["A"].qty == 5
    assert len(http.posts) == 2


async def test_unlisted_product_reports_nothing_rather_than_all_out():
    http = FakeHttp()
    assert await adapter(http).store_stock("booster", ["A"]) == {}
    assert http.posts == []


async def test_empty_answer_reports_nothing_rather_than_all_out():
    http = FakeHttp({JS: {"variants": [{"barcode": "111"}]}}, {"response": []})
    assert await adapter(http).store_stock("booster", ["A"]) == {}


def test_alert_lists_store_quantities():
    event = Event(type=EventType.RESTOCK, retailer_id="toyworld", sku="x", title="Pokemon Bundle", url="https://x",
                  store_id="*1", store_name="2 stores", old_level="out", new_level="in", new_qty=3,
                  stores=[{"id": "a", "name": "Albany", "qty": 3}, {"id": "b", "name": "Botany", "qty": None}])
    stores = next(f for f in build_embed(event).fields if f.name.startswith("Stores"))
    assert stores.value == "Albany [3], Botany"
