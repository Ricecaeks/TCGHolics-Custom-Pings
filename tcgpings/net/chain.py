"""Self-healing fetch chain for sites behind bot protection: our own Chrome first, paid unblockers after.

Each request tries the retailer's routes in order (e.g. browser -> scrapfly -> zyte) and returns
the first answer. Every (retailer, route) pair has a circuit breaker, stored in Postgres so all
nodes share it and it survives restarts:

- Blocked by the site: the route rests (24 h for the browser, 1 h for an unblocker), then gets
  tried again on its own. Nobody has to re-seed anything; the next route covers the gap.
- The service itself failing (bad key, out of credit, throttled): rests for as long as the
  backend says.
- Network errors: 3 in a row rest the route for 30 minutes.
- The retailer answering with an error (e.g. 404) is a real answer: it's raised, not retried.

Paid routes count their spend per calendar month. Past `budget_usd` they're skipped until the
next month; past `low_ratio` of it, `budget_low()` lets adapters cut back (Farmers checks fewer regions).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Protocol

from tcgpings.db import queries
from tcgpings.net.http import Blocked, FetchError, NetPolicy
from tcgpings.net.ratelimit import RateLimiter
from tcgpings.net.unblock import ProviderError

log = logging.getLogger(__name__)

FAILURES_TO_OPEN = 3
FAILURE_COOLDOWN = 30 * 60


class Backend(Protocol):
    name: str
    paid: bool

    async def fetch(self, policy: NetPolicy, origin: str, url: str, headers: dict | None) -> tuple[str, float]: ...


class BrowserBackend:
    """Our own Chrome (net/browser.py): free, but Akamai may refuse it for a while."""

    name = "browser"
    paid = False

    def __init__(self, fetcher: Any) -> None:
        self.fetcher = fetcher

    async def fetch(self, policy: NetPolicy, origin: str, url: str, headers: dict | None) -> tuple[str, float]:
        return await self.fetcher.fetch_text(policy, origin, url, headers), 0.0


class ChainStore(Protocol):
    async def is_open(self, retailer_id: str, backend: str) -> bool: ...
    async def trip(self, retailer_id: str, backend: str, seconds: float, error: str) -> None: ...
    async def failure(self, retailer_id: str, backend: str, error: str) -> None: ...
    async def ok(self, retailer_id: str, backend: str) -> None: ...
    async def spend(self, backend: str, usd: float) -> None: ...
    async def month_spend(self) -> float: ...


class DbChainStore:
    def __init__(self, pool: Any) -> None:
        self.pool = pool

    async def is_open(self, retailer_id: str, backend: str) -> bool:
        return await queries.breaker_open(self.pool, retailer_id, backend)

    async def trip(self, retailer_id: str, backend: str, seconds: float, error: str) -> None:
        await queries.trip_breaker(self.pool, retailer_id, backend, seconds, error)

    async def failure(self, retailer_id: str, backend: str, error: str) -> None:
        await queries.breaker_failure(self.pool, retailer_id, backend, error, FAILURES_TO_OPEN, FAILURE_COOLDOWN)

    async def ok(self, retailer_id: str, backend: str) -> None:
        await queries.breaker_ok(self.pool, retailer_id, backend)

    async def spend(self, backend: str, usd: float) -> None:
        await queries.add_spend(self.pool, backend, usd)

    async def month_spend(self) -> float:
        return await queries.month_spend(self.pool)


class MemoryChainStore:
    """Breakers and spend kept in this process only (probe command, tests)."""

    def __init__(self) -> None:
        self.open_until: dict[tuple[str, str], float] = {}
        self.failures: dict[tuple[str, str], int] = {}
        self.spent: dict[str, float] = {}

    async def is_open(self, retailer_id: str, backend: str) -> bool:
        return self.open_until.get((retailer_id, backend), 0) > time.time()

    async def trip(self, retailer_id: str, backend: str, seconds: float, error: str) -> None:
        self.open_until[(retailer_id, backend)] = time.time() + seconds
        self.failures[(retailer_id, backend)] = 0

    async def failure(self, retailer_id: str, backend: str, error: str) -> None:
        key = (retailer_id, backend)
        self.failures[key] = self.failures.get(key, 0) + 1
        if self.failures[key] >= FAILURES_TO_OPEN:
            await self.trip(retailer_id, backend, FAILURE_COOLDOWN, error)

    async def ok(self, retailer_id: str, backend: str) -> None:
        self.open_until.pop((retailer_id, backend), None)
        self.failures.pop((retailer_id, backend), None)

    async def spend(self, backend: str, usd: float) -> None:
        self.spent[backend] = self.spent.get(backend, 0.0) + usd

    async def month_spend(self) -> float:
        return sum(self.spent.values())


@dataclass
class Cooldowns:
    browser_blocked: int = 24 * 3600
    unblocker_blocked: int = 3600


class FetchChain:
    def __init__(
        self,
        backends: list[Backend],
        store: ChainStore,
        limiter: RateLimiter | None = None,
        budget_usd: float = 20.0,
        low_ratio: float = 0.8,
        cooldowns: Cooldowns | None = None,
    ) -> None:
        self.backends = {b.name: b for b in backends}
        self.store = store
        self.limiter = limiter or RateLimiter()
        self.budget_usd = budget_usd
        self.low_ratio = low_ratio
        self.cooldowns = cooldowns or Cooldowns()

    def available(self, order: list[str]) -> list[str]:
        """The routes in `order` this node can actually use (an unblocker needs its API key set)."""
        return [name for name in order if name in self.backends]

    async def budget_used(self) -> float:
        """Fraction of this month's unblocker budget spent (0 when no budget is set)."""
        if self.budget_usd <= 0:
            return 0.0
        return await self.store.month_spend() / self.budget_usd

    async def budget_low(self) -> bool:
        return await self.budget_used() >= self.low_ratio

    async def fetch_text(
        self, policy: NetPolicy, origin: str, url: str, headers: dict | None = None, order: list[str] | None = None
    ) -> str:
        routes = self.available(order or list(self.backends))
        if not routes:
            raise FetchError(f"{policy.retailer_id}: no fetch route configured (browser or unblocker key)")
        skipped: list[str] = []
        rid = policy.retailer_id
        for name in routes:
            backend = self.backends[name]
            if await self.store.is_open(rid, name):
                skipped.append(f"{name} resting")
                continue
            if backend.paid and self.budget_usd > 0 and await self.store.month_spend() >= self.budget_usd:
                skipped.append(f"{name} over monthly budget")
                continue
            if backend.paid:
                await self.limiter.acquire(rid, name, policy.requests_per_minute)
            try:
                text, cost = await backend.fetch(policy, origin, url, headers)
            except Blocked as exc:
                rest = self.cooldowns.unblocker_blocked if backend.paid else self.cooldowns.browser_blocked
                log.warning("%s: %s blocked, resting it %d min: %s", rid, name, rest // 60, exc)
                await self.store.trip(rid, name, rest, str(exc)[:500])
                skipped.append(f"{name} blocked")
                continue
            except ProviderError as exc:
                log.warning("%s: %s unavailable, resting it %d min: %s", rid, name, exc.cooldown // 60, exc)
                await self.store.trip(rid, name, exc.cooldown, str(exc)[:500])
                skipped.append(f"{name} unavailable")
                continue
            except FetchError as exc:
                if exc.status is not None:  # the retailer answered (404...): that's the result
                    await self.store.ok(rid, name)
                    raise
                log.warning("%s: %s failed: %s", rid, name, exc)
                await self.store.failure(rid, name, str(exc)[:500])
                skipped.append(f"{name} failed")
                continue
            await self.store.ok(rid, name)
            if cost:
                await self.store.spend(name, cost)
            if name != routes[0]:
                log.info("%s: served by %s (%s)", rid, name, ", ".join(skipped))
            return text
        raise Blocked(f"GET {url}: no route got through ({', '.join(skipped)})")

    async def close(self) -> None:
        for backend in self.backends.values():
            close = getattr(backend, "close", None)
            if close and not isinstance(backend, BrowserBackend):  # the browser closes with HttpClient
                await close()
