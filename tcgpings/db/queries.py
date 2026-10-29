"""All SQL lives here. Functions take a Pool or Connection (both expose fetch/execute)."""

from __future__ import annotations

from typing import Any

import asyncpg

from tcgpings.models import Product, Stock, Store

DB = asyncpg.Pool | asyncpg.Connection

# --- retailers -------------------------------------------------------------------------


async def list_retailers(db: DB, enabled_only: bool = False) -> list[asyncpg.Record]:
    where = "WHERE enabled" if enabled_only else ""
    return await db.fetch(f"SELECT * FROM retailers {where} ORDER BY id")


async def get_retailer(db: DB, retailer_id: str) -> asyncpg.Record | None:
    return await db.fetchrow("SELECT * FROM retailers WHERE id = $1", retailer_id)


async def upsert_retailer(
    db: DB,
    retailer_id: str,
    adapter: str,
    name: str,
    config: dict | None = None,
    color: int | None = None,
    requests_per_minute: int | None = None,
    proxy_policy: str | None = None,
    enabled: bool = True,
) -> None:
    """Create a retailer, or refresh its adapter/name/config. Operator-tuned fields are kept."""
    await db.execute(
        """
        INSERT INTO retailers (id, adapter, name, config, color, requests_per_minute, proxy_policy, enabled)
        VALUES ($1, $2, $3, $4, $5, coalesce($6, 30), coalesce($7, 'direct'), $8)
        ON CONFLICT (id) DO UPDATE SET
            adapter = EXCLUDED.adapter,
            name = EXCLUDED.name,
            config = retailers.config || EXCLUDED.config,
            color = coalesce(EXCLUDED.color, retailers.color)
        """,
        retailer_id, adapter, name, config or {}, color, requests_per_minute, proxy_policy, enabled,
    )


async def update_retailer(db: DB, retailer_id: str, **fields: Any) -> bool:
    allowed = {"enabled", "proxy_policy", "requests_per_minute", "name", "color"}
    fields = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not fields:
        return False
    sets = ", ".join(f"{k} = ${i}" for i, k in enumerate(fields, start=2))
    result = await db.execute(f"UPDATE retailers SET {sets} WHERE id = $1", retailer_id, *fields.values())
    return result.endswith(" 1")


# --- stores ----------------------------------------------------------------------------


async def upsert_stores(db: DB, stores: list[Store]) -> None:
    await db.executemany(
        """
        INSERT INTO stores (retailer_id, store_id, name, slug, region)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (retailer_id, store_id) DO UPDATE SET
            name = EXCLUDED.name, slug = EXCLUDED.slug, region = EXCLUDED.region, updated_at = now()
        """,
        [(s.retailer_id, s.store_id, s.name, s.slug, s.region) for s in stores],
    )


async def prune_stores(db: DB, retailer_id: str, keep_ids: list[str]) -> int:
    """Drop stores the retailer no longer lists (closed, or placeholders learned before the list was known)."""
    result = await db.execute(
        "DELETE FROM stores WHERE retailer_id = $1 AND NOT (store_id = ANY($2::text[]))", retailer_id, keep_ids
    )
    return int(result.split()[-1])


async def list_stores(db: DB, retailer_id: str) -> list[asyncpg.Record]:
    return await db.fetch("SELECT * FROM stores WHERE retailer_id = $1 ORDER BY name", retailer_id)


async def resolve_store(db: DB, retailer_id: str, ref: str) -> asyncpg.Record | None:
    """Find a store by id, slug or (partial) name."""
    return await db.fetchrow(
        """
        SELECT * FROM stores WHERE retailer_id = $1
          AND (store_id = $2 OR slug = lower($2) OR name ILIKE '%' || $2 || '%')
        ORDER BY (store_id = $2) DESC, (slug = lower($2)) DESC, length(name)
        LIMIT 1
        """,
        retailer_id, ref,
    )


# --- watches ---------------------------------------------------------------------------


async def add_watch(
    db: DB,
    kind: str,
    query: str,
    retailer_id: str | None,
    store_ids: list[str] | None,
    franchise: str | None,
    interval_seconds: int | None,
    created_by: int | None = None,
) -> int:
    return await db.fetchval(
        """
        INSERT INTO watches (kind, query, retailer_id, store_ids, franchise, interval_seconds, created_by)
        VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id
        """,
        kind, query, retailer_id, store_ids, franchise, interval_seconds, created_by,
    )


