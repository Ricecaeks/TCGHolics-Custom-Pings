# Setting up alerts (staff guide)

Everything here is done from Discord with slash commands. Only server admins and the staff role (`STAFF_ROLE_ID`) can run them.

## The server's alert channels (layout)

Which channel gets which alerts is written down in [`tcgpings/discord/layout.json`](../tcgpings/discord/layout.json). Every 10 minutes the bot applies it on its own (`/layout` previews it, `/layout apply:True` applies it now):

- **Existing channel:** the bot makes its own webhook there (needs **Manage Webhooks**) and saves the channel's routes.
- **Missing channel:** created in its category; a channel listed under an old name (`"was": ["kmart"]`) is renamed. Both need **Manage Channels**. Without it, an old-named channel is still used as it is, and the staff channel is told what's missing.
- **Routes follow the file:** a changed entry replaces its routes, a removed one deletes them. Routes made by hand with `/route set` or `/route pings` are never touched.
- **Renaming or moving a linked channel is fine:** the bot follows it by its Discord ID and keeps its alerts there. Deleting one makes the bot create it again; take it out of `layout.json` instead.
- **Every alert needs stock:** a ping means it can be bought online or is on a shelf right now. A product listed sold out (or with no stock shown) posts when it comes into stock, and a price change on a sold-out product doesn't post at all. The exceptions are `out_of_stock` alerts (opt-in) and queue alerts.
- An alert posts once in every channel whose route matches. A Pokémon 30th restock at Kmart Albany goes to `#kmart-instore`, `#pokemon-store-restocks` and, for members whose `/ping` keywords match, `#custom-pings`.

| Channel | Gets |
|---|---|
| `#kmart-online` / `#kmart-instore` (same for Farmers, JB Hi-Fi, Toyworld) | that retailer, all games, online vs in-store |
| `#the-warehouse`, `#paper-plus`, `#whitcoulls` | that retailer |
| `#card-shop-sites` | every Shopify card shop, plus Retrospace |
| `#pokemon-online-shops` / `#onepiece-online-shops` | that game in stock **online**, any retailer: new listings and restocks |
| `#pokemon-store-restocks` / `#onepiece-store-restocks` | that game in stock **at a physical store**, any retailer, plus member sightings |
| `#pokemon-jb-hifi` | Pokémon at JB Hi-Fi |
| `#pokemon-center-nz` / `-au` / `-uk` | that Pokémon Center store: sealed TCG listings, restocks and queue alerts |
| `#p-bandai-nz` | Premium Bandai NZ card game pre-orders (One Piece, Gundam, Dragon Ball) when they open; also reach the game channels |
| `#lorcana-alerts`, `#magic-alerts`, `#riftbound-alerts`, `#dragonball-alerts`, `#yugioh-alerts`, `#gundam-alerts` | that game anywhere: new listings, restocks, sightings |

**Overseas stores** (Pokémon Center AU and UK) only post in channels that name them. They stay out of the game channels, the catch-all and member `/ping`s, because they don't ship to NZ.

To change it, edit `layout.json` (each route takes `retailer` or `adapter`, `store`: online/instore, `game`, `events`, `keywords`, `role`) and deploy. `CHANNEL_LAYOUT=false` turns it off.

## First-time setup: one command

```
/setup                      preview the layout (nothing is created)
/setup confirm:True         build it
/setup retailer:jbhifi confirm:True role:@Pokemon   one retailer, with a role ping
```

For every enabled retailer with stores (Farmers, JB Hi-Fi, Kmart) this creates two channels in a **Retailers** category:
- **`#<retailer>-online`** for online alerts: new listings, online stock, price (`#farmers-online`, `#kmart-online`),
- **`#<retailer>-instore`** for every store's stock in one place (`#farmers-instore`, `#kmart-instore`). A product that comes back at several stores in the same check is **one alert listing the stores**, not one per store.

Each channel gets a webhook and a route saved in the database. Retailers without store stock (The Warehouse, card shops) get one channel each in an **Online Stores** category. Past Discord's 50-channels-per-category limit a category continues as `Retailers 2`.

**You don't have to run it.** The bot checks every 10 minutes and builds channels for any newly enabled retailer, and recreates a routed channel that was deleted, posting what it did to the staff log channel. `/setup` is still there to preview, or to add a role ping. Turn this off with `AUTO_SETUP=false`.

Move, rename or re-sort the channels and categories however you like: routes follow the channel, not its name or place. Re-running `/setup` only fills gaps (a deleted channel is recreated, existing ones are left alone). The preview shows how many channels the server would have against Discord's 500 limit. Add keywords per channel afterwards with `/route keywords`.

## Member keyword pings

Any member can set their own keywords, and alerts that match tag them in one channel.

```
/ping add keywords: 30th booster bundle, -sleeves
/ping add keywords: 30th albany
/ping list
/ping remove ping_id: 3
```

- Keywords match the product title, game, retailer and store names, so `kmart albany` and `pokemon online` both work. The syntax is the same as route keywords below.
- Only new listings and restocks ping. Price changes and stock count increases don't.
- Each member can have 25.

Staff choose the channel by running `/route pings` in it (e.g. `#custom-pings`). The channel only gets alerts someone asked for.

