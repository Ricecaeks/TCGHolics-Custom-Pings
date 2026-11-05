# Roadmap

What's built, what's next, and what's parked. Reviewed 2026-11-05. Each numbered item ships as its own PR.

## Built

| Area | Status |
|---|---|
| Core platform: job leasing, leader election, outbox, keyword routes, discovery, Docker stack, auto-deploy | done |
| Channel layout (`layout.json`): categories, channels, webhooks and routes kept in sync every 10 minutes | done |
| Every alert needs stock: a ping means it can be bought online or is on a shelf now (out-of-stock alerts are opt-in) | done |
| Fetch chain (Chrome → ScrapFly → Zyte) with circuit breakers and a monthly spend cap | done |
| JB Hi-Fi, Kmart, Farmers, Toyworld: listings, price, online and per-store stock | live |
| The Warehouse: listings, price, online stock | live |
| Mighty Ape (ScrapFly), Whitcoulls, Paper Plus, Retrospace | live |
| 24 independent Shopify card shops | live |
| Pokémon Center NZ / AU / UK (Zyte), with queue alerts | live |
| P-Bandai NZ (its search API) | live |
| Member `/ping` keywords, `/spotted` reports, hot sets with news-fed approval cards | live |

## Wave 1: reliability

1. **Price-flap damping.** Skip a price-change alert when the new price is one the product had in the last 24 h. On 2026-11-04, 314 of 602 alerts were 4 products bouncing between two prices.
2. **Silent-break alarms.** Warn the log channel when a scan finds 0 products, under half the usual count, or nothing succeeds for 3× the check interval. Today a 0-product scan counts as success.
3. **Send queue hardening.** One malformed alert can't block the queue (it counts attempts and dead-letters after 8). A retry doesn't resend ping messages that already went out.
4. **Pause dead checks.** Pause a product check after 20 failures in a row with 403 or 404, report it once, and list paused checks in `/status`.
5. **Spend per store.** Record paid unblocker spend per retailer, including billed failures. The monthly cap rises to $100.
6. **Keep logs, real heartbeat.** Keep rotating log files on disk. The heartbeat checks that jobs and alerts ran recently, not just that the container is up.

## Wave 2: Zephyr cutover

7. **Boardertown** (OpenCart adapter).
8. **Poke Piece** (Wix adapter).
9. **Hobby Lords** through Zyte (Cloudflare).
10. **tcg.co.nz**: look first; build only if the site has real stock data.
11. **Side by side for 7 days**, then remove Zephyr's webhooks and channels (owner's go-ahead), the Zephyr bot and its subscription.

## Wave 3: alert quality

12. **Classifier.**
    - Tag the language instead of dropping "[Japanese]" sealed product.
    - Fix the "Trainers Toolkit" and "Premium Figure Collection" false drops.
    - Add set aliases, so titles without "Pokémon" still match.
    - Add Star Wars Unlimited, Flesh and Blood, Digimon, Final Fantasy, Weiss Schwarz and Union Arena.
    - Treat display cases and mystery repacks as not sealed.
    - Add per-shop title include/exclude filters.
13. **Data cleanup.** Stop storing single cards. Rows unseen for 3+ days become unknown instead of "in stock". Fill in missing product types and remove junk rows.
14. **Pokémon Center check.** Confirm "0 in stock" against product pages.

## Wave 4: member features

15. **Self-assign game roles** with role pings in the game channels.
16. **`/ping` filters:** store, online vs in-store, max price, quiet hours, DM delivery.
17. **New alert types:** pre-order opened, purchase limit changed.
18. **Release calendar** with reminders, and a weekly digest (top drops, how fast they sold out).
19. **Staff tools:**
    - Shopify settings in `/retailer set`.
    - `/retailer remove`.
    - Mute a product.
    - Remove a `/spotted` report.

## Wave 5: more NZ stores

20. **WooCommerce adapter** (Fire Spin Hobby, and future Woo shops).
21. **Lightspeed** (Games Lab) and **ComicHub** (Heroes for Sale, Comics Compulsion).
22. **Big-box recon:** Noel Leeming and Woolworths. Also find URLs for the remaining named hobby shops.

## Ongoing: engineering hygiene

- ruff and mypy in CI.
- Shared adapter helpers: the Constructor.io client (Farmers, Kmart), JSON-LD product parsing (5 adapters) and "left the listings".
- Refresh the README diagram (one PC, local Postgres) and `OPERATIONS.md`. Add a "write an adapter" guide.
- Copy backups off the host automatically.

## Later

- **Paid tiers** (Whop).
- **One alert per product across stores**, edited when it sells out.
- **A second host.** Stay on the local Postgres while everything runs on one machine: the stack sends about 8 GB/month of database traffic, more than Supabase Free's egress allowance. Move to a hosted database when a second machine or cloud host joins; it's a `DATABASE_URL` change.
- **NZ residential proxy** for the Chrome route (`tcgpings/net/browser.py` doesn't take a proxy yet).
- **Shorter data retention:** 2 days for sent alerts and change history, and removal of products unseen for 14 days.
