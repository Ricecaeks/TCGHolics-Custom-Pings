from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from typing import Any

from tcgpings.classify import FRANCHISE_NAMES
from tcgpings.db import queries
from tcgpings.engine.keywords import KeywordFilter
from tcgpings.models import ANY_STORE, DEFAULT_EVENT_TYPES, ONLINE, Event, EventType


def route_matches(route: Mapping[str, Any], event: Event) -> bool:
    """NULL filters match anything; store_id '' matches only online events, '*' only store events."""
    if route["retailer_id"] is not None and route["retailer_id"] != event.retailer_id:
        return False
    if route["store_id"] == ANY_STORE:
        if event.store_id == ONLINE:
            return False
    elif route["store_id"] is not None and route["store_id"] != event.store_id:
        return False
    if route["franchise"] is not None and route["franchise"] != event.franchise:
        return False
    if route.get("in_stock_only") and event.type is EventType.NEW_PRODUCT and event.new_level not in ("in", "low"):
        return False  # a new listing that's sold out or unavailable: its restock will alert instead
    allowed = route["event_types"]
    if allowed is None:
        if event.type not in DEFAULT_EVENT_TYPES:
            return False
    elif event.type.value not in allowed:
        return False
    keywords = route.get("keywords")
    return not keywords or KeywordFilter.parse(keywords).matches(event.title)


def keyword_routes_match(routes: Sequence[Mapping[str, Any]], retailer_id: str, title: str) -> bool:
    """Does any keyword route for this retailer want this product? (Decides store-level tracking.)"""
    for r in routes:
        if r["retailer_id"] not in (None, retailer_id) or not r.get("keywords"):
            continue
        if KeywordFilter.parse(r["keywords"]).matches(title):
            return True
    return False


def match_routes(routes: Sequence[Mapping[str, Any]], event: Event) -> list[Mapping[str, Any]]:
    return [r for r in routes if route_matches(r, event)]


def ping_text(event: Event) -> str:
    """What member keywords match: the title, game, retailer and where it's in stock."""
    return " ".join(filter(None, [
        event.title,
        FRANCHISE_NAMES.get(event.franchise or ""),
        event.extra.get("retailer_name"),
        "online" if event.store_id == ONLINE else None,
        *([s["name"] for s in event.stores] or [event.store_name]),
    ]))


def match_member_pings(pings: Sequence[Mapping[str, Any]], event: Event) -> list[dict]:
    """Members to tag, grouped by the keywords they matched on."""
    text = ping_text(event)
    groups: dict[str, list[int]] = {}
    for ping in pings:
        if KeywordFilter.parse(ping["keywords"]).matches(text):
            groups.setdefault(ping["keywords"].lower(), []).append(ping["user_id"])
    return [{"keywords": keywords, "users": users} for keywords, users in groups.items()]


class RouteCache:
    """Routes and member pings change rarely; every node re-reads them at most every `ttl` seconds."""

    def __init__(self, db, ttl: float = 30) -> None:
        self._db = db
        self._ttl = ttl
        self._routes: list = []
        self._pings: list = []
        self._loaded_at = 0.0

    async def get(self) -> list:
        if time.monotonic() - self._loaded_at > self._ttl:
            self._routes = list(await queries.list_routes(self._db))
            self._pings = list(await queries.list_member_pings(self._db))
            self._loaded_at = time.monotonic()
        return self._routes

    async def member_pings(self) -> list:
        await self.get()
        return self._pings

    def invalidate(self) -> None:
        self._loaded_at = 0.0
