# Setup

Do steps 1–3 once. Do step 4 on every NUC.

## 1. Discord bot

1. Go to <https://discord.com/developers/applications> → **New Application** and name it `TCGHolics Pings`.
2. **Bot** tab:
   - Click **Reset Token** and copy the token. This is `DISCORD_TOKEN`; keep it secret.
   - Leave all *Privileged Gateway Intents* off. The bot doesn't need them.
3. **OAuth2 → URL Generator**:
   - Scopes: `bot`, `applications.commands`.
   - Bot permissions: **View Channels**, **Send Messages**, **Embed Links**, **Manage Webhooks**. **Manage Channels** lets the bot create the categories and channels for you.
   - Open the generated URL and add the bot to the TCGHolics server.
4. In Discord, turn on *User Settings → Advanced → Developer Mode*, then right-click to copy IDs:
   - the server → `GUILD_ID`
   - the staff role allowed to manage the bot → `STAFF_ROLE_ID` (server admins always can)
   - optionally, a private `#bot-health` channel → `LOG_CHANNEL_ID`

## 2. Supabase (database)

1. Go to <https://supabase.com> → **New project**. Pick the **Free** plan and the **Sydney (ap-southeast-2)** region, which is closest to NZ. Save the database password.
2. Go to **Project Settings → Database → Connection string**, choose **Session pooler**, and copy the URI into `DATABASE_URL`:
   ```
   postgresql://postgres.<ref>:<password>@aws-0-ap-southeast-2.pooler.supabase.com:5432/postgres?sslmode=require
   ```
   - Use the **session** pooler (port **5432**). The transaction pooler (port 6543) breaks leader election.
   - On the Free plan, the "Direct connection" is IPv6-only and most NZ home connections don't have IPv6. The session pooler works over IPv4.
3. Optional: create a dedicated database role instead of `postgres`. In the SQL editor:
   ```sql
   create role tcgpings login password 'choose-a-strong-password';
   grant create, usage on schema public to tcgpings;
   ```
   Then use `postgres.<ref>` → `tcgpings.<ref>` as the user in the URI.

Tables are created automatically when the first node starts. Every table has Row Level Security turned on with no policies, so Supabase's public Data API (anon key) can't read anything.

**Free plan limits:**
- 500 MB of storage. The app only keeps the latest state plus a change history, prunes it nightly, and warns at 400 MB.
- Free projects pause after about a week with no activity. Running nodes keep it active.
- No downloadable backups. The leader writes its own nightly `pg_dump` to `data/backups/`.

To upgrade to Pro later, click upgrade in the Supabase dashboard. Nothing in the app changes.

## 3. Proxies (optional)

Without proxies, every node fetches directly from its own IP. If the NUCs share one internet connection, the rate limits are automatically split between them.

To use a proxy provider, put its URLs in `PROXY_URLS`, comma-separated:

```
PROXY_URLS=http://user:pass@proxy.provider.com:8000
```

A retailer only uses proxies once its policy is set:
- `/retailer set retailer:<id> proxy_policy:pool` rotates through the proxies.
- `proxy_policy:sticky` pins the retailer to a single proxy.

If a proxy is blocked (403/429/captcha), it's benched for 10 minutes across the whole cluster.

## 4. Each NUC

1. Install Ubuntu Server 24.04 LTS. In the installer, enable OpenSSH and give the machine a hostname such as `nuc1`.
2. Install Docker:
   ```bash
   curl -fsSL https://get.docker.com | sudo sh
   sudo usermod -aG docker $USER && newgrp docker
   ```
3. Get the code and config:
   ```bash
   git clone https://github.com/Ricecaeks/TCGHolics-Custom-Pings.git
   cd TCGHolics-Custom-Pings
   cp .env.example .env
   nano .env
   ```
   Fill in `.env` with the values from steps 1–3, and give every machine its own `NODE_NAME`.
4. Start it:
   ```bash
   mkdir -p data
   docker compose -f deploy/docker-compose.yml up -d --build
   docker compose -f deploy/docker-compose.yml logs -f
   ```
   You should see `node nuc1 ... started`. On one node only, you should also see `is now the leader` and `discord bot connected`.
   - The container runs as uid 1000, which is the first user account on Ubuntu. If `data/` is owned by someone else, run `sudo chown 1000 data`.
5. The container restarts on its own after crashes and reboots (`restart: unless-stopped`).
6. Recommended:
   - Run `sudo apt install unattended-upgrades` to get security updates automatically.
   - In the BIOS, set the power-loss behaviour to "Power On".

## 5. First alerts

In Discord, as staff:

1. `/retailer add-shopify domain:<shop domain> name:<Shop Name>`. Use this for any Shopify-based NZ card shop.
2. In the channel that should get alerts, run `/route set retailer:<id>`. Add `role:@Pokemon` to ping a role.
3. `/test-alert`. A sample embed should appear within a few seconds.
4. `/watch add query:pokemon booster bundle`. The first check records a silent baseline. After that, anything new, restocked or changed price triggers an alert.
5. `/status` shows every node, retailer and the alert queue.

Run `/setup` to preview, then `/setup confirm:True`. It creates an online and an in-store channel per retailer (such as `#farmers-online` and `#farmers-instore`), one channel per online-only shop, and wires up each webhook and route. Once the bot is running it does this by itself for newly enabled retailers. See [ALERTS.md](ALERTS.md).
