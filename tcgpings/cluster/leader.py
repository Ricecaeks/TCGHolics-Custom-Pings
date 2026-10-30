"""Leader election with a Postgres session advisory lock.

Exactly one node holds the lock and runs the leader-only tasks (Discord gateway, job planning,
maintenance). The lock lives as long as the holder's DB session, so a crashed node loses it
when its connection drops. As a backstop against connection poolers that keep a dead session
alive, a candidate that sees no live leader heartbeat terminates the lock holder's backend.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable

import asyncpg

from tcgpings.context import Context
from tcgpings.db.pool import connect

log = logging.getLogger(__name__)

CHECK_SECONDS = 5
RETRY_SECONDS = 5


class LeaderElector:
    def __init__(self, ctx: Context, lead: Callable[[], Awaitable[None]]) -> None:
        self.ctx = ctx
        self._lead = lead
        self._key = ctx.settings.leader_lock_key

    async def run(self) -> None:
        while True:
            try:
                await self._attempt()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("leader election error")
            await asyncio.sleep(RETRY_SECONDS)

    async def _attempt(self) -> None:
        conn = await connect(self.ctx.settings.database_url)
        try:
            if not await conn.fetchval("SELECT pg_try_advisory_lock($1)", self._key):
                await self._break_stale_lock(conn)
                return
            log.info("%s is now the leader", self.ctx.node_name)
            self.ctx.is_leader = True
            task = asyncio.create_task(self._lead(), name="leader")
            try:
                while not task.done():
                    await asyncio.wait({task}, timeout=CHECK_SECONDS)
                    await asyncio.wait_for(conn.fetchval("SELECT 1"), CHECK_SECONDS * 2)
                if not task.cancelled() and task.exception():
                    log.error("leader tasks crashed", exc_info=task.exception())
            finally:
                self.ctx.is_leader = False
                task.cancel()
                with contextlib.suppress(BaseException):
                    await task
                log.info("%s stepped down as leader", self.ctx.node_name)
                with contextlib.suppress(Exception):
                    await asyncio.wait_for(conn.execute("SELECT pg_advisory_unlock_all()"), 5)
        finally:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(conn.close(), 5)

    async def _break_stale_lock(self, conn: asyncpg.Connection) -> None:
        stale_after = self.ctx.settings.node_stale_seconds * 2
        live_leader = await conn.fetchval(
            "SELECT count(*) FROM nodes WHERE is_leader AND last_heartbeat > now() - make_interval(secs => $1)",
            float(stale_after),
        )
        if live_leader:
            return
        holder = await conn.fetchval(
            """
            SELECT l.pid FROM pg_locks l JOIN pg_stat_activity a ON a.pid = l.pid
            WHERE l.locktype = 'advisory' AND l.granted AND l.classid = 0 AND l.objid = $1
              AND l.objsubid = 1 AND a.backend_start < now() - make_interval(secs => $2)
            """,
            self._key, float(stale_after),
        )
        if holder:
            log.warning("no live leader heartbeat; terminating stale lock holder pid %s", holder)
            await conn.execute("SELECT pg_terminate_backend($1)", holder)
