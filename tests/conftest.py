import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

FIXTURES = Path(__file__).parent / "fixtures"
# A separate database from the dev cluster's, so tests never fight a running node for the leader lock.
DEV_DSN = "postgresql://tcgpings:tcgpings@localhost:54329/tcgpings"
TEST_DSN = os.environ.get("TEST_DATABASE_URL", DEV_DSN + "_test")


def load_fixture(*parts: str):
    path = FIXTURES.joinpath(*parts)
    text = path.read_text(encoding="utf-8")
    return json.loads(text) if path.suffix in (".json", ".js") else text


@pytest.fixture
async def pool():
    """A clean, migrated database per test. Skips when no Postgres is reachable."""
    asyncpg = pytest.importorskip("asyncpg")
    from tcgpings.db.pool import create_pool, migrate

    try:
        try:
            admin = await asyncpg.connect(TEST_DSN, timeout=3)
        except asyncpg.InvalidCatalogNameError:
            dev = await asyncpg.connect(DEV_DSN, timeout=3)
            await dev.execute(f'CREATE DATABASE "{TEST_DSN.rsplit("/", 1)[1]}"')
            await dev.close()
            admin = await asyncpg.connect(TEST_DSN, timeout=3)
    except (OSError, asyncpg.PostgresError, asyncio.TimeoutError) as exc:
        pytest.skip(f"no test database at {TEST_DSN}: {exc}")
    await admin.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    await admin.close()
    p = await create_pool(TEST_DSN, 8)
    await migrate(p)
    yield p
    await p.close()