async def list_watches(db: DB, enabled_only: bool = False) -> list[asyncpg.Record]:
    where = "WHERE enabled" if enabled_only else ""
    return await db.fetch(f"SELECT * FROM watches {where} ORDER BY id")


async def remove_watch(db: DB, watch_id: int) -> bool:
    return (await db.execute("DELETE FROM watches WHERE id = $1", watch_id)).endswith(" 1")


# --- jobs ------------------------------------------------------------------------------


async def claim_jobs(db: DB, node: str, limit: int, lease_seconds: int) -> list[asyncpg.Record]:
    return await db.fetch(
        """
        WITH due AS (
            SELECT j.id FROM jobs j JOIN retailers r ON r.id = j.retailer_id
            WHERE j.enabled AND r.enabled
              AND j.next_run_at <= now()
              AND (j.lease_until IS NULL OR j.lease_until < now())
            ORDER BY j.next_run_at
            LIMIT $2
            FOR UPDATE OF j SKIP LOCKED
        )
        UPDATE jobs j SET lease_owner = $1, lease_until = now() + make_interval(secs => $3)
        FROM due WHERE j.id = due.id
        RETURNING j.*
        """,
        node, limit, float(lease_seconds),
    )


async def extend_lease(db: DB, job_id: int, node: str, lease_seconds: int) -> bool:
    result = await db.execute(
        "UPDATE jobs SET lease_until = now() + make_interval(secs => $3) WHERE id = $1 AND lease_owner = $2",
        job_id, node, float(lease_seconds),
    )
    return result.endswith(" 1")


async def finish_job(db: DB, job_id: int, node: str, error: str | None = None) -> None:
    """Release the lease and schedule the next run. Failures back off exponentially (max 30 min)."""
    await db.execute(
        """
        UPDATE jobs SET
            lease_owner = NULL,
            lease_until = NULL,
            runs = runs + 1,
            last_ok_at = CASE WHEN $3::text IS NULL THEN now() ELSE last_ok_at END,
            last_error = coalesce($3, last_error),
            last_error_at = CASE WHEN $3::text IS NULL THEN last_error_at ELSE now() END,
            consecutive_failures = CASE WHEN $3::text IS NULL THEN 0 ELSE consecutive_failures + 1 END,
            next_run_at = now() + make_interval(secs =>
                CASE WHEN $3::text IS NULL
                     THEN interval_seconds * (0.9 + random() * 0.2)
                     ELSE least(interval_seconds * power(2, least(consecutive_failures + 1, 6)), 1800)
                END)
        WHERE id = $1 AND lease_owner = $2
        """,
        job_id, node, error,
    )


async def release_leases(db: DB, node: str) -> None:
    """On clean shutdown, hand unfinished jobs straight back instead of waiting for leases to expire."""
    await db.execute("UPDATE jobs SET lease_owner = NULL, lease_until = NULL WHERE lease_owner = $1", node)
    await db.execute(
        "UPDATE alert_outbox SET lease_owner = NULL, lease_until = NULL WHERE lease_owner = $1 AND sent_at IS NULL",
        node,
    )
    await db.execute("UPDATE nodes SET is_leader = false WHERE name = $1", node)


async def ensure_auto_job(
    db: DB, key: str, retailer_id: str, payload: dict, interval_seconds: int, watch_id: int
) -> bool:
    result = await db.execute(
        """
        INSERT INTO jobs (key, kind, retailer_id, payload, interval_seconds, watch_id, auto)
        VALUES ($1, 'watch_sku', $2, $3, $4, $5, true)
        ON CONFLICT (key) DO NOTHING
        """,
        key, retailer_id, payload, interval_seconds, watch_id,
    )
    return result.endswith(" 1")


async def discovery_tracked_jobs(db: DB, retailer_id: str) -> list[asyncpg.Record]:
    """Store-level jobs that discovery created for keyword-matching products, with their titles."""
    return await db.fetch(
        """
        SELECT j.id, j.key, j.payload->>'sku' AS sku, p.title FROM jobs j
        LEFT JOIN products p ON p.retailer_id = j.retailer_id AND p.sku = j.payload->>'sku'
        WHERE j.retailer_id = $1 AND j.auto AND j.payload->>'source' = 'discover'
        """,
        retailer_id,
    )


