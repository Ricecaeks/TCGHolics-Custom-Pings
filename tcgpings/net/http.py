from __future__ import annotations

import asyncio
import logging
import random
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from curl_cffi.requests import AsyncSession, RequestsError, Response

from tcgpings.net.proxies import ProxyPool
from tcgpings.net.ratelimit import DIRECT, RateLimiter

log = logging.getLogger(__name__)

BAN_STATUSES = {403, 429}
BAN_MARKERS = re.compile(
    r"captcha|cf-chl|challenge-platform|access denied|px-block|perimeterx|are you a robot|WAF_Deny_Page", re.I
)
PROXY_BAN_SECONDS = 600


class FetchError(Exception):
    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        # The retailer's own HTTP status when it answered (e.g. 404), None for network/route failures.
        self.status = status


class Blocked(FetchError):
    """The retailer refused the request (bot protection / rate limit)."""


@dataclass(frozen=True)
class NetPolicy:
    retailer_id: str
    requests_per_minute: float = 30
    proxy_policy: str = "direct"

    @classmethod
    def from_row(cls, row: Any) -> NetPolicy:
        return cls(row["id"], row["requests_per_minute"], row["proxy_policy"])


class HttpClient:
    def __init__(
        self,
        proxies: ProxyPool | None = None,
        limiter: RateLimiter | None = None,
        on_ban: Callable[[str], Awaitable[None]] | None = None,
        impersonate: str = "chrome",
    ) -> None:
        self.proxies = proxies or ProxyPool()
        self.limiter = limiter or RateLimiter()
        self._on_ban = on_ban
        self._impersonate = impersonate
        self._session: AsyncSession | None = None
        # Set by the app when browser-backed adapters are available (see net/browser.py), and the
        # fetch chain that falls back from that browser to paid unblockers (net/chain.py).
        self.browser = None
        self.chain = None

    async def __aenter__(self) -> HttpClient:
        return self

    async def __aexit__(self, *exc) -> None:
        await self.close()

    @property
    def session(self) -> AsyncSession:
        if self._session is None:
            self._session = AsyncSession(impersonate=self._impersonate, timeout=20)
        return self._session

    async def close(self) -> None:
        if self.chain is not None:
            await self.chain.close()
        if self.browser is not None:
            await self.browser.close()
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def request(
        self,
        policy: NetPolicy,
        method: str,
        url: str,
        *,
        retries: int = 2,
        ok_statuses: frozenset[int] = frozenset({200}),
        **kwargs: Any,
    ) -> Response:
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            proxy = self.proxies.pick(policy.proxy_policy, policy.retailer_id)
            egress = proxy or DIRECT
            await self.limiter.acquire(policy.retailer_id, egress, policy.requests_per_minute)
            try:
                resp = await self.session.request(
                    method, url, proxies={"http": proxy, "https": proxy} if proxy else None, **kwargs
                )
            except RequestsError as exc:
                last_error = FetchError(f"{method} {url}: {exc}")
            else:
                if self._looks_blocked(resp):
                    last_error = Blocked(f"{method} {url}: HTTP {resp.status_code} (blocked)")
                    if proxy:
                        await self._ban(proxy)
                    elif attempt >= 1:
                        break  # no proxy to rotate to; stop hammering
                elif resp.status_code in ok_statuses:
                    return resp
                elif resp.status_code >= 500:
                    last_error = FetchError(f"{method} {url}: HTTP {resp.status_code}")
                else:
                    raise FetchError(f"{method} {url}: HTTP {resp.status_code}", resp.status_code)
            if attempt < retries:
                await asyncio.sleep(1.5 ** (attempt + 1) + random.random())
        assert last_error is not None
        raise last_error

    async def get(self, policy: NetPolicy, url: str, **kwargs: Any) -> Response:
        return await self.request(policy, "GET", url, **kwargs)

    async def get_json(self, policy: NetPolicy, url: str, **kwargs: Any) -> Any:
        resp = await self.get(policy, url, **kwargs)
        try:
            return resp.json()
        except ValueError as exc:
            raise FetchError(f"GET {url}: response was not JSON") from exc

    @staticmethod
    def _looks_blocked(resp: Response) -> bool:
        if resp.status_code in BAN_STATUSES:
            return True
        content_type = resp.headers.get("content-type", "")
        return "html" in content_type and looks_like_ban_page(resp.text)

    async def _ban(self, proxy: str) -> None:
        log.warning("proxy banned for %ss: %s", PROXY_BAN_SECONDS, _redact(proxy))
        self.proxies.report_ban(proxy, PROXY_BAN_SECONDS)
        if self._on_ban:
            try:
                await self._on_ban(proxy)
            except Exception:
                log.exception("failed to record proxy ban")


def looks_like_ban_page(text: str) -> bool:
    """A small page naming a captcha / WAF denial (real pages are far bigger than 20 kB)."""
    return len(text) < 20_000 and bool(BAN_MARKERS.search(text))


def _redact(url: str) -> str:
    return re.sub(r"//[^@/]+@", "//***@", url)
