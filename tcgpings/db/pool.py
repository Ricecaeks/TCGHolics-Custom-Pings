import json
import logging
from importlib import resources

import asyncpg

log = logging.getLogger(__name__)

MIGRATION_LOCK_KEY = 72_4242_02


async def _init_connection(conn: asyncpg.Connection) -> None:
    for typename in ("json", "jsonb"):
        await conn.set_type_codec(typename, encoder=json.dumps, decoder=json.loads, schema="pg_catalog")


async def create_pool(dsn: str, size: int) -> asyncpg.Pool:
    return await asyncpg.create_pool(
        dsn, min_size=1, max_size=size, init=_init_connection, command_timeout=30
    )


async def connect(dsn: str) -> asyncpg.Connection:
    conn = await asyncpg.connect(dsn, command_timeout=30)
    await _init_connection(conn)
    return conn


async def migrate(pool: asyncpg.Pool) -> list[str]:
    """Apply pending migrations in filename order. Safe to call from every node at once."""
    files = sorted(
        (f for f in resources.files("tcgpings.db.migrations").iterdir() if f.name.endswith(".sql")),
        key=lambda f: f.name,
    )
    applied: list[str] = []
    async with pool.acquire() as conn:
        await conn.execute("SELECT pg_advisory_lock($1)", MIGRATION_LOCK_KEY)
        try:
            await conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                " version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
            )
            await conn.execute("ALTER TABLE schema_migrations ENABLE ROW LEVEL SECURITY")
            done = {r["version"] for r in await conn.fetch("SELECT version FROM schema_migrations")}
            for f in files:
                if f.name in done:
                    continue
                async with conn.transaction():
                    await conn.execute(f.read_text(encoding="utf-8"))
                    await conn.execute("INSERT INTO schema_migrations (version) VALUES ($1)", f.name)
                log.info("applied migration %s", f.name)
                applied.append(f.name)
        finally:
            await conn.execute("SELECT pg_advisory_unlock($1)", MIGRATION_LOCK_KEY)
    return applied
