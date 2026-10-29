"""Database-backed behaviour: job leasing, exactly-once alerts, reconcile. Needs the dev Postgres."""

import asyncio

from tcgpings.db import queries
from tcgpings.engine.pipeline import Pipeline
from tcgpings.engine.router import RouteCache
from tcgpings.models import Level, Product, Stock, Store

RETAILER = {"id": "farmers", "name": "Farmers", "color": None}


async def seed(pool, routes=()):
    await queries.upsert_retailer(pool, "farmers", "shopify", "Farmers", {"domain": "x"})
    for kw in routes:
        await queries.add_route(pool, 1, "https://discord.test/webhook", **kw)


def product(level=Level.IN, price=5999):
    return Product("farmers", "bundle", "Pokémon 30th Booster Bundle", "https://x/bundle",
                   price_cents=price, online=Stock(level))


async def outbox(pool):
    return await pool.fetch("SELECT * FROM alert_outbox ORDER BY id")


async def test_migrations_are_idempotent(pool):
    from tcgpings.db.pool import migrate

    assert await migrate(pool) == []


async def test_two_nodes_never_claim_the_same_job(pool):
    await seed(pool)
    async with pool.acquire() as conn:
        await queries.reconcile_jobs(
            conn,
            [dict(key=f"k{i}", kind="watch_sku", retailer_id="farmers", payload={"sku": str(i)}, interval=60) for i in range(20)],
        )
    a, b = await asyncio.gather(
        queries.claim_jobs(pool, "nuc1", 15, 60), queries.claim_jobs(pool, "nuc2", 15, 60)
    )
    ids_a, ids_b = {r["id"] for r in a}, {r["id"] for r in b}
    assert not ids_a & ids_b
    assert len(ids_a | ids_b) == 20
    assert await queries.claim_jobs(pool, "nuc3", 10, 60) == []


async def test_expired_lease_is_reclaimed_and_stale_owner_cannot_finish(pool):
    await seed(pool)
    async with pool.acquire() as conn:
        await queries.reconcile_jobs(conn, [dict(key="k", kind="watch_sku", retailer_id="farmers", payload={}, interval=60)])
    [job] = await queries.claim_jobs(pool, "nuc1", 1, 60)
    await pool.execute("UPDATE jobs SET lease_until = now() - interval '1 second'")  # nuc1 died
    [again] = await queries.claim_jobs(pool, "nuc2", 1, 60)
    assert again["id"] == job["id"] and again["lease_owner"] == "nuc2"

    await queries.finish_job(pool, job["id"], "nuc1")  # late finish from the dead node is ignored
    row = await pool.fetchrow("SELECT * FROM jobs")
    assert row["lease_owner"] == "nuc2" and row["runs"] == 0

    await queries.finish_job(pool, job["id"], "nuc2")
    row = await pool.fetchrow("SELECT *, extract(epoch FROM next_run_at - now()) AS wait FROM jobs")
    assert row["lease_owner"] is None and row["runs"] == 1 and 50 < row["wait"] < 70


async def test_failures_back_off(pool):
    await seed(pool)
    async with pool.acquire() as conn:
        await queries.reconcile_jobs(conn, [dict(key="k", kind="watch_sku", retailer_id="farmers", payload={}, interval=60)])
    [job] = await queries.claim_jobs(pool, "n", 1, 60)
    await queries.finish_job(pool, job["id"], "n", "Blocked: HTTP 403")
    row = await pool.fetchrow("SELECT *, extract(epoch FROM next_run_at - now()) AS wait FROM jobs")
    assert row["consecutive_failures"] == 1 and row["last_error"] == "Blocked: HTTP 403" and 110 < row["wait"] < 130


async def test_reconcile_keeps_auto_jobs_and_removes_stale_manual_ones(pool):
    await seed(pool)
    wid = await queries.add_watch(pool, "keyword", "pokemon", None, None, None, None)
    await queries.ensure_auto_job(pool, "sku:farmers:auto", "farmers", {"sku": "auto"}, 60, wid)
    async with pool.acquire() as conn:
        await queries.reconcile_jobs(conn, [dict(key="a", kind="watch_sku", retailer_id="farmers", payload={}, interval=60)])
        await queries.reconcile_jobs(conn, [dict(key="b", kind="watch_sku", retailer_id="farmers", payload={}, interval=60)])
    assert {r["key"] for r in await pool.fetch("SELECT key FROM jobs")} == {"b", "sku:farmers:auto"}
    await queries.remove_watch(pool, wid)  # auto jobs go with their watch
    assert {r["key"] for r in await pool.fetch("SELECT key FROM jobs")} == {"b"}


