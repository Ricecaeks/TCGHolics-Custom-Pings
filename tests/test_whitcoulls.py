"""Whitcoulls: search JSON and product JSON-LD (fixtures trimmed from the live site 2026-11-04)."""

import json

from conftest import load_fixture

from tcgpings.models import Level
from tcgpings.net.http import FetchError
from tcgpings.retailers.base import REGISTRY
from tcgpings.retailers.whitcoulls import IN_STORES, WhitcoullsAdapter, parse_product, parse_search

ID, NAME, CONFIG, _COLOR = WhitcoullsAdapter.default_retailers[0]
ROW = {"id": ID, "adapter": "whitcoulls", "name": NAME, "config": CONFIG,
       "requests_per_minute": 12, "proxy_policy": "direct", "color": None}


class Resp:
    def __init__(self, text):
        self.text = text


class FakeHttp:
    def __init__(self, *pages, fail_on=None):
        self.pages = list(pages)
        self.fail_on = fail_on
        self.calls = []

    async def get(self, policy, url, params=None, **kw):
        self.calls.append((url, params))
        if self.fail_on and self.fail_on in str(params or url):
            raise FetchError(f"GET {url}: HTTP 500")
        return Resp(self.pages.pop(0) if self.pages else "")


def by_sku():
    return {p.sku: p for p in parse_search(load_fixture("whitcoulls", "search.html"))}


def test_registered():
    assert REGISTRY["whitcoulls"] is WhitcoullsAdapter


def test_search_items_carry_price_url_and_online_stock():
    p = by_sku()["7043527"]
    assert p.title == "Yu-Gi-Oh! Trading Card Game: Retro Pack 2 Booster Pack" and p.price_cents == 999
    assert p.url == "https://www.whitcoulls.co.nz/yu-gi-oh-trading-card-game-retro-pack-2-booster-pack-7043527"
    assert p.online.level is Level.IN and p.stores is None
    assert by_sku()["6981870"].online.level is Level.LOW  # "nearly gone!"


def test_in_store_only_is_tracked_as_stores_nationwide():
    p = by_sku()["6997342"]
    assert p.online.level is Level.OUT and p.note == "In stores, not online"
    assert p.stores[IN_STORES].level is Level.IN
    assert by_sku()["5925649"].stores[IN_STORES].level is Level.OUT  # out of stock everywhere


def test_product_page_json_ld():
    p = parse_product(load_fixture("whitcoulls", "product.html"), "6981870")
    assert (p.sku, p.price_cents, p.online.level) == ("6981870", 4499, Level.LOW)
    assert p.url.endswith("/disney-lorcana-trading-card-game-gateway-shimmering-skies-6981870")
    assert parse_product("<html></html>", "1") is None


async def test_discovery_reads_each_search_once_and_keeps_going_past_a_failure():
    page = load_fixture("whitcoulls", "search.html")
    http = FakeHttp(page, page, fail_on="booster")
    products = await WhitcoullsAdapter(ROW, http).discover()
    assert [params["q"] for _, params in http.calls] == ["trading card", "booster", "tcg"]
    assert len({p.sku for p in products}) == len(products) == len(by_sku())


async def test_fetch_by_id_redirect():
    http = FakeHttp(load_fixture("whitcoulls", "product.html"))
    [p] = await WhitcoullsAdapter(ROW, http).fetch_products(["6981870"])
    assert http.calls[0][0] == "https://www.whitcoulls.co.nz/x-6981870" and p.online.level is Level.LOW


def test_parse_ref_and_store_label():
    a = WhitcoullsAdapter(ROW, FakeHttp())
    assert a.parse_ref("https://www.whitcoulls.co.nz/disney-lorcana-gateway-6981870") == "6981870"
    assert a.parse_ref("6981870") == "6981870"
    assert a.matches_url("https://www.whitcoulls.co.nz/x-1") and a.store_label(IN_STORES) == "Stores nationwide"


def test_books_and_figures_are_not_card_products():
    def item(sku, title, category):
        return {"description": title, "stylecolour": {
            "stylecolourid": sku, "urlkey": f"x-{sku}", "attributes": {"sapcategorycode": category},
            "variants": [{"unitprice": "29.99", "status": ""}]}}
    items = [item("1", "Pokemon Encyclopedia: Horizons Edition", "57-01020510"),
             item("2", "Pokemon Select 30th Anniversary Glitter Battle Figure", "57-050503"),
             item("3", "Pokemon TCG 30th Celebration Booster Bundle", "57-040599"),
             item("4", "Magic The Gathering - Marvel Super Heroes Beginner Box", "57-040109")]
    page = "<script>window.category = {...%s};</script>" % json.dumps({"items": items})
    assert [p.sku for p in parse_search(page)] == ["3", "4"]
