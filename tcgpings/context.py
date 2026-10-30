from __future__ import annotations

import time
from dataclasses import dataclass, field

import asyncpg

from tcgpings.config import Settings
from tcgpings.db import queries
from tcgpings.engine.pipeline import Pipeline
from tcgpings.engine.router import RouteCache
from tcgpings.net.http import HttpClient
from tcgpings.retailers import RetailerAdapter, build_adapter


@dataclass
class Stats:
    jobs_ok: int = 0
    jobs_failed: int = 0
    alerts_sent: int = 0


class AdapterCache:
    """Adapter instances per retailer row, rebuilt when the row changes (config, rate, proxy policy)."""

    def __init__(self, pool: asyncpg.Pool, http: HttpClient, ttl: float = 60) -> None:
        self._pool = pool
        self._http = http
        self._ttl = ttl
        self._rows: dict[str, asyncpg.Record] = {}
        self._adapters: dict[str, tuple[asyncpg.Record, RetailerAdapter]] = {}
        self._loaded_at = 0.0

    async def refresh(self, force: bool = False) -> None:
        if force or time.monotonic() - self._loaded_at > self._ttl:
            self._rows = {r["id"]: r for r in await queries.list_retailers(self._pool)}
            self._loaded_at = time.monotonic()

    async def retailer(self, retailer_id: str) -> asyncpg.Record:
        await self.refresh()
        if retailer_id not in self._rows:
            await self.refresh(force=True)
        return self._rows[retailer_id]

    async def get(self, retailer_id: str) -> RetailerAdapter:
        row = await self.retailer(retailer_id)
        cached = self._adapters.get(retailer_id)
        if cached is None or dict(cached[0]) != dict(row):
            cached = (row, build_adapter(row, self._http))
            self._adapters[retailer_id] = cached
        return cached[1]

    async def all(self) -> list[asyncpg.Record]:
        await self.refresh()
        return list(self._rows.values())


@dataclass
class Context:
    settings: Settings
    pool: asyncpg.Pool
    http: HttpClient
    adapters: AdapterCache
    routes: RouteCache
    pipeline: Pipeline
    node_name: str
    stats: Stats = field(default_factory=Stats)
    egress_ip: str | None = None
    is_leader: bool = False
