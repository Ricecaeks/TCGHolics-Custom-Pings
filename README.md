# TCGHolics Custom Pings

Monitors NZ retailers for TCG products (Pokémon, One Piece, Riftbound, MTG, Lorcana, Yu-Gi-Oh!) and posts alerts to the [TCGHolics](https://tcgholics.co.nz) Discord. Alerts are routed per retailer and per physical store. For example, a stock change for Pokémon 30th Booster Bundles at Farmers Westgate goes to `#farmers-westgate`.

**Alert types:** new listing · restock · stock-quantity increase · price change · out of stock (opt-in)

## How it works

```
 NUC 1 ─┐                                   ┌─> Discord webhooks (#farmers-westgate, ...)
 NUC 2 ─┼──>  Supabase Postgres  <──────────┤
 NUC 3 ─┘   (jobs, state, outbox)           └─> Discord bot (slash commands, leader only)
```

Every node runs the same container. Nodes coordinate only through Postgres:

- **Jobs.** Each watched product or keyword search is a row in `jobs`. Nodes claim due jobs with `FOR UPDATE SKIP LOCKED` and a short lease. When a node dies, its leases expire and other nodes take over the work.
- **Leader.** One node holds a Postgres advisory lock. It runs the Discord bot, turns watches into jobs, prunes old data and takes the nightly backup. If it dies, another node takes over in about 10–15 s.
- **Exactly-once alerts.** The state change and the alert are written in one transaction, protected by a row lock and a dedupe key, so one change produces one Discord message.
- **Polite fetching.** Rate limits are set per retailer and split across nodes that share an IP. Optional proxy pool with ban detection.

## Quick start

**One PC or laptop (current setup).** This runs Postgres and one monitor node, capped at 2 CPU threads and 2 GB of RAM:

1. Copy `.env.example` to `.env` and fill in the Discord values (see [docs/SETUP.md](docs/SETUP.md) §1). `DATABASE_URL` isn't needed here.
2. Start the stack:

   ```bash
   docker compose -f deploy/docker-compose.local.yml up -d --build
   ```

**[docs/HOSTING.md](docs/HOSTING.md)** covers resource use, gaming-friendly limits, the always-on laptop with auto-deploy, cloud options and how each retailer's bot protection is handled.

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

Day-to-day running is covered in **[docs/OPERATIONS.md](docs/OPERATIONS.md)**: adding nodes, `/status`, proxies, updates and backups. **[docs/RETAILERS.md](docs/RETAILERS.md)** lists each retailer's status.

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
2. Add `tcgpings/retailers/<name>.py`: subclass `RetailerAdapter`, decorate it with `@register`, set `default_retailers` and `supports_store_stock`, and implement `search`, `fetch_products`, `list_stores` and `store_stock`.
3. Import it in `tcgpings/retailers/__init__.py`.
4. Save real responses under `tests/fixtures/<name>/` and add parser tests.
