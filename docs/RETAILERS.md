# Retailers

Recon notes for each retailer. An adapter is only marked **live** once it has been checked against the real site and has fixture tests. Bot protection per retailer, store counts and the access approach for each are compared in [HOSTING.md §5](HOSTING.md#5-retailers-what-to-monitor-and-how-to-get-in).

| Retailer | Adapter | Store-level stock | Status |
|---|---|---|---|
| Shopify card shops (any) | `shopify` | — (online only) | **live** |
| Farmers | `farmers` | yes: In / Not in stock, 53 stores | **live via Constructor.io** (discovery, search, online stock). Price and per-store stock once a day through the fetch chain (Chrome → ScrapFly → Zyte) |
| The Warehouse | `warehouse` | nationwide only: "in stores" or not | **live** (discovery of the Trading Cards category newest-first, search, price, online stock incl. "in stores only"). No add-to-cart link (Turnstile) |
| Noel Leeming | `noelleeming` | yes (expected) | recon pending |
| Warehouse Stationery | `warehousestationery` | yes (expected) | recon pending (Cloudflare challenge) |
| Kmart NZ | `kmart` | yes: unit counts, 28 stores | **live** (Constructor.io for discovery of Trading Cards newest-first, search, price, online stock; Kmart's gateway for per-store counts). No add-to-cart link |
| Woolworths NZ | `woolworths` | yes (per store) | recon pending (Akamai) |
| JB Hi-Fi NZ | `jbhifi` | yes: in-stock store IDs in the product page | **live** (discovery, search, price, online + per-store stock for 27 named stores, add-to-cart) |
| Toyworld | `toyworld` (Shopify) | yes: in / low / out, 36 stores | **live** (discovery of the `trading-cards` + `pokemon` collections, search, price, online + per-store stock, add-to-cart) |
| Mighty Ape | `mightyape` | — (online only) | **live via ScrapFly** (Pokémon category every 30 min, all trading cards hourly: first page of each, about 2,000 credits a day). No keyword searches. No add-to-cart link |
| Whitcoulls | `whitcoulls` | nationwide only: "In Store Only" or not | **live** (discovery via card searches, search, price, online stock). No Pokémon cards in Nov 2026 |
| Paper Plus | `paperplus` | — (online only) | **live** (Trading Cards category, search, price, online stock; a product leaving the listing counts as sold out) |
| Retrospace | `retrospace` | — (online only) | **live** (card game categories + newest cards, search, price, online stock with unit counts; a product leaving its category counts as sold out). No add-to-cart link |
| ~~EB Games NZ~~ | — | — | dropped: stores have closed |

## Shopify (generic)

- Uses the public storefront JSON, so no API key is needed. Add a shop with `/retailer add-shopify`.
  - `GET /search/suggest.json?q=…&resources[type]=product&resources[limit]=10` is Shopify's predictive search, which runs on the server over the whole catalogue. It returns at most the 10 most relevant products, and the results are fuzzy ("booster bundle" also returns "MTG Bundle"), so every result is filtered against the keyword again.
  - `GET /products.json?limit=250&page=N` returns the catalogue, **most recently updated first**, which is what catches new listings. Only the first `config.catalogue_pages` pages are read (default 2, i.e. 500 products), because singles shops can be huge. Card Merchant had about 9,750 products in October 2026. For small shops, raise `catalogue_pages` to scan the whole catalogue.
  - `GET /products/<handle>.js` returns a single product. Prices are in cents.
  - Keyword matching checks the title, product type and tags.
- SKU = the product handle, the URL slug after `/products/`.
- Stock is IN/OUT only, because Shopify doesn't expose inventory counts publicly.
- When a single card's title doesn't name the game, the game is taken from the product type or tags.
- Verified live on 2026-10-29 against cardmerchant.co.nz and ironknightgaming.co.nz.
- Shops monitored: Card Merchant and Iron Knight Gaming (added by hand), plus ten shops that listed Delta Reign in Zephyr's alert history (added with `admin add-shopify` on 2026-11-04 after their feeds answered): Game Corner, OCARE, Aniverse, PLAYX, Card Masters, Kidzstuffonline, The Game Tree, Game Roost, Collectors Guild and Toy Time. Ten more added the same way later that day: Pop Stop, Mr Tofu, MetaLife, HobbiXchange, Otakumart, Hobby Zone, TCG Collector NZ, Animal Kingdoms, SecretRareVault and Shuffle n Cut.
  - Shuffle n Cut's newest products are almost all non-card, so it reads its sealed collections (`config.collections`). Otakumart and TCG Collector NZ list singles in bulk, so they read 2 pages (`discover_pages`).
  - Not Shopify: Retrospace (no `/products.json`; it has its own adapter, below). GameKings is Shopify but sells no cards. Shops that need a new adapter are listed in `reports/NZ Pokemon TCG retailers.md`.
- Shopify's bot check answers `429` to plain HTTP clients; the bot's browser-like client (curl_cffi impersonating Chrome) gets the JSON.

## Whitcoulls (recon 2026-11-04)

Plain HTML, no bot protection. Search pages embed their results as JSON (`window.category = {...{"items": [...]}}`, 24 a page): product id (`stylecolourid`, also `/x-<id>` redirects to the product), `urlkey`, price, and `variants[0].status`: `""` in stock online, `limitedstock`, `instore` (In Store Only), `outofstock`. Product pages have JSON-LD `offers.availability`.
- The card range is a few Yu-Gi-Oh!, Magic and Lorcana products; the "30th" seen in a Pokémon search was a 30th Anniversary figure, not cards. Discovery reads the searches "trading card", "booster" and "tcg". Searches can't be sorted or paged by URL, but each fits one page.
- "In Store Only" items count as in stock at one "Stores nationwide" store, like The Warehouse.

## Paper Plus (recon 2026-11-04)

Plain HTML, no bot protection. Category and search pages are `<article>` tiles with `data-url`, `data-skucode` and a hidden span with `data-name` / `data-price`. Product pages have JSON-LD `offers.availability`.
- Discovery reads the Trading Cards category (`/shop/toys-games-puzzles/collectables-trading-cards/trading-cards`, 12 products on one page in Nov 2026). Every listed product was in stock, so a product missing from the listing for 3 scans counts as sold out.
- SKU = the path after `/shop/`: search can't find a product by barcode.
- Not looked at yet: the product page's "Where in stock" button (per-store stock).

## Retrospace (recon 2026-11-04)

Christchurch collectibles shop on a custom site (Cactuslab), plain HTML, no bot protection. Zephyr pinged it for Pitch Black boosters in `#card-shop-sites`.
- Listing tiles are `<li class="result-wrapper">`: product link, `<h2>` title, a stock label and a price. Labels: `2 in stock` (a count), `in stock`, `Pre-Order April 2027` (counted as in stock, label shown as a note), `Special Order (Ships in 2 weeks)` (the shop orders it in: counted as out).
- A category page shows 20 tiles; its "load more" button calls `/<category slug>/more/?start=N&howMany=M`, which returns tiles alone, so one request reads a whole category.
- Discovery reads the card categories (`pokemon-cards`, `magic-the-gathering-1`, `one-piece-card-game`, `yu-gi-oh-cards`, `dragonball-z-cards`, `riftbound-league-of-legends-tcg-in-stock`) plus the 60 newest tiles of `/cards/`. A product missing from its category for 3 scans counts as sold out.
- Search is `/search.do?q=`; its category tiles and merchandise (mugs, figures) are skipped by path.
- SKU = the product path (`games/pokemon-cards/<slug>`). Add-to-cart is a form POST with a CSRF token, so no link.
- Live check 2026-11-04: 76 card products, 71 sealed (mostly Yu-Gi-Oh special orders; Pitch Black boosters and Zarude blister, Dragon Ball FB-11, Riftbound Vendetta in stock).

## Mighty Ape (recon 2026-11-05)

DataDome answers 403 (a CAPTCHA page) to every page with product data: shop, search, `/api`, and the 5,551 product sitemaps. Only `robots.txt` and the sitemap index load. The owner approved ScrapFly for it on 2026-11-05.
- Through ScrapFly (`unblocker=true`, NZ exit): 25–30 credits and 23–50 seconds a page.
- Category pages (`/mn/shop/category/hobbies/trading-cards/`, `…/pokemon`, and one per game) carry a JSON-LD `ItemList` of 36 products: name, SKU (`MPE-…`), image, `AggregateOffer` with `lowPrice` (the Primate members' price), `highPrice` (regular) and availability (`InStock`, `PreOrder`, `OutOfStock`). Sold-out products stay listed. Product pages have a JSON-LD `Product`.
- robots.txt disallows search (`?q=`) and sorting (`order_by`), so discovery reads the first page of each category in its default "featured" order, where new sets and preorders sit near the top.
- SKU = the product URL slug (`kogan-international-pokemon-tcg-pitch-black-booster-pack-41201033`).
- Keyword watches skip it (`supports_search = False`): every request costs credits.

## Farmers (recon 2026-10-29)

**Platform:** Intershop (cookies `pgid-Farmers-Shop-Site`, `sid`, `SecureSessionID-*`), behind **Akamai Bot Manager** (`_abck`, `bm_sz`). Search is powered by Constructor.io.

| Purpose | Request | Response |
|---|---|---|
| Product | `GET /<category path>/<slug>-<SKU>` (SKU = trailing 7 digits, e.g. `7044417`) | HTML with JSON-LD `Product`: name, image, sku, gtin14, `offers.price`, `offers.availability` (online stock) |
| Store stock | `GET /INTERSHOP/web/WFS/Farmers-Shop-Site/en_NZ/-/NZD/ViewCheckoutShipping-GetAvailableStoresAjax?CountryCode=NZ&NoShippingFilter=true&SKU=<sku>&State=<region>` | HTML fragment; each `.panel-heading` holds `.store__name span` and `.store-stock` (`In Stock` / `Not In Stock`). One call per region, so **13 calls cover every store** |
| Store modal | `POST …/ViewProduct-GetStoreModal?SKU=<sku>` | the region picker (not needed) |
| New listings | category `/toys/games-cards-puzzles/trading-cards` | product tiles link to the product URLs |
| Search | `/search?SearchTerm=<q>` (HTML), backed by Constructor.io | not used yet: calling Constructor's API directly needs a decision (see below) |

- **Regions** (`State`): NTL, AUK, WKO, BOP, GIS, TKI, MWT, HKB, WGN, NSN, CAN, OTA, STL.
- **Stores are identified by name only.** There's no store ID. The full list of 53 is in [`tcgpings/retailers/data/farmers_stores.json`](../tcgpings/retailers/data/farmers_stores.json). **Westgate is listed as "Northwest"** (NorthWest Shopping Centre, Massey). "Home by Farmers" homewares stores don't stock cards and aren't returned.
- **In-store stock may refresh once a day (unproven).** The modal says "Stock updated at 8am this morning", but that's fixed text: it read the same at 3am on 2026-11-01. Online stock (JSON-LD) is live.
- **Stock levels:** only "In Stock" and "Not In Stock" were seen. No counts.
- **Unlisted products:** sold-out products can vanish from Constructor's search and category listing (the 30th Booster Bundle, seen 2026-11-01) while the store endpoint still answers for them. Their daily store checks carry on from the stored product, with no online stock reading until they're listed again.

**Access:** the endpoints above go through the **fetch chain** (`tcgpings/net/chain.py`), in the order set by the retailer's `fetch` config (default `["browser", "scrapfly", "zyte"]`):
1. our own Chrome (`net/browser.py`: Patchright driving Google Chrome, headed, Xvfb in Docker, persistent profile), free;
2. ScrapFly, then 3. Zyte API, each only when its key is set in `.env`.

- **Schedule:** new listings and online stock come from Constructor every 2 min (below). Each tracked product's store stock and price are checked **once a day**, at a fixed slot between 8:30 and 9:30am NZ time, after the 8am the site mentions. That's our schedule, not a Farmers one.
- **Cost of a daily check:** 1 product page + 1 call per region with a wanted store (13 for all stores).
- **Regions:** config `regions` limits them (default all 13). Once 80% of the month's unblocker budget is spent, only `priority_regions` are checked (default `["AUK"]`).
- **Request budget:** 10 requests/min.
- **Akamai:** plain `curl_cffi` got 2 answers, then 403s, and every automated browser variant was denied in testing. When Chrome is denied it rests for 24 h and the unblockers take over; it's retried on its own afterwards. Details in [HOSTING.md §6](HOSTING.md#6-farmers-status-and-next-steps).

### Farmers via Constructor.io (search + new listings, no browser)

Farmers' site search is hosted by Constructor.io on `ac.cnstrc.com`, which isn't behind Farmers' Akamai. TCGHolics approved using Farmers' public client key (`key_wafe8wrKCXfPyWKw`, embedded in every farmers.co.nz page) on 2026-10-29.

| Call | Returns |
|---|---|
| `GET https://ac.cnstrc.com/search/<query>?key=<key>&c=ciojs-client-2.0&i=<client-id>&s=<session>&num_results_per_page=N` | JSON results: `data.id`/`sku`, `url`, `image_url`, `stockstatus` ("In stock" / "Out of stock") |
| `GET https://ac.cnstrc.com/browse/group_id/51-070502?...&sort_by=arrivaldate&sort_order=descending&num_results_per_page=200` | the whole **Trading Cards** category (47 items), newest first, with online stock. **59 KB in 0.2 s** |

- Sort options: `relevance`, `arrivaldate`, `name`, `productsalepricegross`.
- **No price** in the response; price still comes from the product page (Akamai).
- 10 quick repeat calls were all 200. No rate limiting was seen.
- If the key changes, read it again from any farmers.co.nz page (`key_…` in the HTML).

**Split this gives:** new listings and online stock come from Constructor (plain HTTP, every 1–2 min, about $0). Price and per-store stock need the Akamai-protected endpoints, through the fetch chain once a day.

## The Warehouse (recon 2026-10-29)

**Platform:** Salesforce Commerce Cloud (site `Sites-twl-Site`), behind Cloudflare. Product IDs look like `R3083239`, and product URLs are `/p/<slug>/<id>.html`.

| Purpose | Request | Plain HTTP? |
|---|---|---|
| Pokémon listing | `/c/official-merchandise/pok%C3%A9mon/pokemon-trading-cards` (HTML tiles with `data-pid` and `data-gtm-product` JSON) | ✅ |
| Store list | `/on/demandware.store/Sites-twl-Site/default/Stores-FindStores?showMap=false&radius=2000&postalCode=0610`, JSON with **76 stores**, real IDs (e.g. `221` Auckland Central) and `stateCode` regions | ✅ |
| Store stock (step 2 of 2) | `/products/stores/region?productId=<id>&region=NZ-AUK&verify=<token>` (`Stores-PDPStoreAvailability`), JSON whose `stores` HTML lists each store with `store-availability__IN_STOCK` / `__NOT_AVAILABLE`, incl. store name, numeric id, hours, address. One call per region (15 regions). Token is **per-region**, minted in step 1's response. | needs per-region `verify` |
| Store availability modal (step 1 of 2) | `/products/stores?pid=<id>&verify=<token>` (`Product-GetPDPStoreStockLevels`) → 200, ~32 KB modal template listing **all 15 regions**, each carrying its own per-region `verify`. Token is minted into the product page's `gep-container-store-availability` element. **Effectively one-shot per session** (repeats → `403 "Cross-Origin Request Blocked"`). | needs `verify` |
| Product page | `/p/<slug>/<id>.html` | ✅ for normal products; hot Pokémon product sits behind a Cloudflare **managed** challenge that **auto-solves in a clean genuine Chrome** (no checkbox, no `cf_clearance` needed) — validated 2026-11-03 |

- `verify` is a signed `<timestamp>-<signature>` token minted **per endpoint**: the page's `gep-container-store-availability` element carries the step-1 token, and step 1's response mints a fresh per-region token for each of the 15 regions. Tokens are short-lived (reusing a step-1 token on a region path → `410 "Expired URL"`), and the step-1 call is one-shot per session (repeats → `403`).
- The hot Pokémon item ("LIMIT 10 PER CUSTOMER") sits behind a Cloudflare **managed** challenge. It **auto-solves in a clean genuine Chrome** (validated 2026-11-03 via the DevTools protocol on a fresh profile — no checkbox, no `cf_clearance`), so our Patchright backend can reach the product page and run the 2-step store-stock flow.
- Online availability and new listings come from the category page, which works with plain HTTP.
- Per-store stock for challenge-protected items **is reachable**: load the product page in the browser backend (managed challenge auto-solves), read the `gep-container-store-availability` URL, fire it **once**, then fire the per-region URLs it returns promptly. Validated live 2026-11-03 (Auckland: 22 stores, 1 in stock — Warkworth).

**Adapter (2026-10-29):** `tcgpings/retailers/warehouse.py`, online only.
- Discovery: `/search?cgid=toysbaby-toys-collectibletoys-tradingcardsaccs&srule=newest&start=N&sz=32` (32 tiles per page, ~40 products in the category). Each tile has `data-gtm-product` JSON (name, id, price, `marketplaceProduct`) and `data-stock-status`: `IN_STOCK`, or `FIND_IN_STORE` (stores only, alerted as online out of stock).
- Third-party marketplace listings (`M…` ids) are skipped unless config `"marketplace": true`.
- Discovery also reads `/search?q=pokemon%20tcg`, because "newest" isn't strictly newest (the 30th products were on page 2) and products may not reach every listing together. Tiles with `FIND_IN_STORE` get an "In stores, not online" note on alerts.
- **Listing timing (unproven):** first sightings so far landed around 3:15–3:30am NZ. On 2026-10-31 another bot posted three 30th products at 3:19–3:23am. We saw the Bundle at 3:27am, but the Mini Tin and Build & Battle Box only at 3:16am the next day, and the cause is unknown. The log line `warehouse: <listing> first shows <id>` records which listing shows each product first.
- Single-product watches read the product page's JSON-LD (`/p/x/<id>.html` works for any id). Hot Pokémon pages (and even a search for their id) return a Cloudflare challenge, so for those the category tiles are the only source.
- **Nationwide in-store alerts:** `FIND_IN_STORE` tiles count as in stock at one pseudo-store, "Stores nationwide". A product missing from the listings for 3 scans in a row counts as out, so its return alerts. This can't say which store, and how closely it tracks real stock isn't known.
- Per-store stock is **validated but not yet built into the adapter**: the 2-step flow (step-1 modal → per-region calls) is confirmed working in a clean genuine Chrome on 2026-11-03 (recon artifacts in `research_notes/warehouse-*.json`, parser in `_parse_store_levels3.py`). To add it, the adapter fetches the product page through the browser backend (managed challenge auto-solves), extracts the `gep-container-store-availability` URL, fires it **once**, then fires the returned per-region URLs promptly (one-shot widget, short-TTL region tokens). Cadence should be event-driven (tile flips / keyword) to stay inside the spend cap.

## Toyworld (recon 2026-10-29)

Shopify (`www.toyworld.co.nz`), so the generic adapter does everything, including add-to-cart links. The store-wide feed is mostly toys, so config `collections: ["trading-cards", "pokemon"]` makes discovery read only those collections (about 100 products). The sealed filter drops the Pokémon toys (model kits, Clip 'N' Go, plush...) and keeps the TCG product (Lorcana boosters, starter decks, gift sets at the time of recon).

**Store stock (recon 2026-11-01):** the product page's "Find in Store" button uses Stock In Store (`stockinstore.net`), with no key or sign-in. Plain HTTP works, using the page's own requests.

| Purpose | Request | Response |
|---|---|---|
| Store list | `POST /stores/getStoresForWidget` with `site=10044&widget=51` | `response.stores_list`: `code`, `name`, `region_name` (36 stores) |
| Store stock | `POST /stores/getStoresStock` with `pid=<barcode>&storeids=<codes>` plus the widget's other fields | `response[]`: `code`, `threshold.threshold_type_by` (`in-stock`, `low-stock`, `out-of-stock`), `recordUpdatedAt`. `stock` is only 0 or 1, not a count. About 360 KB, under a second |

- The barcode comes from `/products/<handle>.js` (`variants[].barcode`). "Assorted" products have several, and each store takes its best level across them.
- Every sealed product discovery finds gets a store check, at most every 15 minutes.
- **Not known yet:** how often the data updates (all stores showed one batch time), and how to look up in-store products Toyworld doesn't list online. These need a barcode from elsewhere.

## Kmart NZ (recon 2026-10-29)

kmart.co.nz is behind Akamai, but its search runs on Constructor.io (`ac.cnstrc.com`), outside Akamai. TCGHolics approved using Kmart's public client key (`key_EyiTrcbGw7IFH3wR`, embedded in every page). Nothing in the adapter touches kmart.co.nz itself.

- Discovery: `GET /browse/group_id/c00f65271ffae599a4b675da63b2e92d?sort_by=numberOfDaysSinceStartDate&sort_order=ascending&num_results_per_page=200` returns Toys > Trading Cards, newest first (85 products, 52 of them sealed TCG, in October 2026).
- Search: `GET /search/<q>`. Searching for a product number finds that product, which is how SKU watches work.
- Per result: `data.variation_id` (the product number in the URL), `value` (title), `data.url`, `data.image_url`, `data.price` (NZD).
- **`data.stateOOS`** lists the islands where the product is out of stock, e.g. `{"SI": "6"}`. An island that isn't listed has stock. The site's "Out of Stock Online" label matches products listed for both islands.
- **`data.FulfilmentChannel`**: `3` = online and in store (the product page offers "Add to bag" and home delivery); `2` = **in-store only**, which covers most Pokémon. Checked on product pages.
- Island flags can include warehouse stock: on 2026-11-01 a product flagged in stock showed 17 in a home-delivery pool and 0 in stores. So they decide online stock (IN when it ships online and an island has it), and they only act as store stock for in-store-only products while store counts are unavailable.
- In-store-only products are always OUT online and carry an "In-store only" note on alerts. Their restocks show up in `#kmart-instore`.

### Kmart store stock (recon 2026-11-01)

`POST https://api.kmart.co.nz/gateway/graphql` with plain HTTP, using the queries in the product page's own scripts. No key or sign-in.

| Query | Input | Returns |
|---|---|---|
| `getNearestLocations` | `lat`, `lon`, `distance: "2000km"`, `limit` | every store: `locationId` (e.g. `8229` Sylvia Park), `publicName`, `state`, `postcode` |
| `getProductAvailability` | `country`, `postcode`, `products: [{keycode, ...}]`, `fulfilmentMethods: ["CLICK_AND_COLLECT"]` | per product, the postcode's 5 nearest stores with `fulfilment.stock.available`, a **unit count** |

- **A sweep:** one product batch per postcode, skipping stores already answered. 8 postcodes covered all 28 stores for 54 products in one test.
- **Akamai:** after about 2.5 hours of sweeps every 5 minutes on 2026-11-01, every request got `429` with `{"cpr_chlge":"true"}`, a bot challenge we don't solve. Sweeps now run every 15 minutes, and a refusal rests our own requests from 30 minutes up to 6 hours.
- **While refused:** the same queries go through the fetch chain's paid unblocker instead (ScrapFly; config `"fetch"`), every 30 minutes, under the chain's breakers and monthly budget. TCGHolics asked for this on 2026-11-04. Our own requests are tried again first once their rest is over, so the unblocker is only paid for during a block. Checked 2026-11-04 with one store-list request each: ScrapFly accepted the POST but the account had hit its quota (`ERR::SCRAPE::QUOTA_LIMIT_REACHED`), so whether it gets past Akamai here is still unproven; Zyte answered `520 Website Ban`, so it isn't in the default order.
- **Short blocks:** stores keep their last counts. The island flags only stand in for in-store-only products once no store counts have come back for 2 hours.
- **Count rises:** a rise only alerts when it's at least 3 units and a tenth of the store's count (`QTY_JUMP` in `engine/diff.py`), so returns and recounts (133 → 134) stay quiet.
- **Checked:** Surging Sparks showed 10 at Sylvia Park while the site said in stock there, and Hot Wheels showed 0 where the site said out of stock. A fake product code showed 0 everywhere.
- **Not used:** `getFindInStore`, which the "check stock nearby" window calls. It returns `High`, `Medium` or `Low`, and a fake product code also gets `Low`. On kmart.co.nz that window sends it to `api.kmart.com.au`, which returned 429 in testing and made the window say "No nearby stores available".
- **Not explained:** some very large counts (Rotorua showed 286 of one product). Counts are what the system holds, and stock may not be on the shelf yet.

## JB Hi-Fi NZ (recon 2026-10-29)

**Platform:** Shopify (`prod-jbhifi-nz.myshopify.com`) behind Cloudflare, with Algolia search. Carries Magic, Final Fantasy, Pokémon and other TCGs; a "pokemon trading card" search returns 1,076 results.

| Purpose | Request | Plain HTTP? |
|---|---|---|
| Product + **every store's stock** | the product page HTML embeds the JB product metafield JSON: `Price.DisplayPriceInc`, `Availability.OverallStatus` (`InStock`/`LimitedStock`/…), `ClickNCollectStatus`, and **`AvailabilityInStore.InStockStoreIds`** (e.g. `[21,23,28,…]`) | ✅ (3 of 3 requests OK) |
| Price + online availability | `/products/<handle>.js` (Shopify standard) | ✅ |
| Search | `/search/suggest.json`, up to 10 results a query | ✅ |
| Category | The store-wide `/products.json` rarely reaches cards, and collection feeds tested on 2026-11-02 were empty (`/collections/trading-card-games` is a 404). Discovery runs the `discovery_searches` config instead | — |
| Store ID → name | Algolia index `shopify_store_locations` (used by `/pages/store-finder`), public search-only key approved 2026-10-29. `shopId` = the InStockStoreIds | ✅ |

- **One request per product gives every store's stock.** It's the cheapest store-level retailer so far.
- Each page is ~620 KB, so check every 2–5 min, not every few seconds.
- **Stores:** 27 retail stores, including Westgate (#42), Sylvia Park (#25) and the two airport stores.
  - They're synced daily from the Algolia index. If that fails, a bundled copy is used (`tcgpings/retailers/data/jbhifi_stores.json`).
  - The index also lists warehouses, head office and retired entries. These are filtered out, and any in-stock IDs they produce are ignored.

## Recon checklist for a new retailer

1. Search on the site with devtools → Network → Fetch/XHR open. Note the search API: URL, parameters, and whether it needs headers or cookies.
2. Open a product page and note the product or price API, and the SKU format in the URL.
3. Use "check stock in store" or click & collect. Note the store-availability API, how stores are identified, and whether it returns counts or levels.
4. Find the store list (store locator API).
5. Try each call with `curl_cffi` outside the browser. Note any bot protection (Akamai, Cloudflare, PerimeterX) and whether a plain request is enough.
6. Save sample responses to `tests/fixtures/<retailer>/` and record everything above in this file.
