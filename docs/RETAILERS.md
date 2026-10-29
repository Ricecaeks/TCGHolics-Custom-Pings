# Retailers

Recon notes for each retailer. An adapter is only marked **live** once it has been checked against the real site and has fixture tests. Bot protection per retailer, store counts and the access approach for each are compared in [HOSTING.md §5](HOSTING.md#5-retailers-what-to-monitor-and-how-to-get-in).

| Retailer | Adapter | Store-level stock | Status |
|---|---|---|---|
| Shopify card shops (any) | `shopify` | — (online only) | **live** |
| Farmers | `farmers` | yes: In / Not in stock, 53 stores | adapter built and tested on fixtures; **live access blocked by Akamai**, retailer disabled by default (see below) |
| The Warehouse | `warehouse` | yes (expected) | recon pending |
| Noel Leeming | `noelleeming` | yes (expected) | recon pending |
| Warehouse Stationery | `warehousestationery` | yes (expected) | recon pending (Cloudflare challenge) |
| Kmart NZ | `kmart` | yes (expected) | recon pending (Akamai) |
| Woolworths NZ | `woolworths` | yes (per store) | recon pending (Akamai) |
| JB Hi-Fi NZ | `jbhifi` | to confirm | recon pending |
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

## Recon checklist for a new retailer

1. Search on the site with devtools → Network → Fetch/XHR open. Note the search API: URL, parameters, and whether it needs headers or cookies.
2. Open a product page and note the product or price API, and the SKU format in the URL.
3. Use "check stock in store" or click & collect. Note the store-availability API, how stores are identified, and whether it returns counts or levels.
4. Find the store list (store locator API).
5. Try each call with `curl_cffi` outside the browser. Note any bot protection (Akamai, Cloudflare, PerimeterX) and whether a plain request is enough.
6. Save sample responses to `tests/fixtures/<retailer>/` and record everything above in this file.
