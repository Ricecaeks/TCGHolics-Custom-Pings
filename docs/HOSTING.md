# Hosting, resources and anti-bot options

Written 2026-10-29. Measurements are from the local stack (`deploy/docker-compose.local.yml`) on an i5-14400F with 32 GB RAM. Prices come from vendor pages and comparison sites; check current pricing before buying anything.

## 1. What it actually costs to run

| Component | RAM | CPU | Notes |
|---|---|---|---|
| Monitor node, no browser | **74 MB** | ~1% of one core, spikes ~10% | Shopify-style JSON retailers only |
| Postgres (local) | **50 MB** | <1% | capped at 256 MB / 0.5 CPU |
| + each open Chrome session | **+~520 MB** | ~1.2 cores for 2–3 s at launch, then <0.3 core | one per browser-backed retailer (Farmers, maybe Kmart/Woolworths). Closed after 10 idle minutes |
| Docker image | 2.0 GB disk | — | mostly Chrome and its libraries |
| Network (Shopify) | — | — | ~1.5 MB per search run. 6 search jobs every 5 min ≈ 2.6 GB/day |

**Realistic totals on your PC:**
- Shopify shops only: **about 130 MB RAM**, almost no CPU.
- Plus Farmers: **about 650 MB** while its Chrome is open.
- All of the browser-backed retailers below: **about 1.5–2 GB**.

The node is hard-capped at **2 CPU threads and 2 GB RAM**. If it ever goes over, Docker restarts it rather than slowing your PC down.

### How many containers?

**One node per machine.** Extra containers on the same PC don't add capacity:
- They share the same IP, and the per-retailer rate limits are split between nodes that share an IP.
- One node already runs 8 checks in parallel (`WORKER_CONCURRENCY`).

Extra nodes only help on **other machines or other IPs**, such as the laptop plus a cloud box. The design supports that whenever you want it.

### Keeping games smooth (Docker Desktop on Windows)

Docker Desktop runs inside a WSL2 virtual machine that can take up to half your RAM and every core. Cap it by creating `C:\Users\<you>\.wslconfig`:

```ini
[wsl2]
memory=6GB
processors=4
```

Then run `wsl --shutdown` and restart Docker Desktop. With 26 GB and 12 threads always left for Windows and games, and the monitor's own 2-thread / 2 GB cap, there's no measurable impact on gaming. The only visible effect is a ~2 s CPU blip on a couple of cores when Chrome launches, at most a few times an hour.

## 2. The always-on gaming laptop

The same `docker-compose.local.yml` works unchanged. To make it a dependable appliance:

1. **Docker Desktop:** Settings → General → *Start Docker Desktop when you sign in*. The containers already use `restart: unless-stopped`.
2. **Windows power settings:**
   - Sleep: *Never* when plugged in.
   - Lid close: *Do nothing*.
   - Turn off *USB selective suspend*.
   - Set Windows Update active hours so restarts happen overnight.
