import asyncio, sys
sys.path.insert(0, ".")
from tcgpings.net.http import HttpClient
from tcgpings.net.browser import BrowserFetcher
from tcgpings.net.ratelimit import RateLimiter
from tcgpings.retailers.warehouse import WarehouseAdapter

ROW = {
    "id": "warehouse", "adapter": "warehouse", "name": "The Warehouse",
    "config": {"categories": ["toysbaby-toys-collectibletoys-tradingcardsaccs"], "discover_pages": 2},
    "requests_per_minute": 60, "proxy_policy": "direct", "color": None,
}

SKU = "R3098657"
STORES = ["221", "196"]  # Auckland Central, Warkworth


async def main():
    http = HttpClient()
    browser = BrowserFetcher("data/browser/warehouse-probe", RateLimiter(), headless=False)
    http.browser = browser
    a = WarehouseAdapter(ROW, http)
    print("store_stock_enabled:", a.store_stock_enabled)
    try:
        stock = await a.store_stock(SKU, STORES)
    finally:
        await browser.close()
    print("STORES:", {sid: (s.level.value, s.qty) for sid, s in stock.items()})


asyncio.run(main())
