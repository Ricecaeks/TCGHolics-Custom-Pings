"""JB Hi-Fi NZ (www.jbhifi.co.nz): a Shopify store, so search, discovery, price, online stock and
add-to-cart links come from the generic Shopify adapter. See docs/RETAILERS.md.

Store stock: every product page embeds JB's product JSON, including
`"AvailabilityInStore":{"OnDisplayStoreIds":[...],"InStockStoreIds":[21,23,...]}`, so one
plain request gives every store's stock. Stores are numeric ids; ids are learned as they show
up in stock lists, and named from STORE_NAMES when known.
"""

from __future__ import annotations

import re

from tcgpings.models import Level, Stock
from tcgpings.retailers.base import register
from tcgpings.retailers.shopify import ShopifyAdapter

_IN_STOCK_IDS = re.compile(r'InStockStoreIds[\\"]*\s*:\s*\[([\d,\s]*)\]')

# JB store id -> name. Fill from JB's store locator; unknown ids show as "JB Hi-Fi store #<id>".
STORE_NAMES: dict[str, str] = {}


def parse_in_stock_store_ids(page: str) -> list[str] | None:
    m = _IN_STOCK_IDS.search(page)
    if not m:
        return None
    return [i.strip() for i in m.group(1).split(",") if i.strip()]


@register
class JBHiFiAdapter(ShopifyAdapter):
    adapter_name = "jbhifi"
    supports_store_stock = True
    store_stock_discovers_stores = True
    store_stock_interval = 10 * 60   # product pages are ~600 KB; store stock doesn't move by the second
    default_sku_interval = 3 * 60
    default_requests_per_minute = 20
    default_retailers = [
        ("jbhifi", "JB Hi-Fi", {"domain": "www.jbhifi.co.nz", "catalogue_pages": 1, "discover_pages": 1}, 0xFFE600)
    ]

    async def store_stock(self, sku: str, store_ids: list[str]) -> dict[str, Stock]:
        resp = await self.http.get(self.policy, f"{self.base}/products/{sku}")
        in_stock = parse_in_stock_store_ids(resp.text)
        if in_stock is None:
            return {}  # page layout changed or product delisted: report nothing rather than "all out"
        stock = {sid: Stock(Level.IN) for sid in in_stock}
        for sid in store_ids:
            stock.setdefault(sid, Stock(Level.OUT))
        return stock

    def store_label(self, store_id: str) -> str:
        return STORE_NAMES.get(store_id, f"JB Hi-Fi store #{store_id}")
