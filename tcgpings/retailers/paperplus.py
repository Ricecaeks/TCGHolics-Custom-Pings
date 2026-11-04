"""Paper Plus (www.paperplus.co.nz). See docs/RETAILERS.md.

Plain HTML, no bot protection (checked 2026-11-04). Listing pages are server-rendered `<article>`
tiles whose attributes carry the product: data-url (/shop/<category path>/<slug>), data-skucode
(barcode), and a hidden js-product-data span with data-name and data-price.
- Discovery: the Trading Cards category (12 products in November 2026, one page). Every product it
  listed was in stock, so a listing only shows what can be bought: a product missing from it for
  GONE_AFTER_SCANS scans in a row counts as sold out, so its return alerts.
- Product pages have JSON-LD with offers.availability ("Instock", ...).
- SKU = the path after /shop/, since search can't find a product by its barcode and the path is
  what opens its page.

Not covered: the product page's "Where in stock" button (per-store stock), not looked at yet.
"""

from __future__ import annotations

import html
import json
import logging
import re
from urllib.parse import urlparse

from tcgpings.models import Level, Product, Stock, to_cents
from tcgpings.net.http import FetchError
from tcgpings.retailers.base import RetailerAdapter, register

log = logging.getLogger(__name__)

BASE = "https://www.paperplus.co.nz"
TRADING_CARDS = "toys-games-puzzles/collectables-trading-cards/trading-cards"
GONE_AFTER_SCANS = 3  # a product must be missing this many scans in a row to count as sold out

AVAILABILITY = {"instock": Level.IN, "limitedavailability": Level.LOW, "preorder": Level.IN, "backorder": Level.IN,
                "outofstock": Level.OUT, "soldout": Level.OUT, "discontinued": Level.OUT}

_TILE = re.compile(r"<article .*?</article>", re.S)
_ATTR = lambda name: re.compile(r"\b" + name + r'="([^"]*)"')  # noqa: E731
_URL, _NAME, _PRICE = (_ATTR(n) for n in ("data-url", "data-name", "data-price"))
_IMAGE = re.compile(r"\bdata-src='([^']*)'")  # the lazy-loaded image, single-quoted
_LD = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
_CANONICAL = re.compile(r'<link rel="canonical" href="([^"]+)"')


def _sku(path: str) -> str:
    return path.split("?")[0].strip("/").removeprefix("shop/")


def parse_tiles(page: str, retailer_id: str = "paperplus") -> list[Product]:
    """Category or search page -> products. A listed product can be bought online."""
    products = []
    for tile in _TILE.findall(page):
        url, name = _URL.search(tile), _NAME.search(tile)
        if not url or not name or not url.group(1).startswith("/shop/"):
            continue
        price, image = _PRICE.search(tile), _IMAGE.search(tile)
        path = html.unescape(url.group(1))
        products.append(Product(
            retailer_id=retailer_id,
            sku=_sku(path),
            title=" ".join(html.unescape(name.group(1)).split()),
            url=BASE + path,
            image=html.unescape(image.group(1)).split("?")[0] if image else None,
            price_cents=to_cents(price.group(1)) if price else None,
            online=Stock(Level.IN),
        ))
    return products


def parse_product(page: str, sku: str, retailer_id: str = "paperplus") -> Product | None:
    """Product page JSON-LD -> product."""
    for block in _LD.findall(page):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        if data.get("@type") != "Product":
            continue
        offers = data.get("offers") or {}
        availability = str(offers.get("availability") or "").rsplit("/", 1)[-1].lower()
        canonical = _CANONICAL.search(page)
        url = canonical.group(1) if canonical else f"{BASE}/shop/{sku}"
        image = data.get("image")
        return Product(
            retailer_id=retailer_id,
            sku=_sku(urlparse(url).path) or sku,
            title=" ".join(html.unescape(data.get("name") or "").split()),
            url=url,
            image=image if isinstance(image, str) else None,
            price_cents=to_cents(offers.get("price")),
            online=Stock(AVAILABILITY.get(availability, Level.UNKNOWN)),
        )
    return None


@register
class PaperPlusAdapter(RetailerAdapter):
    adapter_name = "paperplus"
    supports_discovery = True
    default_discover_interval = 3 * 60
    default_sku_interval = 5 * 60
    default_search_interval = 10 * 60
    default_requests_per_minute = 12
    default_retailers = [("paperplus", "Paper Plus", {"categories": [TRADING_CARDS]}, 0xE30613)]

    def __init__(self, retailer, http) -> None:
        super().__init__(retailer, http)
        self._listed: dict[str, Product] = {}  # last seen listing of each product still counted as listed
        self._missing: dict[str, int] = {}

    async def discover(self) -> list[Product]:
        found: dict[str, Product] = {}
        for category in self.config.get("categories") or [TRADING_CARDS]:
            resp = await self.http.get(self.policy, f"{BASE}/shop/{category}")
            for product in parse_tiles(resp.text, self.retailer_id):
                found.setdefault(product.sku, product)
        if not found:  # a page that lists nothing is more likely broken than sold out
            log.warning("paperplus: the categories listed no products")
            return []
        return list(found.values()) + self._left_the_listings(found)

    def _left_the_listings(self, found: dict[str, Product]) -> list[Product]:
        """Products gone from the listings for GONE_AFTER_SCANS scans in a row, now counted as sold out."""
        gone = []
        for sku in list(self._listed):
            if sku in found:
                self._missing.pop(sku, None)
                continue
            self._missing[sku] = self._missing.get(sku, 0) + 1
            if self._missing[sku] >= GONE_AFTER_SCANS:
                product = self._listed.pop(sku)
                del self._missing[sku]
                product.online = Stock(Level.OUT)
                gone.append(product)
        self._listed.update(found)
        return gone

    async def search(self, query: str) -> list[Product]:
        resp = await self.http.get(self.policy, f"{BASE}/search", params={"q": query})
        return parse_tiles(resp.text, self.retailer_id)

    async def fetch_products(self, skus: list[str]) -> list[Product]:
        products = []
        for sku in skus:
            try:
                resp = await self.http.get(self.policy, f"{BASE}/shop/{sku}")
            except FetchError as exc:
                if exc.status == 404:
                    continue  # delisted; leave the last known state alone
                raise
            product = parse_product(resp.text, sku, self.retailer_id)
            if product:
                products.append(product)
        return products

    def parse_ref(self, ref: str) -> str:
        ref = ref.strip()
        return _sku(urlparse(ref).path) if "/shop/" in ref else ref

    def matches_url(self, url: str) -> bool:
        return "paperplus.co.nz" in url
