# Residential and mobile proxies with New Zealand coverage (late 2026)

All prices and pages were retrieved on 2026-11-02 and are in USD, unless a line says otherwise. Tags: **[page]** means I fetched the provider's or publisher's page, through a summarising fetch tool, so re-check exact figures before buying. **[snippet]** means the figure comes from a search summary only and the page was not opened, so treat it as unverified. "Not published" means the page I retrieved did not state it, not that it does not exist. No requests were sent to any retailer.

## Which providers offer NZ residential or mobile IPs, and what NZ pool size do they state?

### Takeaway
NZ exits are widely sold, but pool figures are vendor claims that differ about 70-fold (7,415 to 524,220) and are not comparable. NetNut should be excluded: the FBI seized its domains in July 2026.

### Cited Findings

| Provider | NZ residential | NZ mobile | Stated NZ pool | Source |
|---|---|---|---|---|
| ProxyEmpire | Yes; 14 of 16 regions, no Tasman or West Coast | Yes; One NZ, Spark, 2degrees | Not published (global 30M+ residential, 4M+ mobile) | [page](https://proxyempire.io/new-zealand-residential-proxy/) |
| SOAX | Yes | Carrier list includes 2degrees Mobile, Vodafone NZ, Spark, Ultimate Mobile; no explicit NZ mobile statement | 144,960, not split by type | [page](https://soax.com/proxies/locations/new-zealand) |
| Oxylabs | Yes | The location page offers datacenter and residential only | 54,794, not split by type | [page](https://oxylabs.io/location-proxy/new-zealand) |
| Bright Data | Yes | Not shown on the NZ page | Conflicting: headline 19,731 NZ IPs; counter 78,925 (residential 74,061, datacenter 4,096, static residential 768), which may not be NZ-only | [page](https://brightdata.com/locations/nz) |
| Webshare | Yes, rotating residential | Not stated | 18,786 across all types | [page](https://www.webshare.io/proxy-locations/nz) |
| Decodo | Yes, "real households" | A heading mentions NZ mobile, but the body describes only residential, so unconfirmed | Not published (global 125M+) | [page](https://decodo.com/proxies/list/new-zealand) |
| IPRoyal | A roundup calls it a budget choice for NZ residential; my fetch of a guessed NZ URL returned 404 | Not verified | Not published | [snippet](https://thunderbit.com/blog/top-new-zealand-proxies) |
| DataImpulse | **NZ unverified**: the page says only 195 countries and does not mention NZ | Not verified | Not published | [page](https://dataimpulse.com/residential-proxies/) |
| NetNut | **Do not use**: seized | n/a | n/a | [Krebs](https://krebsonsecurity.com/2026/07/fbi-seizes-netnut-proxy-platform-popa-botnet/) |

Others with NZ pages, none of them opened:
- Geonode: 84,210 IPs across 12 cities — [snippet](https://geonode.com/proxies-by-location/new-zealand-proxy)
- Litport: 286,410 residential IPs — [snippet](https://litport.net/locations/oceania/new-zealand)
- NSTProxy: 524,220 — [snippet](https://www.nstproxy.com/proxy/New%20Zealand)
- SimplyNode: 62,385 — [snippet](https://www.simplynode.io/locations/new-zealand-proxies)
- Byteful: 7,415 monthly active IPs — [snippet](https://byteful.com/proxies-by-location/new-zealand-proxy)
- Novada: $3.6/GB for NZ — [snippet](https://www.novada.com/locations/nz/)

NetNut detail:
- The FBI and IRS-CI seized hundreds of domains on 2 July 2026, tied to the Popa botnet of at least 2 million compromised devices. Alarum's site also showed a seizure notice by 8 July — [Krebs](https://krebsonsecurity.com/2026/07/fbi-seizes-netnut-proxy-platform-popa-botnet/)
- netnut.io/rotating-residential-proxies/ also showed the seizure banner when fetched on 2026-11-02 — [page](https://netnut.io/rotating-residential-proxies/)

### Inferences
- The counts probably use different definitions (active, monthly or cumulative, and sometimes all proxy types). Byteful labels its figure "monthly active", which may be the most honest, and it is much the smallest. I would not choose a provider on NZ pool size.
- A small real pool matters here: at 800 requests a day, per-request rotation could cycle through a few thousand IPs quickly. Only a test can show how many unique NZ IPs a provider really returns.

### Gaps
- No independent measurement of any provider's NZ pool. Proxyway's 2026 research does not mention NZ (it tests Australia).
- IPRoyal's and DataImpulse's NZ availability should be confirmed in their dashboards or with support.

## What do they cost per GB, with what minimums and expiry, and is NZ city targeting available?

### Takeaway
At this volume the bill is about $0.50 to $7 at 0.5 GB and $2 to $16 at 2 GB, so price barely separates the options. Minimum top-ups, expiry and coupon dependence matter more than the headline rate.

### Cited Findings
The monthly columns are simple rate × GB. Because several providers sell whole GBs, the actual outlay at 0.5 GB can be higher; those cases are noted.

| Provider | Small-volume price | Minimum | Traffic expiry | 0.5 GB/mo | 2 GB/mo | NZ city targeting | Source |
|---|---|---|---|---|---|---|---|
| DataImpulse | $1/GB | $5 one-time for new customers; no monthly minimum | "Never expire" | $0.50 | $2 | General, marked as extra cost (amount not retrieved); no NZ cities named | [page](https://dataimpulse.com/residential-proxies/) |
| ProxyEmpire | $3.50/GB PAYG with limited-time code EMPIRE50; $7 without | 1 GB PAYG; $1.97 trial | Rolls over on "eligible plans", duration not published | $1.75 ($3.50 without code); 1 GB outlay $3.50 | $7 ($14 without code) | **Yes, 26 named NZ cities**, no NZ surcharge | [plans](https://proxyempire.io/rotating-residential-proxies/), [NZ](https://proxyempire.io/new-zealand-residential-proxy/) |
| Decodo | $4/GB PAYG + VAT; 3 GB plan $3.75/GB | 1 GB at a time; 100 MB 3-day trial | Not published | $2; 1 GB outlay $4 | $8 | Not published for NZ; no cities named | [pricing](https://decodo.com/proxies/residential-proxies/pricing), [NZ](https://decodo.com/proxies/list/new-zealand) |
| Bright Data | $4/GB with code RESIGB50; $8 list | PAYG minimum not published | Not published | $2 ($4 list) | $8 ($16 list) | City, state and zip free in general; no NZ cities named | [pricing](https://brightdata.com/pricing/proxy-network/residential-proxies), [NZ](https://brightdata.com/locations/nz) |
| SOAX | Sandbox top-up $5, $4 or $2/GB by geo tier; **NZ's tier not published** | Sandbox free with no credits; top-up minimum not published; Builder $200/mo | Credits expire after **60 days** | $1 to $2.50 | $4 to $10 | **50 place names listed**, a few of them regions | [pricing](https://soax.com/pricing), [NZ](https://soax.com/proxies/locations/new-zealand) |
| Webshare | **Conflict**: $3.50 for a 1 GB monthly plan vs $7/mo for 1 GB | 1 GB monthly plan | Not published | $3.50 to $7 (whole plan) | Rate not retrieved | City targeting said to exist; no NZ cities named | [pricing](https://www.webshare.io/pricing), [NZ](https://www.webshare.io/proxy-locations/nz) |
| Oxylabs | $6/GB up to 5 GB (not labelled PAYG); $30/mo Starter; $5 welcome credit | Not published | Not published | $3 | $12 | Not published on the NZ page | [pricing](https://oxylabs.io/pricing/residential-proxy-pool), [NZ](https://oxylabs.io/location-proxy/new-zealand) |
| IPRoyal | 1 GB $7.35 PAYG; 2 GB tier $6.25/GB | 1 GB tier | **"Never expires"** | $3.68; 1 GB outlay $7.35 | $12.50 | City targeting in general; NZ not confirmed | [page](https://iproyal.com/residential-proxies/) |

- Market context: Proxyway's median residential price is $3.75/GB at 5 GB. Rates stabilised in early 2026 and some rose; long-running coupons were removed at Oxylabs and IPRoyal, among others, and PAYG entry points rose — [Proxyway 2026](https://proxyway.com/research/proxy-market-research-2026)
- Proxyway describes ProxyEmpire and Webshare as resellers that halved their rates year over year — [Proxyway 2026](https://proxyway.com/research/proxy-market-research-2026)
- Volume check: 800 requests × 18 KB is 14.4 MB a day, or about 0.43 GB per 30 days. This is the arithmetic from your figures, for responses only.

### Inferences
- Budget for more than 0.5 GB. Billing likely also counts request bodies, headers and any repeated TLS handshakes, especially with per-request rotation. I found no provider stating how this is counted, so measure it on a trial.
- Non-expiring traffic (IPRoyal, DataImpulse) suits a sub-1 GB workload best. SOAX's 60-day expiry is workable only if small top-ups are allowed.
- Webshare's $7 FAQ figure may be stale given the reported price cuts, but that is unconfirmed.
- City targeting probably does not matter for this use. Country-level NZ should be enough unless the gateway's responses vary by city, and narrowing to a city shrinks the pool.
- Add GST and exchange-rate effects; I did not research how each provider applies them.

### Gaps
- Bright Data's PAYG minimum, and whether its and ProxyEmpire's coupons keep applying on later top-ups.
- Decodo's PAYG expiry: its legal page URL returned 404.
- SOAX's geo tier for NZ.
- DataImpulse's city-targeting surcharge.

## What sticky session lengths, rotation options and authentication methods are offered?

### Takeaway
All the shortlisted providers rotate and offer sticky sessions, and username/password is confirmed for Decodo, DataImpulse and Webshare. Long sessions on residential IPs are limited by the home device staying online, whatever the stated cap.

### Cited Findings

| Provider | Sticky length | Rotation | Authentication | Source |
|---|---|---|---|---|
| IPRoyal | Up to 7 days | Per request, manual via dashboard or API | IP whitelisting and sub-users listed; user/password not stated on this page | [page](https://iproyal.com/residential-proxies/) |
| ProxyEmpire | No fixed limit; holds until rotated or the device goes offline | Per request; timer up to 2 hours | Not described on the page | [page](https://proxyempire.io/rotating-residential-proxies/) |
| SOAX | 10 to 3,600 seconds; default 360 | Sticky or rotating | Not retrieved | [help](https://helpcenter.soax.com/en/articles/6723733-sticky-sessions) [snippet] |
| Decodo | Up to 30 minutes on pricing; a general FAQ says about 1 to 60 minutes | Rotating or sticky | User/password or whitelisted IP | [pricing](https://decodo.com/proxies/residential-proxies/pricing), [NZ](https://decodo.com/proxies/list/new-zealand) |
| DataImpulse | `sessttl` in minutes, doc example 60; a third-party table says 30 default, 120 max | Sticky or rotating | Login/password through a gateway, or by IP | [docs](https://docs.dataimpulse.com/dataimpulse-documentation-es/proxies/parametros/intervalo-de-sesion) [snippet], [table](https://trustmyip.com/blog/best-rotating-proxies) [snippet], [page](https://dataimpulse.com/residential-proxies/) |
| Oxylabs | Residential not verified; mobile docs say 10 minutes or 60 s of inactivity; a third-party table says 10 min / 24 h | Sticky listed | Not retrieved | [docs](https://developers.oxylabs.io/products/proxies/mobile-proxies/session-control) [snippet], [table](https://trustmyip.com/blog/best-rotating-proxies) [snippet] |
| Bright Data | "Extended Session Control", duration not published | Constant rotation, controllable in Proxy Manager | Gateway with country flags in the username | [pricing](https://brightdata.com/pricing/proxy-network/residential-proxies), [snippet](https://docs.brightdata.com/api-reference/proxy/latitude_longitude_targeting_residential_only.md) |
| Webshare | Not stated | Rotating plans; static plans suggested for long sessions | User/password; IP authorization under fair use | [pricing](https://www.webshare.io/pricing), [NZ](https://www.webshare.io/proxy-locations/nz) |

- ProxyEmpire supports HTTP, HTTPS, HTTP/2 and SOCKS5, with ports 80 and 443 open by default — [page](https://proxyempire.io/rotating-residential-proxies/)

### Inferences
- User/password suits your proxy URL setup. IP whitelisting is a poor fit if your home IP changes.
- Whether a 5-minute polling loop should hold one sticky IP or rotate is an empirical question. Either way, keeping a provider's session parameter in the username makes switching cheap.

### Gaps
- SOAX, Oxylabs, ProxyEmpire and IPRoyal authentication details were not confirmed from the pages I retrieved. Username/password is usual in this market, but I did not verify it for them.

## What is the typical latency from NZ, and are NZ exits really local?

### Takeaway
I found no independent latency or locality test for NZ exits. Exits are probably mostly NZ at country level, but this is unverified. Latency should not matter for 5-minute polling, so test locality yourself rather than rely on claims.

### Cited Findings
- Decodo claims under 0.5 s for NZ residential; this is a vendor figure — [page](https://decodo.com/proxies/list/new-zealand)
- Proxyway's global residential median was 0.93 s to a 6 KB CDN page, and 3.21 s on real target sites. Decodo was 0.53 s and Oxylabs 0.60 s globally; IPRoyal 1.24 s — [Proxyway 2026](https://proxyway.com/research/proxy-market-research-2026)
- Proxyway's nearest test was Australia, run for 7 days from a **Singapore** server, with Oxylabs best at 99.96% residential. So the results do not show NZ-client latency — [Proxyway 2026](https://proxyway.com/research/proxy-market-research-2026)
- Proxyway reported the share of IPs classified as residential or mobile by IP2Location, and did not test geolocation accuracy directly — [Proxyway 2026](https://proxyway.com/research/proxy-market-research-2026)
- Traffic path is client, then provider gateway, then router, then residential device, then target — [Databay](https://databay.com/blog/backconnect-proxies-explained) [snippet]
- Country accuracy tends to be high and city accuracy fuzzier, because geo-IP databases disagree (vendor guide) — [Shifter](https://shifter.io/blog/how-to-test-residential-proxy-speed-success-rate-location-accuracy) [snippet]
- One review found a "US" proxy that did not resolve to the US on any of three tools — [HostAdvice](https://hostadvice.com/proxy-servers/proxys-io-review/) [snippet]
- SOAX's NZ network list includes "Starlink" and "Cloudflare Warp" alongside local ISPs; ProxyEmpire's also lists Starlink — [SOAX](https://soax.com/proxies/locations/new-zealand), [ProxyEmpire](https://proxyempire.io/new-zealand-residential-proxy/)

### Inferences
- A local exit does not imply a short path: traffic may leave NZ to reach a gateway and return. Gateway regions were not published on the pages I read.
- Expect roughly 1 to 4 seconds per request as a planning guess from the global figures, not a measurement. That is fine for a bot polling every 5 minutes.
- Starlink and Cloudflare WARP entries suggest "NZ residential" can include exits that do not look like an ordinary NZ home ISP. On a trial, log the ASN and geolocation of each exit IP using a neutral IP-lookup service, not the retailer.

### Gaps
- No NZ-to-NZ latency measurements exist in the sources I found.
- No independent audit of whether NZ exits are physically in NZ.

## How well do residential proxies alone do against Akamai compared with unblockers, and what else does Akamai evaluate?

### Takeaway
**I found no independent, Akamai-specific comparison of residential proxies and unblockers.** General benchmarks show residential success dropping well below advertised rates on protected sites, with unblockers usually higher. Proxies change only the IP part of what Akamai scores, so they may help with rate-based limits but cannot be assumed to fix the 429s.

### Cited Findings
Evidence on proxies versus unblockers, none of it Akamai-specific:
- Proxyway 2026: residential median success was 99.28% to a CDN endpoint, but **74.43%** on Amazon, Google and Instagram. Best was Byteful at 81.23%. Targets were tested from the US, with providers told the method in advance — [Proxyway 2026](https://proxyway.com/research/proxy-market-research-2026)
- AIMultiple: vendors advertise 95 to 99%, while proxies typically manage 55 to 75% on sites that actively block bots. Residential and datacenter were tested on different targets, so this is not head-to-head. A provider's daily score can swing 20 points and its weekly score over 40 — [AIMultiple](https://aimultiple.com/proxy-for-scraping)
- AIMultiple: unblockers returned about 10 to 25 more real pages per 100 than **datacenter** proxies (not residential) on the same targets — [AIMultiple](https://aimultiple.com/proxy-for-scraping)
- AIMultiple unblocker test on the Tranco top 10,000 (260,000 requests): Bright Data 92 to 95%, Zyte 92 to 93%, Nimble 90%, Firecrawl 88%. **526 of those domains use Akamai, but the per-vendor Akamai chart did not load**. Pages were updated in late Oct 2026; test dates are not stated — [AIMultiple](https://aimultiple.com/web-unblockers)
- Older or unclear AIMultiple figures: residential effective on 21 to 37% of pages — [snippet](https://research.aimultiple.com/proxy-benchmark); Bright Data 68 to 78% vs Oxylabs 40 to 50% unblockers — [snippet](https://aimultiple.com/oxylabs-proxies). These sit far from the 92 to 95% above, so test sets or dates probably differ.
- Conflict of interest: AIMultiple's page has affiliate links and benchmarked vendors among its subscribers — [AIMultiple](https://aimultiple.com/proxy-for-scraping)
- AIMultiple says residential and datacenter proxies have no built-in anti-bot features, leaving systems such as Akamai to the user — [AIMultiple](https://aimultiple.com/web-unblockers)

What Akamai evaluates, in general terms. These come from vendor or tutorial sources; I found no official Akamai detail:
- **Combined trust score** across stages; IP type is one input, and residential IPs add positive trust — [ScrapFly](https://scrapfly.io/blog/how-to-bypass-akamai-anti-scraping) (sells bypass services, so treat with care)
- **TLS fingerprint** (JA3, cipher suites, version); JA4 is also mentioned — [HackerNoon](https://hackernoon.com/outsmarting-akamais-bot-detection-with-ja3proxy) [snippet], [ScrapeBadger](https://scrapebadger.com/blog/akamai-bot-manager-how-it-works-and-how-scrapebadger-bypasses-it) [snippet]
- **HTTP protocol** version, HTTP/2 fingerprint, header set and order — [ScrapFly](https://scrapfly.io/blog/how-to-bypass-akamai-anti-scraping)
- **Client-side sensor data** gathered by page JavaScript and tied to the `_abck` cookie — [ScrapFly](https://scrapfly.io/blog/posts/akamai-bot-manager-understanding-abck-cookies-and-sensor-data) [snippet]
- **Behaviour** over time, including navigation and input patterns — [ScrapFly](https://scrapfly.io/blog/how-to-bypass-akamai-anti-scraping), [Scrappey](https://scrappey.com/qa/web-automation/how-akamai-detects-bots) [snippet]
- One source says a low-scoring IP and fingerprint combination may not recover even with fresh cookie state, and another says browserless setups are not enough for top-tier defences. Neither is an independent test — [snippet](https://scrapebadger.com/blog/akamai-bot-manager-how-it-works-and-how-scrapebadger-bypasses-it), [snippet](https://use-apify.com/blog/tags/anti-bot)

### Inferences
- Your own data is the most useful clue. Challenges after about 2.5 hours at 5-minute cycles, roughly 80 requests at your daily rate, fit gradual score or rate accumulation on one IP. They do not separate an IP cause from a client-signal cause.
- If the cause is IP-tied volume, spreading requests across residential IPs may delay or reduce challenges. If it stems from non-browser signals such as absent sensor data, a new IP may only reset the clock. A low-cost trial can show which is closer, by comparing time-to-first-challenge on the existing request pattern with your home-connection baseline.
- Chrome TLS impersonation covers only one signal, and matching TLS does not supply JavaScript-derived state. I am deliberately not going further than this on challenge handling.
- A managed unblocker handles these layers for you, so it is the more reliable option if a proxy trial fails. Unblockers can cost more per request and be slower: Bright Data's mean rose from about 4 to 16 seconds under load — [AIMultiple](https://aimultiple.com/web-unblockers). Whether it works on JSON POSTs to your specific gateway needs testing.

### Gaps
- No per-vendor Akamai success rates and no independent controlled test (IP type vs client stack) exist in what I could read. AIMultiple's granular data is behind a subscription.
- Nothing found specifically on Akamai-protected JSON API gateways rather than web pages, which may behave differently.
- Bright Data's results were not in the part of the Proxyway report I retrieved, and that retrieval was truncated.

## Are NZ mobile proxies available, at what price, and are they any better?

### Takeaway
Yes, both per-GB and as dedicated lines from $129 a month. The evidence shows almost no advantage for mobile over residential, and none that is NZ- or Akamai-specific, so mobile is a second test rather than a first purchase.

### Cited Findings
- ProxyEmpire: rotating mobile on One NZ, Spark and 2degrees, from $2.00/GB (the headline rate; the small-plan rate was not retrieved). The $1.97 trial includes 50 MB of mobile — [NZ](https://proxyempire.io/new-zealand-residential-proxy/), [plans](https://proxyempire.io/rotating-residential-proxies/)
- Coronium: dedicated device and SIM, unmetered, $12 for 24 hours or $129 for 30 days, with **only OneNZ in stock**, page-stated as checked 2026-11-01. IP change by dashboard, API, link or timer (60-second minimum). Other page text mentions Spark and 2degrees too — [page](https://coronium.io/mobile-proxies/new-zealand)
- SOAX: same per-GB rate for residential and mobile, with carrier names on the NZ page, but no explicit NZ mobile statement — [pricing](https://soax.com/pricing), [NZ](https://soax.com/proxies/locations/new-zealand)
- Decodo's NZ mobile availability is unclear from its page — [page](https://decodo.com/proxies/list/new-zealand)
- Bright Data requires KYC for its mobile network; its NZ mobile availability is not confirmed — [pricing](https://brightdata.com/pricing/proxy-network/residential-proxies)
- Proxyway 2026 target-site median success: mobile 75.26% vs residential 74.43%, with DataImpulse best on mobile at 85.31%. Mobile median price is $4.38/GB vs $3.75 at 5 GB. These are US tests on Amazon, Google and Instagram — [Proxyway 2026](https://proxyway.com/research/proxy-market-research-2026)
- "Mobile" labels can be unreliable: Proxyway saw NetNut's global mobile share at 75.14%, and only about a quarter of DataImpulse's and NetNut's Brazil IPs classed as mobile. SIM farms are also a growing supply source — [Proxyway 2026](https://proxyway.com/research/proxy-market-research-2026), [Newswire](https://www.newswire.com/news/proxyway-releases-2026-proxy-server-market-report-22788334) [snippet]

### Inferences
- The usual argument for mobile is that carrier IPs are shared behind NAT, so sites hesitate to block them. I found no independent evidence quantifying that benefit against Akamai.
- A dedicated line costs far more than per-GB residential for this traffic (roughly $129 vs under $16 a month). It is worth considering only if a per-GB mobile test clearly beats residential.
- Any IP-side improvement still leaves the non-IP signals above unchanged.

### Gaps
- No NZ mobile pool size was published by any provider, and no independent quality data for NZ carriers.
- Small-volume NZ mobile prices beyond those above were not retrieved.

## What about ethical sourcing and terms-of-use limits relevant to retail sites?

### Takeaway
Sourcing is a real risk: two major networks were disrupted in 2026 over compromised or non-consenting devices. Prefer vendors with direct sourcing statements and KYC, avoid suspiciously cheap traffic, and read each provider's and the retailer's terms before buying.

### Cited Findings
- Google disrupted IPIDEA in January 2026. Devices were enrolled through SDKs and trojanised apps without owners' knowledge, and Google called the market a "gray market" and asked for more regulation — [The Hacker News](https://thehackernews.com/2026/01/google-disrupts-ipidea-one-of-worlds.html) [snippet], [BleepingComputer](https://www.bleepingcomputer.com/news/security/google-disrupts-ipidea-residential-proxy-networks-fueled-by-malware/amp/) [snippet]
- NetNut, a NASDAQ-listed company's service, was seized in July 2026. It was **widely resold and white-labelled**, and Google warned that operators may rebuild by reselling other networks, as IPIDEA did — [Krebs](https://krebsonsecurity.com/2026/07/fbi-seizes-netnut-proxy-platform-popa-botnet/)
- Grey-market botnet proxies can cost $0.15 to $0.50/GB — [Proxyway 2026](https://proxyway.com/research/proxy-market-research-2026)
- DataImpulse claims a first-party pool with no resold networks and "full user consent"; this is a vendor claim, unaudited — [page](https://dataimpulse.com/residential-proxies/)
- Bright Data: KYC for residential and mobile, possibly a video call and ID; Web Unlocker needs no KYC — [pricing](https://brightdata.com/pricing/proxy-network/residential-proxies)
- Bright Data's acceptable-use policy bars ticket-purchasing bots, posting on resale or classified sites, and collecting non-public data such as data behind login. It may block domains at its discretion. It has no separate rule on public retail data — [AUP](https://brightdata.com/acceptable-use-policy)
- ProxyEmpire requires KYC and a use-case review for ports other than 80 and 443 — [page](https://proxyempire.io/rotating-residential-proxies/)
- Decodo's review coverage promotes shared ISP proxies for buying tickets and sneakers, which is marketing text and not a policy — [Yahoo](https://tech.yahoo.com/vpn/articles/decodo-191432080.html) [snippet]

### Inferences
- Exits on real home connections mean your traffic crosses other people's networks. Reputable sourcing, low volume and small read-only lookups keep that burden small, but consent claims cannot be verified from outside.
- ProxyEmpire and Webshare are described as resellers. That does not show any bad sourcing, but ask each which upstream networks they use, and whether anything changed after the NetNut seizure.
- Read-only stock checks look unlike the purchase-bot use that policies ban, but a provider or retailer may see it differently. Using rotating IPs after a retailer has begun challenging you could breach the retailer's terms, whatever the proxy provider allows. Also consider asking the retailer about a sanctioned feed or API.
- Suggested order to trial, from this evidence only: ProxyEmpire (NZ and mobile confirmed, low-cost trial, but coupon-priced and a reseller), then Decodo (strong Proxyway results, NZ page, trial) or IPRoyal (no expiry, long sessions, though weaker 2026 results at 96.11%). Bright Data if KYC is acceptable. DataImpulse is cheapest, but NZ must be confirmed first.

### Gaps
- Decodo, IPRoyal, ProxyEmpire, SOAX, Oxylabs, Webshare and DataImpulse terms were not read: the Decodo URL returned 404 and searches found no policy text.
- The retailer's own terms were not reviewed, as they are outside this assignment and no retailer was contacted.
- No independent audit of any provider's consent claims was found.
- Legal risk under NZ law was not researched.
