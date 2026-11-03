"""Kmart NZ (kmart.co.nz). See docs/RETAILERS.md.

Listings come from Constructor.io, the site's search (TCGHolics approved using Kmart's public client key):
- Discovery:  /browse/group_id/<Trading Cards> sorted newest first (~85 products).
- Search:     /search/<q>; a product's SKU finds it too.
- Price:      data.price (NZD).
- Online:     data.stateOOS lists the islands that are out of stock, e.g. {"SI": "6"}. These flags
              can include warehouse stock, so they say nothing about individual stores. While store
              stock is unavailable they're the fallback for in-store-only products, which have no other signal.
- Fulfilment: data.FulfilmentChannel 3 = online and in store, 2 = in-store only (most Pokémon).

Store stock comes from the queries behind the product page's stock display, on Kmart's NZ gateway.
No key or sign-in. A count for any postcode's five nearest stores, for many products at once, so a
sweep asks one postcode at a time until every store has answered. Akamai challenged this after about
2.5 hours of sweeps every 5 minutes, so sweeps are slower now and back off hard when refused.
"""

from __future__ import annotations

import html
import logging
import re
import time
import uuid
from urllib.parse import quote, urlparse

from tcgpings.classify import is_sealed_product
from tcgpings.models import Level, Product, Stock, Store, to_cents
from tcgpings.net.http import FetchError
from tcgpings.retailers.base import RetailerAdapter, register

log = logging.getLogger(__name__)

BASE = "https://www.kmart.co.nz"
CONSTRUCTOR = "https://ac.cnstrc.com"
CONSTRUCTOR_KEY = "key_EyiTrcbGw7IFH3wR"  # public client key embedded in kmart.co.nz pages
TRADING_CARDS_GROUP = "c00f65271ffae599a4b675da63b2e92d"  # Toys > Toys by Category > Trading Cards
IN_STORE_ONLY = 2
ISLANDS = {"NI": "North Island", "SI": "South Island"}

GATEWAY = "https://api.kmart.co.nz/gateway/graphql"
HEADERS = {"Origin": BASE, "Referer": f"{BASE}/"}
STORES_QUERY = (
    "query getNearestLocations($lat: String!, $lon: String!, $distance: String!, $limit: Int) { "
    "nearestLocations(input: { lat: $lat, lon: $lon, distance: $distance, limit: $limit }) "
    "{ locationId publicName state postcode } }"
)
STOCK_QUERY = (
    "query getProductAvailability($input: ProductAvailabilityQueryInput!) { getProductAvailability(input: $input) "
    "{ availability { CLICK_AND_COLLECT { keycode locations { fulfilment { isBuddyLocation locationId "
    "stock { available } } } } } } }"
)
ALL_OF_NZ = {"lat": "-41.0", "lon": "174.0", "distance": "2000km", "limit": 100}
BATCH = 100  # products per request; 85 is the most the category has had
STORE_CHECK_SECONDS = 15 * 60
STORE_BACKOFF_LIMIT = 6 * 3600
# A short block keeps the last store counts; the islands only stand in once they're this stale.
ISLANDS_AFTER_SECONDS = 2 * 3600

_SKU_IN_URL = re.compile(r"(\d{7,9})/?$")
_NZ_SUFFIX = re.compile(r"\s+nz$", re.I)


def parse_constructor(data: dict, retailer_id: str = "kmart") -> list[Product]:
    products = []
    for item in (data.get("response") or {}).get("results") or []:
        d = item.get("data") or {}
        sku = str(d.get("variation_id") or str(d.get("id") or "").removeprefix("P_"))
        if not sku:
            continue
        in_store_only = d.get("FulfilmentChannel") == IN_STORE_ONLY
        out = set((d.get("stateOOS") or {}).keys())
        anywhere = not set(ISLANDS) <= out
        url = d.get("url") or f"/product/{sku}/"
        products.append(Product(
            retailer_id=retailer_id,
            sku=sku,
            title=html.unescape(item.get("value") or ""),
            url=url if url.startswith("http") else BASE + url,
            image=d.get("image_url"),
            price_cents=to_cents(d.get("price")),
            online=Stock(Level.IN if anywhere and not in_store_only else Level.OUT),
            stores={i: Stock(Level.OUT if i in out else Level.IN) for i in ISLANDS} if in_store_only else None,
            note="In-store only" if in_store_only else None,
        ))
    return products


def parse_store_list(data: dict) -> list[dict]:
    return [
        {
            "store_id": s["locationId"],
            "name": _NZ_SUFFIX.sub("", s["publicName"].strip()),
            "region": s.get("state") or None,
            "postcode": (s.get("postcode") or "").zfill(4),
        }
        for s in (data.get("data") or {}).get("nearestLocations") or []
    ]


