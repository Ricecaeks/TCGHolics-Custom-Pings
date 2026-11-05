# Operations

## Health

- **`/status` in Discord:**
  - every node, with a 👑 next to the leader, when it last checked in, its job and alert counts, and its lanes
  - the job queue: how many due jobs are over 2 minutes late and how long the oldest has waited (🟡 any late, 🔴 oldest over 10 minutes)
  - each retailer: 🟢 healthy, 🟡 some jobs failing or overdue, 🔴 every job failing
  - paused product checks (see "Rate limits and blocks")
  - the alert queue, database size and proxy health
- **Staff log channel (`LOG_CHANNEL_ID`):** the leader posts ⚠️ when a node stops checking in, a retailer's jobs all fail for 30 minutes, alerts can't be delivered, the job queue's oldest due job has waited over 10 minutes, or the database passes 400 MB. It posts ✅ when the problem clears.
- **On a node:** see [Logs](#logs).
- **From any machine with `.env`:** `python -m tcgpings admin show` dumps retailers, watches, routes, nodes and job health.
- **Heartbeat (NUC):** every 15 minutes [`heartbeat.yml`](../.github/workflows/heartbeat.yml) checks that every container of the stack is healthy, that some job succeeded in the last 15 minutes, that no alert has sat unsent for over 15 minutes, and that jobs at no more than one store have waited over 20 minutes for a worker (one slow store alone shows as a warning in the run, not a failure). Alerts that gave up after 8 tries don't count; the log channel already warns about those. A failed run emails you, and after an hour of failures `watchdog.yml` posts "Stock alerts are offline" in Discord. The run's log says which check failed.

## Logs

Each node writes its own log to `data/logs/bot-<NODE_NAME>.log`, inside the mounted data folder, so it survives restarts and redeploys. The containers share that folder, so each has its own file and never rotates another's. On the NUC (`TCGPINGS_HOME` is `/opt/tcgpings`):

| Container | Node | Log file |
|---|---|---|
| `tcgpings-control-1` | `nuc-control` (leader, Discord bot) | `/opt/tcgpings/data/logs/bot-nuc-control.log` |
| `tcgpings-worker-http-1` | `nuc-http` (plain-HTTP stores) | `/opt/tcgpings/data/logs/bot-nuc-http.log` |
| `tcgpings-worker-browser-1` | `nuc-browser` (Chrome and unblocker stores) | `/opt/tcgpings/data/logs/bot-nuc-browser.log` |

- A new file starts each day (UTC midnight) or when the file reaches 25 MB. The 7 newest old files are kept as `bot-<node>.log.1` (newest) to `bot-<node>.log.7`. That's about a week of history, and never more than 200 MB per node.
- Change it with `LOG_FILE_MAX_MB` and `LOG_FILE_KEEP` in `.env`. Set `LOG_DIR=` (empty) to turn the file off.
- Only the bot (`run`) writes the file; `probe`, `admin` and health checks print to the console only.

Reading them on the NUC (`ssh nuc`):

```bash
tail -n 200 -F /opt/tcgpings/data/logs/bot-nuc-http.log   # follow one node live
tail -n 50 -F /opt/tcgpings/data/logs/bot-*.log            # every node at once
grep ERROR /opt/tcgpings/data/logs/bot-*.log*              # search every node and day kept
```

`docker logs tcgpings-worker-http-1 --tail 200 -f` (or `tcgpings-control-1`, `tcgpings-worker-browser-1`) also works, but it only goes back to the last deploy, because every deploy replaces the containers.

### #bot-logs in Discord

Every node's warnings and errors also go to **#bot-logs** in the Staff category, so you can read them from your phone.

- The leader creates the channel in the first category whose name contains "Staff", with that category's permissions. It checks every 10 minutes and recreates the channel if it's deleted. If there's no Staff category, it makes a private one that only `STAFF_ROLE_ID` and the bot can see. You can rename or move the channel; the bot finds it by its name, `bot-logs`.
- Each node posts every 30 seconds, as `logs · <node>`. Repeated lines are collapsed (`×4`). A node posts at most 3 messages at a time, and anything past that is counted ("… N more lines not posted") and left in the log file. Discord's rate limits can never slow the bot down.
- API keys, tokens and webhook links are hidden (`***`) before posting.
- `BOT_LOGS_LEVEL=INFO` in `.env` sends everything, which is very chatty; the default is `WARNING`. `BOT_LOGS_CATEGORY` picks another category; `BOT_LOGS_CHANNEL=` (empty) turns it off.
- If the bot can't make the channel (it needs Manage Channels and Manage Webhooks), it says so once in the staff log channel.

Database shell on the NUC: `docker exec -it tcgpings-db-1 psql -U tcgpings -d tcgpings`.

## Updating

Merge to `main`. CI runs the tests, then `deploy.yml` rebuilds and restarts the stack on the NUC through its self-hosted runner and waits until every container is healthy. Database migrations apply automatically on start. To redeploy without a code change, run the *deploy* workflow by hand (Actions → deploy → Run workflow).

## Backups

The leader writes `data/backups/tcgpings-<timestamp>.dump` once a day and keeps the newest 7. On the NUC that's `/opt/tcgpings/data/backups/`. Copy them somewhere off-site if you can.

To restore into the NUC's database (stop the bot first: `docker stop tcgpings-control-1 tcgpings-worker-http-1 tcgpings-worker-browser-1`):

```bash
docker exec -i tcgpings-db-1 pg_restore --clean --if-exists --no-owner -U tcgpings -d tcgpings < /opt/tcgpings/data/backups/tcgpings-YYYYMMDD-HHMMSS.dump
```

To restore into a fresh Supabase project:

```bash
pg_restore --no-owner --no-privileges --dbname "$NEW_DATABASE_URL" data/backups/tcgpings-YYYYMMDD-HHMMSS.dump
```

## Rate limits and blocks

- Each retailer has a cluster-wide **requests per minute** budget (default 30), changed with `/retailer set requests_per_minute:`. Nodes behind the same public IP that serve the retailer's lane share the budget; nodes in other lanes don't take a share. Each additional IP or proxy adds capacity.
- Paid unblocker spend (ScrapFly, Zyte) is capped at US$100 a month across all retailers. A retailer can also get its own monthly limit with `/retailer set unblocker_limit_usd:` (0 removes it); `/status` shows each one's spend. See HOSTING.md §6.
- A 403, a 429 or a captcha page counts as **blocked**. The job backs off exponentially, up to 30 minutes.
- **Dead product checks pause themselves.** After 20 failures in a row that are all HTTP 403 or 404, a product check is paused. Timeouts and 5xx errors never pause a check. A paused check is retried once a day and resumes on its own as soon as a retry works. Each new pause is posted once to the staff log channel, and `/status` lists every paused check with its retailer, product, reason and pause time. Discovery and search jobs are never paused.
  - If a retailer stays 🔴, first try lowering its rate.
  - Next, try `proxy_policy:pool`.
  - If neither helps, the site probably changed. Run `python -m tcgpings probe <adapter> search <query>` to see the raw failure.

## Containers, lanes and the job queue

Each retailer's jobs run in one **lane**: `browser` for the stores that use Chrome or the paid unblockers (Farmers, Kmart, Mighty Ape, Pokémon Center, The Warehouse), `http` for the rest. A node only claims jobs in its own lanes, so slow Chrome jobs can't keep the quick stores waiting. To move one store to the other lane, use `/retailer set retailer:<id> lane:http` (or `lane:browser`); `lane:default` goes back to its adapter's lane. This sets the `lane` key of the retailer's config. The lanes are listed in `tcgpings/cluster/lanes.py`.

Each store's products are checked as often as its adapter says (5 minutes for most). To check one store's products less often, for example a store whose checks are slow and keep falling behind, use `/retailer set retailer:<id> check_minutes:10`; `check_minutes:0` goes back to the adapter's default. This sets the `sku_interval` key of the retailer's config (in seconds). The leader applies it to every product job of that store within a minute. A watch with its own interval keeps it, and products in a hot set still get the faster hot checks.

Settings per container (set in `deploy/docker-compose.nuc.yml`, which overrides `.env`):

| Setting | Default | What it does |
|---|---|---|
| `WORKER_LANES` | `http,browser` | Lanes this node claims jobs for. Empty (or `none`): no jobs at all. |
| `WORKER_CONCURRENCY` | 8 | Jobs this node runs at once (`worker-http` 32, `worker-browser` 6). |
| `MAX_INFLIGHT_PER_RETAILER` | 3 | Jobs one store may have running at once, across all nodes. Due jobs of a store at its limit wait, and other stores' jobs go first. |
| `LEADER_ELIGIBLE` | `true` | `false`: this node never becomes leader. On the NUC only `control` may lead. |
| `DB_POOL_SIZE` | 4 | Database connections per node (`worker-http` 10). |

**Queue lag.** Due jobs are claimed most overdue first. `/status` shows how many are over 2 minutes late and how long the oldest has waited. The leader warns in the staff log when the oldest has waited over 10 minutes, and the heartbeat fails when jobs at two or more stores have waited over 20 (one slow store alone is only a warning, so it can't raise a false "offline" alarm). If it keeps happening, check which lane is behind (`/status` per retailer, overdue counts), then raise that worker's `WORKER_CONCURRENCY` or add a copy of it (see the comment at the top of the compose file). On a disabled retailer, or a paused check, nothing counts as late.

## Tuning check frequency

| Watch type | Default | Change with |
|---|---|---|
| Specific product (`/watch add query:<url>`) | 60 s | `interval:` on the watch |
| Keyword search | 300 s | `interval:` on the watch |
| Store list sync | 24 h | `STORE_SYNC_INTERVAL` in `.env` |

Each retailer has one keyword-search job (`search:<retailer>`) that runs all its keyword watches. It runs as often as the fastest of those watches, so a short `interval:` on one keyword watch makes every keyword at that retailer run that often. If one keyword's search fails, the others are still recorded; the job only shows as failing when every keyword failed. A keyword added to a retailer whose search job has already run gets its own silent baseline on its first run, as before.

Repeat alerts for the same product, store and state are suppressed for 15 minutes (`ALERT_COOLDOWN_SECONDS`), so stock flickering in and out doesn't spam channels.

## Moving to the cloud

The container is stateless. Run the same image on any VM or container host, using the same `.env` with a different `NODE_NAME`. Cloud nodes and NUCs can run side by side. Pick each node's `WORKER_LANES` and `LEADER_ELIGIBLE` to suit it.