For retailers with store stock, a keyword can only match a store when that product is being checked per store. JB Hi-Fi, Toyworld and Kmart check every sealed product. Farmers only checks products matching a watch or keyword route, because each check costs money.

## Hot sets

The bot reads public news feeds every 3 hours (PokéBeach, plus Google News for each game) and posts a card to the staff channel (`LOG_CHANNEL_ID`) for each release it hasn't seen, up to 5 at a time. **Approve** lets you edit the keyword, then searches every retailer for it and speeds up its store checks for 14 days. **Ignore** drops it.

```
/hot add keyword: delta reign days: 14
/hot list
/hot remove keyword: delta reign
```

- Faster checks are free ones only: JB Hi-Fi every 2 minutes and Toyworld every 5. Farmers stays daily because each check costs money, and Kmart isn't sped up because Akamai challenges it.
- The bot doesn't read pokemon.com directly, because it answers automated requests with a bot wall.

## Member sightings

Website checks can't see every store, and stock can reach the shelf before a website knows. `/spotted` lets members report what they've seen:

```
/spotted product: 30th Booster Bundle retailer: The Warehouse store: Westgate note: limit 2
```

- It goes out as a clearly labelled **Spotted in store** alert that names the reporter and says the retailer hasn't confirmed it.
- It tags members whose `/ping` keywords match, and also posts to routes that don't limit their event types.
- Staff and members with the `MEMBERS_ROLE_ID` role can use it, up to 5 reports an hour each. The same report within about 15 minutes posts once.
- Retailer and store are free text, with suggestions for ones we know, so any shop can be reported.

## One channel for everything (beta)

To see every alert in one place without the bot, create a webhook in that channel and set `ALERT_WEBHOOK_URL` (from the `TEST_CHANNEL_WEBHOOK` repository secret, copied to the deploy machine's `.env`). `DRY_RUN` must be `false` for alerts to actually post. Alerts use the webhook's own name and picture; [`assets/logo.png`](../assets/logo.png) is the logo.

## How alerts work

1. **Discovery runs on its own.** Every enabled retailer's TCG range is scanned every 2–3 minutes for new listings, stock changes and price changes. You don't need to "watch" anything for this.
2. **Routes decide what goes where.** A route says "alerts from *this retailer / store / game*, whose title matches *these keywords*, go to *this channel*, pinging *this role*". A channel can have several routes.
3. **Watches are for hot sets.** `/watch add query:...` searches every retailer, so a named set like `delta reign` is found even where a category scan doesn't reach it. They also suit a specific product URL. Member `/ping` keywords only filter alerts for products already found, so add a watch when a new set is announced. Found products at Farmers get a paid daily store check.

Only **sealed product** from Pokémon, One Piece, Riftbound, Magic, Lorcana and Yu-Gi-Oh! is announced from discovery and watches. Singles, sleeves, portfolios and other merch are skipped.

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
| `new_product` | a product appears for the first time with stock (one listed sold out posts as a `restock` later) | on |
| `restock` | out of stock → in stock (online or at a store) | on |
| `qty_change` | stock goes up, or Low ↔ In | on |
| `price_change` | online price changes while in stock (going back to a price it had in the last 24 h doesn't alert) | on |
| `out_of_stock` | in stock → out | **off** (add `events:out_of_stock` to opt in) |
| `queue` | a shop turns its waiting room on (Pokémon Center during big drops) | on (also in `#pokemon-online-shops`) |

The first scan of a new retailer or watch is a silent baseline, so adding things never floods channels. The exception is a brand-new product: if it was announced as a new listing in the last 24 hours, its first in-store reading that shows stock posts as an in-store restock, so a drop that's only on shelves (common at Kmart) still reaches `-instore` and `-store-restocks` channels. Repeat alerts for the same product, store and state are suppressed for 15 minutes.

## Store-level tracking

For retailers with store stock (JB Hi-Fi and Farmers), products that match **any keyword route** for that retailer get their own per-store checks automatically, up to 150 per retailer. Products stop being tracked when no keyword route matches them any more.

Farmers' site says store stock was "updated at 8am this morning" (fixed text, not proven), so each tracked product is checked **once a day between 8:30 and 9:30am**, together with its price. Those checks go through the fetch chain (our own Chrome, then ScrapFly, then Zyte; see [HOSTING.md §6](HOSTING.md#6-farmers-status-and-next-steps)).

## Current retailer coverage

| Retailer | New listings | Online stock | Price | Per-store stock | Add-to-cart |
|---|---|---|---|---|---|
| JB Hi-Fi | ✅ | ✅ | ✅ | ✅ 27 stores | ✅ |
| Farmers | ✅ (via Constructor) | ✅ | ✅ daily | ✅ daily, 53 stores (via the fetch chain) | — |
| The Warehouse | ✅ | ✅ (incl. "in stores only") | ✅ | — | — |
| Toyworld | ✅ | ✅ | ✅ | ✅ 36 stores, in / low / out | ✅ |
| The Warehouse | ✅ | ✅ | ✅ | Nationwide only, plus `/spotted` for named stores | — |
| Shopify card shops | ✅ | ✅ | ✅ | — | ✅ |
| Kmart | ✅ (via Constructor) | ✅ (most Pokémon is in-store only) | ✅ | ✅ 28 stores, with unit counts | — |
| Noel Leeming, … | coming | | | | |
