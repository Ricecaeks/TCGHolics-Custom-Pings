# NZ hobby / game / collectible shops selling Pokémon TCG — website & e-commerce platform (late 2026)

> Scope: New Zealand independent/specialty hobby, board-game, comic and collectible shops (not the big chains) that sell Pokémon TCG sealed product online, with platform detection focused on Shopify. Research date: 2026-11-04.
>
> **Method & confidence note (read first).** Direct `curl` platform probing was blocked by the sandbox (most hosts returned an empty body; `-k` is disallowed), so platform detection relied on `WebFetch` of `/products.json` (the definitive Shopify test: a Shopify store returns a JSON object with a `products` array), `/collections.json`, and homepage platform signals. `WebSearch` runs US-region and is **very noisy** for small NZ businesses — many queries returned overseas/eBay/spam results and few exact NZ domains. Several `/products.json` probes failed with `ENOTFOUND` (my domain guess was wrong, not proof the shop lacks a site) or `429 Too Many Requests` (throttled — often itself a sign of a Shopify/Cloudflare store, but not a confirmation). Treat every "unconfirmed" below as needing a manual re-check from an NZ IP/browser. Repo-confirmed platforms are carried from `docs/RETAILERS.md`.

## Key Question 1 — Shop name, website URL, and detected e-commerce platform (Shopify first)

### Takeaway
Among *dedicated* NZ TCG shops, Shopify dominates (Card Merchant, Iron Knight, Toyworld are confirmed Shopify and already monitored). Among *general* hobby/comic/collectible shops, the ones I could verify this session were **not** Shopify — Games Lab is Lightspeed, Heroes for Sale is ComicHub, Geek Gift was WordPress (now closed), Toyco is custom. So the generic Shopify adapter will catch the specialist card shops but will likely miss most comic/hobby generalists, which skew to Lightspeed / ComicHub / WordPress.

### Cited Findings

**Confirmed Shopify (already in repo — safe to point the generic adapter at):**
- **Card Merchant NZ** — https://cardmerchant.co.nz — Shopify. Public `products.json` works; ~9,750 products in Oct 2026; verified live 2026-10-29. Carries Pokémon TCG. — [repo `docs/RETAILERS.md`](../../docs/RETAILERS.md)
- **Iron Knight Gaming** — https://ironknightgaming.co.nz — Shopify. Verified live 2026-10-29 via storefront JSON. — [repo `docs/RETAILERS.md`](../../docs/RETAILERS.md)
- **Toyworld NZ** — Shopify (adapter `toyworld`). Monitors `trading-cards` + `pokemon` collections; 36 stores with per-store stock. — [repo `docs/RETAILERS.md`](../../docs/RETAILERS.md)

**Verified NOT Shopify (this session):**
- **Games Lab** (Auckland) — https://www.gameslab.co.nz — **Lightspeed eCom** ("Powered by Lightspeed" in footer, links to lightspeedhq.com; no Shopify/Woo/BigCommerce/Squarespace/Wix signals). Pokémon category page: `https://www.gameslab.co.nz/products/pokemon`. — [WebFetch gameslab.co.nz 2026-11-04]
- **Heroes for Sale** (Auckland comic shop, since 1995) — https://heroes.co.nz — **ComicHub** platform; `heroes.co.nz` 302-redirects to `https://stores.comichub.com/heroes_for_sale_/`. Not Shopify. — [WebFetch heroes.co.nz 2026-11-04]; [authors.org.nz event page](https://authors.org.nz/event/auckland-comic-shop-heroes-for-sale-to-host-free-comic-book-day-with-local-artist-memoh/)
- **Geek Gift NZ** — https://geekgift.co.nz — **WordPress** (`/wp-content/uploads/` image paths). **Site shows a closure notice** ("Geek Gift is closed… orders still awaiting delivery are on their way") — treat as defunct. Previously a collectibles/TCG store running a monthly pre-order model. — [WebFetch geekgift.co.nz 2026-11-04]; [GeekGift Trustpilot](https://ca.trustpilot.com/review/geekgift.co.nz)
- **Toyco** (NZ toy retailer) — https://toyco.co.nz — homepage returned ~102 KB with **no** Shopify/Woo/BigCommerce/Squarespace/Wix signals; platform is custom/other (likely a NZ enterprise platform). Not Shopify. — [curl toyco.co.nz 2026-11-04]
- **Mighty Ape** — https://www.mightyape.co.nz — custom platform behind **DataDome** bot protection (recon pending in repo). Has a hobby/trading-card section but is not Shopify and is bot-protected. — [repo `docs/RETAILERS.md`](../../docs/RETAILERS.md)

