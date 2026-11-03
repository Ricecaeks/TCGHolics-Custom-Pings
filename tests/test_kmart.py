"""Kmart adapter: Constructor listings (fixture trimmed from the live Trading Cards browse)."""

import json
import time

from conftest import load_fixture

from tcgpings.discord.embeds import build_embed
from tcgpings.engine.planner import plan_jobs
from tcgpings.models import Event, EventType, Level
from tcgpings.net.http import FetchError
from tcgpings.retailers.kmart import KmartAdapter, parse_constructor

ROW = {"id": "kmart", "adapter": "kmart", "name": "Kmart", "config": {}, "requests_per_minute": 12,
       "proxy_policy": "direct", "color": None, "enabled": True}


def by_sku():
    return {p.sku: p for p in parse_constructor(load_fixture("kmart", "browse.json"))}


def test_online_product_in_stock():
    p = by_sku()["43818273"]  # Yu-Gi-Oh! Beyond the Brave booster: online and in store
    assert p.title.startswith("Konami Yu-Gi-Oh!") and p.price_cents == 950
    assert p.url == "https://www.kmart.co.nz/product/konami-yu-gi-oh!-trading-card-game:-beyond-the-brave-9-card-booster-43818273/"
    assert p.online.level is Level.IN and p.note is None and p.stores is None


def test_in_store_only_product_is_never_online():
    p = by_sku()["43788798"]  # Pitch Black Booster Bundle
    assert p.note == "In-store only" and p.online.level is Level.OUT and p.price_cents == 6200


def test_sold_out_everywhere():
    assert by_sku()["43818617"].online.level is Level.OUT  # 30th Celebration Booster Bundle


def test_online_product_out_in_one_island_is_still_online():
    assert by_sku()["43829248"].online.level is Level.IN


def location(store, qty, buddy=False):
    return {"fulfilment": {"locationId": store, "isBuddyLocation": buddy, "stock": {"available": qty}}}


def answer(rows):
    return {"data": {"getProductAvailability": {"availability": {"CLICK_AND_COLLECT": rows}}}}


STORES = {"data": {"nearestLocations": [
    {"locationId": "8229", "publicName": "Sylvia Park Nz ", "state": "North Island", "postcode": "1060"},
    {"locationId": "8213", "publicName": "Botany", "state": "North Island", "postcode": "2013"},
    {"locationId": "8237", "publicName": "Westgate", "state": "North Island", "postcode": "814"},
    {"locationId": "8235", "publicName": "Dunedin", "state": "South Island", "postcode": "9012"},
]}}
BY_POSTCODE = {
    "1060": [location("8229", 10), location("8213", 0)],
    "0814": [location("8237", 3), location("8229", 9, buddy=True)],
    "9012": [],  # some postcodes get no answer
}


class FakeResponse:
    def __init__(self, data):
        self.data = data

    def json(self):
        return self.data


class FakeHttp:
    def __init__(self, fail=None, chain=None):
        self.asked = []
        self.fail = fail
        self.chain = chain
        self.direct_calls = 0

    async def get_json(self, policy, url, **kw):
        return load_fixture("kmart", "browse.json")

    async def request(self, policy, method, url, json=None, **kw):
        assert (method, url) == ("POST", "https://api.kmart.co.nz/gateway/graphql")
        self.direct_calls += 1
        if self.fail:
            raise self.fail
        if json["operationName"] == "getNearestLocations":
            return FakeResponse(STORES)
        form = json["variables"]["input"]
        self.asked.append(form["postcode"])
        return FakeResponse(answer([{"keycode": p["keycode"], "locations": BY_POSTCODE[form["postcode"]]}
                                    for p in form["products"]]))


class FakeChain:
    """The fetch chain's unblockers: answers the same gateway POSTs, as text."""

    def __init__(self, routes=("scrapfly", "zyte"), fail=None):
        self.routes = list(routes)
        self.fail = fail
        self.posts = []

    def available(self, order):
        return [r for r in order if r in self.routes]

    async def fetch_text(self, policy, origin, url, headers=None, order=None, body=None):
        assert url == "https://api.kmart.co.nz/gateway/graphql" and headers["Content-Type"] == "application/json"
        if self.fail:
            raise self.fail
        payload = json.loads(body)
        self.posts.append((payload["operationName"], order))
        return json.dumps((await FakeHttp().request(policy, "POST", url, json=payload)).json())


async def test_store_list_is_real_stores_and_gets_synced():
    a = KmartAdapter(ROW, FakeHttp())
    stores = await a.list_stores()
    assert [(s.store_id, s.name, s.region) for s in stores][:2] == [
        ("8229", "Sylvia Park", "North Island"), ("8213", "Botany", "North Island")]
    assert a.store_label("8237") == "Westgate" and a.store_label("1") == "Store 1"
    jobs = {j["key"] for j in plan_jobs([ROW], [], 300, 600, 86400)}
    assert jobs == {"stores:kmart", "discover:kmart"}


async def test_sweep_skips_stores_already_answered_and_never_invents_stock():
    http = FakeHttp()
    stock = await KmartAdapter(ROW, http)._store_stock(["111"])
    assert http.asked == ["1060", "0814", "9012"]  # Botany was answered by Sylvia Park's postcode
    assert {k: (v.level, v.qty) for k, v in stock["111"].items()} == {
        "8229": (Level.IN, 10), "8213": (Level.OUT, 0), "8237": (Level.IN, 3),
    }  # Dunedin never answered, and a buddy store's reading isn't Sylvia Park's own


