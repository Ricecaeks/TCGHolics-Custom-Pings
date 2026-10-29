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
from tcgpings.net.http import HttpClient
from tcgpings.net.proxies import ProxyPool
from tcgpings.retailers import REGISTRY

log = logging.getLogger(__name__)


async def build_context(settings: Settings) -> Context:
    if not settings.database_url:
        raise SystemExit("DATABASE_URL is not set (see .env.example)")
    pool = await create_pool(settings.database_url, settings.db_pool_size)

    async def on_ban(proxy: str) -> None:
        await queries.proxy_failed(pool, proxy, 600)

    http = HttpClient(ProxyPool(settings.proxies), on_ban=on_ban)
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


async def seed_retailers(ctx: Context) -> None:
    for cls in REGISTRY.values():
        for retailer_id, name, config, color in cls.default_retailers:
            await queries.upsert_retailer(ctx.pool, retailer_id, cls.adapter_name, name, config, color)


async def run(settings: Settings) -> None:
    ctx = await build_context(settings)
    try:
        await migrate(ctx.pool)
        await seed_retailers(ctx)
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
