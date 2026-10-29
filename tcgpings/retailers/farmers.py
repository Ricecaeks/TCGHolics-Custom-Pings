"""Farmers (farmers.co.nz). Intershop storefront behind Akamai Bot Manager; see docs/RETAILERS.md.

All requests go through the real-browser fetcher (net/browser.py): plain HTTP clients are
blocked after a couple of requests.

- Search:      /filter/0/Page-0-PageSize-96-...?SearchTerm=<q>  (HTML product tiles)
- Product:     ViewProduct-Start?SKU=<sku>                       (JSON-LD: price, online availability)
- Store stock: ViewCheckoutShipping-GetAvailableStoresAjax?...&SKU=<sku>&State=<region>
               one call per region; "In Stock" / "Not In Stock" per store. Farmers refreshes
               store stock once a day (~8am), so it's checked every few hours at most.
Stores have no ids on the site, only names; the store id is the slugified name.
"""

from __future__ import annotations

import html
import json
import re
from importlib import resources
from urllib.parse import quote, urlparse

from tcgpings.models import Level, Product, Stock, Store, slugify, to_cents
from tcgpings.net.http import FetchError
from tcgpings.retailers.base import RetailerAdapter, register

BASE = "https://www.farmers.co.nz"
ISH = f"{BASE}/INTERSHOP/web/WFS/Farmers-Shop-Site/en_NZ/-/NZD"
XHR = {"X-Requested-With": "XMLHttpRequest", "Accept": "text/html, */*; q=0.01"}

AVAILABILITY = {
    "InStock": Level.IN,
    "LimitedAvailability": Level.LOW,
    "OnlineOnly": Level.IN,
    "PreOrder": Level.IN,
    "BackOrder": Level.OUT,
    "OutOfStock": Level.OUT,
    "SoldOut": Level.OUT,
    "Discontinued": Level.OUT,
}

_TILE = re.compile(r'<div class="product-tile"')
_TILE_SKU = re.compile(r'data-cnstrc-item-id="(\d+)"')
_TILE_NAME = re.compile(r'data-cnstrc-item-name="([^"]*)"')
_TILE_HREF = re.compile(r'<a class="product-title" href="([^"]+)"')
_TILE_IMG = re.compile(r'<img src="([^"]+)"[^>]*class="product-image"')
_TILE_PRICE = re.compile(r'class="current-price"[^>]*>(?:\s*<!--.*?-->)?\s*([^<]+)<', re.S)
_LD = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
_CANONICAL = re.compile(r'<link rel="canonical" href="([^"]+)"')
_STORE_BLOCK = re.compile(r'<div class="panel-heading">')
_STORE_NAME = re.compile(r'class="store__name">\s*<span>(.*?)</span>', re.S)
_STORE_STOCK = re.compile(r'class="store-stock">(.*?)</div>', re.S)
_SKU_IN_URL = re.compile(r"-(\d{6,8})(?:[/?#]|$)")


def load_stores() -> list[dict]:
    data = resources.files("tcgpings.retailers.data").joinpath("farmers_stores.json").read_text(encoding="utf-8")
    return json.loads(data)["stores"]


def store_level(text: str) -> Level:
    t = text.strip().lower()
    if not t:
        return Level.UNKNOWN
    if "not" in t or "out of" in t or "unavailable" in t:
        return Level.OUT
    if "low" in t or "limited" in t:
        return Level.LOW
    if "in stock" in t or "available" in t:
        return Level.IN
    return Level.UNKNOWN


def parse_search(page: str, retailer_id: str = "farmers") -> list[Product]:
    products = []
    for chunk in _TILE.split(page)[1:]:
        sku, href = _TILE_SKU.search(chunk), _TILE_HREF.search(chunk)
        if not sku or not href:
            continue
        name = _TILE_NAME.search(chunk)
        img = _TILE_IMG.search(chunk)
        price = _TILE_PRICE.search(chunk)
        image = img.group(1) if img else None
        if image and image.startswith("/"):
            image = BASE + image.split("?")[0]
        products.append(Product(
            retailer_id=retailer_id,
            sku=sku.group(1),
            title=html.unescape(name.group(1)) if name else "",
            url=href.group(1),
            image=image,
            price_cents=to_cents(price.group(1)) if price else None,
            online=None,  # tiles don't show stock; the product job fills it in
        ))
    return products


