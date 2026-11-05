import tcgpings.retailers  # noqa: F401  (registers adapters)
from tcgpings.engine.planner import plan_jobs
from tcgpings.engine.router import match_routes, route_matches
from tcgpings.models import ANY_STORE, ONLINE, Event, EventType
from tcgpings.retailers.base import REGISTRY, RetailerAdapter, register


def route(**kw):
    base = dict(id=1, retailer_id=None, store_id=None, franchise=None, event_types=None)
    return {**base, **kw}


def event(kind=EventType.RESTOCK, retailer="farmers", store="westgate", franchise="pokemon", level="in"):
    return Event(type=kind, retailer_id=retailer, sku="1", title="t", url="u", store_id=store, franchise=franchise,
                 new_level=level)


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


def test_instore_route_gets_every_store_but_not_online():
    instore = route(retailer_id="kmart", store_id=ANY_STORE)
    assert route_matches(instore, event(retailer="kmart", store="NI"))
    assert route_matches(instore, event(retailer="kmart", store="SI"))
    assert not route_matches(instore, event(retailer="kmart", store=ONLINE))
    assert not route_matches(instore, event(retailer="farmers", store="NI"))


def test_franchise_filter_and_catch_all():
    assert route_matches(route(franchise="pokemon"), event())
    assert not route_matches(route(franchise="mtg"), event())
    assert route_matches(route(), event(retailer="anything", store="x", franchise=None))


def test_default_event_types_exclude_out_of_stock():
    assert not route_matches(route(), event(EventType.OUT_OF_STOCK))
    assert route_matches(route(event_types=["out_of_stock"]), event(EventType.OUT_OF_STOCK))
    assert not route_matches(route(event_types=["out_of_stock"]), event(EventType.RESTOCK))


def test_every_alert_needs_stock():
    for r in (route(), route(retailer_id="farmers", store_id=ONLINE), route(store_id=ONLINE, in_stock_only=True)):
        for kind in (EventType.NEW_PRODUCT, EventType.PRICE_CHANGE, EventType.QTY_CHANGE):
            for level in ("out", "unknown", None):
                assert not route_matches(r, event(kind, store=ONLINE, level=level)), (r, kind, level)
            assert route_matches(r, event(kind, store=ONLINE, level="in"))
            assert route_matches(r, event(kind, store=ONLINE, level="low"))
    # The opt-in out-of-stock alert is about having none.
    assert route_matches(route(event_types=["out_of_stock"]), event(EventType.OUT_OF_STOCK, level="out"))


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


def watch(wid, kind="keyword", query="Pokemon 30th", retailer_id=None, store_ids=None, franchise=None, interval=None,
          **kw):
    return dict(id=wid, kind=kind, query=query, retailer_id=retailer_id, store_ids=store_ids,
                franchise=franchise, interval_seconds=interval, enabled=True, **kw)


def plan(retailers, watches):
    return {j["key"]: j for j in plan_jobs(retailers, watches, 60, 300, 86400)}


def test_keyword_watch_fans_out_to_every_enabled_retailer():
    jobs = plan([retailer("a"), retailer("b"), retailer("c", enabled=False)], [watch(1)])
    assert {k for k in jobs if k.startswith("search:")} == {"search:a", "search:b"}
    assert jobs["search:a"]["interval"] == 300
    assert jobs["search:a"]["kind"] == "watch_search"
    assert jobs["search:a"]["payload"] == {"queries": [
        {"query": "pokemon 30th", "franchise": None, "store_ids": None, "watch_ids": [1], "since": None},
    ]}


