# Commercial web unblocker / scraping APIs for NZ retail stock checks (researched 2 Nov 2026)

Scope: Zyte API, ScrapFly, Bright Data Web Unlocker, Oxylabs Web Unblocker, Decodo Site Unblocker, ZenRows, Scrape.do, ScraperAPI, Nimble. Workload: about 35,000 requests a month (24,000 Kmart JSON POST at about 18 KB, 10,200 to 11,000 Farmers GET, size unknown).

Method notes: all pricing was read from vendor pages on 2026-11-02. Almost no vendor page prints a price date, so treat "2 Nov 2026" as the observation date. No requests were sent to any retailer. Page reads went through a summarising fetch tool, so exact wording should be rechecked before a purchase. "UNVERIFIED" means I could not confirm the point from a primary source.

## Overall comparison: which service fits this workload?

### Takeaway
On documented POST and headers plus price, the best fits to trial are Oxylabs (US$30 floor), Nimble (about US$35 pay as you go) and the current Zyte (about US$44). Nobody has published evidence that any of these clears an Akamai-protected JSON POST gateway, so a small paid or free-credit trial decides it, not the benchmarks.

### Cited Findings

Costs below are my arithmetic on the vendor prices cited in the next section. Lower figures assume no browser rendering.

| Service | Est. monthly cost at 35k | Depends on difficulty or browser? | NZ geo | POST JSON + headers, no browser | Sticky session | Pay only on success |
|---|---|---|---|---|---|---|
| Zyte API | $44.45 at Advanced HTTP; browser at Advanced would be $562.80 | Both (5 tiers) | Extended set, surcharge not published | Yes, documented | Yes (`session.id`) | Yes |
| ScrapFly | $100 (875k credits at the observed 25) | Yes, Unblocker can raise cost | Yes, `nz` listed | Yes, documented | Yes, lifetime not published | Partly, 30% block rule |
| Bright Data | $52.50, plus premium-domain rate if it applies (not published) | Premium domains | Country code format, `nz` UNVERIFIED | CONFLICTING, see below | Competitor says none | Not with custom headers |
| Oxylabs | $30 floor (about 0.63 GB + Farmers traffic) | No, single per-GB rate | NZ UNVERIFIED (195 countries claimed) | Yes, documented | Yes, 10 min | Yes |
| Decodo | About $10 to $45 per-GB; $33 to $56 per-request (third-party rates) | Not stated | NZ UNVERIFIED (195 claimed) | POST UNVERIFIED | Yes, 10 min | Yes |
| ZenRows | $99 (premium proxy, 10x); $199 (premium + JS, 25x) | Yes, by feature | No extra cost, `nz` UNVERIFIED (190+ claimed) | Yes, documented | Yes, 10 min, IP only | Yes |
| Scrape.do | $99 (10x or 25x both fit Pro) | Yes, plus per-domain list | NZ UNVERIFIED (160+ claimed) | POST only shown in a blog tutorial | Yes, duration not stated | Yes |
| ScraperAPI | $299 (NZ forces Business plan) | Yes, by feature and site | Yes, `nz` on Business and up | POST yes, ultra premium drops headers | Yes, 15 min after last use | Yes (200, 404), cancels billed |
| Nimble | About $35 pay as you go | Not published | `country` field, `nz` UNVERIFIED | Yes, documented | None documented | Not published |

### Inferences
- The observed Zyte figure of US$0.00127 per request is exactly Zyte's Advanced HTTP pay-as-you-go rate ($1.27 per 1,000), so the target is probably already on the top HTTP tier, and browser fallback would be far dearer.
- Per-GB billing (Oxylabs, Decodo) suits this workload unusually well because Kmart responses are only 18 KB. This advantage shrinks if Farmers returns full HTML pages.
- Elimination by constraint: ScraperAPI costs about three to ten times more because of the NZ plan gate, and its strongest mode drops custom headers. Bright Data has an unresolved POST question and bills failures once custom headers are on.
- Suggested trial order: Oxylabs ($5 credit), then Nimble (5,000 free a month). Keep Zyte as the baseline. ZenRows and Scrape.do are the fallback at about $99. Decodo moves up only if its support confirms POST.

