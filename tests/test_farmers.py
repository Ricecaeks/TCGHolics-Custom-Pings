"""Farmers parsing against trimmed real responses captured 2026-10-29 (tests/fixtures/farmers)."""

import pytest
from conftest import load_fixture

from tcgpings.models import Level
from tcgpings.net.http import Blocked, FetchError
from tcgpings.retailers.farmers import (
    FarmersAdapter, load_stores, parse_product, parse_search, parse_store_stock, store_level,
)

ROW = {"id": "farmers", "adapter": "farmers", "name": "Farmers", "config": {},
       "requests_per_minute": 10, "proxy_policy": "direct", "color": None}


def test_store_list_is_complete_and_unique():
    stores = load_stores()
    assert len(stores) == 53
    assert len({s["store_id"] for s in stores}) == 53
    assert len({s["region_code"] for s in stores}) == 13
    northwest = next(s for s in stores if s["store_id"] == "northwest")
    assert "Westgate" in northwest["address"]


def test_parse_search_tiles():
    products = parse_search(load_fixture("farmers", "search.html"))
    assert [p.sku for p in products] == ["7052751", "7044418", "7044417", "7038939", "7052756"]
    zygarde = products[2]
    assert zygarde.title == "Pokemon Trading Card Mega Zygarde EX Premium Collection Box"
    assert zygarde.price_cents == 9999
    assert zygarde.url.endswith("-7044417")
    assert zygarde.image == "https://www.farmers.co.nz/INTERSHOP/static/WFS/Farmers-Shop-Site/-/Farmers-Shop/en_NZ/product/70/44/417/7044417_00_W350_H456.jpg"
    assert zygarde.online is None
    assert products[3].title == "Pokemon Trading Card Pikachu Toploader & Penny Sleeves"


def test_parse_product_json_ld():
    p = parse_product(load_fixture("farmers", "product.html"), "7044417")
    assert p.sku == "7044417" and p.price_cents == 9999
    assert p.online.level is Level.IN
    assert p.url.endswith("pokemon-trading-card-mega-zygarde-ex-premium-collection-box-7044417")
    assert p.image.startswith("https://www.farmers.co.nz/INTERSHOP/") and ":443" not in p.image


def test_parse_product_out_of_stock_and_missing():
    page = load_fixture("farmers", "product.html").replace("schema.org/InStock", "schema.org/OutOfStock")
    assert parse_product(page, "7044417").online.level is Level.OUT
    assert parse_product("<html>not a product</html>", "1") is None


def test_parse_store_stock_auckland():
    stock = parse_store_stock(load_fixture("farmers", "stores-AUK.html"))
    assert len(stock) == 15
    assert stock["albany"].level is Level.IN
    assert stock["northwest"].level is Level.OUT
    assert stock["st-lukes"].level is Level.OUT
    known = {s["store_id"] for s in load_stores()}
    assert set(stock) <= known, "every store name on the site maps to a known store id"


@pytest.mark.parametrize("text, level", [
    ("In Stock", Level.IN), ("Not In Stock", Level.OUT), ("Low Stock", Level.LOW),
    ("Limited stock", Level.LOW), ("", Level.UNKNOWN), ("Call store", Level.UNKNOWN),
])
def test_store_level(text, level):
    assert store_level(text) is level


class FakeBrowser:
    def __init__(self, pages):
        self.pages = pages
        self.urls = []

    async def fetch_text(self, policy, origin, url, headers=None):
        self.urls.append(url)
        for key, value in self.pages.items():
            if key in url:
                if isinstance(value, Exception):
                    raise value
                return value
        raise FetchError(f"GET {url}: HTTP 404")


class FakeHttp:
    def __init__(self, browser):
        self.browser = browser


def adapter(pages):
    return FarmersAdapter(ROW, FakeHttp(FakeBrowser(pages)))


async def test_store_stock_only_queries_needed_regions():
    a = adapter({"State=AUK": load_fixture("farmers", "stores-AUK.html"),
                 "State=NTL": load_fixture("farmers", "stores-NTL.html")})
    stock = await a.store_stock("7044417", ["northwest", "albany", "kaitaia"])
    assert set(stock) == {"northwest", "albany", "kaitaia"}
    assert stock["albany"].level is Level.IN
    regions = sorted(u.split("State=")[1] for u in a.http.browser.urls)
    assert regions == ["AUK", "NTL"]


async def test_fetch_products_skips_missing_and_raises_blocks():
    a = adapter({"SKU=7044417": load_fixture("farmers", "product.html")})
    assert [p.sku for p in await a.fetch_products(["7044417", "9999999"])] == ["7044417"]
    blocked = adapter({"SKU=": Blocked("denied")})
    with pytest.raises(Blocked):
        await blocked.fetch_products(["7044417"])


async def test_needs_browser():
    a = FarmersAdapter(ROW, FakeHttp(None))
    with pytest.raises(FetchError, match="browser"):
        await a.search("pokemon")


def test_parse_ref():
    a = adapter({})
    assert a.parse_ref("https://www.farmers.co.nz/toys/games-cards-puzzles/trading-cards/pokemon-x-7044417") == "7044417"
    assert a.parse_ref("https://www.farmers.co.nz/INTERSHOP/web/WFS/Farmers-Shop-Site/en_NZ/-/NZD/ViewProduct-Start?SKU=7044417") == "7044417"
    assert a.parse_ref("7044417") == "7044417"
    assert a.matches_url("https://www.farmers.co.nz/anything")
    with pytest.raises(ValueError):
        a.parse_ref("https://www.farmers.co.nz/toys")