def test_keyword_watches_group_into_one_search_job_per_retailer():
    from datetime import UTC, datetime

    early, late = datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 6, 1, tzinfo=UTC)
    watches = [
        watch(1, query="Pokemon 30th", created_at=late),
        watch(2, query="  pokemon   30TH ", retailer_id="a", store_ids=["westgate"], interval=120, created_at=early),
        watch(3, query="pokemon 30th", franchise="pokemon"),
        watch(4, query="Delta Reign", store_ids=["albany"]),
        watch(5, query="one piece", retailer_id="b", interval=900),
    ]
    jobs = plan([retailer("a"), retailer("b")], watches)
    assert sorted(k for k in jobs if k.startswith("search:")) == ["search:a", "search:b"]  # 5 watches, 2 jobs
    a, b = jobs["search:a"], jobs["search:b"]
    assert a["interval"] == 120 and b["interval"] == 300  # the fastest watch in the group
    assert a["payload"]["queries"] == [
        {"query": "delta reign", "franchise": None, "store_ids": ["albany"], "watch_ids": [4], "since": None},
        # same query + franchise merge like they always did: all stores win, watch ids add up
        {"query": "pokemon 30th", "franchise": None, "store_ids": None, "watch_ids": [1, 2],
         "since": early.isoformat()},
        {"query": "pokemon 30th", "franchise": "pokemon", "store_ids": None, "watch_ids": [3], "since": None},
    ]
    assert [(q["query"], q["franchise"], q["watch_ids"]) for q in b["payload"]["queries"]] == [
        ("delta reign", None, [4]), ("one piece", None, [5]), ("pokemon 30th", None, [1]), ("pokemon 30th", "pokemon", [3]),
    ]
    assert b["payload"]["queries"][2]["since"] == late.isoformat()


def test_retailers_without_search_get_no_search_job():
    from tcgpings.retailers.mightyape import MightyApeAdapter

    assert not MightyApeAdapter.supports_search
    jobs = plan([retailer("a"), retailer("ape", adapter=MightyApeAdapter.adapter_name)], [watch(1)])
    assert "search:a" in jobs and "search:ape" not in jobs


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


# --- keywords, discovery, merged store alerts --------------------------------------------


def test_route_keywords_filter_titles():
    r = route(keywords="30th booster bundle, elite trainer box, -sleeves")
    hit = Event(type=EventType.NEW_PRODUCT, retailer_id="x", sku="1", url="u", title="Pokemon 30th Booster Bundle", new_level="in")
    miss = Event(type=EventType.NEW_PRODUCT, retailer_id="x", sku="2", url="u", title="Pokemon Booster Pack", new_level="in")
    sleeves = Event(type=EventType.NEW_PRODUCT, retailer_id="x", sku="3", url="u", title="Elite Trainer Box Sleeves", new_level="in")
    assert route_matches(r, hit) and not route_matches(r, miss) and not route_matches(r, sleeves)


def test_keyword_routes_match_respects_retailer():
    from tcgpings.engine.router import keyword_routes_match

    routes = [route(retailer_id="farmers", keywords="etb"), route(retailer_id=None, keywords=None)]
    assert keyword_routes_match(routes, "farmers", "Pokemon Elite Trainer Box")
    assert not keyword_routes_match(routes, "jbhifi", "Pokemon Elite Trainer Box")


def test_discovery_job_for_every_enabled_retailer_that_supports_it():
    jobs = plan([retailer("shop"), retailer("off", enabled=False)], [])
    assert jobs["discover:shop"]["kind"] == "discover" and jobs["discover:shop"]["interval"] == 180
    assert "discover:off" not in jobs


def test_merge_store_events():
    from tcgpings.engine.pipeline import merge_store_events

    def ev(store, kind=EventType.RESTOCK, sku="1"):
        return Event(type=kind, retailer_id="jbhifi", sku=sku, url="u", title="t",
                     store_id=store, store_name=f"Store {store}")

    merged = merge_store_events([ev("21"), ev("14"), ev(ONLINE), ev("33", EventType.OUT_OF_STOCK), ev("5", sku="2")])
    restocks = [e for e in merged if e.type is EventType.RESTOCK and e.sku == "1" and e.store_id != ONLINE]
    assert len(merged) == 4
    [combined] = restocks
    assert combined.store_name == "2 stores" and [s["id"] for s in combined.stores] == ["14", "21"]
    assert combined.store_id.startswith("*")
