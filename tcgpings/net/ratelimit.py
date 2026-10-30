import asyncio
import time

DIRECT = "direct"


class RateLimiter:
    """Spaces requests per (retailer, egress) so the whole cluster stays under a retailer's budget.

    Nodes sharing an egress (same public IP, or the same proxy pool) split the budget between
    them; `set_shares` is fed from the heartbeat table.
    """

    def __init__(self) -> None:
        self._next: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._direct_share = 1
        self._proxy_share = 1

    def set_shares(self, direct: int, proxy: int) -> None:
        self._direct_share = max(direct, 1)
        self._proxy_share = max(proxy, 1)

    def interval(self, egress: str, per_minute: float) -> float:
        share = self._direct_share if egress == DIRECT else self._proxy_share
        return 60.0 * share / max(per_minute, 0.1)

    async def acquire(self, retailer_id: str, egress: str, per_minute: float) -> None:
        key = f"{retailer_id}|{egress}"
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            now = time.monotonic()
            slot = max(now, self._next.get(key, now))
            self._next[key] = slot + self.interval(egress, per_minute)
        if (wait := slot - now) > 0:
            await asyncio.sleep(wait)
