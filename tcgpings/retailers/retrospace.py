"""Retrospace (www.retrospace.co.nz), a Christchurch collectibles shop. See docs/RETAILERS.md.

A custom site (built by Cactuslab), plain HTML, no bot protection (checked 2026-11-04). Listing pages
are `<li class="result-wrapper">` tiles: a link to the product, an `<h2>` title, a stock label
("2 in stock", "in stock", "Special Order (Ships in 2 weeks)", "Pre-Order April 2027") and a price.
- A category page shows 20 tiles; its "load more" button fetches `/<category slug>/more/?start=N&howMany=M`,
  which returns the tiles alone, so one request lists a whole category.
- Discovery: the card game categories in full, plus the newest tiles of the all-cards listing (`/cards/`),
  which catches new card games in other categories. Listings also show Special Order products, so a
  sold-out product most likely leaves them: one missing from its category for GONE_AFTER_SCANS scans in
  a row counts as sold out, so its return alerts.
- Search: `/search.do?q=` (category tiles mixed in, skipped).
- SKU = the product's path (`games/pokemon-cards/<slug>`), which is what opens its page.

Not covered: add-to-cart (a form POST with a CSRF token).
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

BASE = "https://www.retrospace.co.nz"
CATEGORIES = ["pokemon-cards", "magic-the-gathering-1", "one-piece-card-game", "yu-gi-oh-cards",
              "dragonball-z-cards", "riftbound-league-of-legends-tcg-in-stock"]
NEWEST = "cards"  # every card product, newest first
NEWEST_COUNT = 60
CATEGORY_COUNT = 500  # more than any card category holds (Yu-Gi-Oh has 64)
GONE_AFTER_SCANS = 3

# Card game paths; everything else (Pokémon mugs, figures, light-ups) is merchandise. Sleeves, binders and
# deck boxes sit under card-accessories.
_CARD_PATH = re.compile(r"^(?:games/(?:pokemon-cards|magic-the-gathering|one-piece-card-game|yu-gi-oh-cards)|cards/|"
                        r"in-stock/tcg-collector-cards)")
_ACCESSORY_PATH = re.compile(r"accessor")

_TILE = re.compile(r'<li class="result-wrapper">(.*?)</li>', re.S)
_HREF = re.compile(r'href="(/[^"]+)"')
_TITLE = re.compile(r"<h2>(.*?)</h2>", re.S)
_LABEL = re.compile(r'class="[^"]*\bavailability\b[^"]*">(.*?)</span>', re.S)
_PRICE = re.compile(r'class="price">\s*\$?([\d,.]+)')
_TILE_IMAGE = re.compile(r'<img src="([^"]+)"')
_H1 = re.compile(r"<h1>(.*?)</h1>", re.S)
_IMAGE = re.compile(r"data-image='(\{.*?\})'", re.S)
_COUNT = re.compile(r"(\d+)\s+in\s+stock", re.I)


def _text(fragment: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


def _sku(path: str) -> str:
    return urlparse(path).path.strip("/")


def parse_stock(label: str) -> tuple[Stock, str | None]:
    """Stock label -> stock and an alert note. Special Order means the shop orders it in: not stock."""
    text = label.lower()
    count = _COUNT.search(text)
    if count:
        return Stock(Level.IN, int(count.group(1))), None
    if "in stock" in text:
        return Stock(Level.IN), None
    if "pre-order" in text or "preorder" in text:
        return Stock(Level.IN), label
    if "special order" in text or "sold out" in text or "out of stock" in text:
        return Stock(Level.OUT), None
    return Stock(Level.UNKNOWN), None


def is_card_path(sku: str) -> bool:
    return bool(_CARD_PATH.search(sku)) and not _ACCESSORY_PATH.search(sku)


def parse_tiles(page: str, retailer_id: str = "retrospace") -> list[Product]:
    """Listing, "load more" or search page -> card game products (category tiles and merchandise skipped)."""
    products = []
    for tile in _TILE.findall(page):
        if "result-category" in tile:
            continue
        href, title, label = _HREF.search(tile), _TITLE.search(tile), _LABEL.search(tile)
        if not href or not title or not label:
            continue
        sku = _sku(html.unescape(href.group(1)))
        if not is_card_path(sku):
            continue
        stock, note = parse_stock(_text(label.group(1)))
        price, image = _PRICE.search(tile), _TILE_IMAGE.search(tile)
        products.append(Product(
            retailer_id=retailer_id,
            sku=sku,
            title=_text(title.group(1)),
            url=f"{BASE}/{sku}/",
            image=BASE + html.unescape(image.group(1)) if image else None,  # ?k= signs the resized image
            price_cents=to_cents(price.group(1).replace(",", "")) if price else None,
            online=stock,
            note=note,
        ))
    return products


def parse_product(page: str, sku: str, retailer_id: str = "retrospace") -> Product | None:
    """Product page -> product. Related products further down have their own stock labels, so only the
    first label after the title counts."""
    title = _H1.search(page)
    if not title:
        return None
    rest = page[title.end():]
    label, price = _LABEL.search(rest), _PRICE.search(rest)
    stock, note = parse_stock(_text(label.group(1))) if label else (Stock(Level.UNKNOWN), None)
    image = None
    data = _IMAGE.search(page)
    if data:
        try:
            image = json.loads(html.unescape(data.group(1))).get("src")
        except ValueError:
            pass
    return Product(
        retailer_id=retailer_id,
        sku=sku,
        title=_text(title.group(1)),
        url=f"{BASE}/{sku}/",
        image=image,
        price_cents=to_cents(price.group(1).replace(",", "")) if price else None,
        online=stock,
        note=note,
    )


@register
class RetrospaceAdapter(RetailerAdapter):
    adapter_name = "retrospace"
    supports_discovery = True
    default_discover_interval = 5 * 60
    default_sku_interval = 10 * 60
    default_search_interval = 10 * 60
    default_requests_per_minute = 10
    default_retailers = [("retrospace", "Retrospace", {"categories": CATEGORIES}, 0x1F6FB2)]

    def __init__(self, retailer, http) -> None:
        super().__init__(retailer, http)
        self._listed: dict[str, Product] = {}  # last seen listing of each product still in its category
        self._missing: dict[str, int] = {}
        self._scanned = 0

    async def _listing(self, slug: str, count: int) -> list[Product]:
        resp = await self.http.get(self.policy, f"{BASE}/{slug}/more/", params={"start": 0, "howMany": count})
        return parse_tiles(resp.text, self.retailer_id)

    async def discover(self) -> list[Product]:
        in_categories: dict[str, Product] = {}
        for slug in self.config.get("categories") or CATEGORIES:
            for product in await self._listing(slug, CATEGORY_COUNT):
                in_categories.setdefault(product.sku, product)
        self._scanned = len(in_categories)
        found = dict(in_categories)
        for product in await self._listing(NEWEST, NEWEST_COUNT):
            found.setdefault(product.sku, product)
        if not in_categories:  # categories that list nothing are more likely broken than sold out
            log.warning("retrospace: the card categories listed no products")
            return list(found.values())
        return list(found.values()) + self._left_the_listings(in_categories)

    def scan_size(self, results: list[Product]) -> int | None:
        return self._scanned  # what the card categories listed, not the newest page or ones that left

    def _left_the_listings(self, found: dict[str, Product]) -> list[Product]:
        """Products gone from their category for GONE_AFTER_SCANS scans in a row, now counted as sold out."""
        gone = []
        for sku in list(self._listed):
            if sku in found:
                self._missing.pop(sku, None)
                continue
            self._missing[sku] = self._missing.get(sku, 0) + 1
            if self._missing[sku] >= GONE_AFTER_SCANS:
                product = self._listed.pop(sku)
                del self._missing[sku]
                product.online, product.note = Stock(Level.OUT), None
                gone.append(product)
        self._listed.update(found)
        return gone

    async def search(self, query: str) -> list[Product]:
        resp = await self.http.get(self.policy, f"{BASE}/search.do", params={"q": query})
        return parse_tiles(resp.text, self.retailer_id)

    async def fetch_products(self, skus: list[str]) -> list[Product]:
        products = []
        for sku in skus:
            try:
                resp = await self.http.get(self.policy, f"{BASE}/{sku}/")
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
        return _sku(ref) if "retrospace.co.nz" in ref or ref.startswith("/") else ref.strip("/")

    def matches_url(self, url: str) -> bool:
        return "retrospace.co.nz" in url
