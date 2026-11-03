# NZ Pokémon TCG & Trading-Card Specialty Online Stores (late 2026)

Research scope: dedicated New Zealand card/hobby online stores selling Pokémon TCG **sealed** product, with e-commerce platform signals and 30th Celebration / Mega Evolution availability, for a stock-alert bot. Platform detection was done with direct `curl` against each site (homepage markers + working `/products.json` and `/collections/<handle>/products.json` endpoints). Current as of 2026-11-04.

Note on terminology confirmed during research: the current anniversary set is literally branded **"Mega Evolution: 30th Celebration"** — i.e. 30th Celebration cards are part of the Mega Evolution block, alongside Mega Evolution base products (Perfect Order, Phantasmal Flames, etc.). Store product titles use the full string `Mega Evolution: 30th Celebration` / `Mega Evolution: 30th Celebration Classic Collection`.

## Store name, website URL, and e-commerce platform

### Takeaway
Three of the named NZ specialty stores are confirmed **Shopify** (Card Merchant, Iron Knight Gaming, Otakumart), each with a live `/products.json` — ideal for a bot. Two more NZ Shopify stores were found (GameKings, Hobby Zone). Fire Spin Hobby is **WooCommerce**. Many names on the brief (Grey Base, Punreal, Mana Gaming, Shuffle and Cut, VaultTCG, The Games Den, 1UP, Cerberus, Game Haven, Big Boys Hobbies, Sanctuary, Collectables NZ, Poké Mart NZ) could **not** be resolved to a live NZ e-commerce site and are listed as gaps.

### Cited Findings
- **Card Merchant NZ — https://cardmerchant.co.nz — Shopify (confirmed).** Homepage served `Shopify.theme`, `cdn.shopify.com` and `myshopify`; `/products.json` returns live product JSON. Collection handles include `pokemon`, `pokemon-sealed`, `pokemon-booster-packs`, `pokemon-collection-boxes`, `pokemon-scarlet-violet-151`, `pre-orders`. — verified via `curl https://cardmerchant.co.nz/products.json` and `/collections.json`
- **Iron Knight Gaming — https://ironknightgaming.co.nz — Shopify (confirmed).** Homepage served `Powered by Shopify`, `Shopify.theme`, `cdn.shopify.com`, `myshopify`; `/products.json` live. Collection handles include `pokemon-sealed` and `preorders`. Multi-TCG (first product returned was a Magic/Star Trek Commander deck). — verified via `curl https://ironknightgaming.co.nz/products.json` and `/collections.json`
- **Otakumart — https://otakumart.co.nz — Shopify (confirmed).** Homepage served `Shopify.theme`, `cdn.shopify.com`, `myshopify`; `/products.json` live. Very deep TCG catalogue (Pokémon, Yu-Gi-Oh!, Beyblade). Pokémon collection handles include `30th-celebration-singles-pokemon-tcg`, `151-singles-pokemon-tcg`, and many set-singles handles. — verified via `curl https://otakumart.co.nz/collections.json`
- **GameKings — https://gamekings.co.nz — Shopify (confirmed).** Homepage served `Powered by Shopify`, `Shopify.theme`, `cdn.shopify.com`. (Established NZ games/console retailer; Pokémon stock not individually verified this pass.) — verified via `curl` homepage markers
- **Hobby Zone — https://hobbyzone.co.nz — Shopify (confirmed).** Homepage served `Shopify.theme`, `cdn.shopify.com`; collection handles include `pokemon` and `pokemon-cards`. — verified via `curl https://hobbyzone.co.nz/collections.json`
- **Fire Spin Hobby — https://firespin.co.nz — WooCommerce (confirmed).** Homepage served `WooCommerce` / `wp-content` markers (WordPress); no Shopify `/products.json`. Self-describes as a NZ seller of authentic JP/CN/EN Pokémon TCG, sealed + singles. — verified via `curl https://firespin.co.nz/`; store description from [WebSearch result / firespin staging mirror](https://firespin.170.64.171.111.sslip.io/)
- **Pokémon Center AU/NZ (official) — https://www.pokemoncenter.com — custom platform, online-only.** The Pokémon Company International soft-launched (31 May 2024) then officially opened an Australia/New Zealand online store; TCG plus figures/apparel, no physical NZ store. — [Inside Retail NZ](https://insideretail.co.nz/2024/06/19/pokemon-launches-online-stores-for-australia-new-zealand/); [Nintendo AU](https://nintendo.com/au/news-and-articles/pokemon-center-online-store-coming-soon-to-australia-and-new-zealand); 30th-anniversary merch confirmed live at Pokémon Center NZ/AU per [Bulbagarden thread](https://bulbagarden.net/threads/new-pokemon-30th-anniversary-merch-available-now-at-pokemon-centers-us-can-nz-and-aus.309721/)
- **Mighty Ape — https://www.mightyape.co.nz — large NZ general retailer (platform not Shopify; homepage returned HTTP 403 to curl).** Well-known NZ retailer that stocks Pokémon TCG sealed; flagged as a mainstream (non-specialty) option. — `curl` returned 403 (bot-protected; not probed further)

