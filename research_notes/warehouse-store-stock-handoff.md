# The Warehouse — per-store stock: handoff

Status: **built, unit-tested, and live-validated.** The only non-automated step is getting past
the Cloudflare human check on the hot product page, which is a deliberate design boundary (we do
not auto-solve the CAPTCHA). Everything downstream of the page loading is scripted. Read this
before touching `tcgpings/retailers/warehouse.py`.

Last validated live: 2026-11-03. Example SKU used everywhere: **`R3098657`**
("Pokémon TCG 30th Celebration Build & Battle Box (2 per customer)").

---

## 1. TL;DR

- Per-store stock is reachable via a **two-call flow** run through the browser backend
  (`tcgpings/net/browser.py`, Patchright driving real Chrome). No CAPTCHA tooling, no paid
  unblocker required.
- The flow is **implemented** in `WarehouseAdapter.store_stock()` and **unit-tested** against
  real captured fixtures (19 tests pass, including a test that mirrors the live result).
- It is **wired into the pipeline** the same way as Farmers / JB Hi-Fi / Toyworld (worker →
  `store_stock()` on an interval → in-store alerts), and is callable from the CLI.
- **The human gate:** on a *cold* or *expired* profile the hot product page shows a Cloudflare
  interactive Turnstile checkbox. A **human click** mints a `cf_clearance` cookie into the
  profile; while that cookie is valid, every `store_stock()` call runs hands-off. When the
  cookie expires, one more human click is needed. Programmatic clicks do **not** count.
- **Operational shape:** event-driven (fire only when a tile flips to `FIND_IN_STORE`/`IN_STOCK`
  or a keyword watch matches). Cost = 1 page load + 1 widget call + up to 15 region calls per
  product per check, all free (in-page `fetch`, no paid route).

## 2. Findings (the technical truth)

### 2.1 Platform
Salesforce Commerce Cloud (`Sites-twl-Site`), fronted by **Cloudflare**. Product IDs look like
`R3098657`; product URLs are `/p/x/<id>.html`. Category tiles (search/listing) work over plain
HTTP and carry nationwide availability + price. Only **hot Pokémon** pages sit behind the
Cloudflare human check.

### 2.2 The two-call store-stock flow (step 1 → step 2)

There is **no** single "store stock" endpoint. It is two calls, each with its own short-lived
signed `verify` token (shape `<timestamp>-<signature>`), minted into the previous response:

1. **Step 1 — store-availability modal.** The product page contains a custom element
   `<gep-container-store-availability pid="R3098657" url="...">`. Its `url` attribute is
   `/products/stores?pid=<id>&verify=T1` (Salesforce action `Product-GetPDPStoreStockLevels`).
   Fire it **once** → a ~32 KB modal template that lists **all 15 regions**, each `<option>`
   carrying `value="NZ-AUK"` and a
   `data-href="/products/stores/region?productId=<id>&region=NZ-AUK&verify=T2"`.
   - **One-shot per session:** firing the same step-1 URL again returns `403`
     ("Cross-Origin Request Blocked").
2. **Step 2 — per-region store availability.** Each of the 15 region URLs
   (`Stores-PDPStoreAvailability`) returns a ~47 KB JSON whose `stores` field is HTML of
   `<div class="store panel">` blocks, each with `id="c-full-store-details-<id>"` (numeric store
   id, e.g. `196`) and a `store-availability__<STATUS>` class.
   - **Short-TTL per-region tokens:** reusing an old token (or a step-1 token on a region path)
     returns `410` ("Expired URL"). Fire each region **promptly**, right after step 1.

**Status classes seen:** `IN_STOCK`, `LOW_STOCK`, `OUT_OF_STOCK`, `NOT_AVAILABLE`. Mapped in
`warehouse.py::STOCK_STATUS` to `Level.IN / LOW / OUT` (`FIND_IN_STORE` and `NOT_AVAILABLE` → `OUT`).

### 2.3 The Cloudflare challenge — the nuance the earlier notes got wrong

The earlier recon in `docs/RETAILERS.md` (lines 87/90) and `research_notes/warehouse-verify.md`
state the managed challenge "auto-solves in a clean genuine Chrome (no checkbox, no
`cf_clearance`)". That is **partially true and misleading**. What this session established:

- Cloudflare serves **two interstitial variants**:
  1. **Interactive** — a Turnstile iframe with a "Verify you are human" checkbox.
  2. **Managed** — a hidden `cf-turnstile-response` input, no checkbox, meant to auto-solve.
- In a **genuine, warm** Chrome (lots of history, human) it usually shows the managed variant and
  auto-solves — that's what the 2026-11-03 recon saw.
