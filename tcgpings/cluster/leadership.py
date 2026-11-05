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
from tcgpings.net.chain import spend_limits


from tcgpings.retailers import REGISTRY
from tcgpings.engine.keywords import KeywordFilter
from tcgpings.engine.planner import plan_jobs, retailer_sku_interval

log = logging.getLogger(__name__)

RECONCILE_SECONDS = 30
HEALTH_SECONDS = 60
MAINTENANCE_SECONDS = 24 * 3600
ADAPTER_STALE_SECONDS = 30 * 60
AUTO_SETUP_SECONDS = 10 * 60

NEWS_SCAN_SECONDS = 3 * 3600
ROUTES_DOWN_SECONDS = 24 * 3600

SCAN_HISTORY = 10  # the "usual" product count is the median of this many scans before the latest
SCAN_MIN_HISTORY = 3  # scans needed before a drop is judged against them
SCAN_DROP_RATIO = 0.5  # a latest scan below this share of the usual count is a drop
SCAN_STALE_INTERVALS = 3  # no successful discovery for this many check intervals is overdue

QUEUE_LAG_WARN_SECONDS = 10 * 60  # the oldest due job waiting longer than this is a health issue

PAUSED_PREFIX = "paused:"  # issue key for newly paused checks: posted once, never "resolved"
PAUSED_LISTED = 15  # checks named in one post; the rest are in /status


async def lead(ctx: Context) -> None:
    bot = None
    tasks = [reconcile_loop(ctx), maintenance_loop(ctx)]
    if ctx.settings.discord_token:
        from tcgpings.discord.bot import TCGBot

        bot = TCGBot(ctx)
        tasks.append(bot.start(ctx.settings.discord_token))
        if ctx.settings.auto_setup and ctx.settings.guild_id:
            tasks.append(auto_setup_loop(ctx, bot))
        if ctx.settings.channel_layout and ctx.settings.guild_id:
            tasks.append(layout_loop(ctx, bot))
        if ctx.settings.log_channel_id:
            tasks.append(news_loop(ctx, bot))
        if ctx.settings.bot_logs_channel and ctx.settings.guild_id:
            from tcgpings.discord.botlogs import bot_logs_setup_loop

            tasks.append(bot_logs_setup_loop(ctx, bot, AUTO_SETUP_SECONDS))
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
    await apply_hot_intervals(ctx)
    return len(desired)


async def apply_hot_intervals(ctx: Context) -> None:
    """Keep found products' check intervals at their retailer's (see retailer_sku_interval). Products in a
    hot set get the adapter's faster hot checks, and go back to normal when it expires."""
    hot = [KeywordFilter.parse(w["query"]) for w in await queries.list_hot_watches(ctx.pool)]
    changes = []
    for job in await queries.store_check_jobs(ctx.pool):
        cls = REGISTRY.get(job["adapter"])
        if cls is None:
            continue
        interval = retailer_sku_interval(job, cls, ctx.settings.default_sku_interval)
        if cls.hot_sku_interval is not None and any(f.matches(job["title"]) for f in hot):
            interval = min(interval, cls.hot_sku_interval)
        if interval != job["interval_seconds"]:
            changes.append((job["id"], interval))
    if changes:
        await queries.set_job_intervals(ctx.pool, changes)


async def news_loop(ctx: Context, bot) -> None:
    """Suggest new releases for staff to approve."""
    from tcgpings.discord.hot import scan_news

    await bot.wait_until_ready()
    while True:
        try:
            await scan_news(ctx, bot)
        except Exception:
            log.exception("news scan failed")
        await asyncio.sleep(NEWS_SCAN_SECONDS)


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


