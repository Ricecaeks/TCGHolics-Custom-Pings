"""Whitcoulls (www.whitcoulls.co.nz). See docs/RETAILERS.md.

Plain HTML, no bot protection (checked 2026-11-04). Search pages carry their results as JSON in
`window.category = {...{"items": [...], "pagination": {...}}}`, 24 to a page:
- item.stylecolour.stylecolourid: the product id (also the end of its URL, and `/x-<id>` redirects to it)
- item.stylecolour.urlkey: the URL slug; item.stylecolour.variants[0].unitprice: price (NZD)
- variants[0].status: "" (in stock online), "limitedstock" ("only 3 left"), "instore" (In Store Only),
  "outofstock"
Product pages have JSON-LD with offers.availability (InStock, LimitedAvailability, ...).

The card range is small (a few Yu-Gi-Oh!, Magic and Lorcana products; no Pokémon cards in November
2026), so discovery reads a few searches rather than a category. Searches can't be paged or sorted by
URL, but each card search fits on one page. "In Store Only" products are tracked as one
"Stores nationwide" store, like The Warehouse's.
"""

from __future__ import annotations

import html
import json
import logging
import re

from tcgpings.models import Level, Product, Stock, Store, to_cents
from tcgpings.net.http import FetchError
from tcgpings.retailers.base import RetailerAdapter, register

log = logging.getLogger(__name__)

BASE = "https://www.whitcoulls.co.nz"
# Not "pokemon": its results are books and toys, and a book set like "Paldea Trainers' Collection
# Gift Box" reads as sealed product. Pokémon cards would be titled "...Trading Card Game...".
DISCOVERY_SEARCHES = ("trading card", "booster", "tcg")
IN_STORES = "in-stores"
IN_STORES_NAME = "Stores nationwide"
IN_STORES_ONLY = "In stores, not online"

STATUS = {"": Level.IN, "limitedstock": Level.LOW, "instore": Level.OUT, "outofstock": Level.OUT}
AVAILABILITY = {"instock": Level.IN, "limitedavailability": Level.LOW, "preorder": Level.IN, "backorder": Level.IN,
                "outofstock": Level.OUT, "soldout": Level.OUT, "instoreonly": Level.OUT, "discontinued": Level.OUT}

_LD = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
_CANONICAL = re.compile(r'<link rel="canonical" href="([^"]+)"')
_ID_IN_URL = re.compile(r"-(\d{5,})/?$")


def parse_search(page: str, retailer_id: str = "whitcoulls") -> list[Product]:
    """Search page -> products, from its embedded `window.category` JSON."""
    start = page.find("window.category = {")
    if start < 0:
        return []
    try:
        data, _ = json.JSONDecoder().raw_decode(page, page.find("...", start) + 3)
    except ValueError:
        return []
    products = []
    for item in data.get("items") or []:
        style = item.get("stylecolour") or {}
        variant = (style.get("variants") or [{}])[0]
        sku = str(style.get("stylecolourid") or variant.get("barcode") or "")
        if not sku:
            continue
        status = variant.get("status") or ""
        image = (style.get("primaryimage") or {}).get("src")
        products.append(Product(
            retailer_id=retailer_id,
            sku=sku,
            title=html.unescape(item.get("description") or "").strip(),
            url=f"{BASE}/{style['urlkey']}" if style.get("urlkey") else f"{BASE}/x-{sku}",
            image=image,
            price_cents=to_cents(variant.get("unitprice")),
            online=Stock(STATUS.get(status, Level.UNKNOWN)),
            stores=_in_store_stock(status),
            note=IN_STORES_ONLY if status == "instore" else None,
        ))
    return products


def _in_store_stock(status: str) -> dict[str, Stock] | None:
    if status == "instore":
        return {IN_STORES: Stock(Level.IN)}
    if status == "outofstock":
        return {IN_STORES: Stock(Level.OUT)}
    return None  # sold online, so the listing says nothing about stores


def parse_product(page: str, sku: str, retailer_id: str = "whitcoulls") -> Product | None:
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
        return Product(
            retailer_id=retailer_id,
            sku=str(data.get("sku") or sku),
            title=html.unescape(data.get("name") or "").strip(),
            url=canonical.group(1) if canonical else f"{BASE}/x-{sku}",
            image=data.get("image") if isinstance(data.get("image"), str) else None,
            price_cents=to_cents(offers.get("price")),
            online=Stock(AVAILABILITY.get(availability, Level.UNKNOWN)),
        )
    return None


@register
class WhitcoullsAdapter(RetailerAdapter):
    adapter_name = "whitcoulls"
    supports_discovery = True
    stock_in_listings = True
    default_discover_interval = 5 * 60
    default_sku_interval = 5 * 60
    default_search_interval = 10 * 60
    default_requests_per_minute = 12
    default_retailers = [("whitcoulls", "Whitcoulls", {}, 0x00A0DF)]

    async def _search_page(self, query: str) -> list[Product]:
        resp = await self.http.get(self.policy, f"{BASE}/search", params={"q": query})
        return parse_search(resp.text, self.retailer_id)

    async def discover(self) -> list[Product]:
        found: dict[str, Product] = {}
        for query in self.config.get("discovery_searches") or DISCOVERY_SEARCHES:
            try:
                products = await self._search_page(query)
            except FetchError as exc:  # one failed search shouldn't lose the others
                log.warning("whitcoulls: search %r failed: %s", query, exc)
                continue
            for product in products:
                found.setdefault(product.sku, product)
        return list(found.values())

    async def search(self, query: str) -> list[Product]:
        return await self._search_page(query)

    async def fetch_products(self, skus: list[str]) -> list[Product]:
        products = []
        for sku in skus:
            try:
                resp = await self.http.get(self.policy, f"{BASE}/x-{sku}")
            except FetchError as exc:
                if exc.status == 404:
                    continue  # delisted; leave the last known state alone
                raise
            product = parse_product(resp.text, sku, self.retailer_id)
            if product:
                products.append(product)
        return products

    async def list_stores(self) -> list[Store]:
        return [Store(self.retailer_id, IN_STORES, IN_STORES_NAME)]

    def store_label(self, store_id: str) -> str:
        return IN_STORES_NAME if store_id == IN_STORES else f"Store {store_id}"

    def parse_ref(self, ref: str) -> str:
        ref = ref.strip()
        match = _ID_IN_URL.search(ref.split("?")[0])
        return match.group(1) if match and "/" in ref else ref

    def matches_url(self, url: str) -> bool:
        return "whitcoulls.co.nz" in url
