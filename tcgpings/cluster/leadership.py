"""Tasks that run only on the elected leader."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

from tcgpings.context import Context
from tcgpings.db import queries
from tcgpings.engine.planner import plan_jobs

log = logging.getLogger(__name__)

RECONCILE_SECONDS = 30
HEALTH_SECONDS = 60
MAINTENANCE_SECONDS = 24 * 3600
ADAPTER_STALE_SECONDS = 30 * 60
AUTO_SETUP_SECONDS = 10 * 60
ROUTES_DOWN_SECONDS = 24 * 3600


async def lead(ctx: Context) -> None:
    bot = None
    tasks = [reconcile_loop(ctx), maintenance_loop(ctx)]
    if ctx.settings.discord_token:
        from tcgpings.discord.bot import TCGBot

        bot = TCGBot(ctx)
        tasks.append(bot.start(ctx.settings.discord_token))
        if ctx.settings.auto_setup and ctx.settings.guild_id:
            tasks.append(auto_setup_loop(ctx, bot))
    else:
        log.warning("DISCORD_TOKEN not set: slash commands are disabled (alerts still send via webhooks)")
    tasks.append(health_loop(ctx, bot))
    try:
        await asyncio.gather(*tasks)
    finally:
        if bot is not None:
            with contextlib.suppress(Exception):
                await bot.close()


async def reconcile(ctx: Context) -> int:
    s = ctx.settings
    desired = plan_jobs(
        await queries.list_retailers(ctx.pool),
        await queries.list_watches(ctx.pool),
        s.default_sku_interval,
        s.default_search_interval,
        s.store_sync_interval,
        s.default_discover_interval,
    )
    async with ctx.pool.acquire() as conn:
        await queries.reconcile_jobs(conn, desired)
    return len(desired)


async def reconcile_loop(ctx: Context) -> None:
    while True:
        try:
            await reconcile(ctx)
        except Exception:
            log.exception("job reconcile failed")
        await asyncio.sleep(RECONCILE_SECONDS)


async def auto_setup_loop(ctx: Context, bot) -> None:
    """Give newly enabled retailers their channels (and recreate deleted ones) without /setup."""
    from tcgpings.discord.commands import auto_setup

    await bot.wait_until_ready()
    paused = None
    while True:
        try:
            guild = bot.get_guild(ctx.settings.guild_id)
            result = await auto_setup(ctx, guild, bot.user) if guild else None
            if isinstance(result, str):
                if result != paused:
                    await bot.notify_staff(f"⚠️ {result}")
                paused = result
            elif result is not None:
                paused = None
                log.info("auto-setup: %s", result.summary())
                await bot.notify_staff(f"🛠️ Auto-setup: {result.summary()}")
        except Exception:
            log.exception("auto-setup failed")
        await asyncio.sleep(AUTO_SETUP_SECONDS)


async def maintenance_loop(ctx: Context) -> None:
    s = ctx.settings
    await asyncio.sleep(60)  # let a fresh leader settle first
    while True:
        try:
            changes, alerts = await queries.prune(ctx.pool, s.retention_days)
            log.info("pruned %d state changes and %d old alerts", changes, alerts)
            if s.backup_enabled:
                await backup(ctx)
        except Exception:
            log.exception("maintenance failed")
        await asyncio.sleep(MAINTENANCE_SECONDS)


async def backup(ctx: Context) -> Path | None:
    """pg_dump to this node's data dir, keeping the newest `backup_keep` files."""
    s = ctx.settings
    if shutil.which("pg_dump") is None:
        log.warning("pg_dump not installed; skipping backup")
        return None
    folder = Path(s.backup_dir)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"tcgpings-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}.dump"
    proc = await asyncio.create_subprocess_exec(
        "pg_dump", "--format=custom", "--no-owner", "--no-privileges",
        "--schema=public", f"--file={target}", f"--dbname={s.database_url}",
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        target.unlink(missing_ok=True)
        raise RuntimeError(f"pg_dump failed: {stderr.decode(errors='replace')[:500]}")
    for old in sorted(folder.glob("tcgpings-*.dump"))[: -s.backup_keep]:
        old.unlink(missing_ok=True)
    log.info("backup written to %s (%.1f MB)", target, target.stat().st_size / 1e6)
    return target


async def collect_issues(ctx: Context) -> dict[str, str]:
    """Current problems keyed by a stable id, so warnings are posted once per incident."""
    s = ctx.settings
    issues: dict[str, str] = {}
    for n in await queries.list_nodes(ctx.pool):
        if s.node_stale_seconds < n["age"] < 24 * 3600:
            issues[f"node:{n['name']}"] = f"Node **{n['name']}** has not checked in for {int(n['age'])}s"
    now = time.time()
    for h in await queries.job_health(ctx.pool):
        last_ok = h["last_ok_at"].timestamp() if h["last_ok_at"] else None
        if h["failing"] == h["jobs"] and (last_ok is None or now - last_ok > ADAPTER_STALE_SECONDS):
            issues[f"adapter:{h['retailer_id']}"] = (
                f"All {h['jobs']} jobs for **{h['retailer_id']}** are failing — the site may have changed or blocked us"
            )
    backlog = await queries.outbox_backlog(ctx.pool)
    if backlog["dead"]:
        issues["outbox:dead"] = f"{backlog['dead']} alerts could not be delivered (check webhooks)"
    if backlog["pending"] > 200:
        issues["outbox:backlog"] = f"{backlog['pending']} alerts waiting to send"
    size = await queries.database_size_mb(ctx.pool)
    if size > s.db_size_warn_mb:
        issues["db:size"] = f"Database is {size:.0f} MB (warning threshold {s.db_size_warn_mb} MB)"
    if ctx.http.chain is not None:
        issues.update(await fetch_chain_issues(ctx))
    return issues


async def fetch_chain_issues(ctx: Context) -> dict[str, str]:
    """Only what the chain can't fix itself: the budget running out, or every route down for a day."""
    s = ctx.settings
    chain = ctx.http.chain
    issues: dict[str, str] = {}
    used = await chain.budget_used()
    spent = used * s.unblocker_monthly_budget_usd
    if used >= 1:
        issues["budget:out"] = (f"Unblocker budget used up (${spent:.2f} of ${s.unblocker_monthly_budget_usd:.2f}): "
                                "paid routes are paused until next month, the free ones keep going")
    elif used >= chain.low_ratio:
        issues["budget:low"] = (f"Unblocker spend is ${spent:.2f} of ${s.unblocker_monthly_budget_usd:.2f} this month: "
                                "Farmers store checks are cut back to its priority regions")
    by_retailer: dict[str, list] = {}
    for b in await queries.list_breakers(ctx.pool):
        if b["backend"] in chain.backends:
            by_retailer.setdefault(b["retailer_id"], []).append(b)
    now = time.time()
    for retailer_id, rows in by_retailer.items():
        last_ok = max((r["last_ok_at"].timestamp() for r in rows if r["last_ok_at"]), default=None)
        all_open = len(rows) == len(chain.backends) and all(r["is_open"] for r in rows)
        if all_open and (last_ok is None or now - last_ok > ROUTES_DOWN_SECONDS):
            names = ", ".join(r["backend"] for r in rows)
            issues[f"chain:{retailer_id}"] = (
                f"**{retailer_id}** store stock and prices: every route ({names}) has been blocked for over a day. "
                "It keeps retrying on its own; adding or topping up an unblocker key would get it going sooner"
            )
    return issues


async def health_loop(ctx: Context, bot) -> None:
    active: dict[str, str] = {}
    while True:
        await asyncio.sleep(HEALTH_SECONDS)
        try:
            issues = await collect_issues(ctx)
        except Exception:
            log.exception("health check failed")
            continue
        for key, text in issues.items():
            if key not in active:
                log.warning("health: %s", text)
                if bot is not None:
                    await bot.notify_staff(f"⚠️ {text}")
        for key in active.keys() - issues.keys():
            log.info("health resolved: %s", key)
            if bot is not None:
                await bot.notify_staff(f"✅ Resolved: {active[key]}")
        active = issues
