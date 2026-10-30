"""Kmart adapter: Constructor listings (fixture trimmed from the live Trading Cards browse)."""

from conftest import load_fixture

from tcgpings.engine.planner import plan_jobs
from tcgpings.models import Level
from tcgpings.retailers.kmart import KmartAdapter, parse_constructor

ROW = {"id": "kmart", "adapter": "kmart", "name": "Kmart", "config": {}, "requests_per_minute": 12,
       "proxy_policy": "direct", "color": None, "enabled": True}


def by_sku():
    return {p.sku: p for p in parse_constructor(load_fixture("kmart", "browse.json"))}


def test_online_product_in_stock_in_both_islands():
    p = by_sku()["43818273"]  # Yu-Gi-Oh! Beyond the Brave booster: online and in store
    assert p.title.startswith("Konami Yu-Gi-Oh!") and p.price_cents == 950
    assert p.url == "https://www.kmart.co.nz/product/konami-yu-gi-oh!-trading-card-game:-beyond-the-brave-9-card-booster-43818273/"
    assert p.online.level is Level.IN and p.note is None
    assert {k: s.level for k, s in p.stores.items()} == {"NI": Level.IN, "SI": Level.IN}


def test_in_store_only_product_uses_island_flags():
    p = by_sku()["43788798"]  # Pitch Black Booster Bundle: in-store only, out in the South Island
    assert p.note == "In-store only" and p.online.level is Level.OUT and p.price_cents == 6200
    assert {k: s.level for k, s in p.stores.items()} == {"NI": Level.IN, "SI": Level.OUT}


def test_sold_out_everywhere():
    p = by_sku()["43818617"]  # 30th Celebration Booster Bundle
    assert p.online.level is Level.OUT
    assert all(s.level is Level.OUT for s in p.stores.values())


def test_online_product_out_in_one_island_is_still_online():
    p = by_sku()["43829248"]
    assert p.online.level is Level.IN and p.stores["NI"].level is Level.OUT


async def test_islands_are_stores_and_get_synced():
    a = KmartAdapter(ROW, http=None)
    assert [(s.store_id, s.name, s.slug) for s in await a.list_stores()] == [
        ("NI", "North Island", "north-island"), ("SI", "South Island", "south-island")]
    jobs = {j["key"] for j in plan_jobs([ROW], [], 300, 600, 86400)}
    assert jobs == {"stores:kmart", "discover:kmart"}


def test_parse_ref():
    a = KmartAdapter(ROW, http=None)
    assert a.parse_ref("43818617") == "43818617"
    assert a.parse_ref("https://www.kmart.co.nz/product/pokemon-tcg:-30th-celebration-booster-bundle-43818617/") == "43818617"
    assert a.parse_ref("https://www.kmart.co.nz/product/43818273/") == "43818273"
    assert a.matches_url("https://www.kmart.co.nz/product/43818273/")