async def test_discover_attaches_sealed_store_stock_and_checks_stores_less_often_than_listings():
    http = FakeHttp()
    a = KmartAdapter(ROW, http)
    first = {p.sku: p for p in await a.discover()}
    assert first["43818617"].stores["8229"].qty == 10
    asked = len(http.asked)
    second = {p.sku: p for p in await a.discover()}
    assert second["43818617"].stores is None and len(http.asked) == asked


async def test_a_store_stock_failure_keeps_the_listings_and_backs_off():
    http = FakeHttp(fail=FetchError("POST: HTTP 429", 429))
    a = KmartAdapter(ROW, http)
    products = await a.discover()
    assert products and all(set(p.stores or {}) <= {"NI", "SI"} for p in products)
    first_wait = a._next_store_check - time.monotonic()
    assert 29 * 60 < first_wait <= 30 * 60

    http.fail = None
    assert all(set(p.stores or {}) <= {"NI", "SI"} for p in await a.discover())  # still waiting, so nothing was asked
    assert http.asked == []

    a._next_store_check = a._direct_after = 0
    http.fail = FetchError("POST: HTTP 429", 429)
    await a.discover()
    assert a._next_store_check - time.monotonic() > first_wait * 1.9

    a._next_store_check = a._direct_after = 0
    http.fail = None
    assert any(p.stores for p in await a.discover())
    assert a._store_failures == 0


async def test_a_short_block_keeps_the_last_store_counts_instead_of_the_islands():
    from tcgpings.retailers.kmart import ISLANDS_AFTER_SECONDS

    http = FakeHttp()
    a = KmartAdapter(ROW, http)
    await a.discover()
    a._next_store_check, http.fail = 0, FetchError("POST: HTTP 429", 429)
    blocked = {p.sku: p for p in await a.discover()}
    assert blocked["43788798"].stores is None  # the stores keep their last counts

    a._store_ok_at -= ISLANDS_AFTER_SECONDS
    a._next_store_check = 0
    stale = {p.sku: p for p in await a.discover()}
    assert set(stale["43788798"].stores) == {"NI", "SI"}


def test_alert_lists_store_counts():
    event = Event(type=EventType.RESTOCK, retailer_id="kmart", sku="x", title="Pokemon Bundle", url="https://x",
                  store_id="*1", store_name="2 stores", old_level="out", new_level="in", new_qty=3,
                  stores=[{"id": "a", "name": "Albany", "qty": 31}, {"id": "b", "name": "Botany", "qty": None}])
    stores = next(f for f in build_embed(event).fields if f.name.startswith("Stores"))
    assert stores.value == "Albany [31], Botany"


def test_parse_ref():
    a = KmartAdapter(ROW, http=None)
    assert a.parse_ref("43818617") == "43818617"
    assert a.parse_ref("https://www.kmart.co.nz/product/pokemon-tcg:-30th-celebration-booster-bundle-43818617/") == "43818617"
    assert a.parse_ref("https://www.kmart.co.nz/product/43818273/") == "43818273"
    assert a.matches_url("https://www.kmart.co.nz/product/43818273/")


async def test_islands_cover_only_in_store_products_and_only_while_store_stock_is_down():
    http = FakeHttp(fail=FetchError("POST: HTTP 429", 429))
    a = KmartAdapter(ROW, http)
    down = {p.sku: p for p in await a.discover()}
    assert {k: s.level for k, s in down["43788798"].stores.items()} == {"NI": Level.IN, "SI": Level.OUT}
    assert a.store_label("NI") == "North Island"
    assert down["43818273"].stores is None  # sold online, so its flags can include warehouse stock

    a._next_store_check = a._direct_after = 0
    http.fail = None
    up = {p.sku: p for p in await a.discover()}
    assert "NI" not in up["43788798"].stores and "8229" in up["43788798"].stores

    assert all(p.stores is None for p in await a.search("pokemon"))


async def test_a_refused_sweep_goes_through_the_unblockers_and_ours_rest():
    chain = FakeChain()
    http = FakeHttp(fail=FetchError("POST: HTTP 429", 429), chain=chain)
    a = KmartAdapter(ROW, http)
    products = {p.sku: p for p in await a.discover()}
    assert products["43818617"].stores["8229"].qty == 10  # real store counts, not the islands
    assert {op for op, _ in chain.posts} == {"getNearestLocations", "getProductAvailability"}
    assert chain.posts[0][1] == ["scrapfly"]
    assert 29 * 60 < a._next_store_check - time.monotonic() <= 30 * 60
    assert a._direct_after > time.monotonic()

    a._next_store_check, calls = 0, http.direct_calls
    await a.discover()
    assert http.direct_calls == calls  # ours are still resting, so the unblockers answered alone

    a._next_store_check = a._direct_after = 0
    http.fail = None
    posts = len(chain.posts)
    await a.discover()
    assert len(chain.posts) == posts and a._store_failures == 0  # ours work again: no paid requests


async def test_unblockers_failing_too_keeps_the_last_counts_and_tries_again_soon():
    http = FakeHttp(fail=FetchError("POST: HTTP 429", 429), chain=FakeChain(fail=FetchError("no route got through")))
    a = KmartAdapter(ROW, http)
    a._store_ok_at = time.monotonic()  # counts from a moment ago
    products = await a.discover()
    assert all(p.stores is None for p in products)
    assert a._next_store_check - time.monotonic() <= 30 * 60


async def test_no_unblocker_configured_falls_back_as_before():
    http = FakeHttp(fail=FetchError("POST: HTTP 429", 429), chain=FakeChain(routes=()))
    a = KmartAdapter(ROW, http)
    await a.discover()
    assert a._next_store_check == a._direct_after
