"""The Warehouse (www.thewarehouse.co.nz): Salesforce Commerce Cloud behind Cloudflare. See docs/RETAILERS.md.

New listings, online stock and price come from the "Trading Cards & Accessories" category
sorted newest first (`/search?cgid=...&srule=newest`, 32 tiles a page). Each tile carries
`data-gtm-product` JSON (name, id, price, marketplace flag) and
`data-stock-status` (IN_STOCK, FIND_IN_STORE = in stores but not online, ...). "Newest" isn't strictly
newest (hot products were on page 2), and products don't reach every listing together, so discovery
also reads a search, and logs which listing shows each product first.

In-store stock is nationwide only: a tile's FIND_IN_STORE means some store has it, which the bot tracks
as one "store". A product that was in stores and then leaves the listings counts as out, so its return
can alert.

Not covered:
Per-store stock (2026-11-03, validated live in a clean genuine Chrome): hot Pokemon pages sit behind
a Cloudflare *managed* challenge that auto-solves in a real browser (no checkbox). Store availability
is two calls, each with a short-lived per-endpoint verify token:
  1. Load the product page in the browser; its gep-container-store-availability element carries the
     widget URL (/products/stores?pid=...&verify=T1).
  2. Fire that URL **once** (repeats 403) -> a modal listing all 15 regions, each with its own
     per-region token on /products/stores/region?productId=...&region=...&verify=T2.
  3. Fire the per-region URLs (~47 KB of store-availability__IN_STOCK / __NOT_AVAILABLE panels each).
     Store id is the c-full-store-details-<id> number, matching the bundled Stores-FindStores list
     (tcgpings/retailers/data/warehouse_stores.json). store_stock runs this via the browser backend
     and is gated on it being available.
  - Add-to-cart links: adding to cart requires a Turnstile check, so alerts link the product page.
Hot products can be challenge-protected even on their product page, so discovery (category
tiles) is the main source; single-product watches use the product page's JSON-LD.
"""

from __future__ import annotations

import html
import json
import logging
import re
from importlib import resources
from urllib.parse import quote

from tcgpings.models import Level, Product, Stock, Store, to_cents
from tcgpings.net.http import FetchError
from tcgpings.retailers.base import RetailerAdapter, register

log = logging.getLogger(__name__)

BASE = "https://www.thewarehouse.co.nz"
TRADING_CARDS = "toysbaby-toys-collectibletoys-tradingcardsaccs"
PAGE_SIZE = 32
DISCOVERY_SEARCHES = ("pokemon tcg",)
IN_STORES_ONLY = "In stores, not online"
IN_STORES = "in-stores"
IN_STORES_NAME = "Stores nationwide"
GONE_AFTER_SCANS = 3  # listings can flicker, so a product must be missing this many scans in a row
# Match the site's own store-availability XHR when we re-fire its widget / region URLs.
WIDGET_HEADERS = {"accept": "application/json", "x-requested-with": "fetch"}
# A clean Chrome auto-solves the managed challenge; wait until the product DOM is present.
PAGE_RESOLVED_JS = ("document.querySelectorAll('gep-container-store-availability').length > 0"
                    " && !/Just a moment/i.test(document.title)")

STOCK_STATUS = {
    "IN_STOCK": Level.IN,
    "LOW_STOCK": Level.LOW,
    "PREORDER": Level.IN,
    "PRE_ORDER": Level.IN,
    "BACKORDER": Level.IN,
    "FIND_IN_STORE": Level.OUT,  # stores may have it, but it can't be bought online
    "OUT_OF_STOCK": Level.OUT,
    "NOT_AVAILABLE": Level.OUT,
}
AVAILABILITY = {"InStock": Level.IN, "LimitedAvailability": Level.LOW, "PreOrder": Level.IN,
                "BackOrder": Level.IN, "OutOfStock": Level.OUT, "SoldOut": Level.OUT,
                "InStoreOnly": Level.OUT, "Discontinued": Level.OUT}