### Gaps
- No source tests any of these against an Akamai-protected GraphQL or JSON POST endpoint, and none tests a NZ retailer.
- Whether any service clears the `cpr_chlge` response is unknown. Searches found no documentation or developer report mentioning that string, so what it means is also unconfirmed.

## Pricing, minimum commitment, and cost at about 35,000 requests a month

### Takeaway
Real monthly cost runs from about $30 to $299. Credit-plan services step up to a fixed plan price, while per-request and per-GB services track usage. Several prices can rise with site difficulty, and those rates are not public for these specific sites.

### Cited Findings
- **Zyte:** pay as you go HTTP $0.13 to $1.27 per 1,000 across five tiers (Advanced $1.27); browser $1.01 to $16.08. Commitments: $100 a month ($0.10 to $0.95 HTTP), $200, $500 ($0.06 to $0.61). $5 free credit, no subscription required — [Zyte pricing](https://www.zyte.com/pricing/)
- **Zyte:** extended-geolocation requests have different base costs plus network-based charges, and the figures are not on the docs page — [Zyte pricing docs](https://docs.zyte.com/zyte-api/pricing.html)
- **ScrapFly:** Free 1,000 credits; Discovery $30 / 200k (hard cap); Pro $100 / 1M, then $3.50 per 10k; Startup $250 / 2.5M; Enterprise $500 / 5.5M. Annual billing gives 2 months free — [ScrapFly pricing](https://scrapfly.io/pricing)
- **ScrapFly:** datacenter 1 credit, residential 25, browser +5. No fixed Unblocker price, as it can upgrade the proxy pool. Bodies over 100 KB and JSON responses over 1 MB incur bandwidth billing — [ScrapFly billing docs](https://scrapfly.io/docs/scrape-api/billing). `cost_budget` caps Unblocker spend, with examples of 25 and 55 — [ScrapFly docs](https://scrapfly.io/docs/scrape-api/getting-started)
- **Bright Data:** Free 5k requests a month; pay as you go $1.50 per 1,000; Scale $499 a month for 383k, then $1.30 — [Bright Data pricing](https://brightdata.com/pricing/web-unlocker). Listed premium domains cost more, with the price shown only in the zone's estimated cost panel and the list updated quarterly — [Bright Data features](https://docs.brightdata.com/products/web-unlocker/features)
- **Oxylabs:** billed per GB, upstream and downstream both counted: $7.2 per GB up to 4 GB, $6 up to 16 GB, $4.8 up to 104 GB. $5 credit — [Oxylabs product page](https://oxylabs.io/products/web-unblocker). Plans start at $30, then $100, $500, and self-service purchases are non-refundable — [Oxylabs pricing](https://oxylabs.io/pricing/web-unblocker). Features such as geo-targeting are stated to carry no extra fee — [Oxylabs help](https://developers.oxylabs.io/help-center/billing-and-payments/are-there-any-additional-fees-i-should-be-aware-of) (read via search summary)
- **Decodo:** per-GB plans of 1 GB $10, 5 GB $45, 10 GB $85 and so on, with a 14-day money-back option. The page's structured data separately lists a 2 GB plan at $28, which conflicts — [Decodo Site Unblocker](https://decodo.com/proxies/site-unblocker)
- **Decodo per-request:** the Pay/Req prices did not render on Decodo's page. Third-party figures conflict: from $0.95 per 1,000 — [Toolradar](https://toolradar.com/tools/decodo-formerly-smartproxy/pricing); $29 for about 23,000 requests, and $0.95 only at enterprise volume — [Proxidize](https://proxidize.com/blog/decodo-pricing/); $1.60 per 1,000 — [TechRadar](https://www.techradar.com/best/proxies)
- **ZenRows:** Build $19 / 45k, $29 / 80k, $39 / 120k; Launch $69 / 250k, $99 / 500k, $129 / 700k; Growth $199 / 1.2M. Multipliers: JS 5x, premium proxy 10x, both 25x. Free 5,000 credits a month — [ZenRows pricing](https://www.zenrows.com/pricing)
- **Scrape.do:** Hobby $29 / 250k; Pro $99 / 1.25M; Business $249 / 3.5M — [Scrape.do pricing](https://scrape.do/pricing/). Credits: datacenter 1, datacenter + browser 5, residential 10, residential + browser 25. A per-domain list overrides these (lowes.com 10, sainsburys.co.uk 200) and the charge is returned in a response header — [Scrape.do request costs](https://scrape.do/documentation/request-costs/)
- **ScraperAPI:** Hobby $49 / 100k; Startup $149 / 1M; Business $299 / 3M — [ScraperAPI pricing](https://www.scraperapi.com/pricing/). Premium 10 credits, render 10, premium + render 25, ultra premium 30, ultra + render 75 — [ScraperAPI credits](https://docs.scraperapi.com/credits-and-requests)
- **Nimble:** free 5,000 requests a month; Extract $1 per 1,000; plans from $2,500 a month billed annually — [Nimble pricing](https://www.nimbleway.com/pricing)

### Inferences
- Zyte: 35,000 x $1.27 / 1,000 = $44.45. A $100 commitment would price usage at $33.25 but still cost $100, so pay as you go is cheaper here. Any Farmers traffic on a lower tier reduces the total.
- ScrapFly: 35,000 x 25 = 875,000 credits, which fits Pro at $100 (about $83 a month if annual). At 55 credits per call it would be 1.925M, so Startup at $250.
- Bright Data: 35,000 x $1.50 / 1,000 = $52.50 before any premium rate.
- Oxylabs: 35,000 x 18 KB = 0.63 GB, or about $4.54 at $7.20, so the $30 plan floor sets the cost. $30 buys about 4.17 GB. With 0.43 GB of Kmart traffic, Farmers fits if it averages under about 365 KB per response, before overhead and upstream traffic. How plan fees map to GB is not explained on the page.
- Decodo: the 1 GB plan fits only if Farmers averages under about 55 KB per response, otherwise it is the 5 GB plan at $45. Per-request at $0.95 to $1.60 gives $33.25 to $56.
- ZenRows: 350,000 credits at 10x needs the $99 rung, and 875,000 credits at 25x needs the $199 rung.
- Scrape.do: 350,000 or 875,000 credits both fit Pro at $99, assuming Kmart and Farmers are not on the per-domain list or added to it.
- ScraperAPI: NZ needs Business at $299, even though 350,000 credits would otherwise fit Startup.
- Nimble: 35,000 x $1 / 1,000 = $35. Whether the free 5,000 nets off paid use is not published.

### Gaps
- Tier that Zyte assigns to Kmart and Farmers (the vendor's site lookup requires a URL entry, which I did not use).
- NZ extended-geolocation surcharge on Zyte, Bright Data's premium rate and whether these domains are on its list, and Decodo's actual Pay/Req tiers.
- Farmers response size, which drives the per-GB results.

## New Zealand geotargeting and any extra cost

### Takeaway
Only ScrapFly and ScraperAPI have NZ explicitly confirmed in docs that I could read. ScraperAPI gates it behind a $299 plan, and Zyte treats non-standard countries as a separately priced set.

### Cited Findings
- ScrapFly lists `nz` for its datacenter and residential pools, with no separate country charge shown — [ScrapFly proxy docs](https://scrapfly.io/docs/scrape-api/proxy)
- ScraperAPI lists `nz` as Business Plan and higher; Hobby and Startup get only US and EU — [ScraperAPI standard geo](https://docs.scraperapi.com/control-and-optimization/geotargeting/standard-geo). `country_code` adds no cost but cannot be combined with ultra premium — [ScraperAPI docs](https://docs.scraperapi.com/control-and-optimization/supported-parameters) (read via search summary)
- Zyte's standard set is AU, BE, BR, CA, CN, DE, ES, FR, GB, IN, IT, JP, KR, MX, NL, PL, RU, TR, US and ZA; everything else is extended, and setting it explicitly affects cost — [Zyte reference](https://docs.zyte.com/zyte-api/usage/reference.html); [Zyte features](https://docs.zyte.com/zyte-api/usage/features.html)
- ZenRows: `proxy_country` requires Premium Proxy, adds no extra cost, 190+ countries — [ZenRows docs](https://docs.zenrows.com/universal-scraper-api/features/proxy-country)
- Bright Data takes a two-letter ISO code; examples include `au`, not `nz` — [Bright Data API](https://docs.brightdata.com/api-reference/rest-api/unlocker/unlock-website)
- Oxylabs accepts country names and 2-letter codes, and the full list is in a JSON file I could not open — [Oxylabs geo-location](https://developers.oxylabs.io/products/web-unblocker/making-requests/geo-location). It claims 195 countries — [Oxylabs](https://oxylabs.io/products/web-unblocker)
- Decodo uses the `X-SU-Geo` header with a city, state or country — [Decodo geo docs](https://help.decodo.com/docs/site-unblocker-geo-location). Scrape.do: geo on every plan, 160+ countries — [Scrape.do pricing](https://scrape.do/pricing/). Nimble's older Web API has an ISO `country` field — [Nimble real-time docs](https://docs.nimbleway.com/data-platform/web-api/real-time-url-request); its newer Extract headers page documents no country parameter — [Nimble Extract](https://docs.nimbleway.com/nimble-sdk/web-tools/extract/features/headers-and-cookies)

### Inferences
- If Kmart NZ and Farmers do not require a NZ exit IP, Zyte's surcharge and ScraperAPI's plan gate may not apply. An AU exit may be enough, but that is untested and Akamai could score it differently.

### Gaps
- `nz` not confirmed by name for Zyte, Bright Data, Oxylabs, Decodo, ZenRows, Scrape.do or Nimble. The size and quality of any NZ residential pool is not published by any vendor.

## POST with JSON body and custom headers, without a browser (essential)

### Takeaway
Clearly documented: Zyte, ScrapFly, Oxylabs, ZenRows, Nimble. Weaker: ScraperAPI (ultra premium removes headers), Scrape.do (tutorial evidence). Unconfirmed: Decodo. Contradictory: Bright Data.

### Cited Findings
- **Zyte:** `httpRequestMethod`, `httpRequestText` or `httpRequestBody`, and `customHttpRequestHeaders` on HTTP requests. Only `Cookie` is excluded — [Zyte HTTP docs](https://docs.zyte.com/zyte-api/usage/http.html)
- **ScrapFly:** the verb and raw body of the API call carry through to the target, and headers are passed as `headers[name]=value` — [ScrapFly docs](https://scrapfly.io/docs/scrape-api/getting-started). Whether the Unblocker works without `render_js` is not stated on that page
- **Oxylabs:** POST with JSON payload examples exist — [Oxylabs POST docs (Spanish edition)](https://developers.oxylabs.io/products/es/web-unblocker/making-requests/post-requests); [Oxylabs migration guide](https://developers.oxylabs.io/products/web-unblocker/migration-guides/from-bright-data-web-unlocker). Custom headers need `x-oxylabs-force-headers: 1` — [Oxylabs quick start](https://developers.oxylabs.io/get-started/quick-start-web-unblocker)
- **ZenRows:** POST and PUT are forwarded — [ZenRows docs](https://docs.zenrows.com/universal-scraper-api/features/other). `custom_headers=true` is required, works without `js_render`, and managed headers such as User-Agent and Sec-Fetch cannot be overridden. `Referer` is allowed; `Origin` is not named either way — [ZenRows headers](https://docs.zenrows.com/universal-scraper-api/features/headers)
- **Nimble:** `method: POST`, `body` as object or string, custom headers without a render option shown — [Nimble Extract](https://docs.nimbleway.com/nimble-sdk/web-tools/extract/features/headers-and-cookies)
- **ScraperAPI:** POST and PUT supported — [ScraperAPI POST docs](https://docs.scraperapi.com/synchronous-apis/making-post-put-requests); `keep_headers` forwards headers, but ultra premium discards all custom headers — [ScraperAPI headers](https://docs.scraperapi.com/control-and-optimization/sending-custom-headers)
- **Scrape.do:** `customHeaders` and `extraHeaders` exist, but POST is not covered on the docs landing page — [Scrape.do docs](https://scrape.do/documentation/). A tutorial shows POST with a JSON body — [Scrape.do blog](https://scrape.do/blog/trip-com-scraping/)
- **Decodo:** headers pass through to the target apart from `host`, `accept`, `connection` and `cache-control`, and all examples are GET — [Decodo headers](https://help.decodo.com/docs/site-unblocker-headers). No Site Unblocker POST documentation found
- **Bright Data:** the Oxylabs guide says POST and sessions are not supported, but this is a competitor's claim — [Oxylabs migration guide](https://developers.oxylabs.io/products/web-unblocker/migration-guides/from-bright-data-web-unlocker). The synchronous API describes `method` as GET — [Bright Data API](https://docs.brightdata.com/api-reference/rest-api/unlocker/unlock-website). The async API lists `method`, `body` and `headers` without saying POST to the target works — [Bright Data async](https://docs.brightdata.com/api-reference/rest-api/unlocker/request). Custom headers must be enabled, come from a pre-approved list or pass a compliance form, and switch billing to all requests — [Bright Data features](https://docs.brightdata.com/products/web-unlocker/features)

### Inferences
- ScraperAPI's strongest mode loses `Origin` and `Referer` and also the NZ country code, which likely rules it out for the Kmart gateway if ultra premium turns out to be needed.
- Bright Data's header approval step is a real risk, since `Origin` and `Referer` for Kmart would have to be on, or be added to, the approved list.

### Gaps
- Decodo and Bright Data POST need a written answer from their support. Akamai sensor or cookie handling for a bare API POST, with no page load in the session, is not documented by any vendor.

## Latency: independent figures versus vendor claims

### Takeaway
Neutral average figures sit around 11 to 19 seconds, with Akamai targets up to about 29 seconds in 2024. The user's observed 30 to 83 seconds on Zyte is well above Zyte's benchmark averages. All tests are for HTML pages from non-NZ origins.

### Cited Findings
- **Most independent, Proxyway, 15 sites, 2 req/s, tests mostly October 2025:** Zyte 11.15 s, ScraperAPI 13.92 s, Decodo 15.22 s, Oxylabs 16.76 s, ZenRows 19.10 s — [Proxyway best APIs](https://proxyway.com/best/best-web-scraping-apis). Run from a US server with a 600 s timeout; Bright Data, ScrapFly and Scrape.do were not tested — [Proxyway report](https://proxyway.com/research/web-scraping-api-report)
- **Proxyway, September 2024, 10 req/s, overall:** Zyte 6.61 s, Smartproxy (now Decodo) 10.91 s, Nimble 13.01 s, Oxylabs 13.45 s, ScraperAPI 15.39 s, Bright Data 22.08 s. The tool flagged that these were paired to providers by chart order, so check them on the page — [Proxyway 2024](https://proxyway.com/research/comparing-popular-web-scraping-proxy-apis)
- **Vendor-run:**
  - String, 15 July 2026, failure-aware latency: ScraperAPI 13.31 s, ScrapFly 14.28 s, Zyte 17.50 s, Oxylabs 20.85 s, ZenRows 21.35 s, Nimble 21.43 s, Bright Data 24.33 s, Decodo 29.74 s — [String](https://usestring.ai/blog/web-scraping-benchmark-problem)
  - ZenRows, 19 June 2026: ZenRows 9.1 s, ScrapFly 10.9 s, Zyte 14.3 s, ScraperAPI 36.0 s — [ZenRows](https://www.zenrows.com/blog/best-web-scraping-apis-benchmarked)
  - Scrape.do, undated, page updated September 2026: Scrape.do 5.5 s, ScrapFly 5.6 s, ScraperAPI 5.6 s, ZenRows 6.7 s, Decodo 10.7 s, Oxylabs 11.3 s, Bright Data 12.7 s, Zyte 15.8 s — [Scrape.do](https://scrape.do/blog/best-web-scraping-api/)
  - Sponsored, likely Bright Data (my inference from its links), published May 2026: Bright Data 10.6 s, Nimble 11.3 s, Zyte 12.2 s, Decodo 15.2 s, ScraperAPI 15.7 s, Oxylabs 16.7 s — [HackerNoon](https://hackernoon.com/web-scraping-api-success-rates-we-tested-12-tools-so-you-dont-have-to)
- **Vendor claim:** Decodo says "#1" for response time with no measured figure — [Decodo](https://decodo.com/proxies/site-unblocker)
- **Timeouts:** ScrapFly's API read timeout defaults to 155 s — [ScrapFly docs](https://scrapfly.io/docs/scrape-api/getting-started). ScraperAPI's retry window is 70 s — [ScraperAPI credits](https://docs.scraperapi.com/credits-and-requests)

### Inferences
- At 83 s per call, 1,150 calls a day is about 26.5 hours of serial time, so concurrency of at least 2 is needed, and alert freshness suffers regardless of the vendor.
- Latency this far above benchmarks suggests repeated ban retries inside Zyte, but I could not confirm that. It could also come from NZ routing. Latency on a hard target says more than the vendor averages do.

### Gaps
- No benchmark measures a NZ exit, a JSON POST or an 18 KB API response. Nimble's latest Proxyway number was not in what I could read.

## Success rates against Akamai-protected sites

### Takeaway
Per-provider Akamai data exists only in Proxyway's 2024 Lowe's test, which is two years old, a single site and a GET page. On it, Zyte, Decodo and Oxylabs were all above 99%, but Zyte was far faster.

### Cited Findings
- **Lowe's (Akamai), Proxyway, September 2024, 10 req/s:** Zyte 100% / 1.65 s; Smartproxy 99.81% / 28.36 s; Oxylabs 99.69% / 27.57 s; Nimble 95.95% / 9.82 s; Bright Data 92.33% / 29.33 s; ScraperAPI 75.84% / 25.32 s. Average across providers 67.17% — [Proxyway 2024](https://proxyway.com/research/comparing-popular-web-scraping-proxy-apis)
- Proxyway 2023, seven sites including Akamai, reported through Zyte's own blog: Zyte averaged 97.82% / 11.70 s — [Zyte blog](https://zyte.com/blog/proxyway-research-zyte-proxy-api/)
- **Proxyway, tests mostly October 2025:** Lowe's averaged only 52.57% at 2 req/s across APIs, and the per-provider figures were not in what I could read — [Proxyway report](https://proxyway.com/research/web-scraping-api-report)
- **Proxyway overall, all anti-bot types, 2 req/s:** Zyte 93.14%, Decodo 85.88%, Oxylabs 85.82%, ZenRows 70.39%, ScraperAPI 68.95% — [Proxyway best APIs](https://proxyway.com/best/best-web-scraping-apis). Search summaries give a 10 req/s drop for ZenRows to 31.76%, and Proxyway says concurrency caps on its plan limited ZenRows — [Proxyway report](https://proxyway.com/research/web-scraping-api-report)
- **Vendor-run overall, not Akamai-specific, and they disagree:**
  - String: ScrapFly 83.6%, Bright Data 80.9%, ScraperAPI 69.3%, Oxylabs 68.9%, Zyte 68.2%, Decodo 67.8%, Nimble 59.3%, ZenRows 44.2%. String ranks itself first and publishes its harness. It has Akamai results in a heatmap I could not access — [String](https://usestring.ai/blog/web-scraping-benchmark-problem)
  - ZenRows: ZenRows 99%, ScrapFly 98.5%, Zyte 74.75%, ScraperAPI 49% on four sites — [ZenRows](https://www.zenrows.com/blog/best-web-scraping-apis-benchmarked)
  - Scrape.do: Bright Data 98.87%, Scrape.do 98.61%, ZenRows 96.29%, Oxylabs 95.4%, Decodo 94.2%, ScrapFly 93.86%, Zyte 91.43%, ScraperAPI 72.57% on seven sites — [Scrape.do](https://scrape.do/blog/best-web-scraping-api/)
- **Vendor claims:** Decodo claims both "100%" and "99.99%" on the same page — [Decodo](https://decodo.com/proxies/site-unblocker). An Oxylabs customer testimonial reports above 98% — [Oxylabs](https://oxylabs.io/products/web-unblocker)

### Inferences
- The fall in the Lowe's average from 67% in 2024 to 53% in 2025 suggests that Akamai results degrade over time, so old figures should not be relied on. The two tests used different request rates and provider sets.
- Each vendor's own test tends to favour it or its allies, while Proxyway consistently puts Zyte at or near the top. The user's current Zyte block on the Kmart gateway shows that a good benchmark does not transfer automatically to an API endpoint.

### Gaps
- No Akamai data at all for ScrapFly, ZenRows or Scrape.do from an independent source. No vendor publishes an Akamai-specific success rate that I could find.

## Sticky sessions, free trials, and paying only for success

### Takeaway
Most vendors offer sessions and success-only billing, and the main traps are ScrapFly's 30% rule and Bright Data's custom-header billing. Free allowances vary from about 40 to 5,000 test calls at real settings.

### Cited Findings
- **Zyte:** `session.id` reuses the IP, stack and cookies; server-managed sessions are also available, and starting one with actions is billed as a browser request — [Zyte features](https://docs.zyte.com/zyte-api/usage/features.html). Only successful responses are charged — [Zyte pricing docs](https://docs.zyte.com/zyte-api/pricing.html). A 520 ban response is not charged — [Zyte errors](https://docs.zyte.com/zyte-api/usage/errors.html). $5 credit, 30 days — [Zyte pricing](https://www.zyte.com/pricing/)
- **ScrapFly:** `session` holds cookies, fingerprint and IP (best effort), lifetime not stated — [ScrapFly docs](https://scrapfly.io/docs/scrape-api/getting-started). Failed scrapes are free, except that if 30% or more of at least 1,000 scrapes in 24 hours are blocked without the Unblocker, failed scrapes become billable, with a 30-day recheck — [ScrapFly billing](https://scrapfly.io/docs/scrape-api/billing). 1,000 free credits — [ScrapFly pricing](https://scrapfly.io/pricing)
- **Bright Data:** pay for success on pay as you go, but custom features mean billing for 100% of requests — [Bright Data features](https://docs.brightdata.com/products/web-unlocker/features). 5k free a month and a first-deposit match — [Bright Data pricing](https://brightdata.com/pricing/web-unlocker). Sessions marked unsupported by a competitor — [Oxylabs guide](https://developers.oxylabs.io/products/web-unblocker/migration-guides/from-bright-data-web-unlocker)
- **Oxylabs:** `x-oxylabs-session-id`, up to 10 minutes — [Oxylabs guide](https://developers.oxylabs.io/products/web-unblocker/migration-guides/from-bright-data-web-unlocker). Failed attempts are not counted — [Oxylabs](https://oxylabs.io/products/web-unblocker)
- **Decodo:** `X-SU-Session-Id`, 10-minute window — [Decodo session](https://help.decodo.com/docs/site-unblocker-session). Charged only for success; trial size not stated — [Decodo](https://decodo.com/proxies/site-unblocker)
- **ZenRows:** `session_id` keeps the IP for 10 minutes, not cookies — [ZenRows docs](https://docs.zenrows.com/universal-scraper-api/features/other). Failed requests never charged; 404 and 410 count as success — [ZenRows pricing](https://www.zenrows.com/pricing)
- **Scrape.do:** `sessionId`, duration not stated — [Scrape.do docs](https://scrape.do/documentation/). Charged for 2xx, 400, 404 and 410 only — [Scrape.do costs](https://scrape.do/documentation/request-costs/). 1,000 free credits — [Scrape.do pricing](https://scrape.do/pricing/)
- **ScraperAPI:** sessions expire 15 minutes after last use — [ScraperAPI sessions](https://docs.scraperapi.com/making-requests/customizing-requests/sessions). Charged for 200 and 404, and for requests you cancel before 70 s — [ScraperAPI credits](https://docs.scraperapi.com/credits-and-requests). 7-day trial with 5,000 credits; the FAQ describes a 1,000-credit free plan instead — [ScraperAPI pricing](https://www.scraperapi.com/pricing/)
- **Nimble:** no sticky parameter documented, only cookie reuse — [Nimble Extract](https://docs.nimbleway.com/nimble-sdk/web-tools/extract/features/headers-and-cookies). Failed-request billing not stated — [Nimble pricing](https://www.nimbleway.com/pricing)

### Inferences
- **The ScrapFly rule matters here:** 1,150 calls a day crosses the 1,000-scrape threshold, so a run without Unblocker on a blocking target could lose failure protection for 30 days.
- A 429 or challenge passed back as a target response might count as success on some services. For example, Scrape.do and ZenRows list which statuses are billable, and a 429 is not among them, but a 200 carrying `cpr_chlge` might be billed. Validate the body in the bot and check the cost headers.
- Trial size at real settings (my arithmetic): ScrapFly 40 calls at 25 credits; Scrape.do 100; ZenRows 500; ScraperAPI 500; Zyte about 3,900 at Advanced; Bright Data and Nimble 5,000 a month. Oxylabs $5 is about 0.69 GB, about 38,000 Kmart-sized responses.

### Gaps
- Actual session lifetime for Zyte and ScrapFly. Whether a session opened by a page GET can carry Akamai cookies into a later POST on any service.

## Terms of use limits relevant to retail sites

### Takeaway
I found no retail-specific ban in the two policies I read, but Zyte's terms on third-party use and on prohibited-access sites are relevant to a public alert bot. Retailers' own terms remain a separate risk that I did not review.

### Cited Findings
- **Zyte:** no retail-specific rule. Bars accessing sites where you have explicitly agreed to terms prohibiting that access, breaching a site's security or authentication measures, interfering with its operations, and commercially exploiting Service Data for third parties — [Zyte AUP](https://www.zyte.com/terms-policies/acceptable-use-policy/)
- **Bright Data:** no general retail ban. Bars non-public data such as data behind a login, ticket-bots and reselling proxies without approval, and can add site blocks at its discretion — [Bright Data AUP](https://brightdata.com/acceptable-use-policy). Cookies may not be used for login, and custom headers may need compliance approval — [Bright Data features](https://docs.brightdata.com/products/web-unlocker/features)

### Inferences
- A paid or public Discord alert service could arguably count as commercial use of Zyte data for third parties. It is worth reading the terms or asking Zyte, as this is my reading rather than legal advice.
- Automating purchases on top of this data would get closer to the Bright Data ticket-bot style restriction. Stock alerts alone appear further away, but this is also my reading.

### Gaps
- Acceptable-use terms for ScrapFly, Oxylabs, Decodo, ZenRows, Scrape.do, ScraperAPI and Nimble were not reviewed.
- Kmart NZ and Farmers website terms were not checked, as this research avoided retailer sites.
- Any KYC requirement for small accounts was not found for any vendor.