3. **Auto sign-in after reboots**, using `netplwiz` or Sysinternals Autologon, so Docker Desktop starts after Windows Update restarts the machine.
4. **GitHub self-hosted runner:** the deploy machine is **GGPC**. It runs one runner per repo, because a runner on a personal account serves a single repo: `ggpc` for Clipping, and `ggpc-tcgpings` (label `tcgpings`, in `C:\actions-runner-tcgpings`) for this one. Both use GGPC's one Docker Desktop. `ggpc-tcgpings` starts at sign-in under your Windows account, from the *TCGPings GitHub Runner* entry in your user's Run registry key. [`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml) then rebuilds and restarts the stack on every push to `main`, but only after the tests pass.
   - `.env` and `data/` live in `C:\tcgpings` (repository variable `TCGPINGS_HOME`), outside the checkout. The database stays in the `tcgpings-local_pgdata` Docker volume.
   - The `SCRAPFLY_API_KEY` and `ZYTE_API_KEY` repository secrets are copied into that `.env` on each deploy. A secret that isn't set leaves the value in `.env` alone.
5. Gaming laptops run hot at 24/7 idle, so put it on a stand. Battery-charge limiting in the vendor app (e.g. 60–80%) extends battery life.

A home connection is the **best place to run this**. NZ residential IPs are trusted far more by Akamai, Cloudflare and DataDome than cloud IPs (see §4).

## 3. Cloud hosting options (if/when you move)

| Option | Cost (approx.) | Pros | Cons |
|---|---|---|---|
| **Home PC / laptop** (now) | $0 | NZ residential IP (best for bot protection), plenty of RAM for Chrome | power/internet outages, Windows updates |
| **Raspberry Pi 5 / mini PC at home** | one-off $150–400 | same residential-IP advantage, low power, silent | ARM Pi can't run Google Chrome (only Chromium, which is more detectable). An x86 mini PC avoids that |
| **Budget VPS, Sydney** (Vultr ~US$5/mo, DigitalOcean ~US$4/mo, Cloudzy, Lightsail) | US$5–25/mo for 1–4 GB | always on, near NZ | **datacenter IP: Akamai/DataDome sites will block it**, so Farmers/Kmart/Mighty Ape need residential proxies on top. Need ≥2 GB RAM per Chrome |
| **NZ VPS** (local hosts, ~$13–21/mo) | ~NZ$15–30/mo | NZ IP | still a datacenter IP |
| **Oracle Cloud free tier** (Sydney/Auckland regions) | $0 | generous free ARM VM | ARM: no Google Chrome. Free-tier capacity can be hard to get. Datacenter IP |
| **Container PaaS** (Fly.io, Railway, Render) | US$5–30/mo | easy deploys | datacenter IPs. Chrome needs a large instance. Mostly not NZ/AU |
| **Hetzner** | cheapest per GB RAM | very cheap | no AU/NZ region (latency doesn't matter here), foreign datacenter IP |

**Recommended path:** stay on the home machine. If you go to the cloud, use a small Sydney VPS with **NZ residential proxies** for the protected retailers, or a hybrid: cloud for the easy JSON retailers, home laptop for the browser-backed ones. The multi-node design already supports running both together.

## 4. Getting past bot protection: the toolbox

These are ordered from cheapest and most robust to most expensive. Each retailer gets the cheapest option that works.

| # | Technique | Cost | Works against | Notes |
|---|---|---|---|---|
| A | **Use the site's own JSON endpoints** (Shopify `/products.json`, Salesforce Commerce controllers, Algolia/Constructor search) | free | unprotected sites, or protection that only guards HTML pages | what we do for Shopify. Many sites expose clean JSON |
| B | **`curl_cffi` TLS impersonation** (built in) | free | Cloudflare basic, many sites | fails against Akamai Bot Manager after a few requests (seen on Farmers) |
| C | **Real browser (Patchright + Google Chrome, headed, aged profile)**, built in as `net/browser.py` | free + ~0.5 GB RAM | Akamai, DataDome, Cloudflare challenges (in principle) | Farmers is not passing yet. Needs a cooled-off IP, an aged profile and slow pacing. See §6 |
| D | **NZ residential proxies** (pay per GB) | ~US$1–8/GB; NZ-specific offers from ~$0.79–3.50/GB | IP reputation and rate limits | combine with B or C. Keep traffic small: JSON calls, not page loads. Datacenter IPs are cheap but get blocked |
| E | **Unblocker APIs** (Bright Data Web Unlocker, Zyte API, ScrapFly, ZenRows, Decodo, IPRoyal) | ~US$1–3 per 1,000 successful requests; browser-rendering tiers up to ~$16/1k | Akamai, DataDome, Cloudflare | pay only for success. Easiest to plug in as an alternative fetch backend. Cost grows with check frequency |
| F | **Akamai cookie services** (e.g. Apify Akamai actors) | ~US$9 per 1,000 cookie generations | Akamai | generate a valid `_abck` cookie, then use cheap HTTP calls with it. Fragile |
| G | **Official route**: ask the retailer, or use affiliate product feeds (Commission Factory etc.) | free | everything | feeds usually carry price and online stock, not per-store. Worth asking Farmers and Warehouse Group |

**Rough cost of option E for Farmers**, at the current schedule (online every 15 min, all 13 regions every 4 h): about 7 requests per watched product per hour. For 30 products that's ~5,000/day or ~150k/month, which comes to **~US$200/month** at $1.5 per 1,000. Limiting store checks to the regions you care about, e.g. Auckland only, cuts that by about 90%.

## 5. Retailers: what to monitor and how to get in

The store counts marked ≈ are estimates and need confirming during each retailer's recon. "Plain request" is the result of one homepage request on 2026-10-29.

| Retailer | Stores | Store-level stock? | Platform / protection | Plain request | Likely approach |
|---|---|---|---|---|---|
| **Farmers** | **53** (done) | yes: In/Not in stock, refreshed daily ~8am | Intershop + **Akamai Bot Manager** | 200, then 403 | **A via Constructor.io** for new listings and online stock (approved, works). Price and store stock: C (blocked for now), then D+C, or E/F |
| **The Warehouse** | **76** (confirmed) | yes, per store, 15 regions | Salesforce Commerce Cloud + Cloudflare | 200 | A for listings and store list. Store stock needs a per-product token from the product page, and the **Pokémon product page is behind a Cloudflare Turnstile challenge** |
| **Noel Leeming** | ≈70 | likely | Salesforce Commerce Cloud + Cloudflare (same group as Warehouse) | 200 | A: shares most of The Warehouse's code |
| **Warehouse Stationery** | ≈60 | likely | Cloudflare **challenge** | 403 | C or E |
| **Kmart NZ** | ≈27 | likely (click & collect API) | Next.js + Constructor.io + **Akamai** | 200 (first hit) | **Live via Constructor.io** (listings, price, online + per-island stock). Per-store stock: its GraphQL gateway, behind Akamai (recon pending) |
| **JB Hi-Fi NZ** | ≈15 | **yes**: in-stock store IDs embedded in the product page | Shopify + Algolia + Cloudflare | 200 (3/3) | **A, plain HTTP, confirmed.** One request per product gives every store's stock |
| **Toyworld** | ≈30 | maybe | Shopify + Cloudflare | 200 | A: probably works with the generic Shopify adapter as is |
| **Mighty Ape** | online only | no | **DataDome** | 403 | C or E. Online stock only |
| **Whitcoulls** | ≈50 | maybe | nothing detected | 200 | A or B |
| **Paper Plus** | ≈90 | maybe | nothing detected | 200 | A or B |
| **Woolworths NZ** (sells Pokémon) | ≈185 | yes, per store (prices and stock are per store) | Next.js + **Akamai** | 200 (first hit) | its public JSON API, if not Akamai-gated |
| Independent card shops | — | online | Shopify (most) | 200 | A: generic Shopify adapter, works today |
| ~~EB Games NZ~~ | — | — | — | — | **dropped: stores closed** |

**Suggested order** (updated after the Warehouse and JB recon):
1. JB Hi-Fi: plain HTTP with store-level stock, confirmed.
2. Farmers via Constructor.io: new listings and online stock, confirmed.
3. The Warehouse and Noel Leeming: listings and online stock now; per-store only for products whose pages aren't challenged.
4. Toyworld: Shopify, near-free.
5. ~~Kmart~~ (live via Constructor.io), then Woolworths.
6. ~~Farmers per-store stock~~ (built: the fetch chain, §6).
7. Mighty Ape and Warehouse Stationery last.

## 6. Farmers: status and next steps

What was tried on 2026-10-29, from the home IP:

| Client | Result |
|---|---|
| `curl_cffi` (Chrome TLS) | 2 OK, then 403 on everything |
| Playwright Chromium, headless and headed | `WAF_Deny_Page` (served as HTTP 200) |
| Patchright headless | `WAF_Deny_Page` |
| Patchright + Google Chrome, headed | home page OK and `_abck` validated, but the stock call returned 403. A later cold visit to a product page was denied |
| Same, inside Docker (Linux Chrome + Xvfb) | home page OK, search call blocked |
| The app's normal browser (aged cookie) | **every call OK** |
| Retest after a few hours' cool-down (Docker, persistent profile, 10 req/min) | product page (`ViewProduct-Start`) still **blocked** |

Akamai probably scores *new* automated sessions from this IP more harshly after the day's testing.

### The fetch chain (built)

Price and store stock go through `tcgpings/net/chain.py`, which tries each route in turn and fixes itself:

| Route | Cost | When the site blocks it |
|---|---|---|
| 1. Our Chrome (persistent profile) | free | rests **24 h**, then is tried again on its own |
| 2. ScrapFly (`SCRAPFLY_API_KEY`) | credits; ~30+ per Akamai request (US$30 = 200k credits on Discovery) | rests 1 h |
| 3. Zyte API (`ZYTE_API_KEY`) | ~US$1.27 per 1,000 (hardest tier, plain HTTP), pay as you go | rests 1 h |

- Breakers are kept in Postgres (`fetch_breakers`), so every node shares them and they survive restarts. A bad key or empty account (401/402) rests that service for 24 h; three network errors in a row rest a route for 30 min. A retailer's own 404 is an answer, not a failure.
- **Spend cap:** `UNBLOCKER_MONTHLY_BUDGET_USD` (default 20). At 80% Farmers checks only its priority regions; at 100% the paid routes stop until next month and the free ones keep going. ScrapFly reports each request's credit cost; Zyte's is estimated from `ZYTE_USD_PER_REQUEST`. Set a matching limit in each provider's dashboard as a second backstop.
- **Staff pings only when it can't fix itself:** budget at 80% or used up, or every route for a retailer blocked for more than a day. `/status` shows each route's state and this month's spend.
- **Volume** at once a day: 30 products × 13 regions ≈ 12k requests/month (all regions), or ≈ 1k (Auckland only).
- **Testing a key live:** `python -m tcgpings probe farmers stock 7044417 --store albany --set fetch='["scrapfly"]'`.

Still worth doing: let the home IP cool off (the Chrome route then works for free), an NZ residential proxy for Chrome (`net/browser.py` doesn't take one yet), and asking Farmers directly (you plan to).
