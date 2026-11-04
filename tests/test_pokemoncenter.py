"""Pokémon Center NZ / AU / UK: category and product parsing (fixtures trimmed from pages fetched through Zyte
on 2026-11-05), the read schedule, queue detection, per-request country, and overseas routing."""

import base64

import pytest
from conftest import load_fixture

import tcgpings.retailers  # noqa: F401  (registers adapters)
from tcgpings.discord.embeds import build_embed
from tcgpings.engine.planner import plan_jobs
from tcgpings.engine.router import route_matches
from tcgpings.models import Event, EventType, Level
from tcgpings.net.chain import Cooldowns, FetchChain, MemoryChainStore
from tcgpings.net.http import FetchError, NetPolicy, Queued, looks_like_queue_page
from tcgpings.net.unblock import ScrapFlyBackend, ZyteBackend
from tcgpings.retailers import pokemoncenter
from tcgpings.retailers.base import REGISTRY
from tcgpings.retailers.pokemoncenter import (
    QUEUE_SKU,
    PokemonCenterAdapter,
    parse_category,
    parse_product,
)

RETAILERS = {rid: (name, config) for rid, name, config, _ in PokemonCenterAdapter.default_retailers}
UPC = "10-10065-109"
QUEUE_PAGE = ("<html><head><title>Pokémon Center</title></head><body><h1>You are now in line</h1>"
              "<p>Thanks for your patience. You're in our waiting room.</p></body></html>")


def row(rid="pokemoncenter-nz"):
    name, config = RETAILERS[rid]
    return {"id": rid, "adapter": "pokemoncenter", "name": name, "config": config,
            "requests_per_minute": 20, "proxy_policy": "direct", "color": None}


class FakeChain:
    def __init__(self, pages=None, default=None, fail=None):
        self.pages, self.default, self.fail = pages or {}, default, fail
        self.calls = []

    def available(self, order):
        return list(order)

    async def fetch_text(self, policy, origin, url, headers=None, order=None, body=None, country=None,
                         detect_queue=False):
        self.calls.append((url, tuple(order or ()), country, detect_queue))
        if self.fail:
            raise self.fail
        if url in self.pages:
            return self.pages[url]
        if self.default is not None:
            return self.default
        raise AssertionError(f"unexpected fetch {url}")


class Http:
    def __init__(self, chain):
        self.chain = chain


def adapter(chain, rid="pokemoncenter-nz"):
    return PokemonCenterAdapter(row(rid), Http(chain))


def test_three_stores_through_zyte():
    assert REGISTRY["pokemoncenter"] is PokemonCenterAdapter
    assert set(RETAILERS) == {"pokemoncenter-nz", "pokemoncenter-au", "pokemoncenter-uk"}
    assert {rid: (c["geo"], c["locale"], c["overseas"]) for rid, (_, c) in RETAILERS.items()} == {
        "pokemoncenter-nz": ("NZ", "en-nz", False),
        "pokemoncenter-au": ("AU", "en-au", True),
        "pokemoncenter-uk": ("GB", "en-gb", True),
    }
    assert all(c["fetch"] == ["zyte"] for _, c in RETAILERS.values())
    assert PokemonCenterAdapter.supports_search is False


def test_nz_category_page():
    products, total, in_stock = parse_category(load_fixture("pokemoncenter", "nz-tcg-cards-1.html"),
                                               "pokemoncenter-nz", "en-nz")
    assert (len(products), total, in_stock) == (12, 303, 0)
    p = products[0]
    assert p.sku == UPC and p.title == "Pokémon TCG: Mega Charizard X ex Ultra-Premium Collection"
    assert p.price_cents == 23499 and p.online.level is Level.OUT and p.note is None
    assert p.url == ("https://www.pokemoncenter.com/en-nz/product/10-10065-109/"
                     "pokemon-tcg-mega-charizard-x-ex-ultra-premium-collection")
    assert p.image.startswith("https://www.pokemoncenter.com/images/DAMRoot/Full-Size/")


def test_uk_and_au_pages_note_their_currency():
    uk, total, in_stock = parse_category(load_fixture("pokemoncenter", "uk-tcg-cards-1.html"),
                                         "pokemoncenter-uk", "en-gb", "GBP")
    assert (total, in_stock) == (590, 1)
    assert any("30th Celebration Mini Tin" in p.title for p in uk)
    assert {p.note for p in uk} == {"Price in GBP"}
    assert all(p.url.startswith("https://www.pokemoncenter.com/en-gb/product/") for p in uk)
    au, _, _ = parse_category(load_fixture("pokemoncenter", "au-tcg-cards-1.html"), "pokemoncenter-au", "en-au", "AUD")
    assert au[0].sku == UPC and au[0].price_cents == 21499 and au[0].note == "Price in AUD"


