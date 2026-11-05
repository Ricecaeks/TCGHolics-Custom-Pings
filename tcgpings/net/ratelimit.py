import asyncio
import time

DIRECT = "direct"


class RateLimiter:
    """Spaces requests per (retailer, egress) so the whole cluster stays under a retailer's budget.

    Nodes sharing an egress (same public IP, or the same proxy pool) split the budget between
    them; `set_shares` is fed from the heartbeat table. Only nodes that fetch from a retailer (those
    serving its worker lane) share its budget, so a retailer can get its own shares; the rest use the
    defaults.
    """

    def __init__(self) -> None:
        self._next: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._direct_share = 1
        self._proxy_share = 1
        self._retailer_shares: dict[str, tuple[int, int]] = {}

    def set_shares(self, direct: int, proxy: int, retailers: dict[str, tuple[int, int]] | None = None) -> None:
        """`direct`/`proxy`: how many nodes share this node's IP / the cluster's other egresses.
        `retailers`: the same pair per retailer id, counting only the nodes that serve its lane."""
        self._direct_share = max(direct, 1)
        self._proxy_share = max(proxy, 1)
        self._retailer_shares = {rid: (max(d, 1), max(p, 1)) for rid, (d, p) in (retailers or {}).items()}

    def share(self, egress: str, retailer_id: str | None = None) -> int:
        direct, proxy = self._retailer_shares.get(retailer_id or "", (self._direct_share, self._proxy_share))
        return direct if egress == DIRECT else proxy

    def interval(self, egress: str, per_minute: float, retailer_id: str | None = None) -> float:
        return 60.0 * self.share(egress, retailer_id) / max(per_minute, 0.1)

    async def acquire(self, retailer_id: str, egress: str, per_minute: float) -> None:
        key = f"{retailer_id}|{egress}"
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            now = time.monotonic()
            slot = max(now, self._next.get(key, now))
            self._next[key] = slot + self.interval(egress, per_minute, retailer_id)
        if (wait := slot - now) > 0:
            await asyncio.sleep(wait)
