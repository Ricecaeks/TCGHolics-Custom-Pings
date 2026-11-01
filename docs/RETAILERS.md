# Retailers

Recon notes for each retailer. An adapter is only marked **live** once it has been checked against the real site and has fixture tests. Bot protection per retailer, store counts and the access approach for each are compared in [HOSTING.md §5](HOSTING.md#5-retailers-what-to-monitor-and-how-to-get-in).

| Retailer | Adapter | Store-level stock | Status |
|---|---|---|---|
| Shopify card shops (any) | `shopify` | — (online only) | **live** |
| Farmers | `farmers` | yes: In / Not in stock, 53 stores | **live via Constructor.io** (discovery, search, online stock). Price and per-store stock once a day through the fetch chain (Chrome → ScrapFly → Zyte) |
| The Warehouse | `warehouse` | not used (see below) | **live, online only** (discovery of the Trading Cards category newest-first, search, price, online stock incl. "in stores only"). No add-to-cart link (Turnstile) |
| Noel Leeming | `noelleeming` | yes (expected) | recon pending |
| Warehouse Stationery | `warehousestationery` | yes (expected) | recon pending (Cloudflare challenge) |
| Kmart NZ | `kmart` | yes: unit counts, 28 stores | **live** (Constructor.io for discovery of Trading Cards newest-first, search, price, online stock; Kmart's gateway for per-store counts). No add-to-cart link |
| Woolworths NZ | `woolworths` | yes (per store) | recon pending (Akamai) |
| JB Hi-Fi NZ | `jbhifi` | yes: in-stock store IDs in the product page | **live** (discovery, search, price, online + per-store stock for 27 named stores, add-to-cart) |
| Toyworld | `toyworld` (Shopify) | yes: in / low / out, 36 stores | **live** (discovery of the `trading-cards` + `pokemon` collections, search, price, online + per-store stock, add-to-cart) |
| Mighty Ape | `mightyape` | — (online only) | recon pending (DataDome) |
| Whitcoulls | `whitcoulls` | to confirm | recon pending |
| Paper Plus | `paperplus` | to confirm | recon pending |
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
| Store stock | `/products/stores/region?productId=<id>&region=NZ-AUK&verify=<token>` (`Stores-PDPStoreAvailability`), JSON whose `stores` HTML lists each store with `store-availability__IN_STOCK` etc. One call per region (15 regions) | needs `verify` |
| Product page | `/p/<slug>/<id>.html` | ✅ for normal products; **❌ Pokémon product: Cloudflare challenge** (`cf-mitigated: challenge`, Turnstile "verify you are human"), even in a real browser |

- `verify` is a signed `<timestamp>-<signature>` token printed into each product page. It ties the stock call to that product, so **store stock needs the product page first**.
- The Warehouse has put its hot Pokémon item ("LIMIT 10 PER CUSTOMER") behind an interactive Cloudflare challenge. The Uno page next to it loads fine.
- Online availability and new listings come from the category page, which works with plain HTTP.
- Per-store stock for challenge-protected items isn't reachable without passing Turnstile. That's a human checkbox; we don't automate CAPTCHAs.

**Adapter (2026-10-29):** `tcgpings/retailers/warehouse.py`, online only.
- Discovery: `/search?cgid=toysbaby-toys-collectibletoys-tradingcardsaccs&srule=newest&start=N&sz=32` (32 tiles per page, ~40 products in the category). Each tile has `data-gtm-product` JSON (name, id, price, `marketplaceProduct`) and `data-stock-status`: `IN_STOCK`, or `FIND_IN_STORE` (stores only, alerted as online out of stock).
- Third-party marketplace listings (`M…` ids) are skipped unless config `"marketplace": true`.
- Single-product watches read the product page's JSON-LD (`/p/x/<id>.html` works for any id). Hot Pokémon pages (and even a search for their id) return a Cloudflare challenge, so for those the category tiles are the only source.
- Per-store stock is **not implemented**: the store-availability call needs a signed per-product token from the product page. Automating that was ruled out as circumventing the site's access controls, and challenge pages make it impossible for hot items anyway. Revisit only with The Warehouse's permission or via the unblocker augment (see [ROADMAP.md](ROADMAP.md)).

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
- Island flags include warehouse stock: on 2026-11-01 a product flagged in stock showed 17 in a home-delivery pool and 0 in stores. So they only decide online stock (IN when it ships online and an island has it).
- In-store-only products are always OUT online and carry an "In-store only" note on alerts. Their restocks show up in `#kmart-instore`.

### Kmart store stock (recon 2026-11-01)

`POST https://api.kmart.co.nz/gateway/graphql` with plain HTTP, using the queries in the product page's own scripts. No key or sign-in.

| Query | Input | Returns |
|---|---|---|
| `getNearestLocations` | `lat`, `lon`, `distance: "2000km"`, `limit` | every store: `locationId` (e.g. `8229` Sylvia Park), `publicName`, `state`, `postcode` |
| `getProductAvailability` | `country`, `postcode`, `products: [{keycode, ...}]`, `fulfilmentMethods: ["CLICK_AND_COLLECT"]` | per product, the postcode's 5 nearest stores with `fulfilment.stock.available`, a **unit count** |

- **A sweep:** one product batch per postcode, skipping stores already answered. 8 postcodes covered all 28 stores for 54 products in one test, every 5 minutes in the bot.
- **Checked:** Surging Sparks showed 10 at Sylvia Park while the site said in stock there, and Hot Wheels showed 0 where the site said out of stock. A fake product code showed 0 everywhere.
- **Not used:** `getFindInStore`, which the "check stock nearby" window calls. It returns `High`, `Medium` or `Low`, and a fake product code also gets `Low`. On kmart.co.nz that window sends it to `api.kmart.com.au`, which returned 429 in testing and made the window say "No nearby stores available".
- **Not explained:** some very large counts (Rotorua showed 286 of one product). Counts are what the system holds, and stock may not be on the shelf yet.

## JB Hi-Fi NZ (recon 2026-10-29)

**Platform:** Shopify (`prod-jbhifi-nz.myshopify.com`) behind Cloudflare, with Algolia search. Carries Magic, Final Fantasy, Pokémon and other TCGs; a "pokemon trading card" search returns 1,076 results.

| Purpose | Request | Plain HTTP? |
|---|---|---|
| Product + **every store's stock** | the product page HTML embeds the JB product metafield JSON: `Price.DisplayPriceInc`, `Availability.OverallStatus` (`InStock`/`LimitedStock`/…), `ClickNCollectStatus`, and **`AvailabilityInStore.InStockStoreIds`** (e.g. `[21,23,28,…]`) | ✅ (3 of 3 requests OK) |
| Price + online availability | `/products/<handle>.js` (Shopify standard) | ✅ |
| Search / category | Algolia index `shopify_products_families` (public search key in the page), or the Shopify collection `/collections/trading-card-games` | not tested yet |
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
