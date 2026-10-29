"""Every node: claim due jobs from Postgres, run them, write results, reschedule."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

from tcgpings.classify import is_card_product
from tcgpings.context import Context
from tcgpings.db import queries
from tcgpings.engine.pipeline import classify_product
from tcgpings.engine.planner import sku_job_key

log = logging.getLogger(__name__)

POLL_SECONDS = 2


class Worker:
    def __init__(self, ctx: Context) -> None:
        self.ctx = ctx
        self._running: set[asyncio.Task] = set()
        self._stopping = asyncio.Event()

    async def run(self) -> None:
        s = self.ctx.settings
        while not self._stopping.is_set():
            free = s.worker_concurrency - len(self._running)
            if free > 0:
                try:
                    jobs = await queries.claim_jobs(self.ctx.pool, self.ctx.node_name, free, s.lease_seconds)
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
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.ctx.stats.jobs_failed += 1
            error = f"{type(exc).__name__}: {exc}"[:500]
            log.warning("job %s failed: %s", job["key"], error)
        finally:
            keeper.cancel()
        try:
            await queries.finish_job(self.ctx.pool, job["id"], self.ctx.node_name, error)
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
        }[job["kind"]]
        await handler(job)

    async def _sync_stores(self, job: Any) -> None:
        adapter = await self.ctx.adapters.get(job["retailer_id"])
        stores = await adapter.list_stores()
        if stores:
            await queries.upsert_stores(self.ctx.pool, stores)
        log.info("%s: synced %d stores", job["retailer_id"], len(stores))

    async def _store_ids(self, retailer_id: str, wanted: list[str] | None) -> tuple[list[str], dict[str, str]]:
        names = {s["store_id"]: s["name"] for s in await queries.list_stores(self.ctx.pool, retailer_id)}
        ids = list(names) if wanted is None else [i for i in wanted if i in names]
        return ids, names

    async def _store_check_due(self, adapter: Any, sku: str) -> bool:
        if not adapter.store_stock_interval:
            return True
        age = await queries.seconds_since_store_check(self.ctx.pool, adapter.retailer_id, sku)
        return age is None or age >= adapter.store_stock_interval

    async def _watch_sku(self, job: Any) -> None:
        payload = job["payload"]
        retailer = await self.ctx.adapters.retailer(job["retailer_id"])
        adapter = await self.ctx.adapters.get(job["retailer_id"])
        products = await adapter.fetch_products([payload["sku"]])
        if not products:
            return
        product = products[0]
        stock, names = None, None
        if adapter.supports_store_stock and await self._store_check_due(adapter, product.sku):
            ids, names = await self._store_ids(job["retailer_id"], payload.get("store_ids"))
            if ids:
                stock = await adapter.store_stock(product.sku, ids)
        await self.ctx.pipeline.record(retailer, product, stock, names, announce_new=False)

    async def _watch_search(self, job: Any) -> None:
        payload = job["payload"]
        retailer = await self.ctx.adapters.retailer(job["retailer_id"])
        adapter = await self.ctx.adapters.get(job["retailer_id"])
        # The first successful run is a baseline: everything already listed isn't "new".
        announce = job["last_ok_at"] is not None
        franchise = payload.get("franchise")

        results = await adapter.search(payload["query"])
        kept = 0
        for product in results:
            if not is_card_product(product.title, product.franchise):
                continue
            classify_product(product)
            if franchise and product.franchise != franchise:
                continue
            await self.ctx.pipeline.record(retailer, product, announce_new=announce)
            kept += 1
            if adapter.supports_store_stock:
                # Found products get their own store-level job, owned by the watch.
                await queries.ensure_auto_job(
                    self.ctx.pool,
                    sku_job_key(job["retailer_id"], product.sku),
                    job["retailer_id"],
                    {"sku": product.sku, "store_ids": payload.get("store_ids"), "watch_ids": payload["watch_ids"]},
                    adapter.default_sku_interval or self.ctx.settings.default_sku_interval,
                    payload["watch_ids"][0],
                )
        log.debug("%s search %r: %d results, %d kept", job["retailer_id"], payload["query"], len(results), kept)
