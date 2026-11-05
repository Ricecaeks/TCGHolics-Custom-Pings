"""Mighty Ape (www.mightyape.co.nz). See docs/RETAILERS.md.

Every page with product data (shop, search, API, even the product sitemaps) answers 403 behind
DataDome, so pages come through the fetch chain's paid unblocker (config "fetch", default ScrapFly),
approved by the owner on 2026-11-05. Each page costs about 25-30 ScrapFly credits and 25-50 seconds.
- Category pages carry a JSON-LD ItemList: name, SKU (MPE-…), image, AggregateOffer prices and
  availability (InStock, PreOrder, OutOfStock). Sold-out products stay listed, so restocks show.
  lowPrice is the Primate members' price; highPrice is the regular one.
- Pages can't be sorted by newest (robots.txt disallows order_by), so discovery reads each category's
  first page (36 products, "featured" order, where new sets and preorders sit near the top).
- Discovery is the only regular cost: the Pokémon category every 30 minutes and the all-cards category
  hourly (config "categories": [{"path", "every"}]), about 2,000 credits a day.
- No keyword searches (supports_search = False): search is disallowed by robots.txt and each one would
  cost credits. A product URL can still be watched; its page has a JSON-LD Product.
- SKU = the product's URL slug (`kogan-international-pokemon-tcg-pitch-black-booster-pack-41201033`),
  which is what opens its page.
"""

from __future__ import annotations

import html
import json
import logging
import re
import time
from urllib.parse import urlparse

from tcgpings.models import Level, Product, Stock, to_cents
from tcgpings.net.http import FetchError
from tcgpings.retailers.base import RetailerAdapter, register

log = logging.getLogger(__name__)

BASE = "https://www.mightyape.co.nz"
CATEGORY = BASE + "/mn/shop/category/"
FETCH_ORDER = ["scrapfly"]
CATEGORIES = [
    {"path": "hobbies/trading-cards/pokemon", "every": 30 * 60},
    {"path": "hobbies/trading-cards/", "every": 2 * 60 * 60},  # overlaps the Pokémon page; every read is paid
]
SLACK = 120  # a category due within this many seconds is read now rather than skipped to the next run

AVAILABILITY = {"instock": Level.IN, "limitedavailability": Level.LOW, "preorder": Level.IN,
                "backorder": Level.IN, "outofstock": Level.OUT, "soldout": Level.OUT, "discontinued": Level.OUT}

_LD = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
_SLUG = re.compile(r"/mn/buy/([^/?#]+)")


def _blocks(page: str) -> list[dict]:
    out = []
    for raw in _LD.findall(page):
        try:
            data = json.loads(raw)
        except ValueError:
            continue
        out += data if isinstance(data, list) else [data]
    return out


def _slug(url: str) -> str | None:
    m = _SLUG.search(urlparse(url).path)
    return m.group(1) if m else None


def _product(item: dict, retailer_id: str, sku: str | None = None) -> Product | None:
    url = item.get("url") or (item.get("offers") or {}).get("url") or ""
    sku = sku or _slug(url)
    if not sku or not item.get("name"):
        return None
    offers = item.get("offers") or {}
    availability = str(offers.get("availability") or "").rsplit("/", 1)[-1].lower()
    level = AVAILABILITY.get(availability, Level.UNKNOWN)
    price = offers.get("highPrice") or offers.get("price") or offers.get("lowPrice")  # not the members' price
    image = item.get("image")
    if isinstance(image, list):
        image = image[0] if image else None
    if isinstance(image, dict):
        image = image.get("url")
    return Product(
        retailer_id=retailer_id,
        sku=sku,
        title=" ".join(html.unescape(item["name"]).split()),
        url=f"{BASE}/mn/buy/{sku}/",
        image=image if isinstance(image, str) else None,
        price_cents=to_cents(price),
        online=Stock(level),
        note="Pre-order" if availability == "preorder" else None,
    )


def parse_category(page: str, retailer_id: str = "mightyape") -> list[Product]:
    """Category page -> its listed products, from the JSON-LD ItemList."""
    products = []
    for block in _blocks(page):
        if block.get("@type") != "ItemList":
            continue
        for element in block.get("itemListElement") or []:
            product = _product(element.get("item") or {}, retailer_id)
            if product:
                products.append(product)
    return products


def parse_product(page: str, sku: str, retailer_id: str = "mightyape") -> Product | None:
    for block in _blocks(page):
        if block.get("@type") == "Product":
            return _product(block, retailer_id, sku)
    return None


@register
class MightyApeAdapter(RetailerAdapter):
    adapter_name = "mightyape"
    supports_discovery = True
    supports_search = False
    default_discover_interval = 30 * 60
    default_sku_interval = 60 * 60
    default_requests_per_minute = 4
    default_retailers = [("mightyape", "Mighty Ape", {"fetch": FETCH_ORDER, "categories": CATEGORIES}, 0xF7941D)]

    def __init__(self, retailer, http) -> None:
        super().__init__(retailer, http)
        self.fetch_order = list(self.config.get("fetch") or FETCH_ORDER)
        self.categories = list(self.config.get("categories") or CATEGORIES)
        self._read_at: dict[str, float] = {}  # category path -> when it was last read

    @property
    def _chain(self):
        return getattr(self.http, "chain", None)

    async def _get(self, url: str) -> str:
        if self._chain is None:
            raise FetchError("mightyape needs the fetch chain (an unblocker) but this node has none")
        return await self._chain.fetch_text(self.policy, BASE + "/", url, None, self.fetch_order)

    def _due(self, now: float) -> list[dict]:
        return [c for c in self.categories
                if now - self._read_at.get(c["path"], 0) >= int(c.get("every") or self.default_discover_interval) - SLACK]

    async def discover(self) -> list[Product]:
        found: dict[str, Product] = {}
        now = time.time()
        for category in self._due(now):
            page = await self._get(CATEGORY + category["path"])
            self._read_at[category["path"]] = now
            for product in parse_category(page, self.retailer_id):
                found.setdefault(product.sku, product)
        return list(found.values())

    async def search(self, query: str) -> list[Product]:
        return []  # see supports_search

    async def fetch_products(self, skus: list[str]) -> list[Product]:
        products = []
        for sku in skus:
            try:
                page = await self._get(f"{BASE}/mn/buy/{sku}/")
            except FetchError as exc:
                if exc.status == 404:
                    continue
                raise
            product = parse_product(page, sku, self.retailer_id)
            if product:
                products.append(product)
        return products

    def parse_ref(self, ref: str) -> str:
        return _slug(ref.strip()) or ref.strip().strip("/")

    def matches_url(self, url: str) -> bool:
        return "mightyape.co.nz" in url
