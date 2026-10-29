import tcgpings.retailers  # noqa: F401  (registers adapters)
from tcgpings.engine.planner import plan_jobs
from tcgpings.engine.router import match_routes, route_matches
from tcgpings.models import ONLINE, Event, EventType
from tcgpings.retailers.base import REGISTRY, RetailerAdapter, register


def route(**kw):
    base = dict(id=1, retailer_id=None, store_id=None, franchise=None, event_types=None)
    return {**base, **kw}


def event(kind=EventType.RESTOCK, retailer="farmers", store="westgate", franchise="pokemon"):
    return Event(type=kind, retailer_id=retailer, sku="1", title="t", url="u", store_id=store, franchise=franchise)


def test_store_route_gets_only_its_store():
    westgate = route(retailer_id="farmers", store_id="westgate")
    assert route_matches(westgate, event())
    assert not route_matches(westgate, event(store="albany"))
    assert not route_matches(westgate, event(retailer="warehouse"))
    assert not route_matches(westgate, event(store=ONLINE))


def test_online_only_route():
    online = route(retailer_id="farmers", store_id=ONLINE)
    assert route_matches(online, event(store=ONLINE))
    assert not route_matches(online, event(store="westgate"))


def test_franchise_filter_and_catch_all():
    assert route_matches(route(franchise="pokemon"), event())
    assert not route_matches(route(franchise="mtg"), event())
    assert route_matches(route(), event(retailer="anything", store="x", franchise=None))


def test_default_event_types_exclude_out_of_stock():
    assert not route_matches(route(), event(EventType.OUT_OF_STOCK))
    assert route_matches(route(event_types=["out_of_stock"]), event(EventType.OUT_OF_STOCK))
    assert not route_matches(route(event_types=["out_of_stock"]), event(EventType.RESTOCK))


def test_match_routes_returns_all_matches():
    routes = [route(id=1), route(id=2, store_id="westgate"), route(id=3, store_id="albany")]
    assert [r["id"] for r in match_routes(routes, event())] == [1, 2]


# --- planner ---------------------------------------------------------------------------


@register
class _StoreAdapter(RetailerAdapter):
    adapter_name = "_planner_stores"
    supports_store_stock = True

    async def search(self, query):
        return []

    async def fetch_products(self, skus):
        return []


def retailer(rid, adapter="shopify", enabled=True):
    return {"id": rid, "adapter": adapter, "enabled": enabled}


def watch(wid, kind="keyword", query="Pokemon 30th", retailer_id=None, store_ids=None, franchise=None, interval=None):
    return dict(id=wid, kind=kind, query=query, retailer_id=retailer_id, store_ids=store_ids,
                franchise=franchise, interval_seconds=interval, enabled=True)


def plan(retailers, watches):
    return {j["key"]: j for j in plan_jobs(retailers, watches, 60, 300, 86400)}


def test_keyword_watch_fans_out_to_every_enabled_retailer():
    jobs = plan([retailer("a"), retailer("b"), retailer("c", enabled=False)], [watch(1)])
    assert set(jobs) == {"search:a:pokemon 30th:*", "search:b:pokemon 30th:*"}
    assert jobs["search:a:pokemon 30th:*"]["interval"] == 300


def test_store_capable_retailers_get_a_store_sync_job():
    jobs = plan([retailer("farmers", adapter="_planner_stores")], [])
    assert jobs["stores:farmers"]["kind"] == "sync_stores"


def test_duplicate_sku_watches_merge_stores_and_take_fastest_interval():
    jobs = plan(
        [retailer("farmers", adapter="_planner_stores")],
        [
            watch(1, kind="sku", query="123", retailer_id="farmers", store_ids=["westgate"], interval=120),
            watch(2, kind="sku", query="123", retailer_id="farmers", store_ids=["albany"], interval=45),
        ],
    )
    job = jobs["sku:farmers:123"]
    assert job["payload"]["store_ids"] == ["albany", "westgate"]
    assert job["payload"]["watch_ids"] == [1, 2]
    assert job["interval"] == 45


def test_all_stores_wins_when_merging():
    jobs = plan(
        [retailer("farmers", adapter="_planner_stores")],
        [
            watch(1, kind="sku", query="123", retailer_id="farmers", store_ids=["westgate"]),
            watch(2, kind="sku", query="123", retailer_id="farmers", store_ids=None),
        ],
    )
    assert jobs["sku:farmers:123"]["payload"]["store_ids"] is None


def test_unknown_adapters_and_retailers_are_skipped():
    jobs = plan([retailer("x", adapter="nope")], [watch(1, retailer_id="x"), watch(2, kind="sku", query="1", retailer_id="gone")])
    assert jobs == {}
    assert "_planner_stores" in REGISTRY