async def add_discovery_job(db: DB, key: str, retailer_id: str, sku: str, interval_seconds: int) -> bool:
    result = await db.execute(
        """
        INSERT INTO jobs (key, kind, retailer_id, payload, interval_seconds, auto)
        VALUES ($1, 'watch_sku', $2, $3, $4, true)
        ON CONFLICT (key) DO NOTHING
        """,
        key, retailer_id, {"sku": sku, "store_ids": None, "watch_ids": [], "source": "discover"}, interval_seconds,
    )
    return result.endswith(" 1")


async def delete_jobs(db: DB, job_ids: list[int]) -> None:
    if job_ids:
        await db.execute("DELETE FROM jobs WHERE id = ANY($1::bigint[])", job_ids)


async def reconcile_jobs(db: asyncpg.Connection, desired: list[dict]) -> None:
    """Make the non-auto jobs table match `desired` (dicts with key/kind/retailer_id/payload/interval)."""
    async with db.transaction():
        await db.executemany(
            """
            INSERT INTO jobs (key, kind, retailer_id, payload, interval_seconds)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (key) DO UPDATE SET
                kind = EXCLUDED.kind,
                payload = EXCLUDED.payload,
                interval_seconds = EXCLUDED.interval_seconds,
                auto = false,
                watch_id = NULL,
                enabled = true
            WHERE (jobs.kind, jobs.payload, jobs.interval_seconds, jobs.auto)
                  IS DISTINCT FROM (EXCLUDED.kind, EXCLUDED.payload, EXCLUDED.interval_seconds, false)
            """,
            [(d["key"], d["kind"], d["retailer_id"], d["payload"], d["interval"]) for d in desired],
        )
        await db.execute(
            "DELETE FROM jobs WHERE NOT auto AND NOT (key = ANY($1::text[]))",
            [d["key"] for d in desired],
        )


async def job_health(db: DB) -> list[asyncpg.Record]:
    return await db.fetch(
        """
        SELECT retailer_id,
               count(*) AS jobs,
               count(*) FILTER (WHERE consecutive_failures > 0) AS failing,
               max(last_ok_at) AS last_ok_at,
               count(*) FILTER (WHERE next_run_at < now() - interval '5 minutes'
                                  AND lease_owner IS NULL) AS overdue
        FROM jobs WHERE enabled GROUP BY retailer_id ORDER BY retailer_id
        """
    )


# --- products & state ------------------------------------------------------------------


async def upsert_product(db: DB, p: Product) -> bool:
    """Returns True when the product was seen for the first time.

    Fills in `p.atc_url` / `p.image` from earlier sightings when this fetch didn't have them.
    """
    row = await db.fetchrow(
        """
        INSERT INTO products (retailer_id, sku, title, url, image, franchise, ptype, atc_url)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        ON CONFLICT (retailer_id, sku) DO UPDATE SET
            title = EXCLUDED.title,
            url = EXCLUDED.url,
            image = coalesce(EXCLUDED.image, products.image),
            franchise = coalesce(EXCLUDED.franchise, products.franchise),
            ptype = coalesce(EXCLUDED.ptype, products.ptype),
            atc_url = coalesce(EXCLUDED.atc_url, products.atc_url),
            last_seen_at = now()
        RETURNING (xmax = 0) AS inserted, atc_url, image
        """,
        p.retailer_id, p.sku, p.title, p.url, p.image, p.franchise, p.ptype, p.atc_url,
    )
    p.atc_url = p.atc_url or row["atc_url"]
    p.image = p.image or row["image"]
    return row["inserted"]


async def get_product(db: DB, retailer_id: str, sku: str) -> asyncpg.Record | None:
    return await db.fetchrow(
        "SELECT * FROM products WHERE retailer_id = $1 AND sku = $2", retailer_id, sku
    )


