"""Pokémon Center (www.pokemoncenter.com): the NZ, AU and UK stores, one retailer row each. See docs/RETAILERS.md.

Every page sits behind DataDome and the site picks the store from the visitor's country (a US address gets
the US store whatever the URL says), so pages come through Zyte with a per-request geolocation (config
"geo"). ScrapFly only offers US exits for this site. Approved by the owner on 2026-11-05.
- Category pages are Next.js: __NEXT_DATA__ carries the search result (`_raw.response.docs`: pid, title,
  price, launch_date, availability_status IN_STOCK / OUT_OF_STOCK) and a facet with the whole category's
  in-stock count. The product links (/{locale}/product/{pid}/{slug}) are in the HTML.
- "tcg-cards" is the sealed range (booster packs, boxes, tins, ETBs, decks), 32 products a page, sortable by
  newest. Discovery reads page 1 every `every` seconds: new listings and preorders show there. It reads every
  page when the in-stock count changes (something restocked or sold out) and every `sweep_every` seconds.
- Queue: during big drops the store puts shoppers in a waiting room. A waiting-room page in place of the
  category means a queue is on; it's kept as a status row (kind "queue") that alerts when it turns on. The
  bot doesn't try to get through the queue: it reads the store again on its next run.
- AU and UK rows are `overseas`: their alerts only reach channels that name them (#pokemon-center-au/-uk),
  not the NZ game channels or member pings.
- SKU = the product code (pid, e.g. 10-10065-109).
"""

from __future__ import annotations

import html
import json
import logging
import math
import re
import time
from urllib.parse import urlparse

from tcgpings.models import Level, Product, Stock, to_cents
from tcgpings.net.http import FetchError, Queued
from tcgpings.retailers.base import RetailerAdapter, register

log = logging.getLogger(__name__)

BASE = "https://www.pokemoncenter.com"
FETCH_ORDER = ["zyte"]
CATEGORY = "tcg-cards"
PAGE_SIZE = 32
MAX_PAGES = 30
SLACK = 60  # a store due within this many seconds is read now rather than skipped to the next run
QUEUE_SKU = "queue"

AVAILABILITY = {"IN_STOCK": Level.IN, "OUT_OF_STOCK": Level.OUT, "PRE_ORDER": Level.IN, "PREORDER": Level.IN,
                "BACK_ORDER": Level.IN, "BACKORDER": Level.IN, "LOW_STOCK": Level.LOW}
SCHEMA_AVAILABILITY = {"instock": Level.IN, "outofstock": Level.OUT, "preorder": Level.IN, "backorder": Level.IN,
                       "limitedavailability": Level.LOW, "soldout": Level.OUT, "discontinued": Level.OUT}


def _store(locale: str, geo: str, currency: str, every: int, overseas: bool) -> dict:
    return {"locale": locale, "geo": geo, "currency": currency, "every": every, "sweep_every": 6 * 3600,
            "overseas": overseas, "fetch": FETCH_ORDER}


STORES = [
    ("pokemoncenter-nz", "Pokémon Center NZ", _store("en-nz", "NZ", "NZD", 180, False)),
    ("pokemoncenter-au", "Pokémon Center AU", _store("en-au", "AU", "AUD", 600, True)),
    ("pokemoncenter-uk", "Pokémon Center UK", _store("en-gb", "GB", "GBP", 600, True)),
]

_NEXT = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)
_LD = re.compile(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', re.S)
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)


def _results(page: str) -> dict | None:
    m = _NEXT.search(page)
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
        return data["props"]["initialState"]["search"]["results"]
    except (ValueError, KeyError, TypeError):
        return None


def in_stock_count(results: dict) -> int | None:
    try:
        facets = results["_raw"]["facet_counts"]["facet_fields"]["availability_status"]
    except (KeyError, TypeError):
        return None
    return sum(f.get("count") or 0 for f in facets if f.get("name") != "OUT_OF_STOCK")


def parse_category(page: str, retailer_id: str, locale: str, currency: str = "NZD",
                   ) -> tuple[list[Product], int, int | None]:
    """Category page -> (products, total in the category, how many are in stock across the category)."""
    results = _results(page)
    if results is None:
        raise ValueError("no search results on the page")
    links = dict(re.findall(rf'href="/{locale}/product/([^/"?]+)/([^"?#]+)"', page))
    docs = (results.get("_raw") or {}).get("response", {}).get("docs") or []
    products = []
    for doc in docs:
        pid, title = doc.get("pid"), doc.get("title")
        if not pid or not title:
            continue
        status = str(doc.get("availability_status") or "").upper()
        level = AVAILABILITY.get(status, Level.UNKNOWN)
        image = doc.get("primary_image_full_size")
        slug = links.get(pid)
        products.append(Product(
            retailer_id=retailer_id,
            sku=pid,
            title=" ".join(html.unescape(title).split()),
            url=f"{BASE}/{locale}/product/{pid}/{slug}" if slug else f"{BASE}/{locale}/product/{pid}",
            image=f"{BASE}/images/DAMRoot/{image}" if image else doc.get("thumb_image"),
            price_cents=to_cents(doc.get("sale_price") or doc.get("price")),
            online=Stock(level),
            note=_note(status, currency),
        ))
    total = int(results.get("total") or len(products))
    return products, total, in_stock_count(results)


def _note(status: str, currency: str) -> str | None:
    parts = []
    if "PRE" in status:
        parts.append("Pre-order")
    if currency != "NZD":
        parts.append(f"Price in {currency}")
    return " · ".join(parts) or None


