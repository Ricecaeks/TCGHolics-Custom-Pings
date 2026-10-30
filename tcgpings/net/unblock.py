"""Paid unblocker APIs: the fallback when our own Chrome is denied by a site's bot protection.

Each backend fetches one URL and returns (body, cost in USD). They raise:
- Blocked:       the unblocker couldn't get past the site either (not billed by either service).
- ProviderError: a problem with the service itself (bad key, out of credit, throttled).
- FetchError:    with `status` set when the retailer answered (e.g. 404), else a network failure.

ScrapFly (https://scrapfly.io/docs/scrape-api/getting-started)
    GET api.scrapfly.io/scrape?key=..&url=..&unblocker=true&country=nz&session=..&proxified_response=true
    The body and status are the retailer's own; failures carry X-Scrapfly-Reject-Code. The cost in
    credits is in X-Scrapfly-Api-Cost. A session keeps cookies and the exit IP for 7 days, so the
    anti-bot clearance is earned once and reused; one session can't be used concurrently.
Zyte API (https://docs.zyte.com/zyte-api/usage/http.html)
    POST api.zyte.com/v1/extract {"url", "httpResponseBody": true}, API key as the basic-auth user.
    The retailer's status is in `statusCode`; 520/521 mean Zyte was banned. Only successful
    responses are billed, but no cost comes back, so it's estimated from `usd_per_request`.
"""

from __future__ import annotations

import asyncio
import base64
from typing import Any

from curl_cffi.requests import AsyncSession, RequestsError

from tcgpings.net.http import Blocked, FetchError, NetPolicy, looks_like_ban_page

SCRAPFLY_URL = "https://api.scrapfly.io/scrape"
ZYTE_URL = "https://api.zyte.com/v1/extract"
TIMEOUT = 160  # ScrapFly's own read timeout is 155 s


class ProviderError(FetchError):
    """The unblocker service itself failed; `cooldown` is how long to stop using it."""

    def __init__(self, message: str, cooldown: int) -> None:
        super().__init__(message)
        self.cooldown = cooldown


def _check_target(url: str, status: int, text: str) -> str:
    if status in (403, 429) or looks_like_ban_page(text):
        raise Blocked(f"GET {url}: HTTP {status} (blocked)")
    if status != 200:
        raise FetchError(f"GET {url}: HTTP {status}", status)
    return text


class ScrapFlyBackend:
    name = "scrapfly"
    paid = True

    def __init__(self, api_key: str, country: str = "nz", usd_per_credit: float = 0.00015,
                 cost_budget: int = 0, node_name: str = "node", session: Any = None) -> None:
        self.api_key = api_key
        self.country = country
        self.usd_per_credit = usd_per_credit
        self.cost_budget = cost_budget
        self.node_name = node_name
        self._session = session
        # One ScrapFly session per retailer and node, used by one request at a time.
        self._locks: dict[str, asyncio.Lock] = {}

    @property
    def session(self) -> Any:
        if self._session is None:
            self._session = AsyncSession(timeout=TIMEOUT)
        return self._session

    def params(self, policy: NetPolicy, url: str, headers: dict | None) -> dict[str, str]:
        params = {
            "key": self.api_key, "url": url, "unblocker": "true", "proxified_response": "true",
            "session": f"tcgpings-{self.node_name}-{policy.retailer_id}",
        }
        if self.country:
            params["country"] = self.country
        if self.cost_budget:
            params["cost_budget"] = str(self.cost_budget)
        for name, value in (headers or {}).items():
            params[f"headers[{name}]"] = value
        return params

    async def fetch(self, policy: NetPolicy, origin: str, url: str, headers: dict | None) -> tuple[str, float]:
        lock = self._locks.setdefault(policy.retailer_id, asyncio.Lock())
        async with lock:
            try:
                resp = await self.session.get(SCRAPFLY_URL, params=self.params(policy, url, headers))
            except RequestsError as exc:
                raise FetchError(f"scrapfly: {exc}") from exc
        cost = float(resp.headers.get("x-scrapfly-api-cost") or 0) * self.usd_per_credit
        reject = resp.headers.get("x-scrapfly-reject-code")
        if reject:
            raise self._reject_error(resp.status_code, reject)
        return _check_target(url, resp.status_code, resp.text), cost

    @staticmethod
    def _reject_error(status: int, code: str) -> FetchError:
        message = f"scrapfly: HTTP {status} {code}"
        if status in (401, 402, 403):
            return ProviderError(message, cooldown=24 * 3600)  # key, payment or plan problem
        if status == 429:
            return ProviderError(message, cooldown=600)  # quota, concurrency or throttler limit
        if status == 422:
            return Blocked(message)  # the scrape itself failed (anti-bot, proxy); not billed
        return FetchError(message)

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()


class ZyteBackend:
    name = "zyte"
    paid = True

    def __init__(self, api_key: str, geolocation: str = "", usd_per_request: float = 0.00127,
                 session: Any = None) -> None:
        self.api_key = api_key
        self.geolocation = geolocation
        self.usd_per_request = usd_per_request
        self._session = session

    @property
    def session(self) -> Any:
        if self._session is None:
            self._session = AsyncSession(timeout=TIMEOUT)
        return self._session

    def body(self, url: str, headers: dict | None) -> dict[str, Any]:
        body: dict[str, Any] = {"url": url, "httpResponseBody": True}
        if headers:
            body["customHttpRequestHeaders"] = [{"name": k, "value": v} for k, v in headers.items()]
        if self.geolocation:
            body["geolocation"] = self.geolocation.upper()
        return body

    async def fetch(self, policy: NetPolicy, origin: str, url: str, headers: dict | None) -> tuple[str, float]:
        try:
            resp = await self.session.post(ZYTE_URL, json=self.body(url, headers), auth=(self.api_key, ""))
        except RequestsError as exc:
            raise FetchError(f"zyte: {exc}") from exc
        status = resp.status_code
        if status != 200:
            message = f"zyte: HTTP {status} {_zyte_type(resp)}"
            if status in (520, 521):
                raise Blocked(message)
            if status in (401, 403):
                raise ProviderError(message, cooldown=24 * 3600)
            if status == 451:
                raise ProviderError(message, cooldown=7 * 24 * 3600)  # Zyte won't fetch this site
            if status in (429, 503):
                raise ProviderError(message, cooldown=600)
            raise FetchError(message)
        data = resp.json()
        text = base64.b64decode(data.get("httpResponseBody") or "").decode("utf-8", errors="replace")
        return _check_target(url, int(data.get("statusCode") or 200), text), self.usd_per_request

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()


def _zyte_type(resp: Any) -> str:
    try:
        return str(resp.json().get("type", ""))
    except ValueError:
        return ""