async def layout_loop(ctx: Context, bot) -> None:
    """Keep the alert channels in layout.json linked: webhooks, routes, and new or renamed channels."""
    from tcgpings.discord.commands import run_layout

    await bot.wait_until_ready()
    reported: list[str] = []
    while True:
        try:
            guild = bot.get_guild(ctx.settings.guild_id)
            if guild is not None:
                plan, result = await run_layout(ctx, guild, bot.user)
                problems = result.problems if result else plan.problems
                if result is not None and result.changed:
                    log.info("layout: %s", result.summary())
                    await bot.notify_staff(f"🛠️ Alert channels: {result.summary()}")
                elif problems and problems != reported:
                    await bot.notify_staff("⚠️ Alert channels:" + "".join(f"\n{p}" for p in problems))
                reported = problems
        except Exception:
            log.exception("channel layout failed")
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
        if h["jobs"] and h["failing"] == h["jobs"] and (last_ok is None or now - last_ok > ADAPTER_STALE_SECONDS):
            issues[f"adapter:{h['retailer_id']}"] = (
                f"All {h['jobs']} jobs for **{h['retailer_id']}** are failing — the site may have changed or blocked us"
            )
    issues.update(queue_lag_issue(await queries.queue_lag(ctx.pool)))
    backlog = await queries.outbox_backlog(ctx.pool)
    if backlog["dead"]:
        issues["outbox:dead"] = f"{backlog['dead']} alerts could not be delivered (check webhooks)"
    if backlog["pending"] > 200:
        issues["outbox:backlog"] = f"{backlog['pending']} alerts waiting to send"
    size = await queries.database_size_mb(ctx.pool)
    if size > s.db_size_warn_mb:
        issues["db:size"] = f"Database is {size:.0f} MB (warning threshold {s.db_size_warn_mb} MB)"
    scans = scan_issues(await queries.discover_health(ctx.pool, SCAN_HISTORY))
    # A retailer whose every job fails already has a warning; "discovery is overdue" adds nothing.
    issues.update({k: v for k, v in scans.items() if f"adapter:{k.split(':', 1)[1]}" not in issues})
    if ctx.http.chain is not None:
        issues.update(await fetch_chain_issues(ctx))
    issues.update(paused_issue(await queries.paused_jobs(ctx.pool, unreported_only=True)))
    return issues


def queue_lag_issue(lag) -> dict[str, str]:
    """The job queue running behind: the longest-waiting due job is over QUEUE_LAG_WARN_SECONDS late.
    One issue for the whole queue, keyed so it's posted once and resolved once the workers catch up."""
    if lag is None or lag["worst_seconds"] <= QUEUE_LAG_WARN_SECONDS:
        return {}
    return {"queue:lag": (
        f"Checks are running behind: {lag['overdue']} due jobs are over {queries.QUEUE_LAG_SECONDS // 60} min late, "
        f"the oldest by {_span(lag['worst_seconds'])}. The workers can't keep up (see /status)"
    )}


def describe_paused(row) -> str:
    """One paused check: retailer, product, why (the error that paused it, minus the URL)."""
    name = row["title"] or row["sku"] or f"job {row['id']}"
    reason = (row["paused_reason"] or "").rsplit(": ", 1)[-1]
    return f"`{row['retailer_id']}` {name} ({reason})"


def paused_issue(rows) -> dict[str, str]:
    """Product checks paused since the last health post, as one issue. Its key names the jobs, so the health
    loop can mark them reported (see health_loop): each pause is posted once, even across restarts."""
    if not rows:
        return {}
    lines = [f"• {describe_paused(r)}" for r in rows[:PAUSED_LISTED]]
    if len(rows) > PAUSED_LISTED:
        lines.append(f"…and {len(rows) - PAUSED_LISTED} more (see /status)")
    head = (f"Paused {len(rows)} product check{'s' if len(rows) != 1 else ''} after {queries.PAUSE_AFTER} "
            "blocked/not-found errors in a row. They retry once a day and resume on their own:")
    return {PAUSED_PREFIX + ",".join(str(r["id"]) for r in rows): "\n".join([head, *lines])}


def _span(seconds: float) -> str:
    minutes = round(seconds / 60)
    return f"{minutes} min" if minutes < 120 else f"{minutes / 60:.1f} h"


