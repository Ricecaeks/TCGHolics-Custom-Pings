"""Wires one node together: worker, outbox sender, heartbeat and leader election."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal

from tcgpings import __version__
from tcgpings.cluster.heartbeat import beat, heartbeat_loop, lookup_egress_ip
from tcgpings.cluster.leader import LeaderElector
from tcgpings.cluster.leadership import lead
from tcgpings.cluster.worker import Worker
from tcgpings.config import Settings
from tcgpings.context import AdapterCache, Context
from tcgpings.db import queries
from tcgpings.db.pool import create_pool, migrate
from tcgpings.discord.sender import sender_loop
from tcgpings.engine.pipeline import Pipeline
from tcgpings.engine.router import RouteCache
from tcgpings.net.browser import BrowserFetcher
from tcgpings.net.chain import BrowserBackend, ChainStore, Cooldowns, DbChainStore, FetchChain
from tcgpings.net.http import HttpClient
from tcgpings.net.proxies import ProxyPool
from tcgpings.net.unblock import ScrapFlyBackend, ZyteBackend
from tcgpings.retailers import REGISTRY

log = logging.getLogger(__name__)


async def build_context(settings: Settings) -> Context:
    if not settings.database_url:
        raise SystemExit("DATABASE_URL is not set (see .env.example)")
    pool = await create_pool(settings.database_url, settings.db_pool_size)

    async def on_ban(proxy: str) -> None:
        await queries.proxy_failed(pool, proxy, 600)

    http = HttpClient(ProxyPool(settings.proxies), on_ban=on_ban)
    http.browser = BrowserFetcher(
        settings.browser_profile_dir, http.limiter, settings.browser_headless,
        settings.browser_channel, settings.browser_idle_seconds,
    )
    http.chain = build_chain(settings, DbChainStore(pool), http)
    routes = RouteCache(pool)
    return Context(
        settings=settings,
        pool=pool,
        http=http,
        adapters=AdapterCache(pool, http),
        routes=routes,
        pipeline=Pipeline(pool, routes, settings.alert_cooldown_seconds),
        node_name=settings.node_name,
    )


def build_chain(settings: Settings, store: ChainStore, http: HttpClient) -> FetchChain:
    """Our Chrome first, then each unblocker whose API key is set."""
    backends = [BrowserBackend(http.browser)]
    if settings.scrapfly_api_key:
        backends.append(ScrapFlyBackend(
            settings.scrapfly_api_key, settings.scrapfly_country, settings.scrapfly_usd_per_credit,
            settings.scrapfly_cost_budget, settings.node_name,
        ))
    if settings.zyte_api_key:
        backends.append(ZyteBackend(settings.zyte_api_key, settings.zyte_geolocation, settings.zyte_usd_per_request))
    log.info("fetch chain: %s", " -> ".join(b.name for b in backends))
    return FetchChain(
        backends, store, http.limiter,
        settings.unblocker_monthly_budget_usd, settings.unblocker_low_budget_ratio,
        Cooldowns(settings.browser_block_cooldown, settings.unblocker_block_cooldown),
    )


async def seed_retailers(ctx: Context) -> None:
    for cls in REGISTRY.values():
        for retailer_id, name, config, color in cls.default_retailers:
            await queries.upsert_retailer(
                ctx.pool, retailer_id, cls.adapter_name, name, config, color,
                cls.default_requests_per_minute, enabled=cls.default_enabled,
            )


async def run(settings: Settings) -> None:
    ctx = await build_context(settings)
    try:
        await migrate(ctx.pool)
        await seed_retailers(ctx)
        if settings.alert_webhook_url:
            await queries.set_catch_all_route(ctx.pool, settings.alert_webhook_url)
        await queries.register_node_start(ctx.pool, ctx.node_name, __version__)
        ctx.egress_ip = settings.egress_ip or await lookup_egress_ip(settings.egress_lookup_url)
        await beat(ctx)
        log.info(
            "node %s v%s started (egress %s%s)",
            ctx.node_name, __version__, ctx.egress_ip or "unknown", ", DRY RUN" if settings.dry_run else "",
        )

        worker = Worker(ctx)
        elector = LeaderElector(ctx, lambda: lead(ctx))
        tasks = [
            asyncio.create_task(heartbeat_loop(ctx), name="heartbeat"),
            asyncio.create_task(worker.run(), name="worker"),
            asyncio.create_task(sender_loop(ctx), name="sender"),
            asyncio.create_task(elector.run(), name="elector"),
        ]
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            with contextlib.suppress(NotImplementedError):  # Windows
                loop.add_signal_handler(sig, stop.set)

        stopper = asyncio.create_task(stop.wait(), name="stop")
        done, _ = await asyncio.wait([*tasks, stopper], return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            if task is not stopper and not task.cancelled() and task.exception():
                log.error("task %s crashed", task.get_name(), exc_info=task.exception())

        log.info("shutting down")
        await worker.stop()
        for task in [*tasks, stopper]:
            task.cancel()
        await asyncio.gather(*tasks, stopper, return_exceptions=True)
        with contextlib.suppress(Exception):
            await queries.release_leases(ctx.pool, ctx.node_name)
    finally:
        await ctx.http.close()
        await ctx.pool.close()
