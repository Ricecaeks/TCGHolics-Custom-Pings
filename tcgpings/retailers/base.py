from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import time
from typing import Any, ClassVar

from tcgpings.models import Product, Stock, Store
from tcgpings.net.http import HttpClient, NetPolicy

REGISTRY: dict[str, type[RetailerAdapter]] = {}


def register(cls: type[RetailerAdapter]) -> type[RetailerAdapter]:
    REGISTRY[cls.adapter_name] = cls
    return cls


class RetailerAdapter(ABC):
    """One instance per `retailers` row. Adapters only fetch and parse; they never touch the DB."""

    adapter_name: ClassVar[str]
    supports_store_stock: ClassVar[bool] = False
    # Minimum seconds between store-level checks of one product (0 = every run). Retailers whose
    # store stock only refreshes daily don't need hammering every minute.
    store_stock_interval: ClassVar[int] = 0
    # Retailers that refresh store stock at a set time each day (NZ time): each product is checked
    # once a day after it, spread over the following hour. Takes the place of store_stock_interval.
    store_stock_daily_at: ClassVar[time | None] = None
    # Seconds between checks of a product in a hot set, where extra checks are free (None = no change).
    hot_sku_interval: ClassVar[int | None] = None
    # Retailer rows created automatically at startup: (id, name, config, color).
    default_retailers: ClassVar[list[tuple[str, str, dict, int | None]]] = []
    # Whether those rows start enabled. Retailers that need special access (real browser,
    # proxies) start disabled so they're only hit once someone turns them on.
    default_enabled: ClassVar[bool] = True
    # Cluster-wide request budget given to those rows when first created.
    default_requests_per_minute: ClassVar[int | None] = None
    # Check intervals when a watch doesn't set one (None = the global defaults in Settings).
    default_sku_interval: ClassVar[int | None] = None
    default_search_interval: ClassVar[int | None] = None
    # Discovery: a cheap scan of the retailer's whole TCG range (category listing / newest
    # products), run on a timer for every enabled retailer whether or not anything is watched.
    supports_discovery: ClassVar[bool] = False
    # Whether keyword watches search this retailer. Off where every request is paid (Mighty Ape): its
    # discovery scans have to do.
    supports_search: ClassVar[bool] = True
    default_discover_interval: ClassVar[int | None] = None

    def __init__(self, retailer: Any, http: HttpClient) -> None:
        self.retailer_id: str = retailer["id"]
        self.name: str = retailer["name"]
        self.config: dict = dict(retailer["config"] or {})
        self.policy = NetPolicy.from_row(retailer)
        self.http = http

    @abstractmethod
    async def search(self, query: str) -> list[Product]:
        """Products matching the query, with online stock and price where available."""

    async def search_many(self, queries: list[str]) -> dict[str, list[Product] | Exception]:
        """search() for several queries in one job. A query that failed maps to its exception.

        The default runs search() once per query, one after another, so adapters that don't override
        it make exactly the requests they always did. Adapters whose search re-reads the same pages for
        every query (Shopify's catalogue) override it to read them once.
        """
        results: dict[str, list[Product] | Exception] = {}
        for query in dict.fromkeys(queries):
            try:
                results[query] = await self.search(query)
            except Exception as exc:  # noqa: BLE001 - one keyword's failure mustn't stop the rest
                results[query] = exc
        return results

    @abstractmethod
    async def fetch_products(self, skus: list[str]) -> list[Product]:
        """Current online stock and price for specific products."""

    async def discover(self) -> list[Product]:
        """The retailer's current TCG range, newest first where possible."""
        return []

    def scan_size(self, results: list[Product]) -> int | None:
        """How many products the last discover() parsed off the site, to spot a parser the site broke.

        None when that call didn't read the site (nothing was due yet), so it isn't counted. Adapters
        that pad results (products that left the listings) or vary how much they read override this.
        """
        return sum(1 for p in results if not p.kind)

    @property
    def store_stock_enabled(self) -> bool:
        """Instance-level switch (e.g. Farmers only does store stock when its browser is on)."""
        return self.supports_store_stock

    # True when store_stock() reports stores on its own (e.g. a list of in-stock store ids),
    # so it's worth calling before the store list is known.
    store_stock_discovers_stores: ClassVar[bool] = False

    # True when listings already carry store-level stock (Product.stores), so the store list is
    # synced but no per-product store calls are made.
    stock_in_listings: ClassVar[bool] = False

    # True when store checks are cheap enough to run for every sealed product discovery finds,
    # rather than only those matching a keyword route.
    track_all_discovered: ClassVar[bool] = False

    def store_label(self, store_id: str) -> str:
        """Display name for a store id the store list doesn't know yet."""
        return f"Store {store_id}"

    async def list_stores(self) -> list[Store]:
        return []

    async def store_stock(self, sku: str, store_ids: list[str]) -> dict[str, Stock]:
        raise NotImplementedError

    async def refresh_details(self, product: Product) -> None:
        """Fill in details the cheap listing lacks (e.g. Farmers' price), alongside each store check."""

    def parse_ref(self, ref: str) -> str:
        """Turn a product URL (or a bare SKU) into this retailer's SKU."""
        return ref.strip()

    def matches_url(self, url: str) -> bool:
        return False


def build_adapter(retailer: Any, http: HttpClient) -> RetailerAdapter:
    try:
        cls = REGISTRY[retailer["adapter"]]
    except KeyError:
        raise LookupError(f"no adapter named {retailer['adapter']!r}") from None
    return cls(retailer, http)
