"""Multi-node behaviour end to end: leader failover and the worker -> outbox -> sender path."""

import asyncio

import aiohttp
import pytest
from conftest import TEST_DSN

from tcgpings.cluster import leader as leader_mod
from tcgpings.cluster.leader import LeaderElector
from tcgpings.cluster.leadership import reconcile
from tcgpings.cluster.worker import Worker
from tcgpings.config import Settings
from tcgpings.context import AdapterCache, Context
from tcgpings.db import queries
from tcgpings.discord.sender import send_batch
from tcgpings.engine.pipeline import Pipeline
from tcgpings.engine.router import RouteCache
from tcgpings.models import Level, Product, Stock, Store
from tcgpings.net.http import HttpClient
from tcgpings.retailers.base import RetailerAdapter, register


def make_ctx(pool, name, tmp_path):
    settings = Settings(
        _env_file=None, database_url=TEST_DSN, node_name=name, dry_run=True, data_dir=str(tmp_path),
    )
    http = HttpClient()
    routes = RouteCache(pool, ttl=0)
    return Context(
        settings=settings, pool=pool, http=http, adapters=AdapterCache(pool, http, ttl=0), routes=routes,
        pipeline=Pipeline(pool, routes, settings.alert_cooldown_seconds), node_name=name,
    )


async def wait_for(predicate, timeout=10.0):
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("condition not met in time")
        await asyncio.sleep(0.05)


async def test_leader_failover(pool, tmp_path, monkeypatch):
    monkeypatch.setattr(leader_mod, "CHECK_SECONDS", 0.2)
    monkeypatch.setattr(leader_mod, "RETRY_SECONDS", 0.2)
    a, b = make_ctx(pool, "nuc1", tmp_path), make_ctx(pool, "nuc2", tmp_path)
    leading: list[str] = []

    def lead_as(ctx):
        async def lead():
            leading.append(ctx.node_name)
            await asyncio.Event().wait()
        return lead

    task_a = asyncio.create_task(LeaderElector(a, lead_as(a)).run())
    await wait_for(lambda: a.is_leader)
    task_b = asyncio.create_task(LeaderElector(b, lead_as(b)).run())
    await asyncio.sleep(1)
    assert not b.is_leader, "only one node may lead"

    # Simulate nuc1 losing its database session (crash / network drop).
    await pool.execute(
        "SELECT pg_terminate_backend(pid) FROM pg_locks WHERE locktype = 'advisory' AND objid = $1",
        a.settings.leader_lock_key,
    )
    await wait_for(lambda: b.is_leader)
    await wait_for(lambda: not a.is_leader)
    assert leading[:2] == ["nuc1", "nuc2"]

    for t in (task_a, task_b):
        t.cancel()
    await asyncio.gather(task_a, task_b, return_exceptions=True)


# --- worker end to end -----------------------------------------------------------------


@register
class FakeStoreRetailer(RetailerAdapter):
    adapter_name = "_fake_stores"
    supports_store_stock = True
    stock = {"westgate": Stock(Level.OUT, 0), "albany": Stock(Level.IN, 3)}
    online = Stock(Level.OUT)
    calls: list = []

    def _product(self):
        return Product(self.retailer_id, "bundle", "Pokémon TCG: 30th Celebration Booster Bundle",
                       "https://fake/bundle", price_cents=5999, online=self.online)

    async def search(self, query):
        self.calls.append(("search", query))
        return [self._product(), Product(self.retailer_id, "plush", "Pokemon Pikachu Plush", "https://fake/plush")]

    async def fetch_products(self, skus):
        self.calls.append(("fetch", tuple(skus)))
        return [self._product()]

    async def list_stores(self):
        return [Store(self.retailer_id, "westgate", "Westgate"), Store(self.retailer_id, "albany", "Albany")]

    async def store_stock(self, sku, store_ids):
        self.calls.append(("stock", sku, tuple(sorted(store_ids))))
        return {s: self.stock[s] for s in store_ids}


async def run_due(worker, ctx):
    await ctx.pool.execute("UPDATE jobs SET next_run_at = now()")
    for job in await queries.claim_jobs(ctx.pool, ctx.node_name, 50, 60):
        await worker._run_job(job)


async def test_keyword_watch_to_store_alert(pool, tmp_path):
    ctx = make_ctx(pool, "nuc1", tmp_path)
    await queries.upsert_retailer(pool, "fake", "_fake_stores", "Fake Farmers")
    await queries.add_watch(pool, "keyword", "Pokemon 30th", None, None, None, None)
    await queries.add_route(pool, 10, "https://discord.test/westgate", "fake", "westgate")
    await queries.add_route(pool, 11, "https://discord.test/all", "fake")
    worker = Worker(ctx)

    await reconcile(ctx)
    keys = {r["key"] for r in await pool.fetch("SELECT key FROM jobs")}
    assert keys == {"stores:fake", "search:fake:pokemon 30th:*"}

    await run_due(worker, ctx)  # store sync + baseline search (creates the store-level auto job)
    await run_due(worker, ctx)  # first store-level check: baseline
    assert {r["key"] for r in await pool.fetch("SELECT key FROM jobs")} == keys | {"sku:fake:bundle"}
    assert await pool.fetchval("SELECT count(*) FROM alert_outbox") == 0
    assert await pool.fetchval("SELECT count(*) FROM products") == 1, "plush is not a card product"

    FakeStoreRetailer.stock = {"westgate": Stock(Level.IN, 12), "albany": Stock(Level.IN, 3)}
    await run_due(worker, ctx)
    rows = await pool.fetch(
        "SELECT o.payload, r.channel_id FROM alert_outbox o JOIN routes r ON r.id = o.route_id ORDER BY r.channel_id"
    )
    assert [(r["channel_id"], r["payload"]["type"], r["payload"]["store_name"]) for r in rows] == [
        (10, "restock", "Westgate"),
        (11, "restock", "Westgate"),
    ]
    assert ctx.stats.jobs_failed == 0

    async with aiohttp.ClientSession() as session:
        assert await send_batch(ctx, session) == 2  # dry run: logged, not posted
    assert (await queries.outbox_backlog(pool))["pending"] == 0
    assert ctx.stats.alerts_sent == 2


async def test_failing_adapter_is_recorded_and_backed_off(pool, tmp_path):
    @register
    class Broken(FakeStoreRetailer):
        adapter_name = "_broken"

        async def search(self, query):
            raise RuntimeError("site changed")

    ctx = make_ctx(pool, "nuc1", tmp_path)
    await queries.upsert_retailer(pool, "broken", "_broken", "Broken")
    await queries.add_watch(pool, "keyword", "pokemon", "broken", None, None, None)
    await reconcile(ctx)
    await run_due(Worker(ctx), ctx)
    row = await pool.fetchrow("SELECT * FROM jobs WHERE kind = 'watch_search'")
    assert row["consecutive_failures"] == 1 and "site changed" in row["last_error"]
    assert ctx.stats.jobs_failed == 1


@pytest.fixture(autouse=True)
def reset_fake():
    FakeStoreRetailer.stock = {"westgate": Stock(Level.OUT, 0), "albany": Stock(Level.IN, 3)}
    FakeStoreRetailer.calls = []