def test_product_page_and_refs():
    p = parse_product(load_fixture("pokemoncenter", "nz-product.html"), UPC, "pokemoncenter-nz", "en-nz")
    assert (p.sku, p.price_cents, p.online.level) == (UPC, 23499, Level.OUT)
    assert parse_product("<html></html>", UPC, "pokemoncenter-nz", "en-nz") is None
    with pytest.raises(ValueError):
        parse_category("<html></html>", "pokemoncenter-nz", "en-nz")
    a = adapter(FakeChain())
    assert a.parse_ref(p.url + "?srsltid=x") == UPC
    assert a.matches_url("https://www.pokemoncenter.com/en-nz/product/10-10065-109/x")
    assert not a.matches_url("https://www.pokemoncenter.com/en-au/product/10-10065-109/x")
    assert not adapter(FakeChain(), "pokemoncenter-uk").matches_url("https://www.pokemoncenter.com/en-us/product/1")


def _nz_chain():
    a = adapter(FakeChain())
    page1, page2 = load_fixture("pokemoncenter", "nz-tcg-cards-1.html"), load_fixture("pokemoncenter", "nz-tcg-cards-2.html")
    return FakeChain({a.category_url(1): page1}, default=page2), page1


async def test_discover_reads_page_one_then_sweeps_on_schedule_or_stock_change(monkeypatch):
    chain, page1 = _nz_chain()
    a = adapter(chain)
    clock = [1_000_000.0]
    monkeypatch.setattr(pokemoncenter.time, "time", lambda: clock[0])

    first = await a.discover()  # first run: every page (303 products = 10 pages)
    assert len(chain.calls) == 10
    assert all(order == ("zyte",) and country == "NZ" and queue for _, order, country, queue in chain.calls)
    assert chain.calls[1][0].endswith("sort=launch_date%2Bdesc&page=2")
    queue = first[-1]
    assert (queue.sku, queue.kind, queue.online.level) == (QUEUE_SKU, "queue", Level.OUT)
    assert len({p.sku for p in first[:-1]}) == 24  # page 1 and the (repeated) page 2 fixture, deduplicated

    chain.calls.clear()
    clock[0] += 60
    assert await a.discover() == [] and chain.calls == []  # not due yet (NZ: every 3 minutes)

    clock[0] += 180
    assert len(await a.discover()) == 13 and len(chain.calls) == 1  # page 1 only

    chain.calls.clear()
    clock[0] += 180
    restocked = page1.replace('"count": 303', '"count": 302}, {"name": "IN_STOCK", "count": 1')
    chain.pages[a.category_url(1)] = restocked
    await a.discover()
    assert len(chain.calls) == 10  # the in-stock count changed: read every page

    chain.calls.clear()
    clock[0] += 6 * 3600
    await a.discover()
    assert len(chain.calls) == 10  # the 6-hourly sweep


async def test_au_and_uk_read_every_ten_minutes_with_their_country(monkeypatch):
    clock = [1_000_000.0]
    monkeypatch.setattr(pokemoncenter.time, "time", lambda: clock[0])
    a = adapter(FakeChain(), "pokemoncenter-uk")
    chain = FakeChain({a.category_url(1): load_fixture("pokemoncenter", "uk-tcg-cards-1.html")},
                      default=load_fixture("pokemoncenter", "uk-tcg-cards-1.html"))
    a = adapter(chain, "pokemoncenter-uk")
    await a.discover()
    assert len(chain.calls) == 19 and {c[2] for c in chain.calls} == {"GB"}  # 590 products
    assert chain.calls[0][0].startswith("https://www.pokemoncenter.com/en-gb/category/tcg-cards?")
    chain.calls.clear()
    clock[0] += 300
    assert await a.discover() == []
    clock[0] += 300
    await a.discover()
    assert len(chain.calls) == 1


async def test_queue_page_turns_the_queue_on():
    a = adapter(FakeChain(fail=Queued("waiting room", 200)))
    [status] = await a.discover()
    assert (status.sku, status.kind, status.online.level, status.franchise) == (QUEUE_SKU, "queue", Level.IN, "pokemon")
    assert status.title == "Pokémon Center NZ queue is live" and status.url == "https://www.pokemoncenter.com/en-nz"


async def test_an_unexpected_page_is_logged_and_fails_the_run(caplog):
    a = adapter(FakeChain(default="<html><title>Something else</title><body>Hello</body></html>"))
    with pytest.raises(FetchError):
        await a.discover()
    assert "unexpected page" in caplog.text and "Something else" in caplog.text


