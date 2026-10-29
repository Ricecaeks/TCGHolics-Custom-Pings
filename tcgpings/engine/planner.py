"""Leader-only: derive the jobs table from watches + retailers."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from tcgpings.retailers.base import REGISTRY


def sku_job_key(retailer_id: str, sku: str) -> str:
    return f"sku:{retailer_id}:{sku}"


def _merge_stores(a: list[str] | None, b: list[str] | None) -> list[str] | None:
    if a is None or b is None:
        return None  # None = every store wins
    return sorted(set(a) | set(b))


def plan_jobs(
    retailers: Iterable[Mapping[str, Any]],
    watches: Iterable[Mapping[str, Any]],
    sku_interval: int,
    search_interval: int,
    store_sync_interval: int,
) -> list[dict]:
    retailers = [r for r in retailers if r["enabled"] and r["adapter"] in REGISTRY]
    by_id = {r["id"]: r for r in retailers}
    jobs: dict[str, dict] = {}

    for r in retailers:
        if REGISTRY[r["adapter"]].supports_store_stock:
            key = f"stores:{r['id']}"
            jobs[key] = dict(key=key, kind="sync_stores", retailer_id=r["id"], payload={}, interval=store_sync_interval)

    for w in watches:
        if not w["enabled"]:
            continue
        if w["kind"] == "sku":
            if w["retailer_id"] not in by_id:
                continue
            key = sku_job_key(w["retailer_id"], w["query"])
            interval = w["interval_seconds"] or sku_interval
            existing = jobs.get(key)
            if existing:
                existing["payload"]["store_ids"] = _merge_stores(existing["payload"]["store_ids"], w["store_ids"])
                existing["payload"]["watch_ids"].append(w["id"])
                existing["interval"] = min(existing["interval"], interval)
            else:
                jobs[key] = dict(
                    key=key, kind="watch_sku", retailer_id=w["retailer_id"], interval=interval,
                    payload={"sku": w["query"], "store_ids": w["store_ids"], "watch_ids": [w["id"]]},
                )
            continue

        targets = [w["retailer_id"]] if w["retailer_id"] else list(by_id)
        query = " ".join(w["query"].lower().split())
        for retailer_id in targets:
            if retailer_id not in by_id:
                continue
            key = f"search:{retailer_id}:{query}:{w['franchise'] or '*'}"
            interval = w["interval_seconds"] or search_interval
            existing = jobs.get(key)
            if existing:
                existing["payload"]["store_ids"] = _merge_stores(existing["payload"]["store_ids"], w["store_ids"])
                existing["payload"]["watch_ids"].append(w["id"])
                existing["interval"] = min(existing["interval"], interval)
            else:
                jobs[key] = dict(
                    key=key, kind="watch_search", retailer_id=retailer_id, interval=interval,
                    payload={
                        "query": query, "franchise": w["franchise"],
                        "store_ids": w["store_ids"], "watch_ids": [w["id"]],
                    },
                )
    return list(jobs.values())
