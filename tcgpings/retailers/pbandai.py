"""Premium Bandai NZ (p-bandai.com/nz): Bandai's own store, pre-orders only. See docs/RETAILERS.md.

The storefront is a Vue app whose search page sits behind a JavaScript bot check, but the JSON API it
calls answers plain requests: GET /api/search with the header `X-G1-Area-Code: nz` picks the NZ store.
- `_f_categories=04-011` is the "Card Games" category (One Piece, Gundam, Dragon Ball Super, Digimon...),
  `sortType=NewArrival` sorts newest first, `limit` (up to 100) and `offset` page. In Nov 2026 the NZ
  category held 39 products, so one request reads all of it.
- Each row: productCode (the SKU, e.g. N2898133002), productName.en, fixedListPrice {amount, currency},
  productType (always PreOrder in NZ so far), saleStatus Waiting (not open yet) / On / End, displayStatus,
  saleStartExpectedDt / saleEndExpectedDt (UTC), productImages[].fileUrl (relative to https://p-bandai.com/)
  and flags (PRE_ORDER, PRE_ORDER_CLOSED, OUT_OF_STOCK, CHANCE_TO_BUY_DRAWING = a lottery, EXCLUSIVE).
- Orderable = saleStatus On, displayStatus On and no OUT_OF_STOCK flag. An item can be On (its pre-order
  window is open) yet flagged OUT_OF_STOCK once its allocation sells out, so the flag decides.
- Each sale window is its own product code (a re-run gets a new one), so a re-opened pre-order shows up as a
  new listing rather than a restock.
- /api/search/bulk?productCodes=a,b returns the same rows for specific products (watches).
- Product pages are /nz/item/{productCode} (behind the same bot check, so only used as links).
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from tcgpings.models import Level, Product, Stock, to_cents
from tcgpings.net.http import FetchError
from tcgpings.retailers.base import RetailerAdapter, register

log = logging.getLogger(__name__)

BASE = "https://p-bandai.com"
CARD_GAMES = "04-011"
PAGE_SIZE = 100
MAX_PAGES = 5
CHUNK = 50  # product codes per bulk request
NZ = ZoneInfo("Pacific/Auckland")

LOTTERY = "CHANCE_TO_BUY_DRAWING"
OUT_OF_STOCK = "OUT_OF_STOCK"


def headers(area: str) -> dict[str, str]:
    return {"X-G1-Area-Code": area, "Accept-Language": "en", "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json", "Referer": f"{BASE}/{area}/"}


def _when(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).astimezone(NZ)
    except ValueError:
        return None


def _day(when: datetime) -> str:
    return f"{when.day} {when:%b}"


def _time(when: datetime) -> str:
    return f"{when:%I:%M %p}".lstrip("0").lower()


def level_of(row: dict) -> Level:
    sale, display = row.get("saleStatus"), row.get("displayStatus")
    flags = row.get("flags") or []
    if display not in (None, "On") or OUT_OF_STOCK in flags:
        return Level.OUT
    if sale == "On":
        return Level.IN
    if sale in ("Waiting", "End"):
        return Level.OUT
    return Level.UNKNOWN


def note_of(row: dict) -> str | None:
    parts = []
    flags = row.get("flags") or []
    if LOTTERY in flags:
        parts.append("Lottery (chance to buy)")
    elif row.get("productType") == "PreOrder":
        parts.append("Pre-order")
    sale = row.get("saleStatus")
    if sale == "Waiting" and (start := _when(row.get("saleStartExpectedDt"))):
        parts.append(f"opens {_day(start)}, {_time(start)}")
    elif sale == "On" and OUT_OF_STOCK not in flags and (end := _when(row.get("saleEndExpectedDt"))):
        parts.append(f"closes {_day(end)}")
    return " · ".join(parts) or None


def parse_row(row: dict, retailer_id: str, area: str = "nz") -> Product | None:
    code = row.get("productCode")
    name = (row.get("productName") or {}).get("en")
    if not code or not name:
        return None
    images = row.get("productImages") or []
    image = next((i.get("fileUrl") for i in images if i.get("fileUrl") and i.get("mediaType") != "Video"), None)
    price = (row.get("fixedListPrice") or {}).get("amount")
    return Product(
        retailer_id=retailer_id,
        sku=code,
        title=" ".join(name.split()),
        url=f"{BASE}/{area}/item/{code}",
        image=image if not image or image.startswith("http") else f"{BASE}/{image.lstrip('/')}",
        price_cents=to_cents(price),
        online=Stock(level_of(row)),
        note=note_of(row),
    )


def parse_search(data: dict, retailer_id: str, area: str = "nz") -> tuple[list[Product], int]:
    """/api/search response -> (products, total in the result set)."""
    try:
        results = data["productResults"]
        rows = results["products"]
    except (KeyError, TypeError):
        raise ValueError("no productResults in the response") from None
    products = [p for row in rows or [] if (p := parse_row(row, retailer_id, area))]
    return products, int(results.get("totalCount") or len(products))


@register
class PBandaiAdapter(RetailerAdapter):
    adapter_name = "pbandai"
    supports_discovery = True
    supports_search = False  # discovery reads the whole Card Games category in one request
    default_discover_interval = 120
    default_sku_interval = 600
    default_requests_per_minute = 10
    default_retailers = [("pbandai-nz", "P-Bandai NZ", {"area": "nz", "category": CARD_GAMES}, 0x1E50A2)]

    def __init__(self, retailer, http) -> None:
        super().__init__(retailer, http)
        self.area = (self.config.get("area") or "nz").lower()
        self.category = self.config.get("category") or CARD_GAMES

    async def _get(self, path: str, params: dict) -> object:
        return await self.http.get_json(self.policy, f"{BASE}/api/{path}", params=params, headers=headers(self.area))

    async def discover(self) -> list[Product]:
        products: list[Product] = []
        seen: set[str] = set()
        for n in range(MAX_PAGES):
            params = {"_f_categories": self.category, "sortType": "NewArrival", "limit": PAGE_SIZE,
                      "offset": n * PAGE_SIZE}
            data = await self._get("search", params)
            try:
                page, total = parse_search(data, self.retailer_id, self.area)  # type: ignore[arg-type]
            except ValueError:
                raise FetchError(f"{self.retailer_id}: unexpected search response") from None
            products += [p for p in page if p.sku not in seen]
            seen.update(p.sku for p in page)
            if not page or (n + 1) * PAGE_SIZE >= total:
                break
        return products

    async def search(self, query: str) -> list[Product]:
        return []  # see supports_search

    async def fetch_products(self, skus: list[str]) -> list[Product]:
        products = []
        for i in range(0, len(skus), CHUNK):
            chunk = skus[i:i + CHUNK]
            rows = await self._get("search/bulk", {"productCodes": ",".join(chunk), "limit": len(chunk)})
            if not isinstance(rows, list):
                raise FetchError(f"{self.retailer_id}: unexpected bulk response")
            products += [p for row in rows if (p := parse_row(row, self.retailer_id, self.area))]
        return products

    def parse_ref(self, ref: str) -> str:
        m = re.search(r"/item/([A-Za-z0-9]+)", urlparse(ref.strip()).path)
        return m.group(1) if m else ref.strip().strip("/")

    def matches_url(self, url: str) -> bool:
        return "p-bandai.com" in url and f"/{self.area}/" in url.lower() + "/"
