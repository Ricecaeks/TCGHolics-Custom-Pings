"""Every node: report liveness, learn the cluster size, refresh proxies, touch the healthcheck file."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Mapping
from typing import Any

from curl_cffi.requests import AsyncSession

from tcgpings import __version__
from tcgpings.cluster.lanes import LANES, retailer_lane
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
    health_file = s.health_file
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


def _serves(node: Mapping[str, Any], lane: str | None) -> bool:
    """Does this node fetch for `lane` (None: any lane)? Nodes from before lanes (NULL) ran every lane."""
    node_lanes = node["lanes"]
    if node_lanes is None:
        return True
    return bool(node_lanes) if lane is None else lane in node_lanes


def _count(live: list, egress_ip: str | None, lane: str | None) -> tuple[int, int]:
    serving = [n for n in live if _serves(n, lane)]
    same_ip = [n for n in serving if n["egress_ip"] == egress_ip] if egress_ip else serving
    return len(same_ip), len(serving)


def limiter_shares(
    live: list, retailers: list, egress_ip: str | None,
) -> tuple[tuple[int, int], dict[str, tuple[int, int]]]:
    """Rate-limit shares from the live nodes: (direct, proxy) counts by default and per retailer.

    A retailer's budget is split only between the nodes that serve its lane (WORKER_LANES): direct between
    those on this node's public IP, everything else (proxies, Chrome, unblockers) between all of them.
    Counting every node instead would cut each store to a third when three containers share one IP but only
    one of them ever fetches from it.
    """
    by_lane = {lane: _count(live, egress_ip, lane) for lane in LANES}
    return _count(live, egress_ip, None), {r["id"]: by_lane[retailer_lane(r)] for r in retailers}


async def beat(ctx: Context) -> None:
    s = ctx.settings
    st = ctx.stats
    await queries.heartbeat(
        ctx.pool, ctx.node_name, __version__, ctx.egress_ip, ctx.is_leader,
        st.jobs_ok, st.jobs_failed, st.alerts_sent, s.lanes,
    )
    live = [n for n in await queries.list_nodes(ctx.pool) if n["age"] < s.node_stale_seconds]
    default, per_retailer = limiter_shares(live, await queries.list_retailers(ctx.pool), ctx.egress_ip)
    ctx.http.limiter.set_shares(*default, retailers=per_retailer)

    rows = await queries.list_proxies(ctx.pool)
    now = time.time()
    cooldowns = {
        r["url"]: r["cooldown_until"].timestamp() - now
        for r in rows
        if r["cooldown_until"] and r["cooldown_until"].timestamp() > now
    }
    ctx.http.proxies.update(s.proxies + [r["url"] for r in rows], cooldowns)
