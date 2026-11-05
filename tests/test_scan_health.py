"""Discovery scans that "succeed" but parse nothing, far less than usual, or stop running raise a health issue."""

import asyncio

import pytest
from test_cluster import make_ctx, run_due, wait_for

from tcgpings.cluster import leadership
from tcgpings.cluster.leadership import (
    SCAN_HISTORY,
    collect_issues,
    health_loop,
    reconcile,
    scan_issues,
)
from tcgpings.cluster.worker import Worker
from tcgpings.db import queries
from tcgpings.models import Level, Product, Stock, Store
from tcgpings.retailers.base import RetailerAdapter, register


@register
class FlakyCatalogue(RetailerAdapter):
    adapter_name = "_flaky_catalogue"
    supports_discovery = True
    catalogue: list = []
    skip = False

    async def discover(self):
        return [Product(self.retailer_id, sku, f"Pokemon Booster Bundle {sku}", f"https://fake/{sku}",
                        online=Stock(Level.IN)) for sku in self.catalogue]

    def scan_size(self, results):
        return None if FlakyCatalogue.skip else super().scan_size(results)

    async def search(self, query):
        return []

    async def fetch_products(self, skus):
        return []

    async def list_stores(self):
        return [Store(self.retailer_id, "w", "Westgate")]


@pytest.fixture(autouse=True)
def reset_catalogue():
    FlakyCatalogue.catalogue = [f"p{i}" for i in range(20)]
    FlakyCatalogue.skip = False


async def _setup(pool, tmp_path):
    ctx = make_ctx(pool, "nuc1", tmp_path)
    await queries.upsert_retailer(pool, "flaky", "_flaky_catalogue", "Flaky")
    await reconcile(ctx)
    return ctx, Worker(ctx)


async def test_each_scan_records_its_product_count(pool, tmp_path):
    ctx, worker = await _setup(pool, tmp_path)
    await run_due(worker, ctx)
    FlakyCatalogue.skip = True  # a run that didn't read the site isn't a scan
    await run_due(worker, ctx)
    rows = await pool.fetch("SELECT retailer_id, products, sealed FROM discover_scans")
    assert [tuple(r) for r in rows] == [("flaky", 20, 20)]


async def test_zero_product_scan_warns_once_and_recovery_clears_it(pool, tmp_path, monkeypatch):
    ctx, worker = await _setup(pool, tmp_path)
    await run_due(worker, ctx)
    assert await collect_issues(ctx) == {}

    FlakyCatalogue.catalogue = []  # the site changed: the job still "succeeds" but parses nothing
    await run_due(worker, ctx)
    issues = await collect_issues(ctx)
    assert list(issues) == ["scan:flaky"] and "0 products" in issues["scan:flaky"]
    assert await pool.fetchval("SELECT consecutive_failures FROM jobs WHERE kind = 'discover'") == 0

    # Through the health loop: posted once while it lasts, then a resolved note once it recovers.
    class Bot:
        posts: list[str] = []

        async def notify_staff(self, text):
            self.posts.append(text)

    bot = Bot()
    monkeypatch.setattr(leadership, "HEALTH_SECONDS", 0.01)
    loop = asyncio.create_task(health_loop(ctx, bot))
    try:
        await wait_for(lambda: len(bot.posts) == 1)
        await asyncio.sleep(0.1)  # several more health checks
        assert len(bot.posts) == 1 and bot.posts[0].startswith("⚠️") and "0 products" in bot.posts[0]

        FlakyCatalogue.catalogue = [f"p{i}" for i in range(20)]
        await run_due(worker, ctx)
        await wait_for(lambda: len(bot.posts) == 2)
        assert bot.posts[1].startswith("✅ Resolved:") and "flaky" in bot.posts[1]
    finally:
        loop.cancel()
    assert await collect_issues(ctx) == {}


async def test_scan_well_below_the_usual_count_warns(pool, tmp_path):
    _ctx, _worker = await _setup(pool, tmp_path)
    for n in (100, 98, 103, 2000):  # one big outlier doesn't move the median
        await queries.record_discover_scan(pool, "flaky", n, n)
    await queries.record_discover_scan(pool, "flaky", 45, 45)
    issues = scan_issues(await queries.discover_health(pool, SCAN_HISTORY))
    assert "only 45 products" in issues["scan:flaky"] and "usual 102" in issues["scan:flaky"]

    await queries.record_discover_scan(pool, "flaky", 60, 60)  # median of 100, 98, 103, 2000, 45 is 100
    assert scan_issues(await queries.discover_health(pool, SCAN_HISTORY)) == {}


