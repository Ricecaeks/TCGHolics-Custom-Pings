"""Product checks that only ever get 403/404 pause themselves, retry daily, and are reported once."""

import asyncio

import pytest
from test_cluster import make_ctx, run_due, wait_for

from tcgpings.cluster import leadership
from tcgpings.cluster.leadership import collect_issues, describe_paused, health_loop
from tcgpings.cluster.worker import Worker, is_dead_error
from tcgpings.db import queries
from tcgpings.db.queries import PAUSE_AFTER, PAUSE_RETRY_SECONDS
from tcgpings.models import Level, Product, Stock, Store
from tcgpings.net.http import Blocked, FetchError
from tcgpings.retailers.base import RetailerAdapter, register

BLOCKED = Blocked("GET https://shop.test/p/x/123.html: HTTP 403 (blocked)")
GONE = FetchError("GET https://shop.test/products/old-tin: HTTP 404", 404)
TIMEOUT = FetchError("GET https://shop.test/p/x/123.html: Operation timed out")
SERVER = FetchError("GET https://shop.test/p/x/123.html: HTTP 503")


@register
class DeadShop(RetailerAdapter):
    adapter_name = "_dead_shop"
    supports_discovery = True
    error: Exception | None = BLOCKED

    async def fetch_products(self, skus):
        if DeadShop.error:
            raise DeadShop.error
        return [Product(self.retailer_id, sku, f"Pokemon Booster Bundle {sku}", f"https://shop.test/{sku}",
                        online=Stock(Level.IN)) for sku in skus]

    async def discover(self):
        raise DeadShop.error or RuntimeError("unused")

    async def search(self, query):
        return []

    async def list_stores(self):
        return [Store(self.retailer_id, "w", "Westgate")]


@pytest.fixture(autouse=True)
def reset_shop():
    DeadShop.error = BLOCKED


async def _setup(pool, tmp_path, skus=("123",)):
    ctx = make_ctx(pool, "nuc1", tmp_path)
    await queries.upsert_retailer(pool, "dead", "_dead_shop", "Dead Shop")
    for sku in skus:
        await queries.add_discovery_job(pool, f"sku:dead:{sku}", "dead", sku, 60)
    return ctx, Worker(ctx)


async def _runs(worker, ctx, n):
    for _ in range(n):
        await run_due(worker, ctx)


async def _job(pool, sku="123"):
    return await pool.fetchrow(
        "SELECT *, extract(epoch FROM next_run_at - now()) AS wait FROM jobs WHERE key = $1", f"sku:dead:{sku}"
    )


def test_only_403_and_404_count_as_dead():
    assert is_dead_error(f"Blocked: {BLOCKED}")
    assert is_dead_error(f"FetchError: {GONE}")
    assert not is_dead_error(f"FetchError: {TIMEOUT}")
    assert not is_dead_error(f"FetchError: {SERVER}")
    assert not is_dead_error("Blocked: GET https://shop.test/: HTTP 429 (blocked)")
    assert not is_dead_error("FetchError: GET https://shop.test/: HTTP 4040")
    assert not is_dead_error(None)


async def test_check_pauses_after_twenty_blocked_runs_in_a_row(pool, tmp_path):
    ctx, worker = await _setup(pool, tmp_path)
    await _runs(worker, ctx, PAUSE_AFTER - 1)
    job = await _job(pool)
    assert job["paused_at"] is None and job["dead_failures"] == PAUSE_AFTER - 1
    assert job["wait"] <= 1800, "still on the normal back-off"

    await run_due(worker, ctx)
    job = await _job(pool)
    assert job["paused_at"] is not None and job["enabled"]
    assert job["paused_reason"] == f"Blocked: {BLOCKED}"
    assert PAUSE_RETRY_SECONDS * 0.9 < job["wait"] <= PAUSE_RETRY_SECONDS * 1.05, "retried once a day"
    assert [r["sku"] for r in await queries.paused_jobs(pool)] == ["123"]


async def test_timeouts_and_server_errors_never_pause_and_reset_the_count(pool, tmp_path):
    ctx, worker = await _setup(pool, tmp_path)
    await _runs(worker, ctx, PAUSE_AFTER - 1)
    DeadShop.error = TIMEOUT
    await run_due(worker, ctx)
    assert (await _job(pool))["dead_failures"] == 0
    DeadShop.error = GONE
    await _runs(worker, ctx, PAUSE_AFTER - 1)
    DeadShop.error = SERVER
    await _runs(worker, ctx, PAUSE_AFTER + 5)
    job = await _job(pool)
    assert job["paused_at"] is None and job["consecutive_failures"] == 3 * PAUSE_AFTER + 4


