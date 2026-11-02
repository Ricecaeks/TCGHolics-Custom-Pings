# Fast stock alerts: what determines speed, how monitors work, and what services can reveal (as of 2 November 2026)

Evidence labels: **[Doc]** = official documentation or statute-level source. **[Vendor]** = a seller's unverified marketing claim. **[Anecdote]** = forum or hobbyist report. **[Secondary]** = commentary or media. "(excerpt)" means I saw only a search excerpt or summary, not the full page. Legal content is general information, not legal advice. No requests were sent to retailer sites.

## How do established monitors describe how they work, and what can't be established?

### Takeaway
Monitors publish outcomes ("instant", "<1s", "7s"), not methods: none I could read names its polling interval per retailer, its data sources, or how it measures speed. No independent benchmark was found, so no claimed speed can be verified. Zephyr's NZ/AU coverage could not be confirmed either.

### Cited Findings
**NZ services**
- [Vendor] Collectable.gg advertises instant Discord alerts, 150+ NZ stores, 500+ daily restock alerts, and NZ$15/month with a 2-day trial requiring a card. It also runs a peer-to-peer marketplace. Its samples list cities and "Online Now", which suggests online and in-store coverage, but the page does not state this outright. No polling rate, data source or mobile app is described — [Collectable.gg](https://www.collectable.gg/)
- [Vendor] Collectable says it detects a store's delivery "the moment it hits their system". It gives no mechanism, and "their system" is undefined. This is the nearest public wording to the owner's "loaded but not visible" question, and it is not evidence of such access — [Collectable.gg](https://www.collectable.gg/)
- [Vendor] DropNZ says stock is checked every few minutes across 71 stores, online and branch by branch, and elsewhere says it watches over 60 retailers. The two counts may measure different things or may not reconcile. It claims a 7-second average from Shopify restock to ping. NZ$6/month after a 2-day trial. The free radar runs 15 minutes behind and the sample feed an hour behind — [DropNZ](https://dropnz.com/)

**AU services**
- [Vendor] DropZone claims <1s average alert speed and always-on monitoring of named retailers including JB Hi-Fi, BIG W, EB Games, Target, Kmart, Amazon AU and Costco. A$10/month through Whop, with Whop app notifications as a backup to Discord. In-store finds rely on members posting shelf sightings in state channels, not on automated store checks. It says it cannot promise stock — [DropZone](https://dropzone.gg/)
- [Vendor] CardWatch AU offers email or Telegram alerts (excerpt) — [CardWatch](https://cardwatch.com.au/)

**Zephyr and wider monitors**
- [Vendor] Zephyr Monitors describes itself as a fast, reliable monitor supplier to Discord servers (excerpt) — [X profile](https://x.com/ZephyrMonitors)
- [Secondary] A reseller listing describes it as a bot service for group owners that scans hundreds of storefronts and pings on new listings and restocks, focused on sneaker and general retail (excerpt; full page returned 403) — [Cop Supply](https://cop.supply/cook-group-monitors-tools/zephyr-monitors/)
- [Vendor] UK group PokéMart announced a "PokeMart Zephyr Monitor" Android app, pitched as avoiding Discord's unreliable notifications and giving instant restock and queue alerts, with premium membership required (excerpt; post could not be opened) — [PokéMart on X](https://x.com/pokemartalerts/status/2064395375713149170)

**Mobile apps**
- [Vendor] PokeNotify offers push alerts and says it covers Australia, with region monitors for subscribers (excerpts) — [Google Play](https://play.google.com/store/apps/details?id=com.pokenotify.app&hl=en_US); [PokeNotify](https://www.pokenotify.com/discord)
- [Vendor] Poke Alerts says it watches 30+ retailers across the US, Canada, UK and Australia (excerpt) — [Google Play](https://play.google.com/store/apps/details?id=collect.app.mobile&hl=en_US)

**Open-source sneaker and Shopify monitors (the only monitors showing their method)**
- [Anecdote] These projects poll a store's public `/products.json` or similar, compare with stored state, and post changes through Discord webhooks. Stated intervals range from an 8-second delay and a 5 to 30-second setting up to a recommended 30 seconds or more without proxies, to avoid bans (excerpts) — [subreme/shopify-monitor](https://github.com/subreme/shopify-monitor/); [Dam998/shopify-monitor](https://www.github.com/Dam998/shopify-monitor); [NERYS monitor lite](https://github.com/Snivyn/NERYS-product-monitor-lite); [aco-bot releases](https://github.com/ogdoo22/aco-bot/releases)

### Inferences
- "<1s" and "7s" most plausibly measure part of the pipeline, such as detection to post, not stock going live to a member's phone. Nothing published confirms this. A 7-second figure limited to Shopify stores is more credible than a blanket figure, because non-Shopify retailers add feed delays (see next section).
- DropZone's reliance on members for in-store finds suggests branch-level automated stock is not universal. NZ's branch-level claims (DropNZ, possibly Collectable) may rest on retailer-specific public store-stock lookups, but this cannot be confirmed from outside.
- The paid-delay tiers (DropNZ's free radar and sample feed) show that part of a free user's lag is a deliberate product choice, so free-tier comparisons say little about a monitor's real speed.

### Gaps
- No independent speed test of any named service was found. The fair test is to subscribe and log timestamps against the bot's own detections.
- I found no Pokémon-specific Zephyr product for NZ or AU. The brief's grouping of Zephyr with NZ/AU cards could not be confirmed.
- App listings for PokeNotify and PokeWatcher-style apps gave no readable polling or source claims. Zephyr and Discord server listings could not be read in detail.

## What are the real latency sources?

### Takeaway
Polling sets only part of the delay. A monitor cannot see a change before the public surface it reads has updated, and documented search-feed delays alone can be minutes. For the current bot, polling is still the largest delay it controls: on average 1 to 2.5 minutes for listings and 5 to 7.5 minutes for store stock.

### Cited Findings
**Constructor (search platform)**
- [Doc] Constructor recommends a daily full sync plus intraday delta or patch updates to reflect inventory, and does not recommend sending updates more often than every 5 minutes. Update frequency is otherwise the customer's choice — [Constructor product catalog](https://docs.constructor.com/docs/integrating-with-constructor-product-catalog)
- [Doc] A 1,000-item request processes in seconds and goes live in 2 to 5 minutes. Its example retailer batches price and inventory updates every 15 minutes and reports 2 to 3 minutes latency. Urgent launches are still sent as batches. This is an example, not a guarantee — [Constructor ingestion best practices](https://docs.constructor.com/docs/integrating-with-constructor-product-catalog-catalog-ingestion-and-indexing-best-practices)

**Algolia (search platform)**
- [Doc] Indexing is asynchronous: each write joins a queue, usually finishes in milliseconds or seconds, and takes longer as the queue grows — [Algolia asynchronicity guide](https://www.algolia.com/doc/guides/sending-and-managing-data/send-and-update-your-data/in-depth/asynchronicity-and-when-to-wait-for-tasks/)
- [Doc] Support guidance allows for seconds, or minutes when many records are indexed at once (excerpt) — [Algolia support](https://support.algolia.com/hc/en-us/articles/4406981957905-Why-aren-t-my-objects-immediately-available-for-search-after-being-added)

**Shopify (official timing not found)**
- [Anecdote] A forum answer says collection pages update immediately while storefront search can take a few hours for new products, and third-party search apps may need a re-index (excerpt) — [Shopify community](https://community.shopify.com/t/search-function-not-working/654400)
- [Anecdote] A merchant reports 10 to 45 minutes from admin stock change to storefront, in a thread about a specific setup (excerpt) — [Shopify community](https://community.shopify.com/t/inventory-sync-delay-and-variant-mapping-issues-with-independent-stores/669712)
- [Anecdote] Another 5 to 10-minute delay was traced to browser caching, with incognito showing the change at once (excerpt) — [Shopify community](https://community.shopify.com/t/product-updates-not-reflecting-immediately-on-storefront-5-10-minute-delay-in-same-browser/637606)
- [Doc, comparator only] Adobe Commerce Live Search says a product update can take up to 15 minutes, which shows the order of magnitude at another platform (excerpt) — [Adobe](https://experienceleague.adobe.com/docs/commerce-merchant-services/live-search/live-search-admin/indexing.html)

**Project evidence**
- A recent commit in this repo is titled as backing off from Kmart's gateway (`1978698`), so blocking is a live constraint here, not a theoretical one.

### Inferences
- **Polling arithmetic:** average detection delay is about half the interval and the worst case is the full interval. So 2 to 5 minutes gives 1 to 2.5 minutes average, and 10 to 15 minutes gives 5 to 7.5 minutes average.
- **Illustrative floor on a Constructor-backed site** (assuming it follows the example pattern): 15-minute batches average 7.5 minutes of waiting, plus 2 to 3 minutes latency, or about 10 minutes before any monitor can see the change. Polling every 30 seconds then adds at most 30 seconds. Faster polling has steeply diminishing returns once it is well below the retailer's update cycle. Actual NZ retailer cadence is unknown.
- **Likely order of impact for this bot, largest first:**
  1. Store-stock interval (5 to 7.5 minutes average)
  2. Retailer feed or batch cycle (unknown, potentially many minutes)
  3. Listing interval (1 to 2.5 minutes average)
  4. Blocks and backoff (can wipe out speed gains entirely)
  5. Search indexing (seconds to minutes)
  6. Phone notification delivery (unmeasured)
  7. Discord webhook posting (normally small unless queued)
- **Different public surfaces can disagree** in freshness, so a search result can lag a page that is already publicly linked. This may explain some of what looks like "loaded but not visible": the item is public but not yet surfaced in search. It is lag, not hidden data.
- The bot can measure its own floor by logging when each retailer's state changes. Clusters at regular times would indicate a batch cycle. This needs no extra requests.

### Gaps
- No official Shopify figure was found for storefront search delay, inventory propagation, or `products.json` caching. CDN and full-page cache behaviour for Online Store themes remains unverified.
- No public documentation was found on the update cadence or store-system delay of Kmart NZ, Farmers, The Warehouse, Whitcoulls, Paper Plus or JB Hi-Fi NZ. Whether a physical delivery is receipted before shelf placement is also undocumented.
- Constructor's figures are generic and do not describe any specific retailer's configuration.

## What are Discord's limits and practical delivery delays?

### Takeaway
Discord's posted limits rarely bottleneck a small bot, but a burst to one webhook can queue. One setting matters directly: webhooks parse only user mentions by default, so role pings need `allowed_mentions` set explicitly. Discord publishes no per-webhook number and no delivery-time figure.

### Cited Findings
- [Doc] Global limit: 50 requests per second, applied per IP when no authorization header is present, independent of per-route limits — [Discord rate limits](https://docs.discord.com/developers/topics/rate-limits)
- [Doc] Webhooks are a top-level resource with separately calculated limits. Discord says not to hard-code limits; apps should read `X-RateLimit-*` headers and honour `Retry-After` on a 429 — [Discord rate limits](https://docs.discord.com/developers/topics/rate-limits)
- [Doc] An IP is temporarily restricted after 10,000 invalid requests (401, 403, 429) in 10 minutes. Shared-scope 429s do not count. A webhook returning 404 must not be retried — [Discord rate limits](https://docs.discord.com/developers/topics/rate-limits)
- [Doc] Execute Webhook allows 2,000 characters of content and up to 10 embeds. Without `wait=true`, a message that fails to save returns no error. `thread_id` targets a thread. The page advises using `allowed_mentions` when passing user-generated content — [Discord webhook resource](https://docs.discord.com/developers/resources/webhook)
- [Doc] Embed limits: title 256, description 4,096, 25 fields, field name 256, field value 1,024, footer 2,048, author 256, and 6,000 characters combined across a message's embeds — [Discord message resource](https://docs.discord.com/developers/resources/message)
- [Doc] `allowed_mentions` takes up to 100 role IDs and 100 user IDs, and `parse` cannot be combined with those lists. Webhooks default to parsing user mentions only — [Discord message resource](https://docs.discord.com/developers/resources/message)
- [Secondary] A third-party product doc's excerpt gives roughly 5 requests per 2 seconds per webhook URL, while the page's fetched text says it queues about one message per second to stay within limits. Treat both as that vendor's choices, not Discord's spec — [Konvoi](https://docs.konvoi.gg/api/webhooks)
- [Secondary, low confidence] Unofficial guides say mobile pushes pass through Google or Apple push services and device battery settings can delay them (excerpts) — [WiseChecker](https://wisechecker.com/?p=30759); [WiseChecker](https://wisechecker.com/?p=25162)
- [Vendor] Services market apps partly on Discord notifications being unreliable, as PokéMart does, and DropZone offers a second notification path (excerpts/page) — [PokéMart on X](https://x.com/pokemartalerts/status/2064395375713149170); [DropZone](https://dropzone.gg/)

### Inferences
- Webhook posting is usually a tiny share of end-to-end time compared with polling. The exception is a large restock posted through one webhook, where one queue delays later alerts. Separate webhooks per channel or a priority queue for hot products would limit this, and exact safe rates should come from the response headers.
- Using `wait=true` gives both failure detection and a timestamp for measuring detection-to-post latency, at the cost of a slightly slower response. Combining many items into one message can also reduce bursts.
- If role pings are arriving today, `allowed_mentions` is presumably already set. It is worth confirming in the code because the doc's default would silently suppress them.

### Gaps
- No official per-webhook rate figure and no official webhook-to-push latency was found. Phone-side delay is best measured by a test: compare the post timestamp to arrival time on Android and iOS.
- Whether a role mention adds delay relative to a user mention: nothing found.
- The fetch of Discord's rate-limit page noted a stray link to an unrelated domain (`takeb1nzyto.space`) in the page content. I did not open it or use it. It may be a page or conversion artefact.

## Which adaptive polling techniques improve speed without raising request volume?

### Takeaway
The best gain is reallocating the same requests: more for hot products, retailers and release windows, fewer elsewhere. Evidence here is mostly basic HTTP standards plus my own arithmetic, since vendors do not publish their schedules. Sitemaps look too slow to help with speed.

### Cited Findings
- [Doc] HTTP defines `If-None-Match` as a precondition and 304 Not Modified as a status, so a server that supports them can answer without resending the body (section listing read only) — [RFC 9110](https://www.rfc-editor.org/rfc/rfc9110.html#name-conditional-requests)
- [Doc] Shopify's Oxygen host does not return 304. This applies to Hydrogen and Oxygen headless stores, not necessarily standard Online Store themes (excerpt) — [Shopify Hydrogen caching](https://shopify.dev/docs/custom-storefronts/hydrogen/data-fetching/cache)
- [Secondary] A third-party blog says Shopify sets `Cache-Control` and `ETag` headers, unconfirmed by Shopify's docs (excerpt) — [GemPages](https://gempages.net/blogs/shopify/shopify-cache)
- [Doc] Hydrogen documentation says its sitemap is cached for 24 hours and unpublished products are removed from it (excerpt) — [Shopify Hydrogen SEO](https://shopify.dev/custom-storefronts/hydrogen/seo)
- [Secondary] Shopify sitemaps contain only published items, with `lastmod` per entry (excerpt) — [Visionary Marketing](https://visionary-marketing.co.uk/blog/shopify-sitemap)
- [Anecdote] Stores can disable or restrict public JSON feeds, some disallow `/*.json` in robots.txt, and some return 429s to datacentre IPs (excerpts) — [Apify exporter](https://apify.com/practical_ai_lab_jp/pal-shopify-product-collection-export); [Apify changelog](https://apify.com/glidepath/shopify-products-scraper/changelog.md)
- [Doc] Constructor's batching guidance implies a cycle is normal, with updates grouped at 10,000 items or 1 minute — [Constructor ingestion best practices](https://docs.constructor.com/docs/integrating-with-constructor-product-catalog-catalog-ingestion-and-indexing-best-practices)

### Inferences
- **Worked example at equal volume (illustrative):**
  - Today: 100 products every 3 minutes is about 33 requests per minute, with a 90-second average delay.
  - Tiered: 10 hot products every 30 seconds plus 90 others every 7 minutes is about 33 requests per minute. The hot average falls to 15 seconds, and the others rise to 3.5 minutes.
- **Good hot-list inputs:** set release proximity, sell-out history, recent restocks and member demand. Keep a slow sweep for everything else so unexpected stock is still caught.
- **Release windows:** raise rates for a limited window around known dates, then return to baseline. Offset this by lowering overnight polling only if the bot's own logs show changes don't occur then.
- **Match retailer rhythm:** once logs reveal a batch cycle, polling more often than the cycle wastes requests, so schedule checks just after expected update times.
- **Reuse what's already fetched:** a single search or collection response can cover many products, which is more efficient than per-item checks. Conditional requests help only where retailers return validators, which needs checking per endpoint from existing bot responses. They are unlikely to help on POST-based search APIs.
- **Respect signals:** honour 429s and `Retry-After`, add jitter, and stop escalating on blocks. Being blocked costs far more time than any polling gain. This project's Kmart backoff change fits this.
- **Sitemaps and feeds:** useful for discovering new listings on a slow schedule, not for fast stock alerts, given documented caching in at least one Shopify setup. Atom feed contents were not verified.

### Gaps
- Commercial monitors' scheduling logic is not public.
- No source measured how much tiered polling helps retail monitors. The numbers above are arithmetic, not results.
- Validator support on specific NZ endpoints is unknown. It should be read from responses the bot already receives, rather than through new probing.

## What public early signals exist for upcoming drops in NZ and AU?

### Takeaway
Official global release dates are the strongest signal, and the next is imminent: Delta Reign on 6 November 2026, four days from this note's date. NZ-specific signals are weak: I found no public NZ distributor schedule, so retailer pre-orders and community reports must be treated as lower-confidence.

### Cited Findings
- [Doc] Pokémon's own announcement, dated 20 August 2026, sets Mega Evolution—Delta Reign for 6 November 2026, with over 135 cards. It gives no region-specific retail detail — [Pokémon](https://www.pokemon.com/us/news/the-pokemon-tcg-mega-evolution-delta-reign-expansion-arrives-november-6-2026)
- [Doc] A related October 2026 Pokémon article concerns Kyogre, Groudon and Giratina promo cards at participating retailers. Details and regions were not read — [Pokémon](https://www.pokemon.com/us/news/the-pokemon-tcg-mega-evolution-delta-reign-expansion-arrives-november-6-2026)
- [Doc] Pitch Black was officially dated 17 July 2026 (excerpt) — [Pokémon](https://www.pokemon.com/us/news/the-pokemon-tcg-mega-evolution-pitch-black-expansion-arrives-july-17-2026)
- [Secondary] Prerelease events are reported from 24 October to 1 November, with TCG Live on 5 November (excerpt) — [Nerdsnack](https://nerdsnack.com/?p=6789)
- [Secondary] A retailer guide says official Delta Reign detail is thin: only the date and an October Build & Battle Box item are official, and other product dates are media reports (excerpt) — [Samurai Sword Tokyo](https://samuraiswordtokyo.com/es/blogs/news/delta-reign-pre-order-guide-us-retailers-vs-japan)
- [Secondary] Other 2026 dates are reported as Ascended Heroes 30 January, Perfect Order 27 March, Chaos Rising 22 May and 30th Celebration 16 September, with main sets roughly every eight weeks (excerpts) — [The Card Shop Finder](https://thecardshopfinder.com/guides/pokemon-tcg/pokemon-tcg-2026-release-calendar/); [Quazacollect](https://quazacollect.com/blogs/news/pokemon-tcg-release-dates-schedule)
- [Secondary] Dexerto's October 2026 list shows no 2027 sets and contradicts itself on whether 2026 releases are finished — [Dexerto](https://www.dexerto.com/pokemon/pokemon-tcg-release-2629243/)
- [Doc, dated] Pokémon Center's AU and NZ online store launch was announced in 2024 (excerpt). Current status was not checked — [Gamespress](https://gamespress.com/Pokemon-Center-Online-Store-Coming-Soon-to-Australia-and-New-Zealand)
- [Secondary] An earlier promo offer named EB Games as the AU and NZ retailer (excerpt). Check for currency — [Bulbagarden](https://bulbagarden.net/threads/archaludon-and-raging-bolt-promo-cards-available-with-purchase-of-pokemon-tcg-products-in-us-canada-australia-and-new-zealand-from-september-13th.303167/)
- [Vendor] DropZone reports daily member intel and adds sources on member request — [DropZone](https://dropzone.gg/)

### Inferences
- A practical calendar has three inputs: official set dates (high confidence), retailer pre-order or "coming soon" listings already public (medium), and community reports (low until corroborated).
- Delta Reign is the immediate test for a release-window polling mode.
- Early signals mainly tell the bot *when to poll harder*. They do not reveal exact store arrival, so they support preparation rather than alerts.
- Retailer catalogues and newsletters are likely useful for timing because they are published to customers, but this is unproven.

### Gaps
- No official or trade distributor for Pokémon TCG in NZ was confirmed. Searches for names such as Hobby Vault, Ashtabula and Monster Merchandise returned nothing usable.
- It is not established that NZ on-shelf dates match the worldwide date, or whether NZ chains break or delay street dates.
- No 2027 English set dates were found, and no sourced NZ retailer catalogue or newsletter practice. These would need a direct review of retailers' own material, which was out of scope here.

## What can commercial scraping services actually do, and what are the NZ legal and terms risks?

### Takeaway
I found no scraping service that legitimately offers unpublished retailer data. These services fetch what a site serves publicly, handling blocking and rendering, and may add speed or reach but not secret inventory. Going beyond public surfaces raises real risk under NZ computer-access law. A service cannot reveal stock a retailer has not exposed; only the retailer can grant that, for example through a data agreement. General information, not legal advice.

### Cited Findings
**What services say**
- [Vendor] Zyte treats login- or paywall-protected data as outside "publicly available", says its API automatically blocks login on many sites whose terms prohibit scraping, and advises reviewing terms or getting permission (excerpt) — [Zyte blog](https://zyte.com/blog/compliant-web-scraping-with-ai/)
- [Doc] Zyte's Acceptable Use Policy allows lawful use only. It bars retrieving data where the customer has explicitly agreed to terms prohibiting that manner of access, and bars breaching security or authentication measures — [Zyte AUP](https://www.zyte.com/terms-policies/acceptable-use-policy/)
- [Vendor] Scrapfly's account docs describe its use as data extraction and automation and refer to its terms; I found no explicit public-only clause (excerpt) — [Scrapfly](https://scrapfly.io/docs/account)
- [Secondary] Zyte's blog summarises a US Meta v. Bright Data ruling as treating logged-out data as public. It is second-hand and US-only, so it says nothing about NZ (excerpt) — [Zyte blog](https://dev.zyte.com/blog/california-court-meta-ruling/)

**NZ law**
- [Secondary] NZ has no single web-scraping statute; legality depends on several overlapping areas (excerpt and page) — [Sprintlaw NZ](https://sprintlaw.co.nz/articles/is-web-scraping-legal-in-new-zealand-essential-compliance-guide/)
- [Doc, via secondary copy] Crimes Act 1961 s 252: intentional access to a computer system, directly or indirectly, knowing it is unauthorised or reckless about that, with a maximum of two years' imprisonment. I saw this via search excerpts of NZLII and a mailing-list quote; official pages returned errors — [NZLII s 252](https://www.nzlii.org/nz/legis/consol_act/ca196182/s252.html); [NZNOG archive](https://lists.nznog.org/archives/list/nznog@lists.nznog.org/message/DGK43DAVMHSN25IKUW4S7EOMIEEVTFTX)
- [Doc, via excerpt] Section 249 covers access with additional dishonest-purpose elements, with up to seven years per a 2003 amendment extract. Section 248's "authorisation" definition was extended in 2011 — [Crimes Amendment Act 2011](https://legislation.govt.nz/act/public/2011/29/en/latest/); [Commentary](https://itbrief.co.nz/story/cybercrime-in-aotearoa-how-does-new-zealand-law-define-it)
- [Secondary] Sprintlaw says risk rises with bypassing technical barriers, using another person's credentials, or overloading a server. Its author is a legal consultancy, not a law firm, and the guide is general — [Sprintlaw NZ](https://sprintlaw.co.nz/articles/is-web-scraping-legal-in-new-zealand-essential-compliance-guide/)
- [Secondary] Fair Trading Act 1986 s 9 bars misleading or deceptive conduct in trade, including conduct only likely to mislead — [Commerce Commission](https://www.comcom.govt.nz/news-and-media/news-and-events/archive/trustpower-to-publish-corrective-advertising-and-write-to-consumers-commission-also-warns-wrightson/); [Community Law](https://communitylaw.org.nz/community-law-manual/chapter-24-consumer-protection/types-of-misleading-or-unfair-practices-that-are-prohibited/)
- [Secondary] The Act covers false, misleading or unproven statements, with ss 9 to 12 on misleading conduct and ss 13 to 16 on false or misleading representations (excerpt). No intent to mislead is required (excerpt) — [Community Law](https://communitylaw.org.nz/?p=44656); [Sprintlaw FTA guide](https://sprintlaw.co.nz/articles/fair-trading-act-1986-nz-misleading-and-deceptive-conduct-explained/)
- [Secondary] Sprintlaw notes liability for claims based on scraped data generally falls on the publisher, since such data can be stale or incomplete — [Sprintlaw NZ](https://sprintlaw.co.nz/articles/is-web-scraping-legal-in-new-zealand-essential-compliance-guide/)
- [Secondary] The Commerce Commission has sued two offshore sites over allegedly misleading rankings under the Act (excerpt) — [The Lawyer Mag](https://www.thelawyermag.com/nz/practice-areas/corporate-and-ma/commerce-commission-sues-websites-with-allegedly-misleading-rankings/592942)

**Terms of use**
- [Secondary] Terms are where scraping disputes usually start, and breach creates contractual exposure, especially where terms were accepted through an account or clearly prohibit scraping. "Publicly available" does not mean free to reuse under copyright — [Sprintlaw NZ](https://sprintlaw.co.nz/articles/is-web-scraping-legal-in-new-zealand-essential-compliance-guide/)
- [Doc, non-retail examples] NZ sites such as BRANZ and MetService prohibit scraping or automated gathering in their terms (excerpts) — [BRANZ](https://www.branz.co.nz/documents/5124/Terms_of_Use_and_Privacy_Policy_2025_May.pdf); [MetService](https://about.metservice.com/web-terms-of-use)

### Inferences
- **Answer to the owner's question:** treat "service finds stock loaded but not visible" as unproven. Nothing I found documents it. If a retailer publicly serves an item before search shows it, that is index lag on a public surface, which ordinary monitoring can catch.
- **Where the line appears to sit (not a legal conclusion):** reading what a site publicly serves is lower risk, though not risk-free given terms. Crossing authentication, using credentials not issued to you, or defeating a block is where s 252 risk grows, regardless of whether a paid service does the fetching. Using a vendor does not obviously transfer responsibility, and Zyte's AUP puts lawful use on the customer.
- **Fair Trading applies to the bot's own claims** if it is run in trade (paid tiers, sponsorship). Claims such as "instant", "real-time" or "first" should be something the owner can substantiate from logs. A published measured figure, with what it measures stated, is safer. False stock alerts could matter too, so "reported by member" labels help.
- **Practical cost-benefit:** scraping services may help reliability but add a network hop and cost, and do not remove retailer feed delay.

### Gaps
- Official text of ss 248 to 252 could not be read in this session (legislation.govt.nz and NZLII returned 403). A reader should check it directly. Sections 250 and 251 were not reviewed, and s 249's subsections and current penalties are unverified.
- No NZ court decision on web scraping under s 252 was found. Unread leads: [Otago analysis of the computer-crime provisions](https://www.otago.ac.nz/__data/assets/pdf_file/0024/332286/debugging-computer-crime-a-13-year-analysis-of-the-crimes-involving-computers-provisions-of-the-crimes-act-1961-638159.pdf) and [The Spinoff on the 2019 Treasury incident](https://www.thespinoff.co.nz/politics/12-06-2019/why-the-treasury-non-hack-may-still-have-been-illegal), whose title suggests relevance to accessing publicly reachable but unpublished material. The page could not be opened.
- NZ retailers' own terms were not read. By the brief's constraints I did not visit retailer sites, and search did not return them. Terms for Kmart, Farmers, The Warehouse and Whitcoulls need the owner's or a lawyer's direct review.
- Scrapfly's full terms and other providers' terms were not reviewed. No tailored view is possible on the project's approved third-party search keys; a lawyer could review this specific arrangement.

## How do comparable groups run member stock sightings and handle false reports?

### Takeaway
Member sightings are an accepted way to fill in-store gaps, as DropZone shows, but I found no documented reputation system. The only explicit verification features found are confirm/deny and photo proof in one app. Design guidance here is largely my inference.

### Cited Findings
- [Vendor] DropZone's in-store coverage comes from members posting live shelf sightings in state-based channels, with 7,800+ claimed active collectors — [DropZone](https://dropzone.gg/)
- [Vendor] The TCG Restock app lets users confirm or deny others' reports and attach proof-of-stock photos. Its listing describes no reputation score or retraction feature — [TCG Restock](https://apps.apple.com/us/app/-/id6754227978)
- [Vendor] Server listings such as Poke RestockR advertise online and in-store pings, and TCG Tracker advertises an in-store stock checker. Neither describes sighting verification (excerpts) — [Poke RestockR](https://discord.com/servers/pokemon-restocks-and-alerts-restockr-1348719595619614743); [TCG Tracker](https://discord.com/servers/tcg-tracker-802265651086491726)
- [Doc] Discord advises `allowed_mentions` for user-generated content, to prevent unexpected mentions — [Discord webhook resource](https://docs.discord.com/developers/resources/webhook)
- [Secondary] Published claims based on incomplete or stale data can carry Fair Trading risk for the publisher (general point, not about sightings specifically) — [Sprintlaw NZ](https://sprintlaw.co.nz/articles/is-web-scraping-legal-in-new-zealand-essential-compliance-guide/)

### Inferences
Suggested design, not sourced practice:
- **Keep sightings visibly separate** from automated alerts, labelled "member report, unverified", with store, time and an expiry (for example, fading after about 30 to 60 minutes).
- **Structured submission:** a slash command or form with store and product selected from lists, rather than free text, then bot-formatted posts with mentions locked down.
- **Lightweight verification:** optional photo, one-tap "still there / gone" responses, and escalating a ping only after a second confirmation or from a trusted member.
- **Graduated trust:** new members post to a quiet channel, consistent reporters earn direct-ping rights, and false reports get a warning and then loss of rights. Distinguish honest stale reports from deliberate misdirection.
- **Anti-abuse:** rate limits per person and per store, since a false report could send members away from a real location. A moderator review log helps. Guidance on photos: avoid staff, customers' faces or personal details, given Privacy Act 2020 concerns noted in [Sprintlaw NZ](https://sprintlaw.co.nz/articles/is-web-scraping-legal-in-new-zealand-essential-compliance-guide/).
- **Store-floor norms:** remind members not to pressure staff or disrupt stores, to protect relationships with retailers.

### Gaps
- I found no public rules from a restock Discord explaining how false sightings are penalised, and no measured false-report rates. Private servers' rules are not visible from search. Directly viewing rule channels would need joining servers, which was not done.
- One verification guide surfaced from a low-quality site and was excluded. Discord's false-report policy concerns reports to Discord staff, not community sightings, so it was not applied here.
