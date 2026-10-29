from __future__ import annotations

from abc import ABC, abstractmethod
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
    # Retailer rows created automatically at startup: (id, name, config, color).
    default_retailers: ClassVar[list[tuple[str, str, dict, int | None]]] = []

    def __init__(self, retailer: Any, http: HttpClient) -> None:
        self.retailer_id: str = retailer["id"]
        self.name: str = retailer["name"]
        self.config: dict = dict(retailer["config"] or {})
        self.policy = NetPolicy.from_row(retailer)
        self.http = http

    @abstractmethod
    async def search(self, query: str) -> list[Product]:
        """Products matching the query, with online stock and price where available."""

    @abstractmethod
    async def fetch_products(self, skus: list[str]) -> list[Product]:
        """Current online stock and price for specific products."""

    async def list_stores(self) -> list[Store]:
        return []

    async def store_stock(self, sku: str, store_ids: list[str]) -> dict[str, Stock]:
        raise NotImplementedError

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