- In a **cold or automated** profile (fresh `user-data-dir`, or Patchright), it tends to show the
  **interactive** variant and **does not** auto-solve within 60–180 s. **Programmatic
  `page.mouse.click` on the checkbox is scored as automation and does not clear it.**
- The reliable unlock is a **human click**, which mints a `cf_clearance` cookie into the profile.
  Once present and unexpired, the challenge is skipped and the flow runs hands-off.
- Practical rule for the next agent: **expect to occasionally need a human click** to refresh the
  profile's clearance, especially right after a cold start or after the bot has been blocked.

### 2.4 Live-validated result
Auckland region for `R3098657`: **22 stores, 1 in stock** — store `196` (Warkworth) `IN_STOCK`,
store `221` (Auckland Central) `OUT_OF_STOCK`. This is the same assertion the unit test
`test_store_stock_visits_once_fires_the_widget_then_only_the_needed_regions` encodes.

### 2.5 Tooling gotchas hit this session (so they aren't re-hit)
- **Patchright cannot attach to Chrome's default profile dir** — it errors with *"DevTools remote
  debugging requires a non-default data directory."* Use a dedicated dir, e.g.
  `data/browser/chrome-debug`.
- **CDP port binding was flaky** when Chrome was launched via PowerShell `Start-Process`
  (`--remote-debugging-port=9222` didn't bind; the DevTools MCP couldn't reach it). Driving the
  profile directly via **Patchright** (`launch_persistent_context`, headless=False) sidestepped
  this and is the reliable path.
- A force-killed Chrome leaves a stale profile lock; kill with `taskkill /F /IM chrome.exe /T`
  and wait a few seconds before relaunching on the same profile.

## 3. Files

### 3.1 Production code — DONE
- **`tcgpings/retailers/warehouse.py`** — the adapter. Key pieces:
  - `supports_store_stock = True`, `store_stock_discovers_stores = True`, `store_stock_interval = 5*60`.
  - `store_stock_enabled` property → `True` iff `http.browser` is set (the browser backend).
  - `store_stock(sku, store_ids)` → the full two-call flow (visit page → extract widget URL →
    fire widget once → parse 15 regions → fire only needed regions → parse levels).
  - `widget_store_url(page, sku)`, `parse_store_regions(widget)`, `parse_store_levels(region)`.
  - `load_stores()`, `list_stores()` (76 real + "Stores nationwide" pseudo-store), `store_label()`.
  - `PAGE_RESOLVED_JS` = `gep-container-store-availability` present **and** title not "Just a moment".
- **`tcgpings/retailers/data/warehouse_stores.json`** — 76 stores with `store_id`, `name`,
  `region_code` (generated from the `Stores-FindStores` call; see `_gen_warehouse_stores.py`).
