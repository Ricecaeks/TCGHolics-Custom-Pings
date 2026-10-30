# Roadmap

What's built, what's next, and the add-ons parked until the core is finished.

## Built

| Area | Status |
|---|---|
| Core platform: job leasing, leader election, outbox, keyword routes, discovery, Docker stack | done |
| Discord `/setup`: categories, channels (`#farmers-online`, `#farmers-instore`), webhooks and routes in one command | done |
| JB Hi-Fi: listings, price, online + 27 stores, add-to-cart | live |
| Farmers: listings and online stock (Constructor.io) | live |
| Farmers: price and 53-store stock once a day, through the self-healing fetch chain (Chrome → ScrapFly → Zyte) with circuit breakers and a monthly spend cap | built. Needs a ScrapFly and/or Zyte key in `.env` while Akamai blocks our Chrome |
| Online + in-store channel per retailer, grouped in-store alerts, auto-setup of channels by the leader | done |
| The Warehouse: listings, price, online stock | live. No per-store stock |
| Toyworld, independent Shopify card shops: listings, price, online stock, add-to-cart | live |
| Kmart: listings, price, online stock, North / South Island stock (Constructor.io) | live. No per-store stock |

## Next

1. **Prove the Farmers fetch chain live.** Add the keys, then `probe farmers stock <sku> --store albany --set fetch='["scrapfly"]'` (and `'["zyte"]'`) to see which gets through and what it costs; swap their order if Zyte's plain-HTTP mode works.
   - Optional: an NZ residential proxy for the Chrome route (sticky 10–30 min sessions, user:pass auth, pay as you go; Decodo or ProxyEmpire). `tcgpings/net/browser.py` doesn't take a proxy yet.
2. **Kmart per-store stock.** Kmart's "check stock nearby" goes to its own GraphQL gateway behind Akamai; recon pending. Island-level stock already works.
3. **Noel Leeming** recon (same platform as The Warehouse).
4. **Woolworths, Mighty Ape, Warehouse Stationery, Whitcoulls, Paper Plus** recon.
5. **Shorter data retention**: 2 days for sent alerts and change history, 1 day for undeliverable alerts, and removal of products not seen for 14 days. Product state is kept while a product is listed, because that's what makes "new listing" and "restock" alerts work.

## Augments (on hold until everything above is built)

### Unblocker proxies

Built: see the fetch chain in [HOSTING.md §6](HOSTING.md#6-farmers-status-and-next-steps). Other retailers (Kmart per-store, Woolworths, Mighty Ape, Warehouse Stationery) can use it by calling `http.chain.fetch_text` the way the Farmers adapter does.

### Hosted database (Supabase)

Stay on the local Postgres while everything runs on one machine: the stack sends about 8 GB/month of database traffic, more than Supabase Free's egress allowance. Move to Supabase (Pro, or Free after cutting polling with LISTEN/NOTIFY) when a second machine or cloud host joins. It's a `DATABASE_URL` change.
