"""Every node: claim due jobs from Postgres, run them, write results, reschedule."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
import zlib
from datetime import datetime, timedelta
from datetime import time as dt_time
from typing import Any
from zoneinfo import ZoneInfo

from tcgpings.classify import is_sealed_product
from tcgpings.context import Context
from tcgpings.db import queries
from tcgpings.engine.pipeline import classify_product
from tcgpings.engine.planner import retailer_sku_interval, sku_job_key
from tcgpings.engine.router import keyword_routes_match
from tcgpings.models import Product, Store
from tcgpings.net.http import Blocked

log = logging.getLogger(__name__)


POLL_SECONDS = 2
NZ = ZoneInfo("Pacific/Auckland")
DAILY_SPREAD_SECONDS = 3600
# The retailer answered 403 (blocked) or 404 (gone): retrying every few minutes won't change that.
DEAD_ERROR = re.compile(r"\bHTTP (?:403|404)\b")


def is_dead_error(error: str | None) -> bool:
    return bool(error and DEAD_ERROR.search(error))


def _listed_stock(adapter: Any, product: Any) -> tuple[dict | None, dict | None]:
    """Store-level stock that came with the listing itself (Kmart's islands), with display names."""
    if not product.stores:
        return None, None
    return product.stores, {sid: adapter.store_label(sid) for sid in product.stores}


def _search_entries(payload: dict) -> list[dict]:
    """A search job's queries. Jobs planned before searches were grouped per retailer hold just one."""
    if "queries" in payload:
        return payload["queries"]
    return [payload]


def daily_check_due(age: float | None, now: datetime, at: dt_time, sku: str,
                    spread: int = DAILY_SPREAD_SECONDS) -> bool:
    """Has this product's store stock been checked since today's refresh (`at` plus its own offset)?

    Each SKU gets a fixed offset within `spread` seconds after `at`, so a retailer's daily sweep is
    spread out instead of every product hitting the site at once.
    """
    if age is None:
        return True
    offset = timedelta(seconds=zlib.crc32(sku.encode()) % max(spread, 1))
    slot = datetime.combine(now.date(), at, now.tzinfo) + offset
    if slot > now:
        slot -= timedelta(days=1)
    return now - timedelta(seconds=age) < slot


def price_refresh_due(sku: str, now: datetime) -> bool:
    """A known price is re-read once a week, each product on its own weekday."""
    return zlib.crc32(sku.encode()) % 7 == now.weekday()


class Worker:
    def __init__(self, ctx: Context) -> None:
        self.ctx = ctx
        self._running: set[asyncio.Task] = set()
        self._stopping = asyncio.Event()

    async def run(self) -> None:
        s = self.ctx.settings
        lanes = s.lanes
        if not lanes:
            log.info("WORKER_LANES is empty: this node claims no jobs")
            await self._stopping.wait()
            return
        while not self._stopping.is_set():
            free = s.worker_concurrency - len(self._running)
            if free > 0:
                try:
                    jobs = await queries.claim_jobs(
                        self.ctx.pool, self.ctx.node_name, free, s.lease_seconds, lanes, s.max_inflight_per_retailer,
                    )
                except Exception:
                    log.exception("claiming jobs failed")
                    jobs = []
                for job in jobs:
                    task = asyncio.create_task(self._run_job(job), name=f"job:{job['key']}")
                    self._running.add(task)
                    task.add_done_callback(self._running.discard)
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self._stopping.wait(), POLL_SECONDS)

    async def stop(self, timeout: float = 20) -> None:
        """Stop claiming and give in-flight jobs a chance to finish (unfinished leases simply expire)."""
        self._stopping.set()
        if self._running:
            await asyncio.wait(self._running, timeout=timeout)

    async def _run_job(self, job: Any) -> None:
        keeper = asyncio.create_task(self._keep_lease(job["id"]))
        error = None
        try:
            await self.run_job(job)
            self.ctx.stats.jobs_ok += 1
            if job["paused_at"]:
                log.info("job %s works again: resumed after being paused since %s", job["key"], job["paused_at"])
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.ctx.stats.jobs_failed += 1
            error = f"{type(exc).__name__}: {exc}"[:500]
            # A paused check's daily retry is expected to fail; don't fill the log with it.
            log.log(logging.INFO if job["paused_at"] else logging.WARNING, "job %s failed: %s", job["key"], error)
        finally:
            keeper.cancel()
        try:
            await queries.finish_job(self.ctx.pool, job["id"], self.ctx.node_name, error, is_dead_error(error))
        except Exception:
            log.exception("could not release job %s (lease will expire)", job["key"])

    async def _keep_lease(self, job_id: int) -> None:
        lease = self.ctx.settings.lease_seconds
        while True:
            await asyncio.sleep(lease / 3)
            with contextlib.suppress(Exception):
                await queries.extend_lease(self.ctx.pool, job_id, self.ctx.node_name, lease)

    async def run_job(self, job: Any) -> None:
        handler = {
            "sync_stores": self._sync_stores,
            "watch_sku": self._watch_sku,
            "watch_search": self._watch_search,
            "discover": self._discover,
        }[job["kind"]]
        await handler(job)

    async def _sync_stores(self, job: Any) -> None:
        adapter = await self.ctx.adapters.get(job["retailer_id"])
        stores = await adapter.list_stores()
        removed = 0
        if stores:
            await queries.upsert_stores(self.ctx.pool, stores)
            removed = await queries.prune_stores(self.ctx.pool, job["retailer_id"], [s.store_id for s in stores])
        log.info("%s: synced %d stores (%d removed)", job["retailer_id"], len(stores), removed)

    async def _store_ids(self, retailer_id: str, wanted: list[str] | None) -> tuple[list[str], dict[str, str]]:
        names = {s["store_id"]: s["name"] for s in await queries.list_stores(self.ctx.pool, retailer_id)}
        ids = list(names) if wanted is None else [i for i in wanted if i in names]
        return ids, names

    async def _store_check_due(self, adapter: Any, sku: str, job_interval: int) -> bool:
        if not adapter.store_stock_interval and not adapter.store_stock_daily_at:
            return True
        age = await queries.seconds_since_store_check(self.ctx.pool, adapter.retailer_id, sku)
        if adapter.store_stock_daily_at:
            return daily_check_due(age, datetime.now(NZ), adapter.store_stock_daily_at, sku,
                                   adapter.store_stock_daily_spread)
        return age is None or age >= min(adapter.store_stock_interval, job_interval)  # hot jobs run sooner

    async def _refresh_details(self, adapter: Any, product: Product) -> None:
        """Details the listing lacks (Farmers' price, a paid request): fetched when unknown, else once a
        week on the product's own weekday. Other days keep the last known price."""
        if product.price_cents is None:
            known = await queries.online_price(self.ctx.pool, adapter.retailer_id, product.sku)
            if known is not None and not price_refresh_due(product.sku, datetime.now(NZ)):
                product.price_cents = known
                return
        await adapter.refresh_details(product)

    async def _watch_sku(self, job: Any) -> None:
        payload = job["payload"]
        retailer = await self.ctx.adapters.retailer(job["retailer_id"])
        adapter = await self.ctx.adapters.get(job["retailer_id"])
        products = await adapter.fetch_products([payload["sku"]])
        if products:
            product = products[0]
        else:
            # Sold-out products can vanish from a retailer's search while its stores still report them.
            row = await queries.get_product(self.ctx.pool, job["retailer_id"], payload["sku"])
            if not row or not adapter.store_stock_enabled:
                log.warning("%s: %s not found, so it wasn't checked", job["retailer_id"], payload["sku"])
                return
            product = Product(row["retailer_id"], row["sku"], row["title"], row["url"], image=row["image"],
                              franchise=row["franchise"], ptype=row["ptype"], atc_url=row["atc_url"])
        stock, names = None, None
        if adapter.store_stock_enabled and await self._store_check_due(adapter, product.sku, job["interval_seconds"]):
            wanted = payload.get("store_ids")
            ids, names = await self._store_ids(job["retailer_id"], wanted)
            if ids or (wanted is None and adapter.store_stock_discovers_stores):
                try:
                    stock = await adapter.store_stock(product.sku, ids)
                except Blocked as exc:
                    # Every route is resting: keep the online stock coming and retry next run.
                    log.info("%s: store check for %s skipped: %s", adapter.retailer_id, product.sku, exc)
                    stock = None
                else:
                    if stock:  # once per store check, so a day's checks don't repeat it
                        await self._refresh_details(adapter, product)
                    new = [Store(adapter.retailer_id, sid, adapter.store_label(sid)) for sid in stock if sid not in names]
                    if new:
                        await queries.upsert_stores(self.ctx.pool, new)
                        names.update({s.store_id: s.name for s in new})
                    if wanted is not None:
                        stock = {sid: s for sid, s in stock.items() if sid in wanted}
        if stock is None:
            stock, names = _listed_stock(adapter, product)
        await self.ctx.pipeline.record(retailer, product, stock, names, announce_new=False)

    async def _discover(self, job: Any) -> None:
        retailer = await self.ctx.adapters.retailer(job["retailer_id"])
        adapter = await self.ctx.adapters.get(job["retailer_id"])
        announce = job["last_ok_at"] is not None  # first run is a silent baseline
        routes = await self.ctx.routes.get()
        results = await adapter.discover()
        kept, wanted = 0, []
        for product in results:
            classify_product(product)
            if product.kind:  # a status row (a shop's queue), not a product
                await self.ctx.pipeline.record(retailer, product)
                continue
            if not is_sealed_product(product.title, product.franchise, product.ptype):
                continue
            await self.ctx.pipeline.record(retailer, product, *_listed_stock(adapter, product), announce_new=announce)
            kept += 1
            if adapter.store_stock_enabled and (
                adapter.track_all_discovered or keyword_routes_match(routes, adapter.retailer_id, product.title)
            ):
                wanted.append(product.sku)
        if adapter.store_stock_enabled:
            await self._track_discovered(adapter, wanted, routes)
        scanned = adapter.scan_size(results)
        if scanned is not None:  # None: the adapter didn't read the site this run
            await queries.record_discover_scan(self.ctx.pool, adapter.retailer_id, scanned, kept)
        log.log(logging.WARNING if scanned == 0 else logging.DEBUG,
                "%s discovery: %s products parsed, %d listed, %d sealed TCG, %d tracked per store",
                adapter.retailer_id, "skipped" if scanned is None else scanned, len(results), kept, len(wanted))

    async def _track_discovered(self, adapter: Any, skus: list[str], routes: list) -> None:
        """Keep store-level jobs for discovered products that match a keyword route; drop ones that no longer do."""
        existing = await queries.discovery_tracked_jobs(self.ctx.pool, adapter.retailer_id)
        stale = [r["id"] for r in existing
                 if not adapter.track_all_discovered
                 and (not r["title"] or not keyword_routes_match(routes, adapter.retailer_id, r["title"]))]
        await queries.delete_jobs(self.ctx.pool, stale)
        room = self.ctx.settings.max_tracked_per_retailer - (len(existing) - len(stale))
        tracked = {r["sku"] for r in existing}
        interval = retailer_sku_interval(await self.ctx.adapters.retailer(adapter.retailer_id), adapter,
                                         self.ctx.settings.default_sku_interval)
        for sku in skus:
            if sku in tracked:
                continue
            if room <= 0:
                log.warning("%s: store-level tracking limit reached (%d); narrow the route keywords",
                            adapter.retailer_id, self.ctx.settings.max_tracked_per_retailer)
                break
            if await queries.add_discovery_job(self.ctx.pool, sku_job_key(adapter.retailer_id, sku),
                                               adapter.retailer_id, sku, interval):
                room -= 1

    async def _watch_search(self, job: Any) -> None:
        """Run every keyword of a retailer's search job. One failing query doesn't stop the others;
        the job only fails when they all did."""
        retailer = await self.ctx.adapters.retailer(job["retailer_id"])
        adapter = await self.ctx.adapters.get(job["retailer_id"])
        entries = _search_entries(job["payload"])
        results = await adapter.search_many([e["query"] for e in entries])
        errors = []
        for entry in entries:
            found = results.get(entry["query"])
            if isinstance(found, Exception):
                errors.append(found)
                if len(entries) > 1:
                    log.warning("%s search %r failed: %s: %s", job["retailer_id"], entry["query"],
                                type(found).__name__, found)
                continue
            await self._record_search(job, retailer, adapter, entry, found or [])
        if errors and len(errors) == len(entries):
            raise errors[0]

    async def _record_search(self, job: Any, retailer: Any, adapter: Any, payload: dict, results: list) -> None:
        """What one keyword's search found: filter, record and give store-capable finds their own job."""
        # The first successful run is a baseline: everything already listed isn't "new". A keyword added
        # to a job that already ran gets its own baseline: the job hasn't succeeded since it was added.
        last_ok = job["last_ok_at"]
        since = payload.get("since")
        announce = last_ok is not None and (since is None or last_ok > datetime.fromisoformat(since))
        franchise = payload.get("franchise")
        kept = 0
        for product in results:
            if not is_sealed_product(product.title, product.franchise, product.ptype):
                continue
            classify_product(product)
            if franchise and product.franchise != franchise:
                continue
            await self.ctx.pipeline.record(retailer, product, *_listed_stock(adapter, product), announce_new=announce)
            kept += 1
            if adapter.store_stock_enabled:
                # Found products get their own store-level job, owned by the watch.
                await queries.ensure_auto_job(
                    self.ctx.pool,
                    sku_job_key(job["retailer_id"], product.sku),
                    job["retailer_id"],
                    {"sku": product.sku, "store_ids": payload.get("store_ids"), "watch_ids": payload["watch_ids"]},
                    retailer_sku_interval(retailer, adapter, self.ctx.settings.default_sku_interval),
                    payload["watch_ids"][0],
                )
        log.debug("%s search %r: %d results, %d kept", job["retailer_id"], payload["query"], len(results), kept)
