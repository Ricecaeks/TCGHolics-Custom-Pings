"""Farmers (farmers.co.nz). Intershop storefront behind Akamai Bot Manager; see docs/RETAILERS.md.

Two access paths:

1. Constructor.io (plain HTTP, always on). Farmers' site search is hosted on ac.cnstrc.com, outside
   Akamai; TCGHolics approved using Farmers' public client key. Gives discovery of the whole
   Trading Cards category (newest first), keyword search and online in/out of stock. No prices.
2. The fetch chain (net/chain.py): our own Chrome first, then ScrapFly, then Zyte, for Farmers'
   own endpoints behind Akamai. Used once a day per tracked product, after the ~8am store refresh:
   - Product:     ViewProduct-Start?SKU=<sku>                       (JSON-LD: price)
   - Store stock: ViewCheckoutShipping-GetAvailableStoresAjax?...&SKU=<sku>&State=<region>
                  one call per region; "In Stock" / "Not In Stock" per store.
   Config "fetch" sets the route order, "regions" limits the regions checked (default: all 13),
   and "priority_regions" is what's kept once the unblocker budget runs low (default: Auckland).
Stores have no ids on the site, only names; the store id is the slugified name.
Farmers' add-to-cart is a signed form post, so alerts link to the product page.
"""

from __future__ import annotations

import html
import json
import re
import logging
import uuid
from datetime import time
from importlib import resources
from urllib.parse import quote, urlparse

from tcgpings.models import Level, Product, Stock, Store, slugify, to_cents
from tcgpings.net.http import FetchError
from tcgpings.retailers.base import RetailerAdapter, register

log = logging.getLogger(__name__)

BASE = "https://www.farmers.co.nz"
ISH = f"{BASE}/INTERSHOP/web/WFS/Farmers-Shop-Site/en_NZ/-/NZD"
XHR = {"X-Requested-With": "XMLHttpRequest", "Accept": "text/html, */*; q=0.01"}

CONSTRUCTOR = "https://ac.cnstrc.com"
CONSTRUCTOR_KEY = "key_wafe8wrKCXfPyWKw"  # public client key embedded in farmers.co.nz pages
TRADING_CARDS_GROUP = "51-070502"         # Toys > Games, Cards & Puzzles > Trading Cards
FETCH_ORDER = ["browser", "scrapfly", "zyte"]
PRIORITY_REGIONS = ["AUK"]

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


def parse_constructor(data: dict, retailer_id: str = "farmers") -> list[Product]:
    products = []
    for item in (data.get("response") or {}).get("results") or []:
        d = item.get("data") or {}
        sku = str(d.get("id") or (d.get("sku") or [None])[0] or "")
        if not sku:
            continue
        status = str(d.get("stockstatus") or d.get("item-stockstatus") or "").lower()
        level = Level.IN if status == "in stock" else Level.OUT if "out of stock" in status else Level.UNKNOWN
        url = d.get("url") or ""
        image = d.get("image_url")
        products.append(Product(
            retailer_id=retailer_id,
            sku=sku,
            title=html.unescape(item.get("value") or ""),
            url=url if url.startswith("http") else f"{BASE}/{url.lstrip('/')}",
            image=image.replace(":443/", "/") if image else None,
            online=Stock(level),
        ))
    return products


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
    # Store stock refreshes once a day (~8am), so each product is checked once a day after that.
    store_stock_daily_at = time(8, 30)
    default_sku_interval = 15 * 60
    default_search_interval = 30 * 60
    supports_discovery = True
    default_discover_interval = 120
    default_retailers = [("farmers", "Farmers", {"fetch": FETCH_ORDER}, 0x5B2C83)]
    default_requests_per_minute = 10  # be gentle: Akamai scores request bursts

    def __init__(self, retailer, http) -> None:
        super().__init__(retailer, http)
        self._stores = load_stores()
        self._region_of = {s["store_id"]: s["region_code"] for s in self._stores}
        self.fetch_order = list(self.config.get("fetch") or FETCH_ORDER)
        self.regions = self.config.get("regions")  # None = all
        self.priority_regions = list(self.config.get("priority_regions") or PRIORITY_REGIONS)
        self._cio = {"key": self.config.get("constructor_key", CONSTRUCTOR_KEY), "c": "ciojs-client-2.0",
                     "i": str(uuid.uuid4()), "s": "1"}

    @property
    def _chain(self):
        return getattr(self.http, "chain", None)

    @property
    def store_stock_enabled(self) -> bool:
        return self._chain is not None and bool(self._chain.available(self.fetch_order))

    async def _constructor(self, path: str, **params: str) -> list[Product]:
        data = await self.http.get_json(self.policy, f"{CONSTRUCTOR}{path}", params={**self._cio, **params})
        return parse_constructor(data, self.retailer_id)

    async def discover(self) -> list[Product]:
        return await self._constructor(
            f"/browse/group_id/{TRADING_CARDS_GROUP}",
            sort_by="arrivaldate", sort_order="descending", num_results_per_page="200",
        )

    async def _get(self, url: str) -> str:
        if self._chain is None:
            raise FetchError("farmers needs the fetch chain (browser or unblocker) but this node has none")
        return await self._chain.fetch_text(self.policy, BASE + "/", url, XHR, self.fetch_order)

    async def search(self, query: str) -> list[Product]:
        return await self._constructor(f"/search/{quote(query)}", num_results_per_page="100")

    async def fetch_products(self, skus: list[str]) -> list[Product]:
        products = []
        for sku in skus:  # Constructor finds a product by its SKU
            products += [p for p in await self._constructor(f"/search/{quote(sku)}", num_results_per_page="5")
                         if p.sku == sku]
        return products

    async def refresh_details(self, product: Product) -> None:
        """Price from the product page (Constructor has none); skipped quietly if it can't be fetched."""
        try:
            page = await self._get(f"{ISH}/ViewProduct-Start?SKU={quote(product.sku)}")
        except FetchError as exc:
            log.info("farmers: no price for %s: %s", product.sku, exc)
            return
        details = parse_product(page, product.sku, self.retailer_id)
        if details:
            product.price_cents = details.price_cents
            product.image = product.image or details.image

    async def _regions_to_check(self) -> set[str] | None:
        """None = no limit. Once the unblocker budget runs low, only the priority regions."""
        regions = set(self.regions) if self.regions else None
        if self._chain is not None and await self._chain.budget_low():
            regions = (regions or set(self._region_of.values())) & set(self.priority_regions)
        return regions

    async def list_stores(self) -> list[Store]:
        return [Store(self.retailer_id, s["store_id"], s["name"], s["region"]) for s in self._stores]

    async def store_stock(self, sku: str, store_ids: list[str]) -> dict[str, Stock]:
        wanted = set(store_ids)
        regions = {self._region_of[s] for s in wanted if s in self._region_of}
        if (allowed := await self._regions_to_check()) is not None:
            regions &= allowed
        stock: dict[str, Stock] = {}
        for region in sorted(regions):
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
