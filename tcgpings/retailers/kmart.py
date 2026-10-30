"""Kmart NZ (kmart.co.nz). Site search is Constructor.io; TCGHolics approved using Kmart's public
client key. kmart.co.nz itself sits behind Akamai, so everything here goes to ac.cnstrc.com only.
See docs/RETAILERS.md.

- Discovery:  /browse/group_id/<Trading Cards> sorted newest first (~85 products).
- Search:     /search/<q>; a product's SKU finds it too.
- Price:      data.price (NZD).
- Stock:      data.stateOOS lists the islands where the product is out of stock,
              e.g. {"SI": "6"}; an island that isn't listed has stock.
- Fulfilment: data.FulfilmentChannel 3 = online and in store, 2 = in-store only (most Pokémon).
              In-store-only products are never in stock online, so their availability is
              the island-level flag alone.

The two islands are this adapter's "stores" (#kmart-north-island, #kmart-south-island), and
their stock comes with every listing, so watching them costs no extra requests. Kmart's
per-store stock (its "check stock nearby") isn't covered.
"""

from __future__ import annotations

import html
import re
import uuid
from urllib.parse import quote, urlparse

from tcgpings.models import Level, Product, Stock, Store, to_cents
from tcgpings.retailers.base import RetailerAdapter, register

BASE = "https://www.kmart.co.nz"
CONSTRUCTOR = "https://ac.cnstrc.com"
CONSTRUCTOR_KEY = "key_EyiTrcbGw7IFH3wR"  # public client key embedded in kmart.co.nz pages
TRADING_CARDS_GROUP = "c00f65271ffae599a4b675da63b2e92d"  # Toys > Toys by Category > Trading Cards
IN_STORE_ONLY = 2

ISLANDS = {"NI": "North Island", "SI": "South Island"}

_SKU_IN_URL = re.compile(r"(\d{7,9})/?$")


def parse_constructor(data: dict, retailer_id: str = "kmart") -> list[Product]:
    products = []
    for item in (data.get("response") or {}).get("results") or []:
        d = item.get("data") or {}
        sku = str(d.get("variation_id") or str(d.get("id") or "").removeprefix("P_"))
        if not sku:
            continue
        out = set((d.get("stateOOS") or {}).keys())
        islands = {code: Stock(Level.OUT if code in out else Level.IN) for code in ISLANDS}
        in_store_only = d.get("FulfilmentChannel") == IN_STORE_ONLY
        anywhere = any(s.level is Level.IN for s in islands.values())
        url = d.get("url") or f"/product/{sku}/"
        products.append(Product(
            retailer_id=retailer_id,
            sku=sku,
            title=html.unescape(item.get("value") or ""),
            url=url if url.startswith("http") else BASE + url,
            image=d.get("image_url"),
            price_cents=to_cents(d.get("price")),
            online=Stock(Level.IN if anywhere and not in_store_only else Level.OUT),
            stores=islands,
            note="In-store only" if in_store_only else None,
        ))
    return products


@register
class KmartAdapter(RetailerAdapter):
    adapter_name = "kmart"
    supports_discovery = True
    stock_in_listings = True
    default_discover_interval = 120
    default_sku_interval = 5 * 60
    default_search_interval = 10 * 60
    default_requests_per_minute = 12
    default_retailers = [("kmart", "Kmart", {}, 0xE4002B)]

    def __init__(self, retailer, http) -> None:
        super().__init__(retailer, http)
        self._cio = {"key": self.config.get("constructor_key", CONSTRUCTOR_KEY), "c": "ciojs-client-2.77.1",
                     "i": str(uuid.uuid4()), "s": "1"}

    async def _constructor(self, path: str, **params: str) -> list[Product]:
        data = await self.http.get_json(self.policy, f"{CONSTRUCTOR}{path}", params={**self._cio, **params})
        return parse_constructor(data, self.retailer_id)

    async def discover(self) -> list[Product]:
        return await self._constructor(
            f"/browse/group_id/{self.config.get('group_id', TRADING_CARDS_GROUP)}",
            sort_by="numberOfDaysSinceStartDate", sort_order="ascending", num_results_per_page="200",
        )

    async def search(self, query: str) -> list[Product]:
        return await self._constructor(f"/search/{quote(query)}", num_results_per_page="100")

    async def fetch_products(self, skus: list[str]) -> list[Product]:
        products = []
        for sku in skus:
            products += [p for p in await self._constructor(f"/search/{quote(sku)}", num_results_per_page="5")
                         if p.sku == sku]
        return products

    async def list_stores(self) -> list[Store]:
        return [Store(self.retailer_id, code, name) for code, name in ISLANDS.items()]

    def store_label(self, store_id: str) -> str:
        return ISLANDS.get(store_id, store_id)

    def parse_ref(self, ref: str) -> str:
        ref = ref.strip()
        if ref.isdigit():
            return ref
        m = _SKU_IN_URL.search(urlparse(ref).path.rstrip("/")) if "://" in ref else None
        if not m:
            raise ValueError(f"no Kmart product number in {ref!r}")
        return m.group(1)

    def matches_url(self, url: str) -> bool:
        return urlparse(url).netloc.endswith("kmart.co.nz")