async def test_daily_retry_keeps_it_paused_until_one_works(pool, tmp_path):
    ctx, worker = await _setup(pool, tmp_path)
    await _runs(worker, ctx, PAUSE_AFTER)
    paused_at = (await _job(pool))["paused_at"]

    DeadShop.error = TIMEOUT  # the daily retry fails some other way: still paused, try again tomorrow
    await run_due(worker, ctx)
    job = await _job(pool)
    assert job["paused_at"] == paused_at and job["paused_reason"] == f"Blocked: {BLOCKED}"
    assert job["wait"] > PAUSE_RETRY_SECONDS * 0.9

    DeadShop.error = None  # the retailer lets us in again
    await run_due(worker, ctx)
    job = await _job(pool)
    assert job["paused_at"] is None and job["paused_reason"] is None and job["dead_failures"] == 0
    assert job["consecutive_failures"] == 0 and job["wait"] < 120, "back on its normal interval"
    assert await queries.paused_jobs(pool) == []


async def test_only_product_checks_pause(pool, tmp_path):
    ctx, worker = await _setup(pool, tmp_path, skus=())
    await pool.execute(
        "INSERT INTO jobs (key, kind, retailer_id, interval_seconds) VALUES ('discover:dead', 'discover', 'dead', 600)"
    )
    await _runs(worker, ctx, PAUSE_AFTER + 2)
    job = await pool.fetchrow("SELECT * FROM jobs WHERE key = 'discover:dead'")
    assert job["consecutive_failures"] == PAUSE_AFTER + 2 and job["paused_at"] is None


async def test_new_pauses_are_posted_once_even_across_restarts(pool, tmp_path, monkeypatch):
    ctx, worker = await _setup(pool, tmp_path, skus=("123", "456"))
    await queries.upsert_product(pool, Product("dead", "456", "One Piece OP-09 Booster Box", "https://shop.test/456"))
    await _runs(worker, ctx, PAUSE_AFTER - 1)
    assert not any(k.startswith("paused:") for k in await collect_issues(ctx))

    await run_due(worker, ctx)
    issues = await collect_issues(ctx)
    [text] = [v for k, v in issues.items() if k.startswith("paused:")]
    assert "Paused 2 product checks" in text and "One Piece OP-09 Booster Box (HTTP 403 (blocked))" in text
    assert "`dead` 123 (HTTP 403 (blocked))" in text
    # Paused checks don't count as the retailer "failing", even when nothing else is left running.
    assert not any(k.startswith("adapter:") for k in issues)

    class Bot:
        def __init__(self):
            self.posts: list[str] = []

        async def notify_staff(self, text):
            self.posts.append(text)

    monkeypatch.setattr(leadership, "HEALTH_SECONDS", 0.01)

    async def run_health(bot):
        loop = asyncio.create_task(health_loop(ctx, bot))
        await asyncio.sleep(0.15)  # many health checks
        return loop

    bot = Bot()
    loop = await run_health(bot)
    try:
        await wait_for(lambda: len(bot.posts) == 1)
        assert "Paused 2 product checks" in bot.posts[0]
        DeadShop.error = None  # one resumes: that is not a "resolved" incident to post
        await run_due(worker, ctx)
        await asyncio.sleep(0.1)
        assert len(bot.posts) == 1
    finally:
        loop.cancel()
    assert await queries.paused_jobs(pool, unreported_only=True) == []

    restarted = Bot()  # a new leader starts with no memory of what was posted
    loop = await run_health(restarted)
    loop.cancel()
    assert restarted.posts == []

    # Pausing again later is a new incident, reported again.
    DeadShop.error = GONE
    await _runs(worker, ctx, PAUSE_AFTER)
    rows = await queries.paused_jobs(pool, unreported_only=True)
    assert len(rows) == 2 and all(describe_paused(r).endswith("(HTTP 404)") for r in rows)


async def test_status_counts_paused_checks_apart_from_failing_ones(pool, tmp_path):
    ctx, worker = await _setup(pool, tmp_path, skus=("123", "456"))
    await pool.execute("UPDATE jobs SET dead_failures = $1 WHERE key = 'sku:dead:123'", PAUSE_AFTER)
    await run_due(worker, ctx)
    [h] = await queries.job_health(pool)
    assert (h["jobs"], h["failing"], h["paused"]) == (1, 1, 1)
