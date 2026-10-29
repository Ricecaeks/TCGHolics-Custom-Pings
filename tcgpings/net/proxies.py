import itertools
import time
import zlib


class ProxyPool:
    """Proxy URLs from env + the `proxies` table, with local ban cooldowns."""

    def __init__(self, urls: list[str] | None = None) -> None:
        self._urls: list[str] = list(dict.fromkeys(urls or []))
        self._cooldown: dict[str, float] = {}
        self._rr = itertools.count()

    def update(self, urls: list[str], cooldowns: dict[str, float] | None = None) -> None:
        """cooldowns: url -> seconds remaining (from the DB, set by any node)."""
        self._urls = list(dict.fromkeys(urls))
        now = time.monotonic()
        for url, remaining in (cooldowns or {}).items():
            self._cooldown[url] = max(self._cooldown.get(url, 0), now + remaining)

    @property
    def urls(self) -> list[str]:
        return list(self._urls)

    def healthy(self) -> list[str]:
        now = time.monotonic()
        return [u for u in self._urls if self._cooldown.get(u, 0) <= now]

    def pick(self, policy: str, key: str) -> str | None:
        """None means connect directly."""
        if policy == "direct":
            return None
        candidates = self.healthy()
        if not candidates:
            return None
        if policy == "sticky":
            return candidates[zlib.crc32(key.encode()) % len(candidates)]
        return candidates[next(self._rr) % len(candidates)]

    def report_ban(self, url: str, seconds: float) -> None:
        self._cooldown[url] = time.monotonic() + seconds
