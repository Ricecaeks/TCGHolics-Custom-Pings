# Operations

## Health

- **`/status` in Discord:**
  - every node, with a 👑 next to the leader, when it last checked in, and its job and alert counts
  - each retailer: 🟢 healthy, 🟡 some jobs failing or overdue, 🔴 every job failing
  - the alert queue, database size and proxy health
- **Staff log channel (`LOG_CHANNEL_ID`):** the leader posts ⚠️ when a node stops checking in, a retailer's jobs all fail for 30 minutes, alerts can't be delivered, or the database passes 400 MB. It posts ✅ when the problem clears.
- **On a node:** `docker compose -f deploy/docker-compose.yml logs -f --tail 200`
- **From any machine with `.env`:** `python -m tcgpings admin show` dumps retailers, watches, routes, nodes and job health.

## Adding a NUC

Follow SETUP.md step 4 on the new machine, with a new `NODE_NAME`. That's all. The node registers itself and starts claiming jobs within seconds, and the rate limit for nodes sharing an IP is re-split automatically.

## Removing or replacing a NUC

Stop it with `docker compose -f deploy/docker-compose.yml down`. Its jobs move to the other nodes once their leases expire, within 2 minutes, or straight away on a clean stop. The old node shows 🔴 in `/status` for 24 hours and then drops out of the warnings.

## Updating

From a machine that can SSH to the NUCs:

```bash
scripts/rollout.sh nuc1 nuc2 nuc3
```

The script updates one node at a time: `git pull`, rebuild, then wait for the node to be healthy before moving to the next. Database migrations apply automatically; the first node to start takes a lock and runs them.

## Backups

The leader writes `data/backups/tcgpings-<timestamp>.dump` once a day and keeps the newest 7. Because leadership moves between nodes, check every NUC's `data/backups/` when looking for the latest dump. Copy them somewhere off-site if you can.

To restore into a fresh Supabase project:

```bash
pg_restore --no-owner --no-privileges --dbname "$NEW_DATABASE_URL" data/backups/tcgpings-YYYYMMDD-HHMMSS.dump
```

## Rate limits and blocks

- Each retailer has a cluster-wide **requests per minute** budget (default 30), changed with `/retailer set requests_per_minute:`. Nodes behind the same public IP share the budget. Each additional IP or proxy adds capacity.
- A 403, a 429 or a captcha page counts as **blocked**. The job backs off exponentially, up to 30 minutes.
  - If a retailer stays 🔴, first try lowering its rate.
  - Next, try `proxy_policy:pool`.
  - If neither helps, the site probably changed. Run `python -m tcgpings probe <adapter> search <query>` to see the raw failure.

## Tuning check frequency

| Watch type | Default | Change with |
|---|---|---|
| Specific product (`/watch add query:<url>`) | 60 s | `interval:` on the watch |
| Keyword search | 300 s | `interval:` on the watch |
| Store list sync | 24 h | `STORE_SYNC_INTERVAL` in `.env` |

Repeat alerts for the same product, store and state are suppressed for 15 minutes (`ALERT_COOLDOWN_SECONDS`), so stock flickering in and out doesn't spam channels.

## Moving to the cloud

The container is stateless. Run the same image on any VM or container host, using the same `.env` with a different `NODE_NAME`. Cloud nodes and NUCs can run side by side.
