# Operations

## Health

- **`/status` in Discord:**
  - every node, with a 👑 next to the leader, when it last checked in, and its job and alert counts
  - each retailer: 🟢 healthy, 🟡 some jobs failing or overdue, 🔴 every job failing
  - paused product checks (see "Rate limits and blocks")
  - the alert queue, database size and proxy health
- **Staff log channel (`LOG_CHANNEL_ID`):** the leader posts ⚠️ when a node stops checking in, a retailer's jobs all fail for 30 minutes, alerts can't be delivered, or the database passes 400 MB. It posts ✅ when the problem clears.
- **On a node:** see [Logs](#logs).
- **From any machine with `.env`:** `python -m tcgpings admin show` dumps retailers, watches, routes, nodes and job health.
- **Heartbeat (NUC):** every 15 minutes [`heartbeat.yml`](../.github/workflows/heartbeat.yml) checks that every container of the stack is healthy, that some job succeeded in the last 15 minutes, and that no alert has sat unsent for over 15 minutes. Alerts that gave up after 8 tries don't count; the log channel already warns about those. A failed run emails you, and after an hour of failures `watchdog.yml` posts "Stock alerts are offline" in Discord. The run's log says which check failed.

## Logs

The bot writes its log to `data/logs/bot.log`, inside the mounted data folder, so it survives restarts and redeploys. On the NUC that's `/opt/tcgpings/data/logs/bot.log` (`TCGPINGS_HOME`).

- A new file starts each day (UTC midnight) or when the file reaches 25 MB. The 7 newest old files are kept as `bot.log.1` (newest) to `bot.log.7`. That's about a week of history, and never more than 200 MB.
- Change it with `LOG_FILE_MAX_MB` and `LOG_FILE_KEEP` in `.env`. Set `LOG_DIR=` (empty) to turn the file off.
- Only the bot (`run`) writes the file; `probe`, `admin` and health checks print to the console only.

Reading them on the NUC (`ssh nuc`):

```bash
tail -n 200 -F /opt/tcgpings/data/logs/bot.log        # follow live
grep ERROR /opt/tcgpings/data/logs/bot.log*            # search every day kept
```

`docker logs tcgpings-node-1 --tail 200 -f` also works, but it only goes back to the last deploy, because every deploy replaces the container.

Database shell on the NUC: `docker exec -it tcgpings-db-1 psql -U tcgpings -d tcgpings`.

## Updating

Merge to `main`. CI runs the tests, then `deploy.yml` rebuilds and restarts the stack on the NUC through its self-hosted runner and waits until every container is healthy. Database migrations apply automatically on start. To redeploy without a code change, run the *deploy* workflow by hand (Actions → deploy → Run workflow).

## Backups

The leader writes `data/backups/tcgpings-<timestamp>.dump` once a day and keeps the newest 7. On the NUC that's `/opt/tcgpings/data/backups/`. Copy them somewhere off-site if you can.

To restore into the NUC's database (stop the bot first: `docker stop tcgpings-node-1`):

```bash
docker exec -i tcgpings-db-1 pg_restore --clean --if-exists --no-owner -U tcgpings -d tcgpings < /opt/tcgpings/data/backups/tcgpings-YYYYMMDD-HHMMSS.dump
```

To restore into a fresh Supabase project:

```bash
pg_restore --no-owner --no-privileges --dbname "$NEW_DATABASE_URL" data/backups/tcgpings-YYYYMMDD-HHMMSS.dump
```

## Rate limits and blocks

- Each retailer has a cluster-wide **requests per minute** budget (default 30), changed with `/retailer set requests_per_minute:`. Nodes behind the same public IP share the budget. Each additional IP or proxy adds capacity.
- Paid unblocker spend (ScrapFly, Zyte) is capped at US$100 a month across all retailers. A retailer can also get its own monthly limit with `/retailer set unblocker_limit_usd:` (0 removes it); `/status` shows each one's spend. See HOSTING.md §6.
- A 403, a 429 or a captcha page counts as **blocked**. The job backs off exponentially, up to 30 minutes.
- **Dead product checks pause themselves.** After 20 failures in a row that are all HTTP 403 or 404, a product check is paused. Timeouts and 5xx errors never pause a check. A paused check is retried once a day and resumes on its own as soon as a retry works. Each new pause is posted once to the staff log channel, and `/status` lists every paused check with its retailer, product, reason and pause time. Discovery and search jobs are never paused.
  - If a retailer stays 🔴, first try lowering its rate.
  - Next, try `proxy_policy:pool`.
  - If neither helps, the site probably changed. Run `python -m tcgpings probe <adapter> search <query>` to see the raw failure.

## Tuning check frequency

| Watch type | Default | Change with |
|---|---|---|
| Specific product (`/watch add query:<url>`) | 60 s | `interval:` on the watch |
| Keyword search | 300 s | `interval:` on the watch |
| Store list sync | 24 h | `STORE_SYNC_INTERVAL` in `.env` |

Each retailer has one keyword-search job (`search:<retailer>`) that runs all its keyword watches. It runs as often as the fastest of those watches, so a short `interval:` on one keyword watch makes every keyword at that retailer run that often. If one keyword's search fails, the others are still recorded; the job only shows as failing when every keyword failed. A keyword added to a retailer whose search job has already run gets its own silent baseline on its first run, as before.

Repeat alerts for the same product, store and state are suppressed for 15 minutes (`ALERT_COOLDOWN_SECONDS`), so stock flickering in and out doesn't spam channels.

## Moving to the cloud

The container is stateless. Run the same image on any VM or container host, using the same `.env` with a different `NODE_NAME`. Cloud nodes and NUCs can run side by side.
