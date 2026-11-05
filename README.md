# TCGHolics Custom Pings

Monitors NZ retailers for TCG products (Pokémon, One Piece, Riftbound, MTG, Lorcana, Yu-Gi-Oh!) and posts alerts to the [TCGHolics](https://tcgholics.co.nz) Discord. Alerts are routed per retailer, online and in store. For example, Pokémon 30th Booster Bundles coming back at Farmers Westgate and Albany is one alert in `#farmers-instore` listing both stores.

**Alert types:** new listing · restock · stock-quantity increase · price change · out of stock (opt-in)

## How it works

```
 NUC: one Docker Compose stack (project tcgpings)
 ┌─────────────────────────────────────────────────────────────┐
 │  control         leader: bot, planner, health, backups  ────┼──> Discord bot (slash commands)
 │  worker-http     plain-HTTP stores, 32 jobs at once         │
 │  worker-browser  Chrome / unblocker stores, 4 jobs at once  │
 │        │  all three send alerts  ───────────────────────────┼──> Discord webhooks (#farmers-instore, ...)
 │        ▼                                                    │
 │  db              Postgres 17: jobs, state, alert outbox     │
 └─────────────────────────────────────────────────────────────┘
```

Every container runs the same image as a node; settings decide what each one does. `control` stands for leader and claims no jobs, `worker-http` runs the plain-HTTP stores many at a time, and `worker-browser` runs the stores that need Chrome or a paid unblocker, a few at a time. Every node sends alerts. Nodes coordinate only through Postgres, so more nodes (on this machine or others) can join the same database:

- **Jobs.** Each watched product is a row in `jobs`, and so is each retailer's keyword search (one job runs every keyword for that retailer). Nodes claim due jobs, most overdue first, with `FOR UPDATE SKIP LOCKED` and a short lease. A node only claims jobs in its lanes (`WORKER_LANES`), and a store never has more than `MAX_INFLIGHT_PER_RETAILER` (3) jobs running at once. When a node dies, its leases expire and other nodes take over the work.
- **Leader.** One leader-eligible node (`LEADER_ELIGIBLE`) holds a Postgres advisory lock. It runs the Discord bot, turns watches into jobs, prunes old data and takes the nightly backup. If it dies, another node takes over in about 10–15 s.
- **Exactly-once alerts.** The state change and the alert are written in one transaction, protected by a row lock and a dedupe key, so one change produces one Discord message.
- **Polite fetching.** Rate limits are set per retailer and split across the nodes that share an IP and serve that retailer's lane. Optional proxy pool with ban detection.

## Quick start

**Production** runs on the NUC from [`deploy/docker-compose.nuc.yml`](deploy/docker-compose.nuc.yml), deployed by GitHub Actions on every merge to `main` (see [docs/HOSTING.md](docs/HOSTING.md) §2).

**One PC or laptop (development).** This runs Postgres and one monitor node, capped at 2 CPU threads and 2 GB of RAM:

1. Copy `.env.example` to `.env` and fill in the Discord values (see [docs/SETUP.md](docs/SETUP.md) §1). `DATABASE_URL` isn't needed here.
2. Start the stack:

   ```bash
   docker compose -f deploy/docker-compose.local.yml up -d --build
   ```

**[docs/ALERTS.md](docs/ALERTS.md)** is the staff guide to routes, keywords (e.g. `30th booster bundle, etb, upc, -sleeves`), role pings and add-to-cart links.

**[docs/HOSTING.md](docs/HOSTING.md)** covers resource use, the NUC and its auto-deploy, cloud options and how each retailer's bot protection is handled.

**Several machines (cluster):**

1. Follow **[docs/SETUP.md](docs/SETUP.md)** to set up Supabase and each machine.
2. On each machine:

   ```bash
   docker compose -f deploy/docker-compose.yml up -d --build
   ```

3. In Discord:
   - `/retailer add-shopify domain:cardshop.co.nz name:Card Shop`
   - in the alert channel, `/route set retailer:card-shop`
   - `/watch add query:pokemon booster bundle`
   - `/test-alert`

Day-to-day running is covered in **[docs/OPERATIONS.md](docs/OPERATIONS.md)**: adding nodes, `/status`, proxies, updates and backups. **[docs/RETAILERS.md](docs/RETAILERS.md)** lists each retailer's status, and **[docs/ROADMAP.md](docs/ROADMAP.md)** what's next, including the parked unblocker add-on.

## Development

```bash
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
docker compose -f deploy/docker-compose.dev.yml up -d db       # Postgres on localhost:54329
.venv/bin/pytest                                                # unit + database + cluster tests
```

Check a retailer live, with no database or Discord:

```bash
python -m tcgpings probe shopify search "booster bundle" --set domain=cardmerchant.co.nz
```

Run a local 3-node cluster that logs alerts instead of posting them:

```bash
docker compose -f deploy/docker-compose.dev.yml --profile cluster up --build --scale node=3
```

### Adding a retailer

1. Recon: open the site in a browser with devtools on the Network tab. Find the JSON calls behind search, the product page and "check stock in store". Record them in `docs/RETAILERS.md`.
2. Add `tcgpings/retailers/<name>.py`: subclass `RetailerAdapter`, decorate it with `@register`, set `default_retailers` and `supports_store_stock`, and implement `search`, `fetch_products`, `list_stores` and `store_stock`. If every search re-reads the same pages, also override `search_many` to read them once for all keywords (as Shopify does).
3. Import it in `tcgpings/retailers/__init__.py`.
4. Save real responses under `tests/fixtures/<name>/` and add parser tests.