_TILE = re.compile(r'<div class="product-tile"')
_ATTR = lambda name: re.compile(name + r'="([^"]*)"')  # noqa: E731
_PID, _GTM, _STATUS, _ORDERABLE = (_ATTR(n) for n in ("data-pid", "data-gtm-product", "data-stock-status",
                                                       "data-orderable"))
_HREF = re.compile(r'href="(/p/[^"]+\.html)"')
_IMG = re.compile(r'<img[^>]*class="tile-image[^"]*"[^>]*src="([^"]+)"', re.S)
_LD = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
_CANONICAL = re.compile(r'<link rel="canonical" href="([^"]+)"')
_SKU_IN_URL = re.compile(r"/([A-Z]{1,2}\d{5,10})\.html")


def _in_store_stock(status: str | None) -> dict[str, Stock] | None:
    if status == "FIND_IN_STORE":
        return {IN_STORES: Stock(Level.IN)}
    if status in ("OUT_OF_STOCK", "NOT_AVAILABLE"):
        return {IN_STORES: Stock(Level.OUT)}
    return None  # sold online, so the listing says nothing about stores


def _tile_level(status: str | None, orderable: str | None) -> Level:
    if status in STOCK_STATUS:
        return STOCK_STATUS[status]
    if orderable is not None:
        return Level.IN if orderable == "true" else Level.OUT
    return Level.UNKNOWN


def parse_tiles(page: str, retailer_id: str = "warehouse", marketplace: bool = False) -> list[Product]:
    """Search/category result page -> products. Third-party marketplace listings are skipped unless asked for."""
    products = []
    starts = [m.start() for m in _TILE.finditer(page)] + [len(page)]
    for start, end in zip(starts, starts[1:]):
        tile = page[start:end]
        pid, gtm = _PID.search(tile), _GTM.search(tile)
        if not pid or not gtm:
            continue
        try:
            data = json.loads(html.unescape(gtm.group(1)))
        except ValueError:
            continue
        if data.get("marketplaceProduct") and not marketplace:
            continue
        href, img = _HREF.search(tile), _IMG.search(tile)
        status, orderable = _STATUS.search(tile), _ORDERABLE.search(tile)
        stock_status = status and status.group(1)
        products.append(Product(
            retailer_id=retailer_id,
            sku=pid.group(1),
            title=html.unescape(data.get("name") or "").strip(),
            url=BASE + html.unescape(href.group(1)) if href else f"{BASE}/p/x/{pid.group(1)}.html",
            image=html.unescape(img.group(1)) if img else None,
            price_cents=to_cents(data.get("price")),
            online=Stock(_tile_level(stock_status, orderable and orderable.group(1))),
            stores=_in_store_stock(stock_status),
            note=IN_STORES_ONLY if stock_status == "FIND_IN_STORE" else None,
        ))
    return products


def parse_product(page: str, sku: str, retailer_id: str = "warehouse") -> Product | None:
    """Product page JSON-LD -> product."""
    for block in _LD.findall(page):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        if not isinstance(data, dict) or data.get("@type") != "Product":
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
            title=html.unescape(data.get("name", "")).strip(),
            url=canonical.group(1) if canonical else (offer.get("url") or f"{BASE}/p/x/{sku}.html"),
            image=image,
            price_cents=to_cents(offer.get("price")),
            online=Stock(AVAILABILITY.get(availability, Level.UNKNOWN)),
        )
    return None


def load_stores() -> list[dict]:
    data = resources.files("tcgpings.retailers.data").joinpath("warehouse_stores.json").read_text(encoding="utf-8")
    return json.loads(data)["stores"]


_WIDGET_ELEM = re.compile(r'<gep-container-store-availability[^>]*?pid="([^"]+)"[^>]*?url="([^"]+)"', re.S)
_REGION_OPTION = re.compile(r'value="([A-Z]+-[A-Z]+)"\s+data-href="([^"]+)"')
_STORE_PANEL = re.compile(r'<div class="store panel">(.*?)(?=<div class="store panel"|$)', re.S)
_STORE_DETAIL_ID = re.compile(r'id="c-full-store-details-(\d+)"')
_STORE_STATUS = re.compile(r'store-availability__([A-Z_]+)')


