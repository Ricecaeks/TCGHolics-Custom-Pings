"""Shopify adapter parsing. Fixtures follow the public storefront JSON shape (/products.json, /products/<h>.js)."""

from conftest import load_fixture

from tcgpings.models import Level
from tcgpings.net.http import FetchError
from tcgpings.retailers.shopify import ShopifyAdapter

ROW = {
    "id": "cardshop", "adapter": "shopify", "name": "Card Shop", "config": {"domain": "https://cardshop.co.nz/"},
    "requests_per_minute": 60, "proxy_policy": "direct", "color": None,
}


class FakeHttp:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    async def get_json(self, policy, url, params=None, **kw):
        self.calls.append((url, params))
        if url not in self.routes:
            raise FetchError(f"GET {url}: HTTP 404")
        result = self.routes[url]
        if isinstance(result, Exception):
            raise result
        return result(params) if callable(result) else result


def adapter(routes):
    return ShopifyAdapter(ROW, FakeHttp(routes))


async def test_search_filters_catalogue_by_query():
    a = adapter({"https://cardshop.co.nz/products.json": load_fixture("shopify", "products.json")})
    results = await a.search("pokemon")
    assert [p.sku for p in results] == ["pokemon-30th-celebration-booster-bundle", "pokemon-prismatic-evolutions-etb"]
    bundle, etb = results
    assert bundle.online.level is Level.IN and bundle.price_cents == 5999
    assert bundle.url == "https://cardshop.co.nz/products/pokemon-30th-celebration-booster-bundle"
    assert bundle.image == "https://cdn.shopify.com/s/files/1/bundle.jpg"
    assert etb.online.level is Level.OUT and etb.price_cents == 8900 and etb.image is None


async def test_search_matches_tags_and_stops_on_short_page():
    a = adapter({"https://cardshop.co.nz/products.json": load_fixture("shopify", "products.json")})
    assert [p.sku for p in await a.search("etb")] == ["pokemon-prismatic-evolutions-etb"]
    assert [c[0].rsplit("/", 1)[1] for c in a.http.calls] == ["suggest.json", "products.json"]


async def test_catalogue_scan_is_capped_at_catalogue_pages():
    raw = load_fixture("shopify", "products.json")["products"][2]
    pages = {str(n): [dict(raw, handle=f"op-{n}-{i}") for i in range(250)] for n in range(1, 5)}
    a = adapter({"https://cardshop.co.nz/products.json": lambda params: {"products": pages.get(params["page"], [])}})
    assert len(await a.search("one piece")) == 500  # default: first 2 pages (most recently updated)
    a.catalogue_pages = 10
    assert len(await a.search("one piece")) == 1000


async def test_predictive_search_finds_older_products_and_filters_fuzzy_matches():
    a = adapter({
        "https://cardshop.co.nz/search/suggest.json": load_fixture("shopify", "suggest.json"),
        "https://cardshop.co.nz/products.json": {"products": []},
    })
    results = {p.sku: p for p in await a.search("pokemon bundle")}
    assert list(results) == ["pokemon-30th-celebration-booster-bundle"]  # "MTG Bundle" filtered out
    p = results["pokemon-30th-celebration-booster-bundle"]
    assert p.online.level is Level.OUT and p.price_cents == 5499
    assert p.url == "https://cardshop.co.nz/products/pokemon-30th-celebration-booster-bundle"
    assert a.http.calls[0][1]["q"] == "pokemon bundle"


async def test_franchise_from_tags_when_title_lacks_it():
    a = adapter({"https://cardshop.co.nz/search/suggest.json": load_fixture("shopify", "suggest.json"),
                 "https://cardshop.co.nz/products.json": {"products": []}})
    [zard] = await a.search("charizard")
    assert zard.franchise == "pokemon" and zard.price_cents == 125000
    assert zard.image == "https://cdn.shopify.com/s/files/1/zard.jpg"