async def test_drop_needs_some_history_first(pool, tmp_path):
    await _setup(pool, tmp_path)
    for n in (100, 100, 10):
        await queries.record_discover_scan(pool, "flaky", n, n)
    assert scan_issues(await queries.discover_health(pool, SCAN_HISTORY)) == {}


async def test_discovery_that_stops_succeeding_is_overdue(pool, tmp_path):
    ctx, worker = await _setup(pool, tmp_path)
    await run_due(worker, ctx)
    interval = await pool.fetchval("SELECT interval_seconds FROM jobs WHERE kind = 'discover'")
    await pool.execute("UPDATE jobs SET last_ok_at = now() - make_interval(secs => $1) WHERE kind = 'discover'",
                       interval * 3 - 30)
    assert await collect_issues(ctx) == {}
    await pool.execute("UPDATE jobs SET last_ok_at = now() - make_interval(secs => $1) WHERE kind = 'discover'",
                       interval * 3 + 30)
    # Not failing, just queued behind other work: one shared "running behind" warning.
    issues = await collect_issues(ctx)
    assert list(issues) == ["scans:behind"] and "1 retailers" in issues["scans:behind"]

    # Running and failing: the retailer's own warning.
    await pool.execute("UPDATE jobs SET consecutive_failures = 2 WHERE kind = 'discover'")
    issues = await collect_issues(ctx)
    assert list(issues) == ["scan-stale:flaky"]
    assert "hasn't completed a scan for 10 min" in issues["scan-stale:flaky"] and "2 failed runs" in issues["scan-stale:flaky"]

    await queries.update_retailer(pool, "flaky", enabled=False)  # paused retailers aren't overdue
    assert await collect_issues(ctx) == {}


def test_never_successful_discovery_counts_from_creation_and_queued_ones_share_a_warning():
    def row(rid, failures, ok_age, ever_ok=True):
        return {"retailer_id": rid, "interval_seconds": 180, "consecutive_failures": failures, "ok_age": ok_age,
                "ever_ok": ever_ok, "products": None, "usual": None, "scans": 0}

    issues = scan_issues([row("new", 4, 3600, ever_ok=False), row("on-time", 0, 300)]
                         + [row(f"q{i}", 0, 600 + i * 60) for i in range(7)])
    assert "since it was set up" in issues["scan-stale:new"]
    assert set(issues) == {"scan-stale:new", "scans:behind"}
    assert "7 retailers" in issues["scans:behind"] and "longest 16 min: q6, q5, q4, q3, q2 and 2 more" in issues["scans:behind"]


async def test_overdue_scan_is_not_repeated_when_every_job_is_failing(pool, tmp_path):
    ctx, _worker = await _setup(pool, tmp_path)
    await pool.execute("UPDATE jobs SET consecutive_failures = 3, last_ok_at = NULL, "
                       "created_at = now() - interval '1 day'")
    assert list(await collect_issues(ctx)) == ["adapter:flaky"]


def _row(rid):
    return {"id": rid, "name": rid, "config": {}, "requests_per_minute": 30, "proxy_policy": "direct"}


def test_status_rows_are_not_counted():
    adapter = FlakyCatalogue(_row("x"), None)
    queue = Product("x", "queue", "Queue is live", "https://fake", kind="queue")
    assert RetailerAdapter.scan_size(adapter, [queue]) == 0


def test_paperplus_counts_listings_not_sold_out_padding():
    from tcgpings.retailers.paperplus import PaperPlusAdapter

    adapter = PaperPlusAdapter(_row("paperplus"), None)
    adapter._listed = {"gone": Product("paperplus", "gone", "Gone", "https://fake/gone")}
    adapter._missing = {"gone": 99}
    adapter._scanned = 3
    padded = adapter._left_the_listings({})
    assert len(padded) == 1 and adapter.scan_size(padded) == 3