async def apply_state(
    conn: asyncpg.Connection,
    retailer_id: str,
    sku: str,
    store_id: str,
    stock: Stock,
    price_cents: int | None,
) -> asyncpg.Record | None:
    """Store the new state and return the previous one (None on first observation).

    Must run inside a transaction: the row lock serialises concurrent writers, so a state
    change is only ever observed (and alerted) once.
    """
    prev = await conn.fetchrow(
        """
        SELECT level, qty, price_cents FROM product_state
        WHERE retailer_id = $1 AND sku = $2 AND store_id = $3 FOR UPDATE
        """,
        retailer_id, sku, store_id,
    )
    if price_cents is None and prev is not None:
        price_cents = prev["price_cents"]
    await conn.execute(
        """
        INSERT INTO product_state (retailer_id, sku, store_id, level, qty, price_cents)
        VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (retailer_id, sku, store_id) DO UPDATE SET
            level = EXCLUDED.level, qty = EXCLUDED.qty,
            price_cents = EXCLUDED.price_cents, updated_at = now()
        """,
        retailer_id, sku, store_id, stock.level.value, stock.qty, price_cents,
    )
    if prev is None or (prev["level"], prev["qty"], prev["price_cents"]) != (
        stock.level.value, stock.qty, price_cents
    ):
        await conn.execute(
            """
            INSERT INTO state_changes
                (retailer_id, sku, store_id, old_level, new_level, old_qty, new_qty, old_price, new_price)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            """,
            retailer_id, sku, store_id,
            prev and prev["level"], stock.level.value,
            prev and prev["qty"], stock.qty,
            prev and prev["price_cents"], price_cents,
        )
    return prev


async def seconds_since_store_check(db: DB, retailer_id: str, sku: str) -> float | None:
    return await db.fetchval(
        """
        SELECT extract(epoch FROM now() - max(updated_at))::float8 FROM product_state
        WHERE retailer_id = $1 AND sku = $2 AND store_id <> ''
        """,
        retailer_id, sku,
    )


async def product_states(db: DB, retailer_id: str, sku: str) -> list[asyncpg.Record]:
    return await db.fetch(
        """
        SELECT ps.*, s.name AS store_name FROM product_state ps
        LEFT JOIN stores s ON s.retailer_id = ps.retailer_id AND s.store_id = ps.store_id
        WHERE ps.retailer_id = $1 AND ps.sku = $2 ORDER BY ps.store_id
        """,
        retailer_id, sku,
    )


# --- routes ----------------------------------------------------------------------------


async def list_routes(db: DB) -> list[asyncpg.Record]:
    return await db.fetch("SELECT * FROM routes ORDER BY id")


async def add_route(
    db: DB,
    channel_id: int,
    webhook_url: str,
    retailer_id: str | None = None,
    store_id: str | None = None,
    franchise: str | None = None,
    event_types: list[str] | None = None,
    role_id: int | None = None,
    keywords: str | None = None,
) -> int:
    return await db.fetchval(
        """
        INSERT INTO routes (retailer_id, store_id, franchise, event_types, channel_id, webhook_url, role_id, keywords)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8) RETURNING id
        """,
        retailer_id, store_id, franchise, event_types, channel_id, webhook_url, role_id, keywords or None,
    )


async def set_route_keywords(db: DB, route_id: int, keywords: str | None) -> bool:
    result = await db.execute("UPDATE routes SET keywords = $2 WHERE id = $1", route_id, keywords or None)
    return result.endswith(" 1")


async def remove_route(db: DB, route_id: int) -> bool:
    return (await db.execute("DELETE FROM routes WHERE id = $1", route_id)).endswith(" 1")


# --- outbox ----------------------------------------------------------------------------


async def enqueue_alert(db: DB, dedupe_key: str, route_id: int, payload: dict) -> bool:
    """Returns False when an identical alert was already queued (by this or another node)."""
    result = await db.execute(
        """
        INSERT INTO alert_outbox (dedupe_key, route_id, payload) VALUES ($1, $2, $3)
        ON CONFLICT (dedupe_key) DO NOTHING
        """,
        dedupe_key, route_id, payload,
    )
    return result.endswith(" 1")


async def claim_alerts(db: DB, node: str, limit: int, lease_seconds: int = 60) -> list[asyncpg.Record]:
    return await db.fetch(
        """
        WITH due AS (
            SELECT id FROM alert_outbox
            WHERE sent_at IS NULL AND attempts < 8 AND next_attempt_at <= now()
              AND (lease_until IS NULL OR lease_until < now())
            ORDER BY id LIMIT $2
            FOR UPDATE SKIP LOCKED
        )
        UPDATE alert_outbox o SET lease_owner = $1, lease_until = now() + make_interval(secs => $3)
        FROM due, routes r
        WHERE o.id = due.id AND r.id = o.route_id
        RETURNING o.id, o.payload, o.attempts, r.webhook_url, r.role_id, r.channel_id
        """,
        node, limit, float(lease_seconds),
    )


