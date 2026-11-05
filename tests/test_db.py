"""Database-backed behaviour: job leasing, exactly-once alerts, reconcile. Needs the dev Postgres."""

import asyncio

import pytest

from tcgpings.db import queries
from tcgpings.engine.pipeline import Pipeline
from tcgpings.engine.router import RouteCache
from tcgpings.models import Level, Product, Stock, Store
from tcgpings.net.chain import spend_limits
from tcgpings.net.http import NetPolicy

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


async def test_instore_channel_gets_one_alert_listing_the_stores(pool):
    from tcgpings.models import ANY_STORE, ONLINE

    await seed(pool, routes=[{"retailer_id": "farmers", "store_id": ONLINE},
                             {"retailer_id": "farmers", "store_id": ANY_STORE}])
    pipe = Pipeline(pool, RouteCache(pool), cooldown_seconds=900)
    out = {"albany": Stock(Level.OUT), "northwest": Stock(Level.OUT), "sylvia-park": Stock(Level.OUT)}
    await pipe.record(RETAILER, product(Level.OUT), out)
    back = {"albany": Stock(Level.IN), "northwest": Stock(Level.IN), "sylvia-park": Stock(Level.OUT)}
    names = {"albany": "Albany", "northwest": "Northwest"}
    await pipe.record(RETAILER, product(Level.IN), back, names)
    rows = await outbox(pool)
    assert [r["route_id"] for r in rows] == [1, 2]  # #farmers-online, then one #farmers-instore alert
    assert rows[0]["payload"]["store_id"] == ONLINE
    assert [s["name"] for s in rows[1]["payload"]["stores"]] == ["Albany", "Northwest"]


async def test_catch_all_route_is_kept_on_one_webhook(pool):
    await queries.set_catch_all_route(pool, "https://discord.test/one")
    await queries.set_catch_all_route(pool, "https://discord.test/one")
    await queries.set_catch_all_route(pool, "https://discord.test/two")
    [route] = await queries.list_routes(pool)
    assert route["webhook_url"] == "https://discord.test/two"
    assert route["retailer_id"] is None and route["store_id"] is None


async def test_fetch_breakers_and_spend(pool):
    await seed(pool)
    assert not await queries.breaker_open(pool, "farmers", "browser")
    await queries.trip_breaker(pool, "farmers", "browser", 3600, "WAF_Deny_Page")
    assert await queries.breaker_open(pool, "farmers", "browser")
    await queries.breaker_ok(pool, "farmers", "browser")
    assert not await queries.breaker_open(pool, "farmers", "browser")
    for _ in range(2):
        await queries.breaker_failure(pool, "farmers", "scrapfly", "timeout", 3, 1800)
    assert not await queries.breaker_open(pool, "farmers", "scrapfly")
    await queries.breaker_failure(pool, "farmers", "scrapfly", "timeout", 3, 1800)
    [_, scrapfly] = await queries.list_breakers(pool)
    assert scrapfly["is_open"] and 1700 < scrapfly["open_seconds"] <= 1800
    await queries.add_spend(pool, "farmers", "scrapfly", 0.0045)
    await queries.add_spend(pool, "farmers", "scrapfly", 0.0045, failed=True)
    await queries.add_spend(pool, "farmers", "zyte", 0.00127)
    await queries.add_spend(pool, "pokemoncenter-nz", "scrapfly", 0.003)
    assert await queries.month_spend(pool) == pytest.approx(0.01327)
    assert await queries.month_spend(pool, backend="scrapfly") == pytest.approx(0.012)
    assert await queries.month_spend(pool, retailer_id="farmers") == pytest.approx(0.01027)
    assert await queries.month_spend(pool, backend="scrapfly", retailer_id="pokemoncenter-nz") == pytest.approx(0.003)
    assert [(r["retailer_id"], r["backend"], r["requests"], r["failed"])
            for r in await queries.month_spend_rows(pool)] == [
        ("farmers", "scrapfly", 2, 1), ("farmers", "zyte", 1, 0), ("pokemoncenter-nz", "scrapfly", 1, 0)]


