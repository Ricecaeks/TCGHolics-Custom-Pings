"""Mighty Ape: JSON-LD on category and product pages (fixtures trimmed from pages fetched through
ScrapFly on 2026-11-05), the category schedule, and no keyword searches."""

import tcgpings.retailers  # noqa: F401  (registers adapters)
from conftest import load_fixture

from tcgpings.engine.planner import plan_jobs
from tcgpings.models import Level
from tcgpings.net.http import FetchError
from tcgpings.retailers import mightyape
from tcgpings.retailers.base import REGISTRY
from tcgpings.retailers.mightyape import CATEGORIES, MightyApeAdapter, parse_category, parse_product

ID, NAME, CONFIG, _COLOR = MightyApeAdapter.default_retailers[0]
ROW = {"id": ID, "adapter": "mightyape", "name": NAME, "config": CONFIG,
       "requests_per_minute": 4, "proxy_policy": "direct", "color": None}
PITCH_BLACK = "kogan-international-pokemon-tcg-pitch-black-booster-pack-41201033"


class FakeChain:
    def __init__(self, pages=None, fail=None):
        self.pages = pages or {}
        self.fail = fail
        self.calls = []

    def available(self, order):
        return list(order)

    async def fetch_text(self, policy, origin, url, headers=None, order=None, body=None):
        self.calls.append((url, tuple(order or ())))
        if self.fail:
            raise self.fail
        return self.pages.get(url, "<html></html>")


class Http:
    def __init__(self, chain):
        self.chain = chain


def adapter(chain):
    return MightyApeAdapter(ROW, Http(chain))


def test_registered_with_scrapfly_and_its_categories():
    assert REGISTRY["mightyape"] is MightyApeAdapter
    assert CONFIG["fetch"] == ["scrapfly"] and CONFIG["categories"] == CATEGORIES
    assert MightyApeAdapter.supports_search is False


def test_pokemon_category():
    products = {p.sku: p for p in parse_category(load_fixture("mightyape", "pokemon.html"))}
    assert len(products) == 36
    p = products[PITCH_BLACK]
    assert p.title == "Pokemon TCG: Pitch Black - Booster Pack" and p.online.level is Level.IN
    assert p.url == f"https://www.mightyape.co.nz/mn/buy/{PITCH_BLACK}/"
    assert p.price_cents == 1299  # the regular price, not the members' 10.99
    assert p.image.startswith("https://assets.kogan.com/images/product/MPE-41201033/")
    levels = [p.online.level for p in products.values()]
    assert levels.count(Level.IN) == 15 and levels.count(Level.OUT) == 21  # 9 in stock + 6 preorders
    preorders = [p for p in products.values() if p.note == "Pre-order"]
    assert len(preorders) == 6 and any("Delta Reign - Booster Pack" in p.title for p in preorders)


def test_all_cards_category_and_product_page():
    assert len(parse_category(load_fixture("mightyape", "cards.html"))) == 36
    p = parse_product(load_fixture("mightyape", "product.html"), PITCH_BLACK)
    assert (p.sku, p.price_cents, p.online.level) == (PITCH_BLACK, 1299, Level.IN)
    assert parse_product("<html></html>", "x") is None and parse_category("<html></html>") == []


async def test_discover_reads_pokemon_every_run_and_all_cards_every_other(monkeypatch):
    pokemon_url = mightyape.CATEGORY + CATEGORIES[0]["path"]
    cards_url = mightyape.CATEGORY + CATEGORIES[1]["path"]
    chain = FakeChain({pokemon_url: load_fixture("mightyape", "pokemon.html"),
                       cards_url: load_fixture("mightyape", "cards.html")})
    a = adapter(chain)
    clock = [1_000_000.0]
    monkeypatch.setattr(mightyape.time, "time", lambda: clock[0])

    first = await a.discover()
    assert [u for u, _ in chain.calls] == [pokemon_url, cards_url]
    assert all(order == ("scrapfly",) for _, order in chain.calls)
    assert len({p.sku for p in first}) > 36  # both pages, merged

    for minutes, expected in [(30, [pokemon_url]), (60, [pokemon_url, cards_url]), (61, [])]:
        clock[0] = 1_000_000.0 + minutes * 60
        chain.calls.clear()
        await a.discover()
        assert [u for u, _ in chain.calls] == expected, minutes


async def test_fetch_products_and_refs():
    url = f"https://www.mightyape.co.nz/mn/buy/{PITCH_BLACK}/"
    a = adapter(FakeChain({url: load_fixture("mightyape", "product.html")}))
    [p] = await a.fetch_products([PITCH_BLACK])
    assert p.online.level is Level.IN
    assert a.parse_ref(url + "?ssid=1&click_id=x") == PITCH_BLACK
    assert a.matches_url(url) and not a.matches_url("https://www.mightyape.com.au/x")
    missing = adapter(FakeChain(fail=FetchError("gone", status=404)))
    assert await missing.fetch_products([PITCH_BLACK]) == []


async def test_no_chain_is_an_error_not_a_crash():
    import pytest

    with pytest.raises(FetchError):
        await MightyApeAdapter(ROW, object()).discover()


def test_keyword_watches_skip_mighty_ape():
    retailers = [{"id": "mightyape", "adapter": "mightyape", "enabled": True, "config": {}},
                 {"id": "card-merchant", "adapter": "shopify", "enabled": True, "config": {}}]
    watches = [{"id": 1, "kind": "keyword", "query": "delta reign", "retailer_id": None, "store_ids": None,
                "franchise": None, "interval_seconds": None, "enabled": True}]
    jobs = plan_jobs(retailers, watches, sku_interval=60, search_interval=300, store_sync_interval=86400,
                     discover_interval=180)
    searched = {j["retailer_id"] for j in jobs if j["kind"] == "watch_search"}
    assert searched == {"card-merchant"}
    assert any(j["kind"] == "discover" and j["retailer_id"] == "mightyape" for j in jobs)