def parse_product(page: str, sku: str, retailer_id: str, locale: str, currency: str = "NZD") -> Product | None:
    for raw in _LD.findall(page):
        try:
            block = json.loads(raw)
        except ValueError:
            continue
        if block.get("@type") != "Product":
            continue
        offers = block.get("offers") or {}
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        availability = str(offers.get("availability") or "").rsplit("/", 1)[-1].lower()
        image = block.get("image")
        if isinstance(image, list):
            image = image[0] if image else None
        url = offers.get("url") or f"{BASE}/{locale}/product/{sku}"
        return Product(
            retailer_id=retailer_id,
            sku=sku,
            title=" ".join(html.unescape(block.get("name") or sku).split()),
            url=url,
            image=image if isinstance(image, str) else None,
            price_cents=to_cents(offers.get("price")),
            online=Stock(SCHEMA_AVAILABILITY.get(availability, Level.UNKNOWN)),
            note=_note("PRE" if availability == "preorder" else "", currency),
        )
    return None


def describe_page(page: str) -> str:
    """A short description of a page we didn't expect, for the log (to tune queue detection)."""
    title = _TITLE.search(page)
    text = re.sub(r"<script.*?</script>|<style.*?</style>|<[^>]+>", " ", page, flags=re.S)
    return f"{len(page)} bytes, title {html.unescape(title.group(1).strip())[:80] if title else '-'!r}: " \
           f"{' '.join(html.unescape(text).split())[:300]!r}"


@register
class PokemonCenterAdapter(RetailerAdapter):
    adapter_name = "pokemoncenter"
    supports_discovery = True
    supports_search = False  # every request is paid; discovery covers the whole sealed range
    default_discover_interval = 180
    default_sku_interval = 3600
    default_requests_per_minute = 20
    default_retailers = [(rid, name, config, 0xE3350D) for rid, name, config in STORES]

    def __init__(self, retailer, http) -> None:
        super().__init__(retailer, http)
        c = self.config
        self.locale = c.get("locale") or "en-nz"
        self.geo = c.get("geo") or "NZ"
        self.currency = c.get("currency") or "NZD"
        self.every = int(c.get("every") or self.default_discover_interval)
        self.sweep_every = int(c.get("sweep_every") or 6 * 3600)
        self.category = c.get("category") or CATEGORY
        self.fetch_order = list(c.get("fetch") or FETCH_ORDER)
        self._read_at = 0.0
        self._swept_at = 0.0
        self._in_stock: int | None = None

    @property
    def _chain(self):
        return getattr(self.http, "chain", None)

    def category_url(self, page: int = 1) -> str:
        url = f"{BASE}/{self.locale}/category/{self.category}?sort=launch_date%2Bdesc"
        return url if page == 1 else f"{url}&page={page}"

    async def _get(self, url: str) -> str:
        if self._chain is None:
            raise FetchError(f"{self.retailer_id} needs the fetch chain (an unblocker) but this node has none")
        return await self._chain.fetch_text(self.policy, BASE + "/", url, None, self.fetch_order,
                                            country=self.geo, detect_queue=True)

    def queue_status(self, on: bool) -> Product:
        return Product(
            retailer_id=self.retailer_id, sku=QUEUE_SKU, title=f"{self.name} queue is live",
            url=f"{BASE}/{self.locale}", online=Stock(Level.IN if on else Level.OUT), franchise="pokemon",
            kind="queue",
        )

    def _parse(self, page: str, url: str) -> tuple[list[Product], int, int | None]:
        try:
            return parse_category(page, self.retailer_id, self.locale, self.currency)
        except ValueError:
            log.warning("%s: unexpected page at %s (%s)", self.retailer_id, url, describe_page(page))
            raise FetchError(f"{self.retailer_id}: unexpected page at {url}") from None

    async def discover(self) -> list[Product]:
        now = time.time()
        if now - self._read_at < self.every - SLACK:
            return []
        self._read_at = now
        url = self.category_url()
        try:
            page = await self._get(url)
        except Queued as exc:
            log.info("%s: queue is on (%s)", self.retailer_id, exc)
            return [self.queue_status(True)]
        products, total, in_stock = self._parse(page, url)
        changed = in_stock is not None and self._in_stock is not None and in_stock != self._in_stock
        if changed or now - self._swept_at >= self.sweep_every - SLACK:
            pages = min(math.ceil(total / PAGE_SIZE), MAX_PAGES)
            seen = {p.sku for p in products}
            for n in range(2, pages + 1):
                url = self.category_url(n)
                try:
                    page = await self._get(url)
                except Queued:
                    log.info("%s: queue came on mid-sweep", self.retailer_id)
                    return [self.queue_status(True)]
                more, _, _ = self._parse(page, url)
                products += [p for p in more if p.sku not in seen]
                seen.update(p.sku for p in more)
            self._swept_at = now
            log.info("%s: read all %d pages (%d products, %s in stock%s)", self.retailer_id, pages, len(products),
                     in_stock, ", count changed" if changed else "")
        self._in_stock = in_stock
        return [*products, self.queue_status(False)]

    async def search(self, query: str) -> list[Product]:
        return []  # see supports_search

    async def fetch_products(self, skus: list[str]) -> list[Product]:
        products = []
        for sku in skus:
            try:
                page = await self._get(f"{BASE}/{self.locale}/product/{sku}")
            except FetchError as exc:
                if exc.status == 404:
                    continue
                raise
            product = parse_product(page, sku, self.retailer_id, self.locale, self.currency)
            if product:
                products.append(product)
        return products

    def parse_ref(self, ref: str) -> str:
        m = re.search(r"/product/([^/?#]+)", urlparse(ref.strip()).path)
        return m.group(1) if m else ref.strip().strip("/")

    def matches_url(self, url: str) -> bool:
        return "pokemoncenter.com" in url and f"/{self.locale}/" in url.lower() + "/"
