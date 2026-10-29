# Retailers

Recon notes for each retailer. An adapter is only marked **live** once it has been checked against the real site and has fixture tests. Bot protection per retailer, store counts and the access approach for each are compared in [HOSTING.md §5](HOSTING.md#5-retailers-what-to-monitor-and-how-to-get-in).

| Retailer | Adapter | Store-level stock | Status |
|---|---|---|---|
| Shopify card shops (any) | `shopify` | — (online only) | **live** |
| Farmers | `farmers` | yes: In / Not in stock, 53 stores | **live via Constructor.io** (discovery, search, online stock, no price). Price and per-store stock need `"browser": true`, which Akamai currently blocks |
| The Warehouse | `warehouse` | yes: per store, 76 stores, 15 regions | recon done: listings and stores via plain HTTP; store stock needs a per-product token, and the Pokémon product page is behind a Cloudflare challenge |
| Noel Leeming | `noelleeming` | yes (expected) | recon pending |
| Warehouse Stationery | `warehousestationery` | yes (expected) | recon pending (Cloudflare challenge) |
| Kmart NZ | `kmart` | yes (expected) | recon pending (Akamai) |
| Woolworths NZ | `woolworths` | yes (per store) | recon pending (Akamai) |
| JB Hi-Fi NZ | `jbhifi` | yes: in-stock store IDs in the product page | **live** (discovery, search, price, online + per-store stock for 27 named stores, add-to-cart) |
| Toyworld | `toyworld` / `shopify` | to confirm | recon pending (Shopify) |
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
- **In-store stock refreshes once a day.** The modal says "Stock updated at 8am this morning", so polling store stock more than hourly is pointless. Online stock (JSON-LD) is live.
- **Stock levels:** only "In Stock" and "Not In Stock" were seen. No counts.

**Access:** decided to use a real browser (option 1). The adapter (`tcgpings/retailers/farmers.py`) calls the endpoints above with `fetch()` from inside a real Chrome page, using `net/browser.py`: Patchright driving Google Chrome, headed (Xvfb in Docker), with a persistent profile per retailer.

- **Schedule:** online stock is checked every 15 min. Store stock is checked every 4 h; it only refreshes daily, and each check is 13 region calls.
- **Request budget:** 10 requests/min.
- **Not passing Akamai yet.** Plain `curl_cffi` got 2 answers, then 403s. Every automated browser variant was denied as well. Only a real browser with an aged cookie passed. The full table and next steps are in [HOSTING.md §6](HOSTING.md#6-farmers-status-and-next-steps).
- **Disabled by default:** the `farmers` retailer stays off until enabled with `/retailer set retailer:farmers enabled:true`.

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

**Split this gives:** new listings and online stock come from Constructor (plain HTTP, every 1–2 min, about $0). Price and per-store stock still need the Akamai-protected endpoints (browser).

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
