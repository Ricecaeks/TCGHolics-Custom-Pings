from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from typing import Any

from tcgpings.db import queries
from tcgpings.models import DEFAULT_EVENT_TYPES, Event


def route_matches(route: Mapping[str, Any], event: Event) -> bool:
    """NULL filters match anything; store_id '' matches only online events."""
    if route["retailer_id"] is not None and route["retailer_id"] != event.retailer_id:
        return False
    if route["store_id"] is not None and route["store_id"] != event.store_id:
        return False
    if route["franchise"] is not None and route["franchise"] != event.franchise:
        return False
    allowed = route["event_types"]
    if allowed is None:
        return event.type in DEFAULT_EVENT_TYPES
    return event.type.value in allowed


def match_routes(routes: Sequence[Mapping[str, Any]], event: Event) -> list[Mapping[str, Any]]:
    return [r for r in routes if route_matches(r, event)]


class RouteCache:
    """Routes change rarely; every node re-reads them at most every `ttl` seconds."""

    def __init__(self, db, ttl: float = 30) -> None:
        self._db = db
        self._ttl = ttl
        self._routes: list = []
        self._loaded_at = 0.0

    async def get(self) -> list:
        if time.monotonic() - self._loaded_at > self._ttl:
            self._routes = list(await queries.list_routes(self._db))
            self._loaded_at = time.monotonic()
        return self._routes

    def invalidate(self) -> None:
        self._loaded_at = 0.0