def parse_product(page: str, sku: str, retailer_id: str = "farmers") -> Product | None:
    for block in _LD.findall(page):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        if data.get("@type") != "Product":
            continue
        offer = data.get("offers") or {}
        if isinstance(offer, list):
            offer = offer[0] if offer else {}
        availability = str(offer.get("availability", "")).rsplit("/", 1)[-1]
        images = data.get("image") or []
        image = images[0] if isinstance(images, list) and images else (images or None)
        canonical = _CANONICAL.search(page)
        return Product(
            retailer_id=retailer_id,
            sku=str(data.get("sku") or sku),
            title=html.unescape(data.get("name", "")),
            url=offer.get("url") or (canonical.group(1) if canonical else f"{ISH}/ViewProduct-Start?SKU={sku}"),
            image=image.replace(":443/", "/") if image else None,
            price_cents=to_cents(offer.get("price")),
            online=Stock(AVAILABILITY.get(availability, Level.UNKNOWN)),
        )
    return None


def parse_store_stock(page: str) -> dict[str, Stock]:
    """Store slug -> stock for one region's response."""
    out: dict[str, Stock] = {}
    for chunk in _STORE_BLOCK.split(page)[1:]:
        name, stock = _STORE_NAME.search(chunk), _STORE_STOCK.search(chunk)
        if name:
            out[slugify(html.unescape(name.group(1).strip()))] = Stock(store_level(stock.group(1)) if stock else Level.UNKNOWN)
    return out


@register
class FarmersAdapter(RetailerAdapter):
    adapter_name = "farmers"
    supports_store_stock = True
    # Store stock refreshes once a day (~8am); a 13-region sweep every 4h catches it.
    store_stock_interval = 4 * 3600
    default_sku_interval = 15 * 60
    default_search_interval = 30 * 60
    default_retailers = [("farmers", "Farmers", {}, 0x5B2C83)]
    default_requests_per_minute = 10  # be gentle: Akamai scores request bursts
    default_enabled = False  # turn on with /retailer set retailer:farmers enabled:true

    def __init__(self, retailer, http) -> None:
        super().__init__(retailer, http)
        self._stores = load_stores()
        self._region_of = {s["store_id"]: s["region_code"] for s in self._stores}

    async def _get(self, url: str) -> str:
        if self.http.browser is None:
            raise FetchError("farmers needs the browser fetcher (Chrome) but it isn't enabled on this node")
        return await self.http.browser.fetch_text(self.policy, BASE + "/", url, XHR)

    async def search(self, query: str) -> list[Product]:
        url = (f"{BASE}/filter/0/Page-0-PageSize-96-ExcludeFromKeywordSearchResult-false-"
               f"SortingAttribute-SortBy-asc?SearchTerm={quote(query)}")
        return parse_search(await self._get(url), self.retailer_id)

    async def fetch_products(self, skus: list[str]) -> list[Product]:
        products = []
        for sku in skus:
            try:
                page = await self._get(f"{ISH}/ViewProduct-Start?SKU={quote(sku)}")
            except FetchError as exc:
                if "HTTP 404" in str(exc):
                    continue
                raise
            product = parse_product(page, sku, self.retailer_id)
            if product:
                products.append(product)
        return products

    async def list_stores(self) -> list[Store]:
        return [Store(self.retailer_id, s["store_id"], s["name"], s["region"]) for s in self._stores]

    async def store_stock(self, sku: str, store_ids: list[str]) -> dict[str, Stock]:
        wanted = set(store_ids)
        regions = sorted({self._region_of[s] for s in wanted if s in self._region_of})
        stock: dict[str, Stock] = {}
        for region in regions:
            url = (f"{ISH}/ViewCheckoutShipping-GetAvailableStoresAjax"
                   f"?CountryCode=NZ&NoShippingFilter=true&SKU={quote(sku)}&State={region}")
            for store_id, s in parse_store_stock(await self._get(url)).items():
                if store_id in wanted:
                    stock[store_id] = s
        return stock

    def parse_ref(self, ref: str) -> str:
        ref = ref.strip()
        if ref.isdigit():
            return ref
        m = _SKU_IN_URL.search(urlparse(ref).path) or re.search(r"SKU=(\d+)", ref)
        if not m:
            raise ValueError(f"no Farmers SKU in {ref!r}")
        return m.group(1)

    def matches_url(self, url: str) -> bool:
        return urlparse(url).netloc.endswith("farmers.co.nz")
