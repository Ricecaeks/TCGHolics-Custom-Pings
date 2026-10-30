"""Every node: report liveness, learn the cluster size, refresh proxies, touch the healthcheck file."""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

from curl_cffi.requests import AsyncSession

from tcgpings import __version__
from tcgpings.context import Context
from tcgpings.db import queries

log = logging.getLogger(__name__)


async def lookup_egress_ip(url: str) -> str | None:
    try:
        async with AsyncSession(timeout=10) as s:
            resp = await s.get(url)
            ip = resp.text.strip()
            return ip if resp.status_code == 200 and len(ip) < 64 else None
    except Exception as exc:
        log.warning("egress IP lookup failed: %s", exc)
        return None


async def heartbeat_loop(ctx: Context) -> None:
    s = ctx.settings
    health_file = Path(s.data_dir) / "heartbeat"
    health_file.parent.mkdir(parents=True, exist_ok=True)
    while True:
        try:
            await beat(ctx)
            health_file.write_text(str(time.time()))
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("heartbeat failed")
        await asyncio.sleep(s.heartbeat_seconds)


async def beat(ctx: Context) -> None:
    s = ctx.settings
    st = ctx.stats
    await queries.heartbeat(
        ctx.pool, ctx.node_name, __version__, ctx.egress_ip, ctx.is_leader,
        st.jobs_ok, st.jobs_failed, st.alerts_sent,
    )
    live = [n for n in await queries.list_nodes(ctx.pool) if n["age"] < s.node_stale_seconds]
    same_ip = [n for n in live if ctx.egress_ip and n["egress_ip"] == ctx.egress_ip]
    ctx.http.limiter.set_shares(direct=len(same_ip) if ctx.egress_ip else len(live), proxy=len(live))

    rows = await queries.list_proxies(ctx.pool)
    now = time.time()
    cooldowns = {
        r["url"]: r["cooldown_until"].timestamp() - now
        for r in rows
        if r["cooldown_until"] and r["cooldown_until"].timestamp() > now
    }
    ctx.http.proxies.update(s.proxies + [r["url"] for r in rows], cooldowns)
