from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from enum import StrEnum

ONLINE = ""  # store_id used for a product's online (non-store) state
ANY_STORE = "*"  # route store_id: every physical store, no online alerts (#kmart-instore)


class Level(StrEnum):
    OUT = "out"
    LOW = "low"
    IN = "in"
    UNKNOWN = "unknown"

    @property
    def available(self) -> bool:
        return self in (Level.LOW, Level.IN)


@dataclass(frozen=True)
class Stock:
    level: Level
    qty: int | None = None

    def describe(self) -> str:
        if self.qty is not None:
            return f"{self.qty} ({self.level.value})" if self.level is Level.LOW else str(self.qty)
        return {Level.OUT: "Out of stock", Level.LOW: "Low stock", Level.IN: "In stock"}.get(
            self.level, "Unknown"
        )


@dataclass
class Product:
    retailer_id: str
    sku: str
    title: str
    url: str
    image: str | None = None
    price_cents: int | None = None
    online: Stock | None = None
    franchise: str | None = None
    ptype: str | None = None
    atc_url: str | None = None  # direct add-to-cart link, when the retailer supports one
    # Store-level stock that comes with the listing itself (Kmart's per-island flags), store_id -> stock.
    stores: dict[str, Stock] | None = None
    note: str | None = None  # shown on alerts, e.g. "In-store only"


@dataclass(frozen=True)
class Store:
    retailer_id: str
    store_id: str
    name: str
    region: str | None = None

    @property
    def slug(self) -> str:
        return slugify(self.name)


class EventType(StrEnum):
    NEW_PRODUCT = "new_product"
    RESTOCK = "restock"
    OUT_OF_STOCK = "out_of_stock"
    QTY_CHANGE = "qty_change"
    PRICE_CHANGE = "price_change"


# Out-of-stock alerts are opt-in per route; everything else is on by default.
DEFAULT_EVENT_TYPES = frozenset(EventType) - {EventType.OUT_OF_STOCK}


@dataclass
class Event:
    type: EventType
    retailer_id: str
    sku: str
    title: str
    url: str
    store_id: str = ONLINE
    store_name: str | None = None
    image: str | None = None
    franchise: str | None = None
    ptype: str | None = None
    old_level: str | None = None
    new_level: str | None = None
    old_qty: int | None = None
    new_qty: int | None = None
    old_price: int | None = None
    new_price: int | None = None
    atc_url: str | None = None
    # Store-level events merged into one alert: [{"id": ..., "name": ...}, ...]
    stores: list = field(default_factory=list)
    extra: dict = field(default_factory=dict)

    def to_payload(self) -> dict:
        data = asdict(self)
        data["type"] = self.type.value
        return data

    @classmethod
    def from_payload(cls, data: dict) -> Event:
        data = dict(data)
        data["type"] = EventType(data["type"])
        known = cls.__dataclass_fields__.keys()
        return cls(**{k: v for k, v in data.items() if k in known})

    def dedupe_key(self, bucket: int) -> str:
        state = f"{self.new_level}:{self.new_qty}:{self.new_price}"
        return f"{self.retailer_id}|{self.sku}|{self.store_id}|{self.type.value}|{state}|{bucket}"


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def to_cents(value) -> int | None:
    """'12.99', 12.99, '$1,299.00' -> cents. Returns None when unparseable."""
    if value is None:
        return None
    if isinstance(value, int):
        return value * 100
    text = re.sub(r"[^\d.]", "", str(value))
    if not text:
        return None
    try:
        return round(float(text) * 100)
    except ValueError:
        return None


def format_price(cents: int | None) -> str:
    return "—" if cents is None else f"${cents / 100:,.2f}"