async def test_catalogue_result_wins_over_suggest_for_same_handle():
    a = adapter({"https://cardshop.co.nz/search/suggest.json": load_fixture("shopify", "suggest.json"),
                 "https://cardshop.co.nz/products.json": load_fixture("shopify", "products.json")})
    results = {p.sku: p for p in await a.search("30th")}
    assert results["pokemon-30th-celebration-booster-bundle"].online.level is Level.IN


async def test_fetch_product_js_uses_cents_and_fixes_protocol_relative_image():
    handle = "pokemon-30th-celebration-booster-bundle"
    a = adapter({f"https://cardshop.co.nz/products/{handle}.js": load_fixture("shopify", "product.js")})
    [p] = await a.fetch_products([handle])
    assert p.online.level is Level.OUT and p.price_cents == 5499
    assert p.image == "https://cdn.shopify.com/s/files/1/bundle.jpg"


async def test_delisted_product_is_skipped():
    a = adapter({"https://cardshop.co.nz/products/gone.js": FetchError("GET x: HTTP 404")})
    assert await a.fetch_products(["gone"]) == []


def test_parse_ref_and_matches_url():
    a = adapter({})
    assert a.parse_ref("https://cardshop.co.nz/products/op-10-box?variant=1") == "op-10-box"
    assert a.parse_ref("https://cardshop.co.nz/collections/tcg/products/op-10-box") == "op-10-box"
    assert a.parse_ref("op-10-box") == "op-10-box"
    assert a.matches_url("https://www.cardshop.co.nz/products/x")
    assert not a.matches_url("https://othershop.co.nz/products/x")


async def test_add_to_cart_links_use_first_available_variant():
    a = adapter({"https://cardshop.co.nz/products.json": load_fixture("shopify", "products.json")})
    by_sku = {p.sku: p for p in await a.discover()}
    assert by_sku["pokemon-30th-celebration-booster-bundle"].atc_url == "https://cardshop.co.nz/cart/1:1"
    assert by_sku["pokemon-prismatic-evolutions-etb"].atc_url == "https://cardshop.co.nz/cart/2:1"  # none available
    handle = "pokemon-30th-celebration-booster-bundle"
    b = adapter({f"https://cardshop.co.nz/products/{handle}.js": load_fixture("shopify", "product.js")})
    [p] = await b.fetch_products([handle])
    assert p.atc_url == "https://cardshop.co.nz/cart/1:1"


async def test_discover_reads_recent_catalogue_page_only():
    a = adapter({"https://cardshop.co.nz/products.json": load_fixture("shopify", "products.json")})
    assert len(await a.discover()) == 3
    assert [c[1]["page"] for c in a.http.calls] == ["1"]


async def test_discover_reads_only_configured_collections():
    from tcgpings.retailers.toyworld import ToyworldAdapter

    rid, name, config, _ = ToyworldAdapter.default_retailers[0]
    products = load_fixture("shopify", "products.json")
    routes = {f"https://www.toyworld.co.nz/collections/{h}/products.json": products for h in config["collections"]}
    a = ToyworldAdapter({**ROW, "id": rid, "adapter": "toyworld", "name": name, "config": config}, FakeHttp(routes))
    assert len(await a.discover()) == 3  # same products in both collections, counted once
    assert [c[0] for c in a.http.calls] == list(routes)


async def test_discovery_searches_keep_only_card_titles():
    from tcgpings.retailers.jbhifi import JBHiFiAdapter

    rid, name, config, _ = JBHiFiAdapter.default_retailers[0]
    assert "pokemon tcg" in config["discovery_searches"]
    suggest = {"resources": {"results": {"products": [
        {"handle": "etb", "title": "Pokémon TCG: Mega Greninja ex League Battle Deck", "available": True, "price": "45.00"},
        {"handle": "lamp", "title": "Teknofun Pokémon Eevee 30cm LED Lamp", "available": True, "price": "60.00"},
    ]}}}
    routes = {"https://www.jbhifi.co.nz/products.json": {"products": []}, "https://www.jbhifi.co.nz/search/suggest.json": suggest}
    a = JBHiFiAdapter({**ROW, "id": rid, "adapter": "jbhifi", "name": name, "config": config}, FakeHttp(routes))
    assert [p.sku for p in await a.discover()] == ["etb"]


