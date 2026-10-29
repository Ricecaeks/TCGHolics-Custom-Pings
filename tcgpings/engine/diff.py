"""Turns (previous state, new state) into alert events. Pure functions, no I/O."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from tcgpings.models import ONLINE, Event, EventType, Level, Product, Stock


def _event(kind: EventType, product: Product, store_id: str, store_name: str | None, **kw: Any) -> Event:
    return Event(
        type=kind,
        retailer_id=product.retailer_id,
        sku=product.sku,
        title=product.title,
        url=product.url,
        image=product.image,
        franchise=product.franchise,
        ptype=product.ptype,
        store_id=store_id,
        store_name=store_name,
        **kw,
    )


def new_product_event(product: Product) -> Event:
    online = product.online
    return _event(
        EventType.NEW_PRODUCT, product, ONLINE, None,
        new_level=online.level.value if online else None,
        new_qty=online.qty if online else None,
        new_price=product.price_cents,
    )


def diff_state(
    product: Product,
    store_id: str,
    store_name: str | None,
    prev: Mapping[str, Any] | None,
    new: Stock,
    new_price: int | None,
) -> list[Event]:
    """Events for one product at one location.

    - First observation is a silent baseline (adding a watch doesn't flood channels).
    - Quantity alerts fire on increases, or when the level moves between LOW and IN;
      a shelf selling down 12 -> 11 -> 10 stays quiet.
    - Price changes are only tracked for the online state.
    """
    if prev is None or new.level is Level.UNKNOWN:
        return []

    old = Stock(Level(prev["level"]), prev["qty"])
    old_price = prev["price_cents"]
    state = dict(
        old_level=old.level.value, new_level=new.level.value,
        old_qty=old.qty, new_qty=new.qty,
        old_price=old_price, new_price=new_price if new_price is not None else old_price,
    )
    events: list[Event] = []

    if not old.level.available and new.level.available:
        events.append(_event(EventType.RESTOCK, product, store_id, store_name, **state))
    elif old.level.available and not new.level.available and new.level is Level.OUT:
        events.append(_event(EventType.OUT_OF_STOCK, product, store_id, store_name, **state))
    elif old.level.available and new.level.available:
        qty_up = old.qty is not None and new.qty is not None and new.qty > old.qty
        if qty_up or old.level != new.level:
            events.append(_event(EventType.QTY_CHANGE, product, store_id, store_name, **state))

    if (
        store_id == ONLINE
        and old_price is not None
        and new_price is not None
        and new_price != old_price
    ):
        events.append(_event(EventType.PRICE_CHANGE, product, store_id, store_name, **state))

    return events
