"""Leader-only: derive the jobs table from watches + retailers."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any

from tcgpings.retailers.base import REGISTRY


def sku_job_key(retailer_id: str, sku: str) -> str:
    return f"sku:{retailer_id}:{sku}"


def search_job_key(retailer_id: str) -> str:
    """The one keyword-search job per retailer. Its payload lists every query: see plan_jobs."""
    return f"search:{retailer_id}"


def _earliest(a: datetime | None, b: datetime | None) -> datetime | None:
    return min(a, b) if a and b else a or b


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
    discover_interval: int = 180,
) -> list[dict]:
    retailers = [r for r in retailers if r["enabled"] and r["adapter"] in REGISTRY]
    by_id = {r["id"]: r for r in retailers}
    jobs: dict[str, dict] = {}

    for r in retailers:
        cls = REGISTRY[r["adapter"]]
        if cls.supports_store_stock or cls.stock_in_listings:
            key = f"stores:{r['id']}"
            jobs[key] = dict(key=key, kind="sync_stores", retailer_id=r["id"], payload={}, interval=store_sync_interval)
        if cls.supports_discovery:
            key = f"discover:{r['id']}"
            jobs[key] = dict(key=key, kind="discover", retailer_id=r["id"], payload={},
                             interval=cls.default_discover_interval or discover_interval)

    for w in watches:
        if not w["enabled"]:
            continue
        if w["kind"] == "sku":
            if w["retailer_id"] not in by_id:
                continue
            key = sku_job_key(w["retailer_id"], w["query"])
            cls = REGISTRY[by_id[w["retailer_id"]]["adapter"]]
            interval = w["interval_seconds"] or cls.default_sku_interval or sku_interval
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
            cls = REGISTRY[by_id[retailer_id]["adapter"]]
            if not cls.supports_search:
                continue
            # One job per retailer runs all its keywords, so pages every search reads (Shopify's
            # catalogue) are fetched once per run instead of once per keyword.
            key = search_job_key(retailer_id)
            interval = w["interval_seconds"] or cls.default_search_interval or search_interval
            job = jobs.get(key)
            if job is None:
                job = jobs[key] = {"key": key, "kind": "watch_search", "retailer_id": retailer_id,
                                   "interval": interval, "payload": {"queries": []}}
            job["interval"] = min(job["interval"], interval)
            entries = job["payload"]["queries"]
            entry = next((e for e in entries if (e["query"], e["franchise"]) == (query, w["franchise"])), None)
            if entry:
                entry["store_ids"] = _merge_stores(entry["store_ids"], w["store_ids"])
                entry["watch_ids"].append(w["id"])
                entry["since"] = _earliest(entry["since"], w.get("created_at"))
            else:
                entries.append({"query": query, "franchise": w["franchise"], "store_ids": w["store_ids"],
                                "watch_ids": [w["id"]], "since": w.get("created_at")})

    for job in jobs.values():
        if job["kind"] == "watch_search":
            entries = job["payload"]["queries"]
            entries.sort(key=lambda e: (e["query"], e["franchise"] or ""))
            for e in entries:  # payloads are JSON
                e["since"] = e["since"].isoformat() if isinstance(e["since"], datetime) else e["since"]
    return list(jobs.values())