# --- grouped search: one job runs every keyword for a shop --------------------------------

QUERIES = ["pokemon", "etb", "30th", "pokemon bundle", "charizard", "one piece", "nothing matches this"]


def fixture_routes():
    return {"https://cardshop.co.nz/search/suggest.json": load_fixture("shopify", "suggest.json"),
            "https://cardshop.co.nz/products.json": load_fixture("shopify", "products.json")}


async def test_search_many_matches_search_for_every_query():
    single = {query: await adapter(fixture_routes()).search(query) for query in QUERIES}
    grouped = await adapter(fixture_routes()).search_many(QUERIES)
    assert list(grouped) == QUERIES
    assert grouped == single  # same products, same order, same fields
    assert grouped["pokemon bundle"] and grouped["charizard"] and not grouped["nothing matches this"]


async def test_search_many_reads_the_catalogue_once():
    raw = load_fixture("shopify", "products.json")["products"][2]
    pages = {str(n): [dict(raw, handle=f"op-{n}-{i}") for i in range(250)] for n in range(1, 5)}
    routes = fixture_routes()
    routes["https://cardshop.co.nz/products.json"] = lambda params: {"products": pages.get(params["page"], [])}
    a = adapter(routes)
    results = await a.search_many(QUERIES)
    assert len(results["one piece"]) == 500
    catalogue = [c[1]["page"] for c in a.http.calls if c[0].endswith("/products.json")]
    assert catalogue == ["1", "2"]  # catalogue_pages, read once for the whole run
    assert [c[1]["q"] for c in a.http.calls if c[0].endswith("/suggest.json")] == QUERIES


async def test_search_many_keeps_going_when_one_query_fails():
    def suggest(params):
        if params["q"] == "etb":
            raise RuntimeError("suggest broke")
        return load_fixture("shopify", "suggest.json")

    routes = fixture_routes()
    routes["https://cardshop.co.nz/search/suggest.json"] = suggest
    results = await adapter(routes).search_many(["pokemon", "etb", "30th"])
    assert isinstance(results["etb"], RuntimeError)
    assert results["pokemon"] == await adapter(fixture_routes()).search("pokemon")
    assert results["30th"] == await adapter(fixture_routes()).search("30th")


async def test_search_many_fails_every_query_when_the_catalogue_fails():
    routes = fixture_routes()
    routes["https://cardshop.co.nz/products.json"] = FetchError("GET products.json: HTTP 403")
    a = adapter(routes)
    results = await a.search_many(["pokemon", "etb"])
    assert all(isinstance(r, FetchError) and "HTTP 403" in str(r) for r in results.values())
    assert [c[0].rsplit("/", 1)[1] for c in a.http.calls] == ["products.json"]  # no suggest calls wasted


async def test_default_search_many_runs_search_per_query_and_captures_errors():
    from tcgpings.retailers.base import RetailerAdapter

    class Plain(RetailerAdapter):
        adapter_name = "_plain"

        def __init__(self, retailer, http):
            super().__init__(retailer, http)
            self.searched = []

        async def search(self, query):
            self.searched.append(query)
            if query == "bad":
                raise RuntimeError("site changed")
            return [query]

        async def fetch_products(self, skus):
            return []

    a = Plain(ROW, FakeHttp({}))
    results = await a.search_many(["a", "bad", "b", "a"])
    assert a.searched == ["a", "bad", "b"]  # one search() each, in order, duplicates once
    assert results["a"] == ["a"] and results["b"] == ["b"]
    assert isinstance(results["bad"], RuntimeError)