async def test_fetch_products_reads_the_product_page():
    url = "https://www.pokemoncenter.com/en-nz/product/10-10065-109"
    a = adapter(FakeChain({url: load_fixture("pokemoncenter", "nz-product.html")}))
    [p] = await a.fetch_products([UPC])
    assert p.online.level is Level.OUT
    gone = adapter(FakeChain(fail=FetchError("gone", status=404)))
    assert await gone.fetch_products([UPC]) == []


def test_no_keyword_searches():
    retailers = [{"id": "pokemoncenter-nz", "adapter": "pokemoncenter", "enabled": True, "config": {}}]
    watches = [{"id": 1, "kind": "keyword", "query": "30th", "retailer_id": None, "store_ids": None,
                "franchise": None, "interval_seconds": None, "enabled": True}]
    jobs = plan_jobs(retailers, watches, sku_interval=60, search_interval=300, store_sync_interval=86400,
                     discover_interval=180)
    assert [j["kind"] for j in jobs] == ["discover"]


# --- queue detection and per-request country in the network layer ---------------------------

POLICY = NetPolicy("pokemoncenter-nz", requests_per_minute=6000)
URL = "https://www.pokemoncenter.com/en-nz/category/tcg-cards"


def test_queue_page_markers():
    assert looks_like_queue_page(QUEUE_PAGE)
    assert looks_like_queue_page("<p>Your estimated wait time is 12 minutes</p>")
    assert not looks_like_queue_page(load_fixture("pokemoncenter", "nz-tcg-cards-1.html"))
    assert not looks_like_queue_page("<html>" + "waiting room " + "x" * 400_000 + "</html>")  # a real, big page


class FakeResponse:
    def __init__(self, status, text="", headers=None, data=None):
        self.status_code, self.text, self.headers, self._data = status, text, headers or {}, data

    def json(self):
        return self._data


class FakeSession:
    def __init__(self, resp):
        self.resp, self.calls = resp, []

    async def get(self, url, params=None):
        self.calls.append(params)
        return self.resp

    async def post(self, url, json=None, auth=None, **kw):
        self.calls.append(json)
        return self.resp


def _zyte(text, status=200):
    return FakeSession(FakeResponse(200, data={"statusCode": status,
                                               "httpResponseBody": base64.b64encode(text.encode()).decode()}))


async def test_zyte_country_and_queue_detection():
    session = _zyte(QUEUE_PAGE)
    b = ZyteBackend("zk", "nz", session=session)
    with pytest.raises(Queued) as exc:
        await b.fetch(POLICY, "o", URL, None, country="GB", detect_queue=True)
    assert exc.value.status == 200 and session.calls[0]["geolocation"] == "GB"
    text, _ = await ZyteBackend("zk", "nz", session=_zyte(QUEUE_PAGE)).fetch(POLICY, "o", URL, None)
    assert text == QUEUE_PAGE  # other retailers never asked for queue detection: unchanged


async def test_scrapfly_country_override():
    session = FakeSession(FakeResponse(200, "<html>" + "x" * 30_000 + "</html>", {"x-scrapfly-api-cost": "1"}))
    await ScrapFlyBackend("k", "nz", session=session).fetch(POLICY, "o", URL, None, country="AU")
    assert session.calls[0]["country"] == "au"


class OptionRoute:
    paid, posts = True, True

    def __init__(self, name, options, answer):
        self.name, self.options, self.answer, self.kwargs = name, options, answer, None

    async def fetch(self, policy, origin, url, headers, **kwargs):
        self.kwargs = kwargs
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer, 0.0


async def test_chain_passes_options_only_to_routes_that_take_them_and_a_queue_is_an_answer():
    plain = OptionRoute("browser", False, "<html>page</html>")
    c = FetchChain([plain], MemoryChainStore(), budget_usd=10, cooldowns=Cooldowns(1, 1))
    await c.fetch_text(POLICY, "o", URL, None, ["browser"], country="NZ", detect_queue=True)
    assert plain.kwargs == {}

    queued = OptionRoute("zyte", True, Queued("waiting room", 200))
    store = MemoryChainStore()
    c = FetchChain([queued, OptionRoute("scrapfly", True, "page")], store, budget_usd=10, cooldowns=Cooldowns(1, 1))
    with pytest.raises(Queued):
        await c.fetch_text(POLICY, "o", URL, None, ["zyte", "scrapfly"], country="NZ", detect_queue=True)
    assert queued.kwargs == {"country": "NZ", "detect_queue": True}
    assert not await store.is_open("pokemoncenter-nz", "zyte")  # not rested: the store answered


# --- routing and the alert --------------------------------------------------------------------