async def test_a_stores_spend_limit_lives_in_its_config(pool):
    await seed(pool)
    assert await queries.set_retailer_config(pool, "farmers", "unblocker_monthly_usd", 40.0)
    row = await queries.get_retailer(pool, "farmers")
    assert row["config"] == {"domain": "x", "unblocker_monthly_usd": 40.0}
    assert NetPolicy.from_row(row).spend_limit_usd == 40.0
    await seed(pool)  # startup re-seeding keeps it
    assert spend_limits(await queries.list_retailers(pool)) == {"farmers": 40.0}
    assert await queries.set_retailer_config(pool, "farmers", "unblocker_monthly_usd", None)
    row = await queries.get_retailer(pool, "farmers")
    assert row["config"] == {"domain": "x"} and NetPolicy.from_row(row).spend_limit_usd == 0
    assert not await queries.set_retailer_config(pool, "nobody", "unblocker_monthly_usd", 5.0)


async def test_spend_from_before_per_store_tracking_still_counts(pool):
    await pool.execute(
        "INSERT INTO unblocker_spend (month, backend, requests, cost_usd)"
        " VALUES (date_trunc('month', now() AT TIME ZONE 'UTC')::date, 'scrapfly', 10, 1.5)"
    )
    await queries.add_spend(pool, "farmers", "scrapfly", 0.5)
    assert await queries.month_spend(pool) == pytest.approx(2.0)
    assert [r["retailer_id"] for r in await queries.month_spend_rows(pool)] == ["", "farmers"]


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


async def test_default_retailers_seeded_and_operator_choice_sticks(pool):
    from types import SimpleNamespace

    from tcgpings.app import seed_retailers

    ctx = SimpleNamespace(pool=pool)
    await seed_retailers(ctx)
    farmers = await queries.get_retailer(pool, "farmers")
    assert farmers["enabled"] is True and farmers["requests_per_minute"] == 10
    assert farmers["config"]["fetch"] == ["browser", "scrapfly", "zyte"]  # the self-healing route order
    assert (await queries.get_retailer(pool, "jbhifi"))["config"]["domain"] == "www.jbhifi.co.nz"
    await queries.update_retailer(pool, "farmers", enabled=False)
    await seed_retailers(ctx)  # a restart must not switch it back on
    assert (await queries.get_retailer(pool, "farmers"))["enabled"] is False


async def test_single_card_price_change_is_recorded_without_an_alert(pool):
    await seed(pool, routes=[{}])
    pipe = Pipeline(pool, RouteCache(pool), cooldown_seconds=900)

    def card(price):
        return Product("farmers", "mage", "Pokemon Stingcaster Mage [Reality Fracture]", "https://x/mage",
                       price_cents=price, online=Stock(Level.IN))

    await pipe.record(RETAILER, card(400))
    assert await pipe.record(RETAILER, card(350)) == []
    assert await outbox(pool) == []
    assert await pool.fetchval("SELECT price_cents FROM product_state WHERE sku = 'mage'") == 350
    await pipe.record(RETAILER, product(price=5999))
    assert [e.type.value for e in await pipe.record(RETAILER, product(price=4999))] == ["price_change"]


