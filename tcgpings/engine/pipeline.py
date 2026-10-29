"""Records fetched products, diffs them against the stored state and queues alerts.

State update and alert enqueue happen in one transaction per product, so a change is
alerted exactly once even if two nodes observe it at the same moment.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import asyncpg

from tcgpings.classify import classify
from tcgpings.db import queries
from tcgpings.engine.diff import diff_state, new_product_event
from tcgpings.engine.router import RouteCache, match_routes
from tcgpings.models import ONLINE, Event, Level, Product, Stock

log = logging.getLogger(__name__)


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
        events: list[Event] = []
        async with self.pool.acquire() as conn, conn.transaction():
            is_new = await queries.upsert_product(conn, product)
            if is_new and announce_new:
                events.append(new_product_event(product))

            if product.online and product.online.level is not Level.UNKNOWN:
                prev = await queries.apply_state(
                    conn, product.retailer_id, product.sku, ONLINE, product.online, product.price_cents
                )
                events += diff_state(product, ONLINE, None, prev, product.online, product.price_cents)

            for store_id, stock in (store_stock or {}).items():
                if stock.level is Level.UNKNOWN:
                    continue
                prev = await queries.apply_state(conn, product.retailer_id, product.sku, store_id, stock, None)
                name = (store_names or {}).get(store_id, store_id)
                events += diff_state(product, store_id, name, prev, stock, None)

            if events:
                await self._enqueue(conn, retailer, events)
        return events

    async def _enqueue(self, conn: asyncpg.Connection, retailer: Any, events: list[Event]) -> None:
        routes = await self.routes.get()
        bucket = int(time.time() // self.cooldown)
        for event in events:
            event.extra.update(retailer_name=retailer["name"], retailer_color=retailer["color"])
            matched = match_routes(routes, event)
            if not matched:
                log.debug("no route for %s %s %s", event.type, event.retailer_id, event.store_id or "online")
            payload = event.to_payload()
            for route in matched:
                await queries.enqueue_alert(conn, f"{event.dedupe_key(bucket)}#{route['id']}", route["id"], payload)