def _event(retailer_id="pokemoncenter-uk", overseas=True, kind=EventType.RESTOCK):
    extra = {"retailer_name": "Pokémon Center UK"}
    if overseas:
        extra["overseas"] = True
    return Event(type=kind, retailer_id=retailer_id, sku="x", title="Pokémon TCG: 30th Celebration Mini Tin",
                 url="https://www.pokemoncenter.com/en-gb", franchise="pokemon", new_level="in", extra=extra)


def _route(**kw):
    return {"retailer_id": None, "store_id": None, "franchise": None, "event_types": None, "keywords": None, **kw}


def test_overseas_alerts_only_reach_routes_that_name_the_store():
    assert not route_matches(_route(franchise="pokemon", store_id=""), _event())
    assert not route_matches(_route(), _event())  # catch-all and member pings
    assert route_matches(_route(retailer_id="pokemoncenter-uk"), _event())
    assert route_matches(_route(franchise="pokemon", store_id=""), _event("pokemoncenter-nz", overseas=False))


def test_queue_alert_reaches_default_routes_and_has_its_own_card():
    event = _event("pokemoncenter-nz", overseas=False, kind=EventType.QUEUE)
    event.title = "Pokémon Center NZ queue is live"
    assert route_matches(_route(retailer_id="pokemoncenter-nz"), event)
    assert route_matches(_route(franchise="pokemon", store_id="", event_types=["new_product", "restock", "queue"]), event)
    assert not route_matches(_route(franchise="pokemon", event_types=["new_product", "restock"]), event)
    embed = build_embed(event)
    assert embed.author.name.startswith("🚦 Queue live") and "waiting room" in embed.description
    assert embed.title == "Pokémon Center NZ queue is live"


# --- the queue status row and overseas alerts, end to end through the database ---------------------


async def test_queue_alerts_once_when_it_turns_on(pool):
    from tcgpings.db import queries
    from tcgpings.engine.pipeline import Pipeline
    from tcgpings.engine.router import RouteCache

    rid, (name, config) = "pokemoncenter-nz", RETAILERS["pokemoncenter-nz"]
    await queries.upsert_retailer(pool, rid, "pokemoncenter", name, config)
    await queries.add_route(pool, 1, "https://discord.test/pc-nz", retailer_id=rid)
    await queries.add_route(pool, 2, "https://discord.test/pokemon-online", franchise="pokemon", store_id="",
                            event_types=["new_product", "restock"])
    retailer = {"id": rid, "name": name, "color": None, "config": config}
    pipe = Pipeline(pool, RouteCache(pool), cooldown_seconds=900)
    a = adapter(FakeChain())

    assert await pipe.record(retailer, a.queue_status(False), announce_new=True) == []  # silent baseline
    [event] = await pipe.record(retailer, a.queue_status(True))
    assert event.type is EventType.QUEUE and event.title == "Pokémon Center NZ queue is live"
    assert await pipe.record(retailer, a.queue_status(True)) == []  # still on: no repeat
    assert await pipe.record(retailer, a.queue_status(False)) == []  # off: quiet
    rows = await pool.fetch("SELECT route_id, payload FROM alert_outbox")
    assert [(r["route_id"], r["payload"]["type"]) for r in rows] == [(1, "queue")]


async def test_overseas_restock_skips_game_channels(pool):
    from tcgpings.db import queries
    from tcgpings.engine.pipeline import Pipeline
    from tcgpings.engine.router import RouteCache
    from tcgpings.models import Product, Stock

    rid, (name, config) = "pokemoncenter-uk", RETAILERS["pokemoncenter-uk"]
    await queries.upsert_retailer(pool, rid, "pokemoncenter", name, config)
    await queries.add_route(pool, 1, "https://discord.test/pc-uk", retailer_id=rid)
    await queries.add_route(pool, 2, "https://discord.test/pokemon-online", franchise="pokemon", store_id="")
    await queries.add_route(pool, 3, "https://discord.test/catch-all")
    retailer = {"id": rid, "name": name, "color": None, "config": config}
    pipe = Pipeline(pool, RouteCache(pool), cooldown_seconds=900)

    def tin(level):
        return Product(rid, "10-10600-101", "Pokémon TCG: 30th Celebration Mini Tin – Mew (Day)", "https://x",
                       price_cents=999, online=Stock(level))

    await pipe.record(retailer, tin(Level.OUT))
    await pipe.record(retailer, tin(Level.IN))
    rows = await pool.fetch("SELECT route_id, payload FROM alert_outbox")
    assert [r["route_id"] for r in rows] == [1]
    assert rows[0]["payload"]["extra"]["overseas"] is True
