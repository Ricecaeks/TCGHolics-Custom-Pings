# Retailers

Recon notes for each retailer. An adapter is only marked **live** once it has been checked against the real site and has fixture tests.

| Retailer | Adapter | Store-level stock | Status |
|---|---|---|---|
| Shopify card shops (any) | `shopify` | — (online only) | **live** |
| Farmers | `farmers` | yes (expected) | recon pending: phase 2 |
| The Warehouse | `warehouse` | yes (expected) | recon pending: phase 3 |
| Kmart NZ | `kmart` | yes (expected) | recon pending: phase 3 |
| Noel Leeming | `noelleeming` | yes (expected) | recon pending: phase 3 |
| JB Hi-Fi NZ | `jbhifi` | to confirm | recon pending: phase 4 |
| EB Games NZ | `ebgames` | to confirm | recon pending: phase 4 |
| Mighty Ape | `mightyape` | — (online only) | recon pending: phase 4 |
| Toyworld | `toyworld` | to confirm | recon pending: phase 4 |
| Whitcoulls | `whitcoulls` | to confirm | recon pending: phase 4 |
| Paper Plus | `paperplus` | to confirm | recon pending: phase 4 |

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

## Recon checklist for a new retailer

1. Search on the site with devtools → Network → Fetch/XHR open. Note the search API: URL, parameters, and whether it needs headers or cookies.
2. Open a product page and note the product or price API, and the SKU format in the URL.
3. Use "check stock in store" or click & collect. Note the store-availability API, how stores are identified, and whether it returns counts or levels.
4. Find the store list (store locator API).
5. Try each call with `curl_cffi` outside the browser. Note any bot protection (Akamai, Cloudflare, PerimeterX) and whether a plain request is enough.
6. Save sample responses to `tests/fixtures/<retailer>/` and record everything above in this file.
