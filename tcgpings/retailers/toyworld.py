"""Toyworld NZ (www.toyworld.co.nz): a Shopify store, so listings, price, online stock and add-to-cart
links come from the generic adapter. See docs/RETAILERS.md.

Its catalogue is mostly toys, so discovery reads only the card collections instead of the
store-wide feed.

Store stock: the product page's "Find in Store" button uses Stock In Store (stockinstore.net), which
answers per store, by barcode, with a stock level. No key or sign-in; these are the page's own requests.
"""

from __future__ import annotations

import json

from tcgpings.models import Level, Stock, Store
from tcgpings.net.http import FetchError
from tcgpings.retailers.base import register
from tcgpings.retailers.shopify import ShopifyAdapter

STOCK_API = "https://stockinstore.net"
HEADERS = {"Origin": "https://www.toyworld.co.nz", "Referer": "https://www.toyworld.co.nz/"}
WIDGET_FORM = {"site": "10044", "widget": "51", "widgetType": "product", "lang": "en", "isajax": "1",
               "info": "none", "preview": "false"}
AUCKLAND = "-36.85_174.76"  # the widget always sends a location; every store is requested by code anyway
# The answer's `stock` is only 0 or 1, so the level comes from the threshold the widget displays.
LEVELS = {"in-stock": Level.IN, "low-stock": Level.LOW, "out-of-stock": Level.OUT}
BEST_FIRST = (Level.IN, Level.LOW, Level.OUT)


def parse_store_list(data: dict) -> list[dict]:
    stores = []
    for s in (data.get("response") or {}).get("stores_list") or []:
        stores.append({
            "store_id": s["code"],
            "name": s["name"].removeprefix("Toyworld ").strip(),
            "region": s.get("region_name") or None,
        })
    return stores


def parse_store_levels(data: dict) -> dict[str, Level]:
    """Store code -> level. A store with an unrecognised level is left out rather than called empty."""
    levels = {}
    for s in data.get("response") or []:
        level = LEVELS.get((s.get("threshold") or {}).get("threshold_type_by"))
        if level and s.get("code"):
            levels[s["code"]] = level
    return levels


@register
class ToyworldAdapter(ShopifyAdapter):
    adapter_name = "toyworld"
    supports_store_stock = True
    track_all_discovered = True  # a small sealed range, and one cheap request per product
    store_stock_interval = 15 * 60  # each answer is ~360 KB, and stock updates in batches
    default_sku_interval = 5 * 60
    default_discover_interval = 5 * 60
    default_requests_per_minute = 12
    default_retailers = [
        ("toyworld", "Toyworld",
         {"domain": "www.toyworld.co.nz", "collections": ["trading-cards", "pokemon"], "catalogue_pages": 1},
         0x00A651)
    ]

    async def _post(self, path: str, form: dict) -> dict:
        resp = await self.http.request(
            self.policy, "POST", f"{STOCK_API}{path}", data={**WIDGET_FORM, **form}, headers=HEADERS
        )
        try:
            return resp.json()
        except ValueError as exc:
            raise FetchError(f"POST {path}: response was not JSON") from exc

    async def list_stores(self) -> list[Store]:
        stores = parse_store_list(await self._post("/stores/getStoresForWidget", {}))
        return [Store(self.retailer_id, s["store_id"], s["name"], s["region"]) for s in stores]

    async def _barcodes(self, handle: str) -> list[str]:
        try:
            data = await self.http.get_json(self.policy, f"{self.base}/products/{handle}.js")
        except FetchError as exc:
            if "HTTP 404" in str(exc):
                return []  # no longer listed, so there's no barcode to ask about
            raise
        return [str(v["barcode"]) for v in data.get("variants") or [] if v.get("barcode")]

    async def store_stock(self, sku: str, store_ids: list[str]) -> dict[str, Stock]:
        best: dict[str, Level] = {}
        for barcode in await self._barcodes(sku):  # "assorted" products have one barcode per variant
            data = await self._post("/stores/getStoresStock", {
                "timezoneOffsetMinutes": "780", "pid": barcode, "storeids": ",".join(store_ids),
                "latlong": AUCKLAND, "thresholdType": "cnc",
                "items": json.dumps([{"upi": barcode, "quantity": "1"}]),
            })
            for store_id, level in parse_store_levels(data).items():
                if store_id not in best or BEST_FIRST.index(level) < BEST_FIRST.index(best[store_id]):
                    best[store_id] = level
        wanted = set(store_ids)
        return {sid: Stock(level) for sid, level in best.items() if sid in wanted}
