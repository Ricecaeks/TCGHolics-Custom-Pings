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
4. **GitHub self-hosted runner:** install it as a Windows service on the laptop and give it the label `tcgpings`. [`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml) then rebuilds and restarts the stack on every push to `main`, but only after the tests pass.
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
| **Farmers** | **53** (done) | yes: In/Not in stock, refreshed daily ~8am | Intershop + **Akamai Bot Manager** | 200, then 403 | C (blocked for now), then D+C, or E/F as fallback. Search could use Constructor.io (needs your OK) |
| **The Warehouse** | ≈85 | likely (click & collect) | Salesforce Commerce Cloud + Cloudflare | 200 | A: SFCC controller JSON for product, store and inventory |
| **Noel Leeming** | ≈70 | likely | Salesforce Commerce Cloud + Cloudflare (same group as Warehouse) | 200 | A: shares most of The Warehouse's code |
| **Warehouse Stationery** | ≈60 | likely | Cloudflare **challenge** | 403 | C or E |
| **Kmart NZ** | ≈27 | likely (click & collect API) | Next.js + Constructor.io + **Akamai** | 200 (first hit) | A via its stock API if not Akamai-gated, otherwise C/E |
| **JB Hi-Fi NZ** | ≈15 | maybe | Shopify + Algolia + Cloudflare | 200 | A: Shopify JSON / Algolia, like the existing adapter |
| **Toyworld** | ≈30 | maybe | Shopify + Cloudflare | 200 | A: probably works with the generic Shopify adapter as is |
| **Mighty Ape** | online only | no | **DataDome** | 403 | C or E. Online stock only |
| **Whitcoulls** | ≈50 | maybe | nothing detected | 200 | A or B |
| **Paper Plus** | ≈90 | maybe | nothing detected | 200 | A or B |
| **Woolworths NZ** (sells Pokémon) | ≈185 | yes, per store (prices and stock are per store) | Next.js + **Akamai** | 200 (first hit) | its public JSON API, if not Akamai-gated |
| Independent card shops | — | online | Shopify (most) | 200 | A: generic Shopify adapter, works today |
| ~~EB Games NZ~~ | — | — | — | — | **dropped: stores closed** |

**Suggested order:**
1. The Warehouse + Noel Leeming: one shared codebase, ~155 stores, probably plain JSON.
2. Toyworld and JB Hi-Fi: Shopify, near-free.
3. Kmart, then Woolworths.
4. Farmers once a browser/proxy approach is proven.
5. Mighty Ape and Warehouse Stationery last.

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

Akamai probably scores *new* automated sessions from this IP more harshly after the day's testing. Next steps, cheapest first:
1. **Let it cool for 24–48 h**, then trial again with the persistent profile in `data/browser/farmers`, which keeps its cookies, at 10 requests/min. Start with a warm-up of several page views.
2. **Seed trust by hand:** open the bot's own Chrome profile once (via noVNC into the container), browse Farmers normally for a minute, and let the cookie age. This is the setup that consistently worked.
3. **Route only the Farmers browser through an NZ residential proxy** (D). That's a fresh IP reputation, and cheap because the traffic is small.
4. **Fall back to an unblocker API (E) or a cookie service (F)** for the stock call only.
5. **Long term: ask Farmers** (you plan to).
