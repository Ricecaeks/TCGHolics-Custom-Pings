"""JB Hi-Fi NZ (www.jbhifi.co.nz): a Shopify store, so search, discovery, price, online stock and
add-to-cart links come from the generic Shopify adapter. See docs/RETAILERS.md.

Store stock: every product page embeds JB's product JSON, including
`"AvailabilityInStore":{"OnDisplayStoreIds":[...],"InStockStoreIds":[21,23,...]}`, so one
plain request gives every store's stock.

Store list: JB's store finder reads the Algolia index `shopify_store_locations`; TCGHolics
approved using its public search-only key. The ids there (`shopId`) are the InStockStoreIds.
That index also holds warehouses, head office and retired entries, so only active retail
stores are kept. A copy ships in data/jbhifi_stores.json as the fallback if Algolia fails.
"""

from __future__ import annotations

import json
import re
from importlib import resources

from tcgpings.models import Level, Stock, Store
from tcgpings.net.http import FetchError
from tcgpings.retailers.base import register
from tcgpings.retailers.shopify import ShopifyAdapter

_IN_STOCK_IDS = re.compile(r'InStockStoreIds[\\"]*\s*:\s*\[([\d,\s]*)\]')

ALGOLIA_APP = "VHBKEAHERO"
ALGOLIA_KEY = "f65c581554c47bd2644975c00b63910a"  # public search-only key used by jbhifi.co.nz/pages/store-finder
STORE_INDEX = "shopify_store_locations"

# Entries in the store index that aren't shops customers can walk into.
_NOT_A_SHOP = re.compile(
    r"do not use|^\W*$|^oot$|warehouse|commercial|^international$|direct|offsite|support office|pop up|^jbrl$",
    re.I,
)


def parse_in_stock_store_ids(page: str) -> list[str] | None:
    m = _IN_STOCK_IDS.search(page)
    if not m:
        return None
    return [i.strip() for i in m.group(1).split(",") if i.strip()]


def parse_store_locations(data: dict) -> list[dict]:
    """Algolia store-locator response -> active retail stores, sorted by id."""
    stores = []
    for h in data.get("hits") or []:
        name = (h.get("storeName") or "").strip()
        if not h.get("isActive") or h.get("locationType") not in ("Store", "Home") or _NOT_A_SHOP.search(name):
            continue
        address = h.get("storeAddress") or {}
        stores.append({
            "store_id": str(h["shopId"]),
            "name": name,
            "region": (address.get("Suburb") or "").strip().title() or None,
            "phone": h.get("phone") or None,
        })
    return sorted(stores, key=lambda s: int(s["store_id"]))


def load_bundled_stores() -> list[dict]:
    text = resources.files("tcgpings.retailers.data").joinpath("jbhifi_stores.json").read_text(encoding="utf-8")
    return json.loads(text)["stores"]


@register
class JBHiFiAdapter(ShopifyAdapter):
    adapter_name = "jbhifi"
    supports_store_stock = True
    store_stock_interval = 10 * 60   # product pages are ~600 KB; store stock doesn't move by the second
    default_sku_interval = 3 * 60
    default_requests_per_minute = 20
    default_retailers = [
        ("jbhifi", "JB Hi-Fi", {"domain": "www.jbhifi.co.nz", "catalogue_pages": 1, "discover_pages": 1}, 0xFFE600)
    ]

    def __init__(self, retailer, http) -> None:
        super().__init__(retailer, http)
        self._names = {s["store_id"]: s["name"] for s in load_bundled_stores()}

    async def list_stores(self) -> list[Store]:
        try:
            data = await self.http.get_json(
                self.policy,
                f"https://{ALGOLIA_APP.lower()}-dsn.algolia.net/1/indexes/{STORE_INDEX}/query",
                headers={"X-Algolia-Application-Id": ALGOLIA_APP,
                         "X-Algolia-API-Key": self.config.get("algolia_key", ALGOLIA_KEY)},
                params={"hitsPerPage": "200"},
            )
            stores = parse_store_locations(data)
        except FetchError:
            stores = []
        stores = stores or load_bundled_stores()
        self._names = {s["store_id"]: s["name"] for s in stores}
        return [Store(self.retailer_id, s["store_id"], s["name"], s.get("region")) for s in stores]

    async def store_stock(self, sku: str, store_ids: list[str]) -> dict[str, Stock]:
        resp = await self.http.get(self.policy, f"{self.base}/products/{sku}")
        in_stock = parse_in_stock_store_ids(resp.text)
        if in_stock is None:
            return {}  # page layout changed or product delisted: report nothing rather than "all out"
        # Only shops customers can visit; warehouses and head office also appear in these lists.
        stock = {sid: Stock(Level.IN) for sid in in_stock if sid in self._names}
        for sid in store_ids:
            stock.setdefault(sid, Stock(Level.OUT))
        return stock

    def store_label(self, store_id: str) -> str:
        return self._names.get(store_id, f"JB Hi-Fi store #{store_id}")