async def test_state_change_alerts_once_per_matching_route(pool):
    await queries.upsert_retailer(pool, "other", "shopify", "Other", {"domain": "y"})
    await seed(pool, routes=[{"retailer_id": "farmers"}, {"retailer_id": "farmers", "store_id": "westgate"}, {"retailer_id": "other"}])
    await queries.upsert_stores(pool, [Store("farmers", "westgate", "Westgate")])
    pipe = Pipeline(pool, RouteCache(pool), cooldown_seconds=900)

    # baseline: silent
    assert await pipe.record(RETAILER, product(Level.OUT), {"westgate": Stock(Level.OUT, 0)}, {"westgate": "Westgate"}) == []
    # unchanged: silent
    assert await pipe.record(RETAILER, product(Level.OUT), {"westgate": Stock(Level.OUT, 0)}) == []

    events = await pipe.record(RETAILER, product(Level.IN), {"westgate": Stock(Level.IN, 12)}, {"westgate": "Westgate"})
    assert sorted(e.store_id for e in events) == ["", "westgate"]
    rows = await outbox(pool)
    # online restock -> route 1 only; Westgate restock -> routes 1 and 2
    assert sorted((r["route_id"], r["payload"]["store_id"]) for r in rows) == [(1, ""), (1, "westgate"), (2, "westgate")]
    assert {r["payload"]["extra"]["retailer_name"] for r in rows} == {"Farmers"}
    changes = await pool.fetchval("SELECT count(*) FROM state_changes")
    assert changes == 4  # 2 baselines + 2 changes


async def test_concurrent_observers_produce_one_alert(pool):
    await seed(pool, routes=[{}])
    pipe = Pipeline(pool, RouteCache(pool), cooldown_seconds=900)
    await pipe.record(RETAILER, product(Level.OUT))
    results = await asyncio.gather(*(pipe.record(RETAILER, product(Level.IN)) for _ in range(5)))
    assert sum(len(r) for r in results) == 1
    assert len(await outbox(pool)) == 1


async def test_flapping_within_cooldown_does_not_repeat(pool):
    await seed(pool, routes=[{}])
    pipe = Pipeline(pool, RouteCache(pool), cooldown_seconds=900)
    await pipe.record(RETAILER, product(Level.OUT))
    for level in (Level.IN, Level.OUT, Level.IN, Level.OUT, Level.IN):
        await pipe.record(RETAILER, product(level))
    assert [r["payload"]["type"] for r in await outbox(pool)] == ["restock"]


async def test_new_product_only_when_announced(pool):
    await seed(pool, routes=[{}])
    pipe = Pipeline(pool, RouteCache(pool), cooldown_seconds=900)
    await pipe.record(RETAILER, product(), announce_new=False)
    other = Product("farmers", "etb", "Pokemon ETB", "https://x/etb", online=Stock(Level.IN))
    events = await pipe.record(RETAILER, other, announce_new=True)
    assert [e.type.value for e in events] == ["new_product"]
    assert events[0].franchise == "pokemon"


async def test_outbox_claim_send_and_retry(pool):
    await seed(pool, routes=[{}])
    assert await queries.enqueue_alert(pool, "k1", 1, {"x": 1})
    assert not await queries.enqueue_alert(pool, "k1", 1, {"x": 1})
    a, b = await asyncio.gather(queries.claim_alerts(pool, "n1", 10), queries.claim_alerts(pool, "n2", 10))
    assert len(a) + len(b) == 1
    row = (a or b)[0]
    assert row["webhook_url"] == "https://discord.test/webhook"
    await queries.mark_alert_failed(pool, row["id"], "boom", 0)
    [again] = await queries.claim_alerts(pool, "n1", 10)
    assert again["attempts"] == 1
    await queries.mark_alert_sent(pool, again["id"])
    assert await queries.claim_alerts(pool, "n1", 10) == []
    assert (await queries.outbox_backlog(pool))["pending"] == 0