def widget_store_url(page: str, sku: str) -> str | None:
    """The store-availability widget URL (with its verify token) for a product's own element."""
    urls = [html.unescape(url) for pid, url in _WIDGET_ELEM.findall(page) if pid == sku]
    return next((u for u in urls if "edit=" not in u), urls[0] if urls else None)


def parse_store_regions(widget) -> dict[str, str]:
    """Step-1 widget response -> {region_code: region_url}; 15 regions, each with its own verify token."""
    if not isinstance(widget, dict):
        try:
            widget = json.loads(widget)
        except ValueError:
            return {}
    if not isinstance(widget, dict):
        return {}
    tpl = widget.get("modalTemplate") or ""
    return {code: html.unescape(href) for code, href in _REGION_OPTION.findall(tpl)}


def parse_store_levels(region) -> dict[str, Stock]:
    """Step-2 region response -> {store_id: Stock}; store_id is the c-full-store-details number."""
    if not isinstance(region, dict):
        try:
            region = json.loads(region)
        except ValueError:
            return {}
    if not isinstance(region, dict):
        return {}
    out: dict[str, Stock] = {}
    for block in _STORE_PANEL.findall(region.get("stores") or ""):
        detail = _STORE_DETAIL_ID.search(block)
        status = _STORE_STATUS.search(block)
        if detail and status:
            out[detail.group(1)] = Stock(STOCK_STATUS.get(status.group(1), Level.OUT))
    return out