async def test_member_pings_tag_only_matching_members_in_the_ping_channel(pool):
    from tcgpings.models import Store

    await seed(pool)
    await queries.add_route(pool, 1, "https://discord.test/beta")
    await queries.add_route(pool, 2, "https://discord.test/pings", event_types=["new_product", "restock"], member_pings=True)
    await queries.upsert_stores(pool, [Store("farmers", "albany", "Albany"), Store("farmers", "botany", "Botany")])
    for user, keywords in [(1, "30th"), (2, "30th"), (3, "booster bundle -bundle"), (4, "albany"), (5, "sylvia park"), (6, "farmers online")]:
        await queries.add_member_ping(pool, user, keywords)
    assert await queries.add_member_ping(pool, 1, "30TH") is None
    pipe = Pipeline(pool, RouteCache(pool), cooldown_seconds=900)
    names = {"albany": "Albany", "botany": "Botany"}

    def bundle(level):
        return Product("farmers", "b", "Pokémon 30th Booster Bundle", "https://x/b", online=Stock(level))

    await pipe.record(RETAILER, bundle(Level.OUT), {"albany": Stock(Level.OUT), "botany": Stock(Level.OUT)}, names)
    await pipe.record(RETAILER, bundle(Level.OUT), {"albany": Stock(Level.IN, 3), "botany": Stock(Level.OUT)}, names)
    rows = [r for r in await outbox(pool) if r["route_id"] == 2]
    assert len(rows) == 1
    assert rows[0]["payload"]["extra"]["pings"] == [{"keywords": "30th", "users": [1, 2]}, {"keywords": "albany", "users": [4]}]
    assert "pings" not in next(r for r in await outbox(pool) if r["route_id"] == 1)["payload"]["extra"]

    await pipe.record(RETAILER, bundle(Level.IN), {"albany": Stock(Level.IN, 3), "botany": Stock(Level.OUT)}, names)
    rows = [r for r in await outbox(pool) if r["route_id"] == 2]
    assert rows[-1]["payload"]["store_id"] == ""
    assert {"keywords": "farmers online", "users": [6]} in rows[-1]["payload"]["extra"]["pings"]

    assert not await queries.remove_member_ping(pool, 2, 1)  # one member can't remove another's
    assert await queries.remove_member_ping(pool, 1, (await queries.list_member_pings(pool, 1))[0]["id"])


async def test_ping_channel_stays_quiet_when_nobody_matches(pool):
    await seed(pool)
    await queries.add_route(pool, 2, "https://discord.test/pings", member_pings=True)
    await queries.add_member_ping(pool, 1, "lorcana")
    pipe = Pipeline(pool, RouteCache(pool), cooldown_seconds=900)
    await pipe.record(RETAILER, product(Level.OUT))
    await pipe.record(RETAILER, product(Level.IN))
    assert await outbox(pool) == []


async def test_spotted_report_tags_matching_members_and_posts_once(pool):
    from tcgpings.discord.commands import PING_EVENTS, spotted_event

    await seed(pool)
    await queries.add_route(pool, 1, "https://discord.test/beta")
    await queries.add_route(pool, 2, "https://discord.test/pings", event_types=PING_EVENTS, member_pings=True)
    await queries.add_member_ping(pool, 1, "30th westgate")
    await queries.add_member_ping(pool, 2, "30th albany")
    pipe = Pipeline(pool, RouteCache(pool), cooldown_seconds=900)
    event = spotted_event("Pokemon 30th Booster Bundle", "warehouse", "The Warehouse", "Westgate", 42, None)
    row = {"id": "warehouse", "name": "The Warehouse", "color": None}
    assert await pipe.report(row, event) == 2
    rows = await outbox(pool)
    ping = next(r for r in rows if r["route_id"] == 2)
    assert ping["payload"]["extra"]["pings"] == [{"keywords": "30th westgate", "users": [1]}]
    assert await pipe.report(row, event) == 0  # a second report of the same thing
    assert await queries.list_member_pings(pool, 1)


def store_product(level=Level.IN, qty=4):
    return Product("farmers", "30th-bb", "Pokemon TCG 30th Celebration Booster Bundle", "https://x/30th",
                   online=Stock(Level.OUT))


async def test_a_new_drop_already_on_the_shelf_alerts_in_store(pool):
    await seed(pool, routes=[{}])
    pipe = Pipeline(pool, RouteCache(pool), cooldown_seconds=900)
    events = await pipe.record(RETAILER, store_product(), {"albany": Stock(Level.IN, 4)}, {"albany": "Albany"},
                               announce_new=True)
    assert sorted(e.type.value for e in events) == ["new_product", "restock"]
    [shelf] = [e for e in events if e.store_id == "albany"]
    assert (shelf.new_level, shelf.new_qty, shelf.old_level) == ("in", 4, None)
    # a later store check (JB Hi-Fi and Toyworld check stores separately) still counts as the drop
    later = await pipe.record(RETAILER, store_product(), {"henderson": Stock(Level.LOW, 1)}, {"henderson": "Henderson"})
    assert [(e.type.value, e.store_id) for e in later] == [("restock", "henderson")]
    # and the next reading is an ordinary diff again
    assert await pipe.record(RETAILER, store_product(), {"albany": Stock(Level.IN, 5)}) == []