def parse_store_counts(data: dict) -> dict[str, dict[str, int]]:
    """SKU -> store -> units. Stores answering for another store's stock are left out."""
    availability = ((data.get("data") or {}).get("getProductAvailability") or {}).get("availability") or {}
    counts: dict[str, dict[str, int]] = {}
    for row in availability.get("CLICK_AND_COLLECT") or []:
        stores = counts.setdefault(row["keycode"], {})
        for location in row.get("locations") or []:
            fulfilment = location.get("fulfilment") or {}
            if fulfilment.get("isBuddyLocation") or not fulfilment.get("locationId"):
                continue
            stores[fulfilment["locationId"]] = max((fulfilment.get("stock") or {}).get("available") or 0, 0)
    return counts


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
        self._stores: list[dict] = []
        self._next_store_check = 0.0
        self._store_failures = 0
        self._store_ok_at = float("-inf")

    async def _constructor(self, path: str, keep_islands: bool = False, **params: str) -> list[Product]:
        data = await self.http.get_json(self.policy, f"{CONSTRUCTOR}{path}", params={**self._cio, **params})
        products = parse_constructor(data, self.retailer_id)
        if not keep_islands:
            for product in products:
                product.stores = None
        return products

    async def _gateway(self, operation: str, query: str, variables: dict) -> dict:
        resp = await self.http.request(
            self.policy, "POST", GATEWAY, headers=HEADERS,
            json={"operationName": operation, "query": query, "variables": variables},
        )
        try:
            return resp.json()
        except ValueError as exc:
            raise FetchError(f"POST {GATEWAY}: response was not JSON") from exc

    async def discover(self) -> list[Product]:
        products = await self._constructor(
            f"/browse/group_id/{self.config.get('group_id', TRADING_CARDS_GROUP)}",
            keep_islands=True, sort_by="numberOfDaysSinceStartDate", sort_order="ascending", num_results_per_page="200",
        )
        counts = None
        if time.monotonic() >= self._next_store_check:
            try:
                counts = await self._store_stock([p.sku for p in products if is_sealed_product(p.title)])
            except FetchError as exc:  # the listings are still good; leave the stores alone for a while
                self._store_failures += 1
                wait = min(STORE_CHECK_SECONDS * 2 ** self._store_failures, STORE_BACKOFF_LIMIT)
                self._next_store_check = time.monotonic() + wait
                log.warning("kmart: store stock unavailable, next try in %d min: %s", wait // 60, exc)
            else:
                self._store_failures = 0
                self._store_ok_at = time.monotonic()
                self._next_store_check = self._store_ok_at + STORE_CHECK_SECONDS
        if time.monotonic() - self._store_ok_at < ISLANDS_AFTER_SECONDS:  # islands only when store stock is down
            for product in products:
                product.stores = (counts or {}).get(product.sku)
        return products

    async def _store_stock(self, skus: list[str]) -> dict[str, dict[str, Stock]]:
        """Every store's stock. A store that never answers is left out, not called empty."""
        stores = self._stores or await self._load_stores()
        stock: dict[str, dict[str, Stock]] = {}
        for start in range(0, len(skus), BATCH):
            products = [{"keycode": sku, "quantity": 1, "isNationalInventory": False, "isClickAndCollectOnly": True}
                        for sku in skus[start:start + BATCH]]
            answered: set[str] = set()
            for store in stores:
                if store["store_id"] in answered:
                    continue
                data = await self._gateway("getProductAvailability", STOCK_QUERY, {"input": {
                    "country": "NZ", "postcode": store["postcode"], "products": products,
                    "fulfilmentMethods": ["CLICK_AND_COLLECT"], "limit": 5,
                }})
                for sku, counts in parse_store_counts(data).items():
                    answered.update(counts)
                    stock.setdefault(sku, {}).update(
                        {sid: Stock(Level.IN if qty else Level.OUT, qty) for sid, qty in counts.items()}
                    )
        return stock

    async def _load_stores(self) -> list[dict]:
        self._stores = parse_store_list(await self._gateway("getNearestLocations", STORES_QUERY, ALL_OF_NZ))
        return self._stores

    async def search(self, query: str) -> list[Product]:
        return await self._constructor(f"/search/{quote(query)}", num_results_per_page="100")

    async def fetch_products(self, skus: list[str]) -> list[Product]:
        products = []
        for sku in skus:
            products += [p for p in await self._constructor(f"/search/{quote(sku)}", num_results_per_page="5")
                         if p.sku == sku]
        return products

    async def list_stores(self) -> list[Store]:
        stores = await self._load_stores()
        return [Store(self.retailer_id, s["store_id"], s["name"], s["region"]) for s in stores]

    def store_label(self, store_id: str) -> str:
        if store_id in ISLANDS:
            return ISLANDS[store_id]
        return next((s["name"] for s in self._stores if s["store_id"] == store_id), f"Store {store_id}")

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