def scan_issues(rows) -> dict[str, str]:
    """Discovery scans that "succeeded" but look broken: nothing parsed, far fewer products than usual,
    or no successful scan for SCAN_STALE_INTERVALS check intervals. Rows come from queries.discover_health.

    An overdue scan whose job keeps failing is that retailer's problem and gets its own warning. Overdue
    scans whose jobs haven't failed are just waiting for a worker, so they share one "running behind" warning
    rather than one per retailer.
    """
    issues: dict[str, str] = {}
    queued: list[tuple[float, str]] = []
    for h in rows:
        rid = h["retailer_id"]
        products = h["products"]
        if products == 0:
            issues[f"scan:{rid}"] = (
                f"**{rid}** discovery found 0 products on its last scan — the site may have changed "
                "and the parser is reading nothing"
            )
        elif (products is not None and h["scans"] >= SCAN_MIN_HISTORY and h["usual"]
              and products < h["usual"] * SCAN_DROP_RATIO):
            issues[f"scan:{rid}"] = (
                f"**{rid}** discovery found only {products} products on its last scan, against a usual "
                f"{h['usual']:.0f} — part of the site may have changed"
            )
        limit = SCAN_STALE_INTERVALS * h["interval_seconds"]
        if h["ok_age"] is None or h["ok_age"] <= limit:
            continue
        if not h["consecutive_failures"]:
            queued.append((h["ok_age"], rid))
            continue
        since = f"for {_span(h['ok_age'])}" if h["ever_ok"] else "since it was set up"
        issues[f"scan-stale:{rid}"] = (
            f"**{rid}** discovery hasn't completed a scan {since} (it runs every {_span(h['interval_seconds'])}; "
            f"{h['consecutive_failures']} failed runs in a row)"
        )
    if queued:
        queued.sort(reverse=True)
        names = ", ".join(rid for _, rid in queued[:5]) + (f" and {len(queued) - 5} more" if len(queued) > 5 else "")
        issues["scans:behind"] = (
            f"Discovery is running behind: {len(queued)} retailers have gone over {SCAN_STALE_INTERVALS}× their "
            f"check interval without a scan, waiting for a free worker (longest {_span(queued[0][0])}: {names})"
        )
    return issues


async def fetch_chain_issues(ctx: Context) -> dict[str, str]:
    """Only what the chain can't fix itself: the budget (or a store's own limit) running out, or every route
    down for a day."""
    chain = ctx.http.chain
    issues: dict[str, str] = {}
    used = await chain.budget_used()
    cap = chain.cap_usd()  # the total budget, or less when every paid route's own cap is lower
    spent = used * cap
    if used >= 1:
        issues["budget:out"] = (f"Unblocker budget used up (${spent:.2f} of ${cap:.2f}): "
                                "paid routes are paused until next month, the free ones keep going")
    elif used >= chain.low_ratio:
        issues["budget:low"] = (f"Unblocker spend is ${spent:.2f} of ${cap:.2f} this month: "
                                "Farmers store checks are cut back to its priority regions")
    store_spend: dict[str, float] = {}
    for r in await queries.month_spend_rows(ctx.pool):
        store_spend[r["retailer_id"]] = store_spend.get(r["retailer_id"], 0.0) + r["cost_usd"]
    for retailer_id, limit in spend_limits(await queries.list_retailers(ctx.pool)).items():
        if store_spend.get(retailer_id, 0.0) >= limit:
            issues[f"budget:{retailer_id}"] = (
                f"**{retailer_id}** has used its own unblocker limit (${store_spend[retailer_id]:.2f} of "
                f"${limit:.2f}): its paid routes are paused until next month, its free ones keep going"
            )
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
        paused = [int(i) for key in issues if key.startswith(PAUSED_PREFIX)
                  for i in key[len(PAUSED_PREFIX):].split(",")]
        try:
            await queries.mark_pauses_reported(ctx.pool, paused)
        except Exception:
            log.exception("could not mark paused checks as reported")
        for key in active.keys() - issues.keys():
            if key.startswith(PAUSED_PREFIX):
                continue  # a one-off notice: there's nothing to resolve
            log.info("health resolved: %s", key)
            if bot is not None:
                await bot.notify_staff(f"✅ Resolved: {active[key]}")
        active = issues
