"""The Warehouse (www.thewarehouse.co.nz): Salesforce Commerce Cloud behind Cloudflare. See docs/RETAILERS.md.

New listings, online stock and price come from the "Trading Cards & Accessories" category
sorted newest first (`/search?cgid=...&srule=newest`, 32 tiles a page). Each tile carries
`data-gtm-product` JSON (name, id, price, marketplace flag) and
`data-stock-status` (IN_STOCK, FIND_IN_STORE = in stores but not online, ...).

Not covered:
  - Per-store stock: the store-availability call needs a signed per-product token, and hot
    Pokémon products sit behind a Cloudflare challenge. Left out deliberately.
  - Add-to-cart links: adding to cart requires a Turnstile check, so alerts link the product page.
Hot products can be challenge-protected even on their product page, so discovery (category
tiles) is the main source; single-product watches use the product page's JSON-LD.
"""

from __future__ import annotations

import html
import json
import re
from urllib.parse import quote

from tcgpings.models import Level, Product, Stock, to_cents
from tcgpings.retailers.base import RetailerAdapter, register

BASE = "https://www.thewarehouse.co.nz"
TRADING_CARDS = "toysbaby-toys-collectibletoys-tradingcardsaccs"
PAGE_SIZE = 32

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
        products.append(Product(
            retailer_id=retailer_id,
            sku=pid.group(1),
            title=html.unescape(data.get("name") or "").strip(),
            url=BASE + html.unescape(href.group(1)) if href else f"{BASE}/p/x/{pid.group(1)}.html",
            image=html.unescape(img.group(1)) if img else None,
            price_cents=to_cents(data.get("price")),
            online=Stock(_tile_level(status and status.group(1), orderable and orderable.group(1))),
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


@register
class WarehouseAdapter(RetailerAdapter):
    adapter_name = "warehouse"
    supports_discovery = True
    default_discover_interval = 180
    default_sku_interval = 5 * 60
    default_search_interval = 10 * 60
    default_requests_per_minute = 12
    default_retailers = [("warehouse", "The Warehouse", {"categories": [TRADING_CARDS], "discover_pages": 2}, 0xE2231A)]

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
            for p in await self._listing(f"cgid={quote(cgid)}", pages):
                found.setdefault(p.sku, p)
        return list(found.values())

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

    def parse_ref(self, ref: str) -> str:
        m = _SKU_IN_URL.search(ref)
        return m.group(1) if m else ref.strip()

    def matches_url(self, url: str) -> bool:
        return "thewarehouse.co.nz" in url
