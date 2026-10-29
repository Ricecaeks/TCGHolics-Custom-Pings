"""CLI: `python -m tcgpings <command>`. See `--help` on each command."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from dataclasses import asdict
from pathlib import Path

from tcgpings.config import Settings


def _setup_logging(settings: Settings) -> None:
    logging.basicConfig(
        level=settings.log_level.upper(),
        format=f"%(asctime)s {settings.node_name} %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    logging.getLogger("discord").setLevel(logging.WARNING)


# --- probe: hit a retailer live without a database or Discord ----------------------------


async def _probe(args: argparse.Namespace) -> None:
    from tcgpings.engine.pipeline import classify_product
    from tcgpings.net.http import HttpClient
    from tcgpings.retailers import REGISTRY, build_adapter

    if args.adapter not in REGISTRY:
        raise SystemExit(f"unknown adapter {args.adapter!r}; known: {', '.join(REGISTRY)}")
    config = dict(kv.split("=", 1) for kv in args.set)
    row = {
        "id": args.adapter, "adapter": args.adapter, "name": args.adapter, "config": config,
        "requests_per_minute": args.rpm, "proxy_policy": "pool" if args.proxy else "direct", "color": None,
    }
    from tcgpings.net.proxies import ProxyPool

    async with HttpClient(ProxyPool([args.proxy] if args.proxy else [])) as http:
        adapter = build_adapter(row, http)
        started = time.monotonic()
        if args.action == "search":
            out = [asdict(classify_product(p)) for p in await adapter.search(" ".join(args.args))]
        elif args.action == "product":
            out = [asdict(classify_product(p)) for p in await adapter.fetch_products([adapter.parse_ref(a) for a in args.args])]
        elif args.action == "stores":
            out = [asdict(s) for s in await adapter.list_stores()]
        elif args.action == "stock":
            out = {k: asdict(v) for k, v in (await adapter.store_stock(args.args[0], args.store)).items()}
        else:
            raise SystemExit(f"unknown action {args.action}")
    print(json.dumps(out, indent=2, default=str, ensure_ascii=False))
    print(f"# {len(out)} results in {time.monotonic() - started:.1f}s", file=sys.stderr)


# --- admin: headless setup (also useful without the Discord bot) -------------------------


async def _admin(args: argparse.Namespace, settings: Settings) -> None:
    from tcgpings.db import queries
    from tcgpings.db.pool import create_pool, migrate
    from tcgpings.models import ONLINE, slugify

    pool = await create_pool(settings.database_url, 2)
    try:
        await migrate(pool)
        if args.admin == "add-shopify":
            rid = args.id or slugify(args.name)
            await queries.upsert_retailer(pool, rid, "shopify", args.name, {"domain": args.domain})
            print(f"retailer {rid} ok")
        elif args.admin == "add-watch":
            wid = await queries.add_watch(
                pool, args.kind, args.query, args.retailer, args.stores or None, args.franchise, args.interval
            )
            print(f"watch #{wid} added (jobs appear at the leader's next reconcile, within 30s)")
        elif args.admin == "add-route":
            store = ONLINE if args.store == "online" else args.store
            rid = await queries.add_route(
                pool, args.channel_id, args.webhook, args.retailer, store, args.franchise, args.events or None, args.role
            )
            print(f"route #{rid} added")
        elif args.admin == "show":
            for title, rows in (
                ("retailers", await queries.list_retailers(pool)),
                ("watches", await queries.list_watches(pool)),
                ("routes", await queries.list_routes(pool)),
                ("nodes", await queries.list_nodes(pool)),
                ("job health", await queries.job_health(pool)),
            ):
                print(f"== {title}")
                for r in rows:
                    d = dict(r)
                    d.pop("webhook_url", None)
                    print("  ", json.dumps(d, default=str))
    finally:
        await pool.close()


def _health(settings: Settings) -> int:
    path = Path(settings.data_dir) / "heartbeat"
    try:
        age = time.time() - float(path.read_text())
    except (OSError, ValueError):
        return 1
    return 0 if age < settings.heartbeat_seconds * 4 else 1


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="tcgpings")
    sub = parser.add_subparsers(dest="cmd", required=True)

    run_p = sub.add_parser("run", help="run this node (worker + sender + leader election)")
    run_p.add_argument("--dry-run", action="store_true", help="log alerts instead of posting to Discord")
    sub.add_parser("migrate", help="apply database migrations and exit")
    sub.add_parser("health", help="exit 0 if this node's heartbeat is fresh (Docker healthcheck)")

    probe = sub.add_parser("probe", help="query a retailer live, no database needed")
    probe.add_argument("adapter")
    probe.add_argument("action", choices=["search", "product", "stores", "stock"])
    probe.add_argument("args", nargs="*")
    probe.add_argument("--set", action="append", default=[], metavar="KEY=VALUE", help="adapter config, e.g. domain=x.co.nz")
    probe.add_argument("--store", action="append", default=[], help="store id (for stock)")
    probe.add_argument("--proxy", help="proxy URL to send requests through")
    probe.add_argument("--rpm", type=float, default=60)

    admin = sub.add_parser("admin", help="manage retailers/watches/routes from the shell")
    asub = admin.add_subparsers(dest="admin", required=True)
    a = asub.add_parser("add-shopify")
    a.add_argument("domain")
    a.add_argument("name")
    a.add_argument("--id")
    a = asub.add_parser("add-watch")
    a.add_argument("query")
    a.add_argument("--kind", choices=["keyword", "sku"], default="keyword")
    a.add_argument("--retailer")
    a.add_argument("--stores", nargs="*")
    a.add_argument("--franchise")
    a.add_argument("--interval", type=int)
    a = asub.add_parser("add-route")
    a.add_argument("--webhook", required=True)
    a.add_argument("--channel-id", type=int, default=0)
    a.add_argument("--retailer")
    a.add_argument("--store", help="store id, or 'online'")
    a.add_argument("--franchise")
    a.add_argument("--events", nargs="*")
    a.add_argument("--role", type=int)
    asub.add_parser("show")

    args = parser.parse_args(argv)
    if sys.platform == "win32":  # curl_cffi needs a selector loop; production runs on Linux
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    settings = Settings()
    if getattr(args, "dry_run", False):
        settings.dry_run = True
    _setup_logging(settings)

    if args.cmd == "health":
        raise SystemExit(_health(settings))
    if args.cmd == "probe":
        asyncio.run(_probe(args))
        return
    if args.cmd == "admin":
        asyncio.run(_admin(args, settings))
        return
    if args.cmd == "migrate":
        from tcgpings.db.pool import create_pool, migrate

        async def _migrate() -> None:
            pool = await create_pool(settings.database_url, 1)
            print("applied:", await migrate(pool) or "nothing")
            await pool.close()

        asyncio.run(_migrate())
        return

    from tcgpings.app import run

    asyncio.run(run(settings))


if __name__ == "__main__":
    main()
