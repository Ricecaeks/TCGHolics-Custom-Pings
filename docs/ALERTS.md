# Setting up alerts (staff guide)

Everything here is done from Discord with slash commands. Only server admins and the staff role (`STAFF_ROLE_ID`) can run them.

## First-time setup: one command

```
/setup                      preview the layout (nothing is created)
/setup confirm:True         build it
/setup retailer:jbhifi confirm:True role:@Pokemon   one retailer, with a role ping
```

For every enabled retailer with stores (Farmers, JB Hi-Fi, Kmart) this creates two channels in a **Retailers** category:
- **`#<retailer>-online`** for online alerts: new listings, online stock, price (`#farmers-online`, `#kmart-online`),
- **`#<retailer>-instore`** for every store's stock in one place (`#farmers-instore`, `#kmart-instore`). A product that comes back at several stores in the same check is **one alert listing the stores**, not one per store.

Each channel gets a webhook and a route saved in the database. Retailers without store stock (The Warehouse, Toyworld, card shops) get one channel each in an **Online Stores** category. Past Discord's 50-channels-per-category limit a category continues as `Retailers 2`.

**You don't have to run it.** The bot checks every 10 minutes and builds channels for any newly enabled retailer, and recreates a routed channel that was deleted, posting what it did to the staff log channel. `/setup` is still there to preview, or to add a role ping. Turn this off with `AUTO_SETUP=false`.

Move, rename or re-sort the channels and categories however you like: routes follow the channel, not its name or place. Re-running `/setup` only fills gaps (a deleted channel is recreated, existing ones are left alone). The preview shows how many channels the server would have against Discord's 500 limit. Add keywords per channel afterwards with `/route keywords`.

## One channel for everything (beta)

To see every alert in one place without the bot, create a webhook in that channel and set `ALERT_WEBHOOK_URL` (from the `TEST_CHANNEL_WEBHOOK` repository secret, copied to the deploy machine's `.env`). `DRY_RUN` must be `false` for alerts to actually post. Alerts use the webhook's own name and picture; [`assets/logo.png`](../assets/logo.png) is the logo.

## How alerts work

1. **Discovery runs on its own.** Every enabled retailer's TCG range is scanned every 2–3 minutes for new listings, stock changes and price changes. You don't need to "watch" anything for this.
2. **Routes decide what goes where.** A route says "alerts from *this retailer / store / game*, whose title matches *these keywords*, go to *this channel*, pinging *this role*". A channel can have several routes.
3. **Watches are optional extras.** `/watch add query:...` adds a targeted search, which is useful for older products that discovery's "newest" scan wouldn't see, or for a specific product URL.

Only **sealed product** from Pokémon, One Piece, Riftbound, Magic, Lorcana and Yu-Gi-Oh! is announced from discovery. Singles, sleeves, portfolios and other merch are skipped.

## Keywords

```
/route set keywords: 30th booster bundle, elite trainer box, ultra premium collection, -sleeves
```

| You write | Meaning |
|---|---|
| `,` (comma) | separates alternatives: **any** of them can match |
| words in one alternative | **all** must appear in the title, in any order: `30th booster bundle` |
| `-word` or `-two words` | **exclude** titles containing it: `-sleeves`, `-code card`. Excludes always win |
| shorthands | `etb` = elite trainer box · `upc` = ultra premium collection · `spc` = super premium collection · `bb` = booster bundle · `pkm`/`ptcg` = Pokémon · `mtg` = Magic · `op` = One Piece · `ygo` = Yu-Gi-Oh |

Matching ignores case and accents ("pokemon" matches "Pokémon"). Words match from the start, so `bundle` matches "Bundles" but `box` doesn't match "Toolbox". A route with no keywords gets every sealed release for its filters.

**Try before you save:** `/keywords-test keywords: 30th, etb, -sleeves` shows which recently seen products would match.

**Change later:** `/route keywords route_id:<id> keywords:<new list>`. Leave `keywords` empty to clear it.

## Recipes

| Goal | Run in the target channel |
|---|---|
| Hype Pokémon sealed, anywhere, ping @Pokemon | `/route set franchise:Pokémon keywords:booster bundle, etb, upc, spc, booster box, -sleeves role:@Pokemon` |
| Pokémon 30th everything | `/route set keywords:30th pokemon` |
| Everything new at JB Hi-Fi | `/route set retailer:jbhifi events:new_product` |
| Restocks only, Farmers | `/route set retailer:farmers events:restock` |
| Online + in-store channels for every retailer | `/setup confirm:True` (or let auto-setup do it), then add keywords per channel with `/route keywords` |
| Every store of one retailer, in this channel | `/route set retailer:kmart store:instore` |
| A single store, with keywords | in e.g. `#farmers-westgate`: `/route set retailer:farmers store:Northwest keywords:booster bundle, etb` |
| Price drops on Magic | `/route set franchise:Magic: The Gathering events:price_change` |

## What an alert contains

- **Title:** links straight to **add to cart** where the retailer supports it (Shopify stores: JB Hi-Fi, independent card shops). Otherwise it links to the product page.
- **🛒 Add to cart · View product** links at the top.
- **Stock** before → after, **price**, **store** (or "*N* stores" with the list in `-instore` channels), and **game**.
- **Role ping** if the route has one.

## Event types

| Type | When | Default |
|---|---|---|
| `new_product` | a product appears for the first time | on |
| `restock` | out of stock → in stock (online or at a store) | on |
| `qty_change` | stock goes up, or Low ↔ In | on |
| `price_change` | online price changes | on |
| `out_of_stock` | in stock → out | **off** (add `events:out_of_stock` to opt in) |

The first scan of a new retailer or watch is a silent baseline, so adding things never floods channels. Repeat alerts for the same product, store and state are suppressed for 15 minutes.

## Store-level tracking

For retailers with store stock (JB Hi-Fi and Farmers), products that match **any keyword route** for that retailer get their own per-store checks automatically, up to 150 per retailer. Products stop being tracked when no keyword route matches them any more.

Farmers updates its store stock once a day (~8am), so each tracked product is checked **once a day between 8:30 and 9:30am**, together with its price. Those checks go through the fetch chain (our own Chrome, then ScrapFly, then Zyte; see [HOSTING.md §6](HOSTING.md#6-farmers-status-and-next-steps)).

## Current retailer coverage

| Retailer | New listings | Online stock | Price | Per-store stock | Add-to-cart |
|---|---|---|---|---|---|
| JB Hi-Fi | ✅ | ✅ | ✅ | ✅ 27 stores | ✅ |
| Farmers | ✅ (via Constructor) | ✅ | ✅ daily | ✅ daily, 53 stores (via the fetch chain) | — |
| The Warehouse | ✅ | ✅ (incl. "in stores only") | ✅ | — | — |
| Toyworld | ✅ | ✅ | ✅ | — | ✅ |
| Shopify card shops | ✅ | ✅ | ✅ | — | ✅ |
| Kmart | ✅ (via Constructor) | ✅ (most Pokémon is in-store only) | ✅ | per island: North / South | — |
| Noel Leeming, … | coming | | | | |