@register
class WarehouseAdapter(RetailerAdapter):
    adapter_name = "warehouse"
    supports_discovery = True
    stock_in_listings = True
    supports_store_stock = True
    store_stock_discovers_stores = True
    store_stock_interval = 5 * 60
    default_discover_interval = 120
    default_sku_interval = 5 * 60
    default_search_interval = 10 * 60
    default_requests_per_minute = 12
    default_retailers = [("warehouse", "The Warehouse", {"categories": [TRADING_CARDS], "discover_pages": 2}, 0xE2231A)]

    def __init__(self, retailer, http) -> None:
        super().__init__(retailer, http)
        self._seen: dict[str, set[str]] = {}
        self._in_stores: dict[str, Product] = {}
        self._missing: dict[str, int] = {}
        self._stores = load_stores()
        self._region_of = {s["store_id"]: s["region_code"] for s in self._stores}

    def _listing_url(self, params: str, start: int = 0) -> str:
        return f"{BASE}/search?{params}&srule=newest&start={start}&sz={PAGE_SIZE}"

    async def _listing(self, params: str, pages: int) -> list[Product]:
        found: dict[str, Product] = {}
        for page in range(pages):
            resp = await self.http.get(self.policy, self._listing_url(params, page * PAGE_SIZE))
            tiles = parse_tiles(resp.text, self.retailer_id, bool(self.config.get("marketplace")))
            for p in tiles:
                found.setdefault(p.sku, p)
            if resp.text.count('<div class="product-tile"') < PAGE_SIZE:
                break
        return list(found.values())

    async def discover(self) -> list[Product]:
        pages = int(self.config.get("discover_pages", 2))
        found: dict[str, Product] = {}
        for cgid in self.config.get("categories") or [TRADING_CARDS]:
            self._collect(found, f"category {cgid}", await self._listing(f"cgid={quote(cgid)}", pages))
        for query in DISCOVERY_SEARCHES:
            try:
                self._collect(found, f"search {query}", await self._listing(f"q={quote(query)}", 1))
            except FetchError as exc:  # the categories already gave a good result
                log.info("warehouse: discovery search %r failed: %s", query, exc)
        return list(found.values()) + self._left_the_listings(found)

    def _left_the_listings(self, found: dict[str, Product]) -> list[Product]:
        """Products that were in stores and have now been missing from the listings for several scans."""
        gone = []
        for sku in list(self._in_stores):
            if sku in found:
                self._missing.pop(sku, None)
                continue
            self._missing[sku] = self._missing.get(sku, 0) + 1
            if self._missing[sku] >= GONE_AFTER_SCANS:
                product = self._in_stores.pop(sku)
                del self._missing[sku]
                product.stores = {IN_STORES: Stock(Level.OUT)}
                product.note = None
                gone.append(product)
        self._in_stores.update({
            sku: p for sku, p in found.items() if p.stores and p.stores[IN_STORES].level is Level.IN
        })
        return gone

    async def list_stores(self) -> list[Store]:
        stores = [Store(self.retailer_id, s["store_id"], s["name"], s["region_code"]) for s in self._stores]
        stores.append(Store(self.retailer_id, IN_STORES, IN_STORES_NAME))
        return stores

    def store_label(self, store_id: str) -> str:
        name = next((s["name"] for s in self._stores if s["store_id"] == store_id), None)
        return name or (IN_STORES_NAME if store_id == IN_STORES else f"Store {store_id}")

    def _collect(self, found: dict[str, Product], source: str, products: list[Product]) -> None:
        seen = self._seen.get(source)
        for p in products:
            found.setdefault(p.sku, p)
            if seen is not None and p.sku not in seen:
                log.info("warehouse: %s first shows %s (%s)", source, p.sku, p.title)
        self._seen[source] = (seen or set()) | {p.sku for p in products}

    async def search(self, query: str) -> list[Product]:
        return await self._listing(f"q={quote(query)}", 1)

    async def fetch_products(self, skus: list[str]) -> list[Product]:
        products = []
        for sku in skus:
            resp = await self.http.get(self.policy, f"{BASE}/p/x/{quote(sku)}.html")
            product = parse_product(resp.text, sku, self.retailer_id)
            if product:
                products.append(product)
        return products

    @property
    def store_stock_enabled(self) -> bool:
        return getattr(self.http, "browser", None) is not None

    async def store_stock(self, sku: str, store_ids: list[str]) -> dict[str, Stock]:
        """Per-store stock: load the product page in the browser (managed challenge auto-solves),
        fire its store-availability widget once, then the per-region URLs it returns."""
        browser = getattr(self.http, "browser", None)
        if browser is None:
            raise FetchError("warehouse per-store stock needs the browser backend")
        wanted = {s for s in store_ids if s != IN_STORES}
        regions = sorted({self._region_of[s] for s in wanted if s in self._region_of}) or sorted(
            {s["region_code"] for s in self._stores})
        if not regions:
            return {}
        page_url = f"{BASE}/p/x/{quote(sku)}.html"
        page = await browser.visit(self.policy, page_url, success_js=PAGE_RESOLVED_JS)
        widget_url = widget_store_url(page, sku)
        if not widget_url:
            raise FetchError(f"GET {page_url}: no store-availability widget for {sku}")
        widget_text = await browser.fetch_text(self.policy, BASE, widget_url, WIDGET_HEADERS)
        region_urls = parse_store_regions(widget_text)
        stock: dict[str, Stock] = {}
        for code in regions:
            url = region_urls.get(code)
            if not url:
                continue
            try:
                text = await browser.fetch_text(self.policy, BASE, url, WIDGET_HEADERS)
            except FetchError as exc:
                log.info("warehouse: region %s for %s failed: %s", code, sku, exc)
                continue
            stock.update(parse_store_levels(text))
        return {sid: stock[sid] for sid in wanted if sid in stock} if wanted else stock

    def parse_ref(self, ref: str) -> str:
        m = _SKU_IN_URL.search(ref)
        return m.group(1) if m else ref.strip()

    def matches_url(self, url: str) -> bool:
        return "thewarehouse.co.nz" in url
