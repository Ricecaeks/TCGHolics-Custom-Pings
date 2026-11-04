"""Records fetched products, diffs them against the stored state and queues alerts.

State update and alert enqueue happen in one transaction per product, so a change is
alerted exactly once even if two nodes observe it at the same moment.
"""

from __future__ import annotations

import logging
import time
import zlib
from typing import Any

import asyncpg

from tcgpings.classify import classify, is_single_card
from tcgpings.db import queries
from tcgpings.engine.diff import diff_state, first_store_stock_event, new_product_event
from tcgpings.engine.router import RouteCache, match_member_pings, match_routes
from tcgpings.models import ANY_STORE, ONLINE, Event, EventType, Level, Product, Stock

log = logging.getLogger(__name__)

# A product announced as a new listing this recently alerts on its first in-store reading too. Store checks
# can come hours after discovery (JB Hi-Fi, Toyworld), and a new drop is often in-store only (Kmart).
NEW_DROP_SECONDS = 24 * 3600


def classify_product(product: Product) -> Product:
    if product.franchise is None or product.ptype is None:
        franchise, ptype = classify(product.title)
        product.franchise = product.franchise or franchise
        product.ptype = product.ptype or ptype
    return product


class Pipeline:
    def __init__(self, pool: asyncpg.Pool, routes: RouteCache, cooldown_seconds: int) -> None:
        self.pool = pool
        self.routes = routes
        self.cooldown = max(cooldown_seconds, 1)

    async def record(
        self,
        retailer: Any,
        product: Product,
        store_stock: dict[str, Stock] | None = None,
        store_names: dict[str, str] | None = None,
        announce_new: bool = False,
    ) -> list[Event]:
        classify_product(product)
        if product.kind == "queue":
            return await self._record_queue(retailer, product)
        events: list[Event] = []
        async with self.pool.acquire() as conn, conn.transaction():
            is_new = await queries.upsert_product(conn, product)
            announced: bool | None = None  # looked up only when a store reports stock for the first time
            if is_new and announce_new:
                events.append(new_product_event(product))
                await queries.mark_announced(conn, product.retailer_id, product.sku)
                announced = True

            if product.online and product.online.level is not Level.UNKNOWN:
                prev = await queries.apply_state(
                    conn, product.retailer_id, product.sku, ONLINE, product.online, product.price_cents
                )
                changes = diff_state(product, ONLINE, None, prev, product.online, product.price_cents)
                # Single cards reprice constantly: the change is recorded, but not worth an alert.
                events += [e for e in changes if not (e.type is EventType.PRICE_CHANGE and is_single_card(product.title))]

            for store_id, stock in (store_stock or {}).items():
                if stock.level is Level.UNKNOWN:
                    continue
                prev = await queries.apply_state(conn, product.retailer_id, product.sku, store_id, stock, None)
                name = (store_names or {}).get(store_id, store_id)
                if prev is None and stock.level.available:
                    # A first reading is normally a silent baseline (a new watch or retailer doesn't flood
                    # channels), but not for a product just announced as new: that's a drop on the shelf.
                    if announced is None:
                        announced = await queries.announced_within(
                            conn, product.retailer_id, product.sku, NEW_DROP_SECONDS)
                    if announced:
                        events.append(first_store_stock_event(product, store_id, name, stock))
                    continue
                events += diff_state(product, store_id, name, prev, stock, None)

            if events:
                await self._enqueue(conn, retailer, events)
        return events

    async def _record_queue(self, retailer: Any, product: Product) -> list[Event]:
        """A shop's waiting room, kept as a status row: alert when it turns on (IN), quietly note when it's off."""
        events: list[Event] = []
        async with self.pool.acquire() as conn, conn.transaction():
            await queries.upsert_product(conn, product)
            prev = await queries.apply_state(conn, product.retailer_id, product.sku, ONLINE, product.online, None)
            changes = diff_state(product, ONLINE, None, prev, product.online, None)
            for event in changes:
                if event.type is EventType.RESTOCK:
                    event.type = EventType.QUEUE
                    events.append(event)
            if events:
                await self._enqueue(conn, retailer, events)
        return events

    async def report(self, retailer: Any, event: Event) -> int:
        """Queue an event nobody observed through a stock check. Returns how many alerts were queued."""
        async with self.pool.acquire() as conn, conn.transaction():
            return await self._enqueue(conn, retailer, [event])

    async def _enqueue(self, conn: asyncpg.Connection, retailer: Any, events: list[Event]) -> int:
        queued = 0
        routes = await self.routes.get()
        bucket = int(time.time() // self.cooldown)
        per_route: dict[int, tuple[Any, list[Event]]] = {}
        for event in events:
            event.extra.update(retailer_name=retailer["name"], retailer_color=retailer["color"])
            if is_overseas(retailer):
                event.extra["overseas"] = True
            matched = match_routes(routes, event)
            if not matched:
                log.debug("no route for %s %s %s", event.type, event.retailer_id, event.store_id or "online")
            for route in matched:
                per_route.setdefault(route["id"], (route, []))[1].append(event)

        for route_id, (route, route_events) in per_route.items():
            # A channel covering a retailer's stores (#kmart-instore, or the whole retailer) gets one
            # alert listing the stores, not one alert per store. Single-store routes keep theirs.
            merge = route["store_id"] is None or route["store_id"] == ANY_STORE
            outgoing = merge_store_events(route_events) if merge else route_events
            for event in outgoing:
                payload = event.to_payload()
                if route.get("member_pings"):
                    payload["extra"]["pings"] = match_member_pings(await self.routes.member_pings(), event)
                    if not payload["extra"]["pings"]:
                        continue
                key = f"{event.dedupe_key(bucket)}#{route_id}"
                queued += await queries.enqueue_alert(conn, key, route_id, payload)
        return queued


def is_overseas(retailer: Any) -> bool:
    """A store outside NZ (Pokémon Center AU/UK): its alerts only reach channels that name it."""
    try:
        config = retailer["config"]
    except (KeyError, TypeError):
        return False
    return bool(isinstance(config, dict) and config.get("overseas"))


def merge_store_events(events: list[Event]) -> list[Event]:
    """Collapse store-level events of the same type for one product into a single event."""
    out: list[Event] = []
    groups: dict[tuple, list[Event]] = {}
    for e in events:
        if e.store_id == ONLINE:
            out.append(e)
        else:
            groups.setdefault((e.type, e.retailer_id, e.sku), []).append(e)
    for group in groups.values():
        if len(group) == 1:
            out.append(group[0])
            continue
        group.sort(key=lambda e: e.store_name or e.store_id)
        first = group[0]
        ids = ",".join(e.store_id for e in group)
        merged = Event.from_payload(first.to_payload())
        merged.store_id = f"*{zlib.crc32(ids.encode()):08x}"
        merged.store_name = f"{len(group)} stores"
        merged.stores = [{"id": e.store_id, "name": e.store_name or e.store_id, "qty": e.new_qty} for e in group]
        out.append(merged)
    return out