### Inferences
- A live, unauthenticated Shopify `/products.json` (and per-collection `/collections/<handle>/products.json?limit=250`) exists for Card Merchant, Iron Knight, Otakumart, and almost certainly GameKings/Hobby Zone — these are the cleanest targets for a polling stock bot (no login, no bot-protection hit observed).
- Fire Spin (WooCommerce/WordPress) would need WooCommerce Store API or HTML scraping rather than a Shopify JSON feed.
- Mighty Ape's 403 suggests bot protection; monitoring it will likely need the ScrapFly/Zyte fallback noted in project memory rather than plain curl.

### Gaps
- **TCG Collector** is a collection-tracking database site (tcgcollector.com), **not** an NZ retailer — exclude from monitoring. (Not separately fetched; identified from prior knowledge — flag for confirmation.)
- No live NZ e-commerce site resolved for: **Grey Base, Punreal/Pun Real, Mana Gaming, Shuffle and Cut, VaultTCG, The Games Den, 1UP Games, Cerberus Cards, Game Haven, Big Boys Hobbies, Sanctuary Trading/Gaming, Collectables NZ, Poké Mart NZ.** Multiple `.co.nz`/`.com` domain guesses returned no DNS/connection. Several are likely Instagram/Facebook/TradeMe-based sellers or may have since closed/rebranded; needs a human to supply the exact URL or a social handle.
- **Good Games, Dropbear Games, Hobbyco, Gemini Collectables, Catch of the Day** appear to be **Australian** (e.g. goodgames.com.au is Shopify/AU) — out of NZ scope unless an NZ domain is confirmed.
- **GoblinGaming NZ / Goblin Games** — a Reddit comment places a "Goblin Games" physical store in Wellington ("in town") but no online store URL was confirmed. [Reddit NZ snapshot](https://reddit.sentinel-team.org/posts/1unycj0/snapshots/2026-07-07T06%3A29%3A10.35744Z)

## Pokémon sealed product & 30th Celebration / Mega Evolution availability

### Takeaway
All three confirmed Shopify stores carry Pokémon sealed product and have live Mega Evolution / 30th Celebration listings. Otakumart has by far the deepest 30th Celebration presence (full singles set plus sealed preorders including the Ultra-Premium Collection); Card Merchant and Iron Knight list Mega Evolution items with explicit purchase limits (a release-drop/allocation signal).

### Cited Findings
- **Card Merchant** `pokemon-sealed` collection includes **"PKM Booster Pack - Mega Evolution: Perfect Order *LIMIT 3*"**; `pokemon` collection returned 108 products; `pre-orders` collection returned 20 products. — verified via `curl .../collections/pokemon-sealed/products.json` and `/collections/pre-orders/products.json`
- **Iron Knight Gaming** `preorders` collection (24 products) includes Mega Evolution merchandise (e.g. **"POKEMON - Portfolio 9PKT Mega Evolutions 6 Delta Reign"**); `pokemon-sealed` collection present (1 product at time of check). — verified via `curl .../collections/preorders/products.json`
- **Otakumart** `30th-celebration-singles-pokemon-tcg` collection returned **192 products**, all titled `[Mega Evolution: 30th Celebration]` or `[Mega Evolution: 30th Celebration Classic Collection]` (e.g. Pikachu ex, Mew ex, Gengar ex, Sylveon ex, Umbreon ex, Charizard Classic Collection). — verified via `curl .../collections/30th-celebration-singles-pokemon-tcg/products.json`
- **Otakumart sealed 30th Celebration preorders** confirmed via search: **Ultra-Premium Collection — Day (NZ$435, pre-order, ships on release, 29 expansion packs + Classic Collection pack)**, Elite Trainer Box, Sylveon ex Box, Sylveon Tin, Mew/Mewtwo Figure Collections, Lucario Tech Sticker Collection, Knock Out Collection. — [Otakumart UPC Day](https://otakumart.co.nz/products/30th-celebration-ultra-premium-collection-day-pokemon-tcg); [ETB](https://otakumart.co.nz/products/30th-celebration-elite-trainer-box-pokemon-tcg); [Sylveon ex Box](https://otakumart.co.nz/products/30th-celebration-sylveon-ex-box-pokemon-tcg)
- **Otakumart Mega Evolution base sealed:** **"Perfect Order Booster Box" listed at NZ$330, shown Sold Out** at time of check. — [Otakumart Perfect Order Booster Box](https://otakumart.co.nz/products/perfect-order-booster-box-pokemon-tcg)
- **Hobby Zone** has `pokemon` and `pokemon-cards` collections (sealed/cards stocked); specific 30th/Mega items not individually verified this pass. — verified via `curl .../collections.json`
- **Release timing:** one Japanese-retailer blog states the 30th Celebration / Mega Evolution English expansion launched globally/simultaneously on **16 September 2026**; an Otakumart Sylveon Tin listing showed a **December 2026** date (conflict — likely a later wave/restock vs. main set). — [samuraiswordtokyo.com preorder guide](https://samuraiswordtokyo.com/nl/blogs/news/pokemon-30th-anniversary-set-preorder-guide-us-retailers-vs-japan); Otakumart listing date via WebSearch result (not separately re-fetched)

### Inferences
- `*LIMIT 1*` / `*LIMIT 3*` suffixes in Card Merchant titles indicate hot/allocated SKUs — the exact products a release-day drop bot should watch.
- The useful bot signal per SKU is the Shopify variant `available` boolean (and `inventory`/price) in `/products.json`; collections like `pokemon-sealed`, `pokemon-booster-packs`, `pre-orders`/`preorders` are the right poll targets.
- Because the set is branded "Mega Evolution: 30th Celebration", a bot keyword filter should match both `30th Celebration` AND `Mega Evolution` (plus sub-product names: Perfect Order, Phantasmal Flames, Ultra-Premium Collection, Ninja Spinner, Pitch Black) to avoid missing listings.

### Gaps
- Could not confirm whether Card Merchant / Iron Knight do formal timed "release-day drops" vs. rolling preorder allocation — product limits imply allocation but no store policy page was fetched.
- Per-SKU in-stock vs. preorder status is time-sensitive and will change; only a snapshot was captured. No stock verification done for GameKings.
- NZ-specific official release date for 30th Celebration not pinned down (16 Sep 2026 figure is from a non-NZ retailer blog; one NZ listing conflicts with December 2026).

## Location & nationwide shipping / drop behaviour

### Takeaway
The confirmed stores are NZ-based Shopify shops that ship nationwide; Card Merchant is Wellington-based with an in-person monthly trading event. Shipping/location detail is thin and should be confirmed per store.

### Cited Findings
- **Card Merchant** — Wellington CBD ("in town"), with a monthly in-person trading event reported on Manners Street on the last Saturday of each month (commenter hedged "from memory"). — [Reddit NZ snapshot](https://reddit.sentinel-team.org/posts/1unycj0/snapshots/2026-07-07T06%3A29%3A10.35744Z)
- **Otakumart** — operates a physical store with click-and-collect ("Pickup currently unavailable at Otakumart store" message seen on a sold-out item) plus online ordering; NZ retailer. — WebSearch of Otakumart product pages
- **Fire Spin Hobby** — self-described "locally owned" NZ Pokémon TCG seller; also stocks Funko Pop, Star Wars, DBZ, etc. — [firespin staging mirror](https://firespin.170.64.171.111.sslip.io/); primary domain https://firespin.co.nz
- **Pokémon Center AU/NZ** — online-only (no physical NZ store); a 2024 launch-period forum report said free shipping was not offered at launch (verify current FAQ). — [Inside Retail NZ](https://insideretail.co.nz/2024/06/19/pokemon-launches-online-stores-for-australia-new-zealand/)

### Inferences
- Being Shopify NZ stores, Card Merchant / Iron Knight / Otakumart / GameKings / Hobby Zone almost certainly offer nationwide NZ courier shipping (standard for NZ Shopify retail), but exact rates/thresholds were not fetched.

### Gaps
- No shipping-policy pages were fetched for any store; nationwide shipping is inferred, not read from each store's policy.
- Physical addresses for Iron Knight, GameKings, Hobby Zone, Fire Spin not confirmed.

## Data-quality / safety notes for the bot

### Takeaway
A few search hits were spam/SEO domains impersonating card shops — exclude them.

### Cited Findings
- Domains **mudiameuniversity.edu.ng** and **sisoluzioniimpresa.it** surfaced with Pokémon-booster-box titles but mix in unrelated clothing collection URLs — these are SEO-spam/scrape pages, **not** legitimate NZ retailers. — flagged in WebSearch results (pokemon tcg store nz shopify queries)
- The **firespin.170.64.171.111.sslip.io** address is an IP-based sslip.io host (staging/temporary mirror), not the canonical domain; use **https://firespin.co.nz**. — WebSearch result

### Gaps
- Could not verify Fire Spin's live catalogue via its canonical domain's product API (WooCommerce, no Shopify JSON); HTML scrape or WooCommerce Store API needed.

## Quick reference table (confirmed stores)

| Store | URL | Platform | Pokémon sealed? | 30th Celebration / Mega Evolution | Bot-friendly feed |
|---|---|---|---|---|---|
| Card Merchant NZ | cardmerchant.co.nz | Shopify (confirmed) | Yes (`pokemon-sealed`, `pokemon-booster-packs`) | Yes — Mega Evolution: Perfect Order booster packs (LIMIT) | `/products.json`, per-collection JSON |
| Iron Knight Gaming | ironknightgaming.co.nz | Shopify (confirmed) | Yes (`pokemon-sealed`) | Yes — Mega Evolution items in `preorders` | `/products.json` |
| Otakumart | otakumart.co.nz | Shopify (confirmed) | Yes (deep catalogue) | Yes — full 30th Celebration singles set + sealed UPC/ETB/boxes/tins preorders | `/products.json`, per-collection JSON |
| GameKings | gamekings.co.nz | Shopify (confirmed) | Likely (unconfirmed this pass) | Unconfirmed | `/products.json` (expected) |
| Hobby Zone | hobbyzone.co.nz | Shopify (confirmed) | Yes (`pokemon`, `pokemon-cards`) | Unconfirmed | `/products.json`, per-collection JSON |
| Fire Spin Hobby | firespin.co.nz | WooCommerce (confirmed) | Yes (JP/CN/EN sealed + singles) | Unconfirmed on canonical domain | WooCommerce Store API / HTML |
| Pokémon Center AU/NZ | pokemoncenter.com | Custom (official, online-only) | Yes | Yes (30th anniversary merch live) | No open JSON; bot-protected |
| Mighty Ape (mainstream) | mightyape.co.nz | Custom (HTTP 403 to curl) | Yes (sealed) | Unconfirmed | Bot-protected (needs ScrapFly/Zyte) |
