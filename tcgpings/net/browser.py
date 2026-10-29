"""Real-browser fetching for retailers behind Akamai / DataDome / Cloudflare challenges.

Plain HTTP clients get fingerprinted and blocked by these sites, so browser-backed adapters
send their requests with `fetch()` from inside a real Chrome page instead, which is exactly
what the site's own "check stock" buttons do. Uses Patchright (a Playwright fork that hides
the automation flags) driving Google Chrome.

- One persistent profile per retailer under `browser_profile_dir`, so the bot-manager cookies
  (e.g. Akamai's `_abck`) age and keep their trust across restarts.
- A session "warms up" by loading the retailer's home page and moving the mouse around for a
  few seconds; it re-warms after a block.
- Requests per retailer are serialised and go through the shared rate limiter.
- Chrome is closed after `idle_seconds` without requests so it costs no RAM between checks.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tcgpings.net.http import BAN_MARKERS, Blocked, FetchError, NetPolicy
from tcgpings.net.ratelimit import RateLimiter

log = logging.getLogger(__name__)

BROWSER_EGRESS = "browser"
WARMUP_SECONDS = 6

FETCH_JS = """
async ([url, headers]) => {
  const r = await fetch(url, {headers: headers || {}, credentials: 'include'});
  return {status: r.status, url: r.url, text: await r.text()};
}
"""


@dataclass
class _Session:
    context: Any
    page: Any
    origin: str
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    last_used: float = field(default_factory=time.monotonic)
    warmed: bool = False


class BrowserFetcher:
    def __init__(
        self,
        profile_dir: str,
        limiter: RateLimiter,
        headless: bool = False,
        channel: str = "chrome",
        idle_seconds: int = 600,
    ) -> None:
        self.profile_dir = Path(profile_dir)
        self.limiter = limiter
        self.headless = headless
        self.channel = channel
        self.idle_seconds = idle_seconds
        self._pw = None
        self._sessions: dict[str, _Session] = {}
        self._start_lock = asyncio.Lock()
        self._reaper: asyncio.Task | None = None

    async def fetch_text(
        self, policy: NetPolicy, origin: str, url: str, headers: dict | None = None, retries: int = 1
    ) -> str:
        """GET `url` from inside a page on `origin`. Raises Blocked / FetchError like HttpClient."""
        await self.limiter.acquire(policy.retailer_id, BROWSER_EGRESS, policy.requests_per_minute)
        session = await self._session(policy.retailer_id, origin)
        async with session.lock:
            session.last_used = time.monotonic()
            for attempt in range(retries + 1):
                if not session.warmed:
                    await self._warm(session)
                result = await session.page.evaluate(FETCH_JS, [url, headers])
                session.last_used = time.monotonic()
                status, text = result["status"], result["text"]
                if status in (403, 429) or (len(text) < 20_000 and BAN_MARKERS.search(text[:5000])):
                    log.warning("%s: blocked on %s (HTTP %s), attempt %d", policy.retailer_id, url, status, attempt + 1)
                    session.warmed = False
                    if attempt < retries:
                        await asyncio.sleep(10 + random.random() * 10)
                    continue
                if status == 200:
                    return text
                raise FetchError(f"GET {url}: HTTP {status}")
        raise Blocked(f"GET {url}: blocked by bot protection")

    async def _session(self, retailer_id: str, origin: str) -> _Session:
        existing = self._sessions.get(retailer_id)
        if existing is not None:
            return existing
        async with self._start_lock:
            if retailer_id in self._sessions:
                return self._sessions[retailer_id]
            if self._pw is None:
                from patchright.async_api import async_playwright  # heavy import, only when needed

                self._pw = await async_playwright().start()
                self._reaper = asyncio.create_task(self._reap_idle())
            profile = self.profile_dir / retailer_id
            profile.mkdir(parents=True, exist_ok=True)
            context = await self._pw.chromium.launch_persistent_context(
                str(profile),
                channel=self.channel or None,
                headless=self.headless,
                no_viewport=True,
                locale="en-NZ",
                timezone_id="Pacific/Auckland",
                args=["--disable-dev-shm-usage", "--no-first-run", "--no-default-browser-check"],
            )
            page = context.pages[0] if context.pages else await context.new_page()
            session = _Session(context, page, origin)
            self._sessions[retailer_id] = session
            log.info("%s: browser session started (profile %s)", retailer_id, profile)
            return session

    async def _warm(self, session: _Session) -> None:
        page = session.page
        await page.goto(session.origin, wait_until="domcontentloaded", timeout=45_000)
        end = time.monotonic() + WARMUP_SECONDS
        while time.monotonic() < end:
            await page.mouse.move(random.randint(80, 1000), random.randint(80, 650), steps=random.randint(6, 18))
            if random.random() < 0.35:
                await page.mouse.wheel(0, random.randint(-250, 450))
            await page.wait_for_timeout(random.randint(180, 550))
        html = await page.content()
        if BAN_MARKERS.search(html[:20_000]) and len(html) < 20_000:
            raise Blocked(f"{session.origin}: home page denied during warm-up")
        session.warmed = True

    async def _reap_idle(self) -> None:
        while True:
            await asyncio.sleep(30)
            now = time.monotonic()
            for retailer_id, s in list(self._sessions.items()):
                if not s.lock.locked() and now - s.last_used > self.idle_seconds:
                    log.info("%s: closing idle browser session", retailer_id)
                    self._sessions.pop(retailer_id, None)
                    with contextlib.suppress(Exception):
                        await s.context.close()

    async def close(self) -> None:
        if self._reaper:
            self._reaper.cancel()
        for s in list(self._sessions.values()):
            with contextlib.suppress(Exception):
                await s.context.close()
        self._sessions.clear()
        if self._pw is not None:
            with contextlib.suppress(Exception):
                await self._pw.stop()
            self._pw = None