- **`tcgpings/net/browser.py`** — `BrowserFetcher.visit()` (loads the page, waits for
  `success_js` within `timeout_ms`, does **not** click) and `BrowserFetcher.fetch_text()` (in-page
  `fetch(url, {credentials:'include'})` — this is how the widget + region calls are fired,
  reusing the page's cookies).
- **Pipeline wiring (generic, shared with other retailers):**
  - `tcgpings/cluster/worker.py` — checks `store_stock_enabled`, calls `store_stock()` on
    `store_stock_interval`, raises in-store alerts.
  - `tcgpings/engine/planner.py` — schedules the `sync_stores` job for retailers with
    `supports_store_stock`.
  - `tcgpings/__main__.py` — CLI: `probe warehouse stock <sku> --store <id> [...]`.

### 3.2 Tests + fixtures — DONE (19 tests pass)
- **`tests/test_warehouse.py`** — 19 tests. Store-stock ones:
  - `test_parse_store_regions` (15 regions, URLs unescaped, no `&amp;`).
  - `test_parse_store_levels_reads_stock_by_store_id` (22 stores; `196` IN, `221` OUT).
  - `test_store_stock_visits_once_fires_the_widget_then_only_the_needed_regions` (visits once,
    fires widget + only needed region, correct IN/OUT).
  - `test_store_stock_ignores_store_ids_outside_the_bundle`.
  - `test_list_stores_is_the_real_76_plus_the_nationwide_pseudo_store` (77 total).
- **`tests/fixtures/warehouse/`** — real captured payloads used by the tests:
  - `widget.json` (step-1 modal, 32 KB), `region-auckland.json` (step-2, 47 KB),
    `listing.html` (category tiles), `product.html` (JSON-LD).

### 3.3 Recon / diagnostics (reference, not imported)
- **`research_notes/warehouse-*.json`** — raw captured payloads: `warehouse-store-call-1.json`,
  `warehouse-region-auckland-full.json`, `warehouse-retest-r3098657.json` (keys
  `step/widget/auckland/westland`), `warehouse-findstores.json` (76-store source).
- **`research_notes/_diag_wh_defaultprofile.py`** — the **live re-test driver** (Patchright on
  the `chrome-debug` profile). Waits-or-clicks through the challenge (prints a "CLICK NOW"
  prompt + bell), then runs the two-call flow in-page, prints per-store levels, and dumps
  `research_notes/warehouse-region-*.json` + `warehouse-retest-<sku>.json`.
- **`research_notes/_probe_warehouse_live.py`** — live probe through the real `BrowserFetcher`
  (uses `data/browser/warehouse-probe` profile).
- **`research_notes/_parse_store_levels3.py`** — the working level-extraction parser (source of
  `parse_store_levels`).
- **`research_notes/_gen_warehouse_stores.py`** — regenerates `warehouse_stores.json` from
  `warehouse-findstores.json`.
- Other `_diag_*.py` / `_parse_*.py` / `_wh_*.py` are scratch experiments; safe to ignore.

### 3.4 Docs
- **`docs/RETAILERS.md`** (lines 78–101) — Warehouse recon. **Note:** its "auto-solves, no
  checkbox, no cf_clearance" wording (lines 87/90) is superseded by §2.3 above — a human click is
  the practical gate on cold profiles.
- **`research_notes/warehouse-verify.md`** — an earlier, more pessimistic note recommending a
  sanctioned feed. Partially superseded: the two-call flow demonstrably works; the sanctioned feed
  remains the cleanest long-term route but is no longer the *only* way.

## 4. What to expect (operational)

- **Normal run (warm profile):** `store_stock()` loads the product page (challenge skipped via
  `cf_clearance`), fires the widget once, fires only the regions for the requested stores, and
  returns `{store_id: Stock}`. No human needed.
- **Cold/expired profile:** `browser.visit()` times out
  (`FetchError: challenge did not resolve within Ns`, last title `'Just a moment...'`). A
  **human** must click the checkbox in the visible window (the driver script prints a "CLICK NOW"
  banner and beeps). After that click the profile is warm again.
- **Frequency of re-clicks:** depends on `cf_clearance` lifetime and how aggressively Cloudflare
  challenges; treat it as "occasionally," not "every run."
- **Cost per check:** 1 page load + 1 widget + ≤15 region fetches, all free in-page requests.
  Keep it event-driven so you don't pay 15 fetches per product per minute.
- **One-shot widget / short-TTL regions:** never refire a step-1 URL (403) or a stale region URL
  (410) — a fresh page load re-mints the tokens.

## 5. Recommended next steps (all optional robustness / product, none blocking)

1. **Turnstile-click fallback in `browser.visit()`** (or a warehouse-specific warm helper):
   detect the interactive Turnstile, click it once, keep waiting. Reduces (but does not remove)
   reliance on a manual click — programmatic clicks clear it less often than human ones, so keep
   the manual path as the guaranteed fallback.
2. **Re-warm after a block:** the `BrowserFetcher` already resets `session.warmed` on 403/429;
   confirm it re-navigates the home page before retrying the product page.
3. **Sanctioned feed:** a short email to The Warehouse's ecommerce team asking for a stock API /
   data partnership. If granted, per-store alerts become trivial and need no browser backend.
4. **Parity check:** Kmart / JB Hi-Fi / Toyworld already expose per-store stock openly (documented
   in this repo) — if the 30th products hit those, you already have per-store alerts there today.

## 6. Verification checklist (how to confirm it still works)

1. **Unit tests:** `.venv\Scripts\python.exe -m pytest tests/test_warehouse.py -q` → 19 passed.
2. **Live re-test (needs a human click on a cold profile):**
   - Kill Chrome: `taskkill /F /IM chrome.exe /T`
   - Run: `.venv\Scripts\python.exe research_notes/_diag_wh_defaultprofile.py`
   - When it prints the "CLICK NOW" banner, click the checkbox in the Chrome window.
   - Expect `PAGE RESOLVED`, then `TOTAL stores seen: N`, `IN STOCK: N`, and the per-store list.
   - It writes `research_notes/warehouse-region-<code>.json` + `warehouse-retest-<sku>.json`.
3. **CLI (warm profile):** `.venv\Scripts\python.exe -m tcgpings probe warehouse stock R3098657
   --store 196 --store 221`.

