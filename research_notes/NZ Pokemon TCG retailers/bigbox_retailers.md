# Mainstream / Big-Box NZ Retailers Selling Sealed Pokémon TCG (late 2026)

Scope: New Zealand mainstream, big-box, toy, hobby and department chains stocking sealed
Pokémon TCG product, with emphasis on the **30th Celebration / 30th Anniversary (Mega
Evolution-era)** range, for a stock-alert bot. Current as of 2026-11-04. Only publicly
visible signals used; no logins or bot-protection bypass.

Two source types are cited below:
- **Web sources** (URLs) — public pages / news.
- **Internal recon** — `docs/RETAILERS.md` in this repo, the user's own verified recon of
  these sites (dated entries, with saved fixtures). Treated as a primary source because it
  records live devtools/HTTP observations; I could not independently re-verify every live
  page because most NZ retail sites returned 403/429/Cloudflare/DataDome to automated fetch,
  and the available web-search tool is US-biased and would not surface `.co.nz` pages.

Context on the set itself: **Pokémon TCG: 30th Celebration** is a Mega Evolution-era special
set; it began releasing worldwide **16 September 2026**, with the Booster Bundle around
2 October 2026 and some collections (e.g. Ditto, Mew & Mewtwo) dated **6 November 2026**
([Pokeguardian](https://pokeguardian.com/3203075_poke..); [Bulbagarden product line-up](https://bulbagarden.net/threads/new-cards-and-product-lineup-revealed-for-the-pokemon-trading-card-games-upcoming-30th-celebration-expansion.310971/)).
Product line: Elite Trainer Box, Booster Bundle, Poster Collection, Binder Collection,
Ultra-Premium Collection (Day/Night; Espeon/Umbreon), Figure Collection, Knock Out
Collection, Mini Tins, Build & Battle Box ([icv2](https://icv2.com/articles/news/view/62747/pokemon-tcg-30th-celebration-product-line-deets-unveiled); [miketendo64](https://miketendo64.com/2026/06/30/pokemon-tcg-30th-celebration-product-line-up/)).
The "Mega Evolution 30th Celebration Elite Trainer Box" naming is confirmed at retail
([Face to Face Games](https://facetofacegames.com/products/pokemon-tcg-mega-evolution-30th-celebration-elite-trainer-box)).

## Store name & website URL (NZ sites)

### Takeaway
The live, confirmed mainstream NZ sellers of sealed Pokémon TCG are The Warehouse, Kmart NZ,
Farmers, JB Hi-Fi NZ, Mighty Ape and Toyworld NZ, with Noel Leeming, Warehouse Stationery,
Whitcoulls, Paper Plus and Woolworths NZ as likely-but-unverified sellers. EB Games NZ,
Toymate, Big W and Torpedo7 are **not** viable NZ Pokémon-TCG targets (see Gaps / Inferences).

### Cited Findings
- **The Warehouse** — https://www.thewarehouse.co.nz — Pokémon trading cards category confirmed; product URLs `/p/<slug>/<id>.html` — internal recon `docs/RETAILERS.md` (The Warehouse, recon 2026-10-29, live 2026-11-03).
- **Kmart NZ** — https://www.kmart.co.nz — Pokémon category live at `https://www.kmart.co.nz/category/toys/pokemon/` and brand page `/category/toys/brands/pokemon/440594` — [Kmart NZ category URLs returned in search](https://www.kmart.co.nz/category/toys/pokemon/); internal recon `docs/RETAILERS.md` (Kmart NZ, recon 2026-10-29 / 2026-11-01).
- **Farmers** — https://www.farmers.co.nz — Trading Cards category `/toys/games-cards-puzzles/trading-cards`; product URLs `/<category>/<slug>-<7-digit-SKU>` — internal recon `docs/RETAILERS.md` (Farmers, recon 2026-10-29).
- **JB Hi-Fi NZ** — https://www.jbhifi.co.nz — carries Magic, Final Fantasy, Pokémon; "pokemon trading card" search returns ~1,076 results — internal recon `docs/RETAILERS.md` (JB Hi-Fi NZ, recon 2026-10-29).
- **Mighty Ape** — https://www.mightyape.co.nz — large Pokémon TCG range; listing URLs under `/l/...` — internal recon `docs/RETAILERS.md` (Mighty Ape, recon pending).
- **Toyworld NZ** — https://www.toyworld.co.nz — collections `trading-cards` and `pokemon` — internal recon `docs/RETAILERS.md` (Toyworld, recon 2026-10-29 / 2026-11-01).
- **Noel Leeming** — https://www.noelleeming.co.nz — Warehouse Group electronics/toys chain — internal recon `docs/RETAILERS.md` (Noel Leeming, recon pending).
- **Warehouse Stationery** — https://www.warehousestationery.co.nz — Warehouse Group stationery chain — internal recon `docs/RETAILERS.md` (Warehouse Stationery, recon pending, Cloudflare challenge).
- **Whitcoulls** — https://www.whitcoulls.co.nz — books/stationery/gifts chain — internal recon `docs/RETAILERS.md` (Whitcoulls, recon pending).
- **Paper Plus** — https://www.paperplus.co.nz — books/stationery chain — internal recon `docs/RETAILERS.md` (Paper Plus, recon pending).
- **Woolworths NZ** (ex-Countdown supermarkets) — https://www.woolworths.co.nz — adapter present, recon pending (Akamai) — internal recon `docs/RETAILERS.md` (Woolworths NZ).
- **PB Tech** — https://www.pbtech.co.nz — electronics chain (Pokémon TCG presence unverified).
- **Briscoes** — https://www.briscoes.co.nz — homeware/kitchen chain (not a typical TCG seller).
- **1-day** — https://www.1-day.co.nz — Warehouse Group daily-deals site.
- **Mogo** — domain `www.mogo.co.nz` did **not resolve** (DNS ENOTFOUND) on 2026-11-04.

### Inferences
- NZ-focused price/listing confirmation is easiest via NZ TCG specialists that mirror these
  SKUs, e.g. Otakumart (Shopify) listing the 30th Celebration ETB at NZ$120 pre-order
  ([otakumart.co.nz](https://otakumart.co.nz/products/30th-celebration-elite-trainer-box-pokemon-tcg)) — useful as a cross-check of NZ pricing, though Otakumart is a specialist, not big-box.

### Gaps
- **TheMarket.com** (Warehouse Group marketplace, https://themarket.com) — could not confirm current operating status or Pokémon listings; `site:themarket.com` searches returned nothing. Status unverified.
- **Mogo** — no resolvable site at the obvious domain; may be defunct or a different URL. Unverified.
- **"The Markit" / Smiths City** (https://www.smithscity.co.nz) — appliances/furniture/electronics; no evidence it stocks sealed Pokémon TCG. Unverified but unlikely.

## E-commerce platform (with the detection signal)

### Takeaway
Platforms are a mix: Salesforce Commerce Cloud (The Warehouse), Intershop (Farmers), Shopify
(JB Hi-Fi NZ, Toyworld), a custom GraphQL headless stack (Kmart NZ), and custom (Mighty Ape).
Most big-box sites front their storefront with bot protection (Cloudflare, Akamai, DataDome)
and outsource search to Constructor.io (Farmers, Kmart) or Algolia (JB Hi-Fi).

### Cited Findings
- **The Warehouse — Salesforce Commerce Cloud**, site `Sites-twl-Site`, behind Cloudflare. Signals: Demandware endpoints `/on/demandware.store/Sites-twl-Site/...`, product URLs `/p/<slug>/<id>.html`, product IDs like `R3083239` — internal recon `docs/RETAILERS.md`.
- **Farmers — Intershop**, behind Akamai Bot Manager; search by Constructor.io. Signals: cookies `pgid-Farmers-Shop-Site`, `SecureSessionID-*`; `/INTERSHOP/web/WFS/Farmers-Shop-Site/...` endpoints; Akamai `_abck`/`bm_sz` cookies; Constructor key `key_wafe8wrKCXfPyWKw` embedded in page — internal recon `docs/RETAILERS.md`.
- **Kmart NZ — custom/headless (GraphQL gateway)**, behind Akamai; search by Constructor.io. Signals: `POST https://api.kmart.co.nz/gateway/graphql`; Constructor key `key_EyiTrcbGw7IFH3wR` embedded in page; product URLs `/product/<id>`, categories `/category/...` — internal recon `docs/RETAILERS.md`. Underlying commerce engine **unconfirmed** (Kmart AU is SFCC; NZ fronted by its own GraphQL gateway).
- **JB Hi-Fi NZ — Shopify**, store `prod-jbhifi-nz.myshopify.com`, behind Cloudflare, Algolia search. Signals: `myshopify.com` host, Shopify `/products/<handle>.js`, Algolia index `shopify_store_locations` — internal recon `docs/RETAILERS.md`.
- **Toyworld NZ — Shopify**. Signals: standard Shopify `/collections/`, `/products/<handle>.js`, `/products.json`; "Find in Store" via stockinstore.net — internal recon `docs/RETAILERS.md`.
- **Mighty Ape — custom platform** (Kogan-owned), behind DataDome. Signal: DataDome bot protection noted in recon; `/l/<slug>/` listing URLs — internal recon `docs/RETAILERS.md`.

### Inferences
- **Noel Leeming** and **Warehouse Stationery** are Warehouse Group siblings of The Warehouse, so plausibly also Salesforce Commerce Cloud — **unconfirmed** (not yet reconned; Warehouse Stationery showed a Cloudflare challenge).
- Generic NZ hobby/TCG shops the bot already supports (Card Merchant, Iron Knight, Toyworld, Otakumart) are **Shopify**, detected via `/products.json` and `cdn.shopify.com` — internal recon `docs/RETAILERS.md` (Shopify generic).

### Gaps
- **Whitcoulls, Paper Plus, Briscoes, PB Tech, 1-day, Woolworths NZ** — e-commerce platform **unconfirmed**; automated fetch was blocked (403/Cloudflare) and the US search tool did not surface their pages. No reliable public signal captured.

## Do they list 30th Celebration / Mega Evolution sealed product? (preorder / in-stock)

### Takeaway
The Warehouse, Kmart NZ and Farmers have demonstrably carried 30th Celebration / Mega
Evolution sealed items in Oct–Nov 2026 (internal recon). JB Hi-Fi NZ and Mighty Ape carry
broad Pokémon TCG ranges and almost certainly include the set, but a specific 30th-item sighting
was not independently captured. Mega Evolution is the current TCG series, so these items are
"in-stock/newly-releasing", not distant preorders.

### Cited Findings
- **The Warehouse** — 30th-era products observed live: a 30th **Booster Bundle**, a **Mini Tin**, and a **Build & Battle Box** first-sighted around 2026-10-31 to early Nov 2026; items shown as `IN_STOCK` or `FIND_IN_STORE` (in-store only) — internal recon `docs/RETAILERS.md` (The Warehouse listing timing notes).
- **Kmart NZ** — Trading Cards category had ~85 products (52 sealed TCG) in Oct 2026; most Pokémon flagged `FulfilmentChannel: 2` = **in-store only**. Kmart AU sibling range includes Mega Evolution ETBs/battle decks/mini-tins (e.g. "Mega Evolution – Perfect Order Elite Trainer Box", "Mega Evolution Ascended Heroes Mini Tins") — internal recon `docs/RETAILERS.md`; [Kmart AU Mega Evolution listings](https://www.kmart.com.au/product/pokemon-trading-card-game:-mega-evolution-perfect-order-elite-trainer-box-43737062/).
- **Farmers** — a **30th Booster Bundle** was tracked; it sold out and was delisted from search/category on 2026-11-01 while the per-store endpoint still answered — internal recon `docs/RETAILERS.md` (Farmers unlisted-products note).
- **EB Games Australia** (for reference, not NZ) — listed 30th Celebration **Ultra-Premium Collection (Espeon)** as **Preorder, dated Fri 06 Nov 2026** — [ebgames.com.au product page](https://www.ebgames.com.au/product/other/378902-pokemon-tcg-30th-celebration-ultra-premium-collection-espeon).
- **JB Hi-Fi NZ** — broad TCG range incl. Pokémon (~1,076 "pokemon trading card" results) — internal recon `docs/RETAILERS.md`. Specific 30th SKU not independently captured.

### Inferences
- Because Mega Evolution is the **current** TCG block and 30th Celebration released 16 Sep 2026, any big-box that stocks current Pokémon TCG (The Warehouse, Kmart, Farmers, JB Hi-Fi, Mighty Ape, Toyworld, likely Noel Leeming / Warehouse Stationery / Whitcoulls / Paper Plus / Woolworths) is expected to carry at least some 30th Celebration / Mega Evolution SKUs while stock lasts.

### Gaps
- Could not independently confirm a specific **30th Celebration** SKU listing on Mighty Ape, JB Hi-Fi NZ, Noel Leeming, Warehouse Stationery, Whitcoulls, Paper Plus or Woolworths NZ (sites blocked automated fetch; US search tool did not surface `.co.nz` product pages). Mark stock **unconfirmed** for these.

## Purchase limits & in-store-only notes

### Takeaway
Per-customer purchase limits are common on hot 30th/Mega Evolution items, and a large share of
big-box Pokémon TCG is **in-store only** (not sold online), which matters for an online bot.

### Cited Findings
- **The Warehouse** — a hot Pokémon item carried a visible **"LIMIT 10 PER CUSTOMER"** label; many Pokémon tiles are `FIND_IN_STORE` = in-store only (alerted as online out-of-stock) — internal recon `docs/RETAILERS.md`.
- **Kmart NZ** — most Pokémon products are **in-store only** (`FulfilmentChannel: 2`); these are always OUT online and flagged "In-store only" — internal recon `docs/RETAILERS.md`.
- **Farmers** — sold-out items can **disappear from search/category** while still existing (per-store endpoint still answers) — internal recon `docs/RETAILERS.md`.
- **EB Games Australia** (reference) — **limit 1 product per customer** on the 30th UPC preorder — [ebgames.com.au](https://www.ebgames.com.au/product/other/378902-pokemon-tcg-30th-celebration-ultra-premium-collection-espeon). EB Games AU also publicly walked back initially-double 30th prices (e.g. ETB revised to A$120) — [Press Start](https://press-start.com.au/?p=167874).

### Inferences
- Expect similar 1–2 per-customer caps on 30th UPCs and ETBs at NZ big-box during launch windows; NZ-specific limit text was not captured for most retailers.

### Gaps
- No captured NZ purchase-limit text for Kmart NZ, Farmers, JB Hi-Fi NZ, Mighty Ape, Toyworld or the unverified chains. Unconfirmed.

## Retailers to exclude (not viable NZ Pokémon-TCG targets)

### Takeaway
Several named candidates are closed, Australia-only, or not TCG sellers.

### Cited Findings
- **EB Games NZ / Zavvi NZ** — **closed**. All 38 NZ stores shut **31 January 2026**, distribution centre **28 February 2026**; `ebgames.co.nz` now 302-redirects to `ebgames.com.au` — [ScreenHub](https://www.screenhub.com.au/news/games/eb-games-new-zealand-closure-confirmed-2690747/); [1News](https://www.1news.co.nz/2026/01/14/all-eb-games-stores-in-nz-confirmed-to-close-at-end-of-month/); [Stevivor (38 stores)](https://stevivor.com/news/eb-games-australia-closing-all-of-new-zealands-38-stores/). Repo already marks it "dropped: stores have closed."
- **Toymate** — Australia-only ("Proudly Australian owned... stores across Sydney, Melbourne, Perth, Brisbane and the Gold Coast"); no NZ stores or NZ site found — [Toymate store listings / ellaslist](https://m.ellaslist.com.au/articles/toymate-biggest-toy-store-Australia).
- **Torpedo7** — sold by Warehouse Group to Tahua Partners for $1 (Feb 2024); operates as an **outdoor sports/gear** retailer and was rebranding in 2025 — [Wikipedia: Torpedo7](https://en.wikipedia.org/wiki/Torpedo7); [Newstalk ZB rebrand](https://www.newstalkzb.co.nz/on-air/heather-du-plessis-allan-drive/audio/roger-harper-torpedo7-owner-reveals-plans-to-rebrand-retailer). Not a TCG seller.

### Inferences
- **Big W** has no NZ retail presence (Australian Woolworths Group discount chain) — treat as out of scope for NZ.
- **Smiths City / "The Markit"** are appliances/furniture/electronics; no evidence of sealed Pokémon TCG.

### Gaps
- Big W NZ absence is inferred from general market knowledge, not a cited NZ-specific source in this session.