**Real NZ shops found but platform unconfirmed (need manual re-check):**
- **Vagabond Games & Collectables** (Auckland, Courthouse Lane / Queen St area) — https://www.vagabond.co.nz — `products.json` returned **404**, so **not** a (default) Shopify store; actual platform unconfirmed. Sells Pokémon TCG, Lorcana, Yu-Gi-Oh!. — [Boardoro store page](https://boardoro.com/en/store/vagabond-games-and-collectables-auckland-new-zealand); [Boardoro Auckland](https://boardoro.com/en/oceania/new-zealand/auckland)
- **SecretRareVault NZ** — https://secretrarevault.co.nz — self-describes as "sealed and graded TCG for NZ players and collectors," sells sealed Pokémon. `products.json` returned **429 (throttled)** on repeated tries — consistent with a Shopify/Cloudflare store but **unconfirmed**. — [SecretRareVault Trustpilot](https://dk.trustpilot.com/review/secretrarevault.co.nz)
- **Dice Goblin** (Auckland, 691 Manukau Rd, Royal Oak) — gaming lounge + shop; lists Pokémon TCG and MTG. Website URL not confirmed (`dicegoblin.co.nz` does not resolve). — [Boardoro Auckland](https://boardoro.com/en/oceania/new-zealand/auckland); [SWNZ article](https://swnz.co.nz/2021/02/11/star-wars-gaming-in-auckland-with-dice-goblin/)
- **Anime House** (Auckland) — lists Pokémon TCG and One Piece Card Game. Website unconfirmed. — [Boardoro Auckland](https://boardoro.com/en/oceania/new-zealand/auckland)
- **Hobby Lords, Takapuna** (Auckland) — community "trade days" for Pokémon noted on Reddit; Boardoro lists it but shows no card-game tags. Website unconfirmed. — [Boardoro Auckland](https://boardoro.com/en/oceania/new-zealand/auckland)
- **Shuffle n Cut Hobbies & Games** (Auckland) — Boardoro-listed; no card tags shown. Website unconfirmed. — [Boardoro Auckland](https://boardoro.com/en/oceania/new-zealand/auckland)
- **Comics Compulsion** (Christchurch, 58 Main North Rd, Papanui) — has a website (per Christchurch Libraries blog) but the URL did not verify (`comicscompulsion.co.nz` connected but returned empty/blocked). Many NZ comic shops use ComicHub (see Heroes for Sale), so this is a likely ComicHub store — unconfirmed. — [Christchurch Libraries blog](https://my.christchurchcitylibraries.com/blogs/post/free-comic-book-day-2019-and-star-wars-day-saturday-4-may-2019)
- **King of Cards** (Herne Bay / Queens Arcade, Queen St, Auckland) — card games, board games, comics. Website unconfirmed. — [Yellow.co.nz games & puzzles](https://yellow.co.nz/herne-bay/games-puzzles)

**Non-hobby-shop NZ online options (for context, outside the specialist-shop scope):**
- **Pokémon Center** official AU/NZ online store — announced/launched 2024; sells official sealed TCG, plush, figures; online-only, no NZ physical stores. Not an independent hobby shop. — [Inside Retail NZ](https://insideretail.co.nz/2024/06/19/pokemon-launches-online-stores-for-australia-new-zealand/); [Nintendo AU](https://nintendo.com/au/news-and-articles/pokemon-center-online-store-coming-soon-to-australia-and-new-zealand)
- **Fire Spin Hobby** — self-describes as "NZ's premier destination for authentic Pokémon TCG" (English/Japanese/Chinese). Only surfaced on a raw dev IP host (`firespin.…sslip.io`); real production domain/platform unconfirmed — verify before trusting. — [WebSearch result 2026-11-04](https://firespin.170.64.171.111.sslip.io/)

### Inferences
- The generic Shopify adapter's natural NZ targets are the **dedicated single-vertical TCG shops** (Card Merchant, Iron Knight already covered). New Shopify additions are most likely to be found among other specialist card shops, not among comic/toy generalists.
- NZ **comic** shops cluster on **ComicHub** (`stores.comichub.com/<shop>`), which exposes a per-shop storefront — a single ComicHub adapter could cover many comic shops (Heroes for Sale confirmed; Comics Compulsion probable) better than the Shopify adapter would.
- A `/products.json` **404** reliably rules out a default Shopify store; a **429** on `/products.json` is weakly *suggestive* of Shopify-behind-Cloudflare but must be confirmed (e.g. via `cdn.shopify.com` assets or `Powered by Shopify`).

### Gaps
- Exact live domains for Dice Goblin, Anime House, Hobby Lords, Shuffle n Cut, Comics Compulsion, King of Cards, Vagabond's platform — WebSearch did not surface them and domain guesses failed (`ENOTFOUND`). Needs an NZ-IP browser session or Google Maps/Facebook lookups.
- Task-list shops I could **not** confirm as live NZ online stores: **Toymate NZ** (`toymate.co.nz` does not resolve; Toymate is an Australian brand — no NZ webstore found), **Kapow Collectibles**, **Area 52**, **Overlord Games**, **The Laughing Dog Games** (Laughing Dog is a UK firm), **Geekery**, **Serious Fun**, **Board Game Barrister NZ**, **Dice & Dagger**, **Fantasy Flight NZ**, **Imaginative Minds**, **Toy Box**, **Collectormania NZ**, **CardVault NZ**, **Acquire/Mindgames NZ** (closest match "Mind Games" is Canadian; an NZ `mindgames.co.nz` did not resolve this session). Each needs manual verification.
- SecretRareVault and secretrarevault's throttling blocked platform confirmation.

## Key Question 2 — Pokémon TCG sealed range (incl. 30th Celebration / Mega Evolution), stock state, and a monitorable "new products" / Pokémon collection page

### Takeaway
I confirmed Pokémon TCG is sold by Games Lab, Vagabond, Anime House, Dice Goblin and SecretRareVault, and that Games Lab exposes a clean Pokémon category URL. I could **not** verify specific set availability (30th Celebration / Mega Evolution) or preorder-vs-in-stock on any of these this session, because product pages weren't fetched (budget) and several sites throttled/blocked probes.

### Cited Findings
- **Games Lab** has a dedicated, watchable Pokémon category page: `https://www.gameslab.co.nz/products/pokemon` (Lightspeed — would need a Lightspeed adapter, not the Shopify one). Specific sealed SKUs not confirmed. — [WebFetch gameslab.co.nz 2026-11-04]
- **SecretRareVault NZ** states it sells "a variety of sealed Pokémon." — [SecretRareVault Trustpilot](https://dk.trustpilot.com/review/secretrarevault.co.nz)
- **Vagabond / Dice Goblin / Anime House** are tagged as carrying Pokémon TCG in the NZ directory, but no online sealed-product listing was confirmed. — [Boardoro Auckland](https://boardoro.com/en/oceania/new-zealand/auckland)
- **Card Merchant / Iron Knight / Toyworld** carry Pokémon TCG and (as Shopify stores) expose `/products.json` sorted most-recently-updated-first, which is exactly what the repo's generic adapter already watches for new listings. — [repo `docs/RETAILERS.md`](../../docs/RETAILERS.md)
- For Shopify shops generally, the monitorable endpoints are `/products.json?limit=250&page=N` (catalogue, newest-updated first) and `/collections/<handle>/products.json`; `/collections.json` lists collection handles (e.g. a `pokemon` or `new-arrivals` handle). Confirmed as the repo's approach. — [repo `docs/RETAILERS.md`](../../docs/RETAILERS.md)

### Inferences
- For any shop confirmed as Shopify, a Pokémon-specific watch page almost always exists at `/collections/pokemon` (or similar) and can be polled via `/collections/pokemon/products.json`; for 30th Celebration / Mega Evolution, a title/tag keyword filter on the catalogue feed (as the repo already does) is more reliable than hoping for a per-set collection.
- Lightspeed shops (Games Lab) expose category pages at `/products/<category>` but not a Shopify-style JSON feed, so monitoring them means HTML scraping, not the generic adapter.

### Gaps
- No confirmation of 30th Celebration or Mega Evolution sealed availability, or preorder vs in-stock, at any specialist/hobby shop — product pages were not fetched and several sites blocked/throttled automated requests. This needs targeted per-shop product-page checks (ideally from an NZ browser session).