async def test_first_store_readings_of_a_baseline_product_stay_silent(pool):
    await seed(pool, routes=[{}])
    pipe = Pipeline(pool, RouteCache(pool), cooldown_seconds=900)
    assert await pipe.record(RETAILER, store_product(), {"albany": Stock(Level.IN, 4)}, announce_new=False) == []
    assert await pipe.record(RETAILER, store_product(), {"henderson": Stock(Level.IN, 2)}) == []
    [gone] = await pipe.record(RETAILER, store_product(), {"albany": Stock(Level.OUT, 0)})
    assert gone.type.value == "out_of_stock"
    [back] = await pipe.record(RETAILER, store_product(), {"albany": Stock(Level.IN, 6)})
    assert back.type.value == "restock" and back.old_level == "out"


async def test_an_announced_product_out_of_stock_in_store_is_quiet(pool):
    await seed(pool, routes=[{}])
    pipe = Pipeline(pool, RouteCache(pool), cooldown_seconds=900)
    events = await pipe.record(RETAILER, store_product(), {"albany": Stock(Level.OUT, 0)}, announce_new=True)
    assert [e.type.value for e in events] == ["new_product"]


async def test_sold_out_listings_and_their_price_changes_stay_quiet(pool):
    await seed(pool, routes=[{}])
    pipe = Pipeline(pool, RouteCache(pool), cooldown_seconds=900)
    await pipe.record(RETAILER, product(Level.OUT, 8999), announce_new=True)
    await pipe.record(RETAILER, product(Level.OUT, 9999))
    assert await outbox(pool) == []
    await pipe.record(RETAILER, product(Level.IN, 9999))
    await pipe.record(RETAILER, product(Level.IN, 7999))
    assert [r["payload"]["type"] for r in await outbox(pool)] == ["restock", "price_change"]


async def test_a_listing_without_stock_info_posts_when_stock_shows(pool):
    await seed(pool, routes=[{}])
    pipe = Pipeline(pool, RouteCache(pool), cooldown_seconds=900)
    tile = Product("farmers", "30th-tin", "Pokemon TCG 30th Celebration Tin", "https://x/tin", online=None)
    await pipe.record(RETAILER, tile, announce_new=True)
    assert await outbox(pool) == []  # Farmers tiles carry no stock
    checked = Product("farmers", "30th-tin", "Pokemon TCG 30th Celebration Tin", "https://x/tin", online=Stock(Level.IN))
    [event] = await pipe.record(RETAILER, checked)
    assert (event.type.value, event.new_level) == ("new_product", "in")
    assert [r["payload"]["type"] for r in await outbox(pool)] == ["new_product"]
    assert await pipe.record(RETAILER, checked) == []


async def test_a_price_flipping_back_and_forth_alerts_once(pool):
    await seed(pool, routes=[{}])
    pipe = Pipeline(pool, RouteCache(pool), cooldown_seconds=900)
    await pipe.record(RETAILER, product(price=14999))
    for price in (7499, 14999, 7499, 14999, 7499):  # a sale toggling, or two pages disagreeing
        await pipe.record(RETAILER, product(price=price))
    alerts = await outbox(pool)
    assert [(r["payload"]["type"], r["payload"]["new_price"]) for r in alerts] == [("price_change", 7499)]
    # every flip is still recorded, and a genuinely new price alerts again
    assert await pool.fetchval("SELECT price_cents FROM product_state WHERE sku = 'bundle'") == 7499
    [new] = await pipe.record(RETAILER, product(price=5999))
    assert (new.type.value, new.new_price) == ("price_change", 5999)