async def mark_alert_sent(db: DB, alert_id: int) -> None:
    await db.execute(
        "UPDATE alert_outbox SET sent_at = now(), lease_owner = NULL, lease_until = NULL WHERE id = $1",
        alert_id,
    )


async def mark_alert_failed(db: DB, alert_id: int, error: str, retry_in: float) -> None:
    await db.execute(
        """
        UPDATE alert_outbox SET attempts = attempts + 1, last_error = $2,
            next_attempt_at = now() + make_interval(secs => $3), lease_owner = NULL, lease_until = NULL
        WHERE id = $1
        """,
        alert_id, error[:500], float(retry_in),
    )


async def outbox_backlog(db: DB) -> asyncpg.Record:
    return await db.fetchrow(
        """
        SELECT count(*) FILTER (WHERE attempts < 8) AS pending,
               count(*) FILTER (WHERE attempts >= 8) AS dead
        FROM alert_outbox WHERE sent_at IS NULL
        """
    )


# --- nodes -----------------------------------------------------------------------------


async def heartbeat(
    db: DB, name: str, version: str, egress_ip: str | None, is_leader: bool,
    jobs_ok: int, jobs_failed: int, alerts_sent: int,
) -> None:
    await db.execute(
        """
        INSERT INTO nodes (name, version, egress_ip, is_leader, jobs_ok, jobs_failed, alerts_sent)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        ON CONFLICT (name) DO UPDATE SET
            version = EXCLUDED.version, egress_ip = EXCLUDED.egress_ip, is_leader = EXCLUDED.is_leader,
            last_heartbeat = now(), jobs_ok = EXCLUDED.jobs_ok, jobs_failed = EXCLUDED.jobs_failed,
            alerts_sent = EXCLUDED.alerts_sent
        """,
        name, version, egress_ip, is_leader, jobs_ok, jobs_failed, alerts_sent,
    )


async def register_node_start(db: DB, name: str, version: str) -> None:
    await db.execute(
        """
        INSERT INTO nodes (name, version) VALUES ($1, $2)
        ON CONFLICT (name) DO UPDATE SET version = EXCLUDED.version, started_at = now(),
            last_heartbeat = now(), is_leader = false
        """,
        name, version,
    )


async def list_nodes(db: DB) -> list[asyncpg.Record]:
    return await db.fetch(
        "SELECT *, extract(epoch FROM now() - last_heartbeat) AS age FROM nodes ORDER BY name"
    )


async def remove_node(db: DB, name: str) -> bool:
    return (await db.execute("DELETE FROM nodes WHERE name = $1", name)).endswith(" 1")


# --- proxies ---------------------------------------------------------------------------


async def list_proxies(db: DB) -> list[asyncpg.Record]:
    return await db.fetch("SELECT * FROM proxies WHERE enabled ORDER BY id")


async def proxy_failed(db: DB, url: str, cooldown_seconds: float) -> None:
    await db.execute(
        """
        UPDATE proxies SET fail_count = fail_count + 1,
            cooldown_until = now() + make_interval(secs => $2)
        WHERE url = $1
        """,
        url, float(cooldown_seconds),
    )


# --- maintenance -----------------------------------------------------------------------


async def prune(db: DB, retention_days: int) -> tuple[int, int]:
    changes = await db.execute(
        "DELETE FROM state_changes WHERE changed_at < now() - make_interval(days => $1)", retention_days
    )
    alerts = await db.execute(
        """
        DELETE FROM alert_outbox
        WHERE (sent_at IS NOT NULL AND sent_at < now() - make_interval(days => $1))
           OR (sent_at IS NULL AND created_at < now() - make_interval(days => $1))
        """,
        retention_days,
    )
    return int(changes.split()[-1]), int(alerts.split()[-1])


async def database_size_mb(db: DB) -> float:
    return await db.fetchval("SELECT (pg_database_size(current_database()) / 1048576.0)::float8")


async def recent_products(db: DB, retailer_id: str | None, limit: int) -> list[asyncpg.Record]:
    return await db.fetch(
        """
        SELECT retailer_id, sku, title FROM products
        WHERE $1::text IS NULL OR retailer_id = $1
        ORDER BY last_seen_at DESC LIMIT $2
        """,
        retailer_id, limit,
    )
