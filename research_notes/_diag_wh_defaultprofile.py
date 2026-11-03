"""Drive the user's REAL default Chrome profile via Patchright (headless, visible) and run the
Warehouse two-call store-stock flow in-page.

- Launches a persistent context on the user's default profile (warm cookies / cf_clearance).
- Navigates to the hot product page, waits-or-clicks through any Cloudflare turnstile.
- Then, in one in-page async fetch: read the gep-container-store-availability widget URL,
  fire it (step 1) -> parse the 15 region URLs -> fire each region (step 2) -> parse
  store-availability__<STATUS> panels into {store_id: status}.
- Prints per-store levels and dumps raw payloads to research_notes/ for fixtures.
"""
import asyncio
import json
import os
import pathlib
import re
import sys
import time

sys.path.insert(0, ".")

SKU = "R3098657"
URL = f"https://www.thewarehouse.co.nz/p/x/{SKU}.html"
PROFILE = r"C:\Github\TCGHolics-Custom-Pings\data\browser\chrome-debug"
OUT = pathlib.Path("research_notes")

TS = 'iframe[src*="challenges.cloudflare.com"]'

FLOW_JS = r"""
async (sku) => {
  const H = { accept: 'application/json', 'x-requested-with': 'fetch' };
  const el = [...document.querySelectorAll('gep-container-store-availability')]
    .find(e => e.getAttribute('pid') === sku);
  if (!el) return { error: 'no widget element for ' + sku };
  const widgetUrl = el.getAttribute('url');
  const w = await (await fetch(widgetUrl, { headers: H, credentials: 'include' })).text();
  let widget; try { widget = JSON.parse(w); } catch (e) { return { error: 'widget not json', widget: w.slice(0, 200) }; }
  const tpl = widget.modalTemplate || '';
  const regionMap = {};
  const reOpt = /value="([A-Z]+-[A-Z]+)"\s+data-href="([^"]+)"/g;
  let m;
  while ((m = reOpt.exec(tpl))) regionMap[m[1]] = decodeURIComponent(m[2]);
  const regions = Object.entries(regionMap);
  const results = [];
  for (const [code, href] of regions) {
    try {
      const t = await (await fetch(href, { headers: H, credentials: 'include' })).text();
      results.push({ code, len: t.length, body: t });
    } catch (e) {
      results.push({ code, error: String(e) });
    }
    await new Promise(r => setTimeout(r, 400));
  }
  return { widgetUrl, regionCount: regions.length, results };
}
"""

async def main() -> None:
    from patchright.async_api import async_playwright

    async with async_playwright() as pw:
        ctx = await pw.chromium.launch_persistent_context(
            PROFILE, channel="chrome", headless=False, no_viewport=True,
            locale="en-NZ", timezone_id="Pacific/Auckland",
            args=["--disable-dev-shm-usage", "--no-first-run", "--no-default-browser-check"],
        )
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await page.bring_to_front()
        await page.goto(URL, wait_until="domcontentloaded", timeout=60_000)
        try:
            await page.bring_to_front()
        except Exception:  # noqa: BLE001
            pass

        clicks = 0
        last_click = 0.0
        end = time.monotonic() + 180
        resolved = False
        prompted = False
        clicked_once = False
        while time.monotonic() < end:
            title = await page.title()
            if "just a moment" not in title.lower():
                has_widget = await page.evaluate("() => !!document.querySelector('gep-container-store-availability')")
                if has_widget:
                    resolved = True
                    print("PAGE RESOLVED title=%r" % title)
                    break
            if "just a moment" in title.lower():
                if not prompted:
                    print("\a" + "\n" + "=" * 60)
                    print(">>>  A CHALLENGE IS SHOWING.  NOW CLICK THE")
                    print(">>>  'Verify you are human' CHECKBOX in the Chrome")
                    print(">>>  window (bottom-left of the box).  Waiting up to")
                    print(">>>  3 minutes for your click...  <<<")
                    print("=" * 60 + "\n")
                    sys.stdout.flush()
                    prompted = True
                # one gentle programmatic nudge is harmless; the real click is yours
                if not clicked_once:
                    await page.wait_for_timeout(4000)
                    try:
                        loc = page.locator(TS).first
                        if await loc.count():
                            box = await loc.bounding_box()
                            if box:
                                await page.mouse.click(box["x"] + 30, box["y"] + box["height"] / 2)
                                clicked_once = True
                                print("nudged turnstile once; please click in the window if it's still showing")
                    except Exception as exc:  # noqa: BLE001
                        print("no turnstile to nudge: %s" % exc)
            await asyncio.sleep(1.5)

        if not resolved:
            print("NOT RESOLVED; title=%r (the 3 min window closed before it passed; re-run and click the checkbox)" % (await page.title(),))
            await ctx.close()
            return

        data = await page.evaluate(FLOW_JS, SKU)
        if data.get("error"):
            print("FLOW ERROR:", data["error"], data.get("widget", ""))
            await ctx.close()
            return

        print("widgetUrl:", data["widgetUrl"][:120])
        print("regionCount:", data["regionCount"])

        status_re = re.compile(r'store-availability__([A-Z_]+)')
        id_re = re.compile(r'id="c-full-store-details-(\d+)"')
        agg: dict[str, str] = {}
        for res in data["results"]:
            if "body" not in res:
                print("region", res.get("code"), "err", str(res.get("error", ""))[:80])
                continue
            OUT.joinpath("warehouse-region-%s.json" % res["code"].lower()).write_text(res["body"], encoding="utf-8")
            for block in re.split(r'<div class="store panel">', res["body"])[1:]:
                i = id_re.search(block)
                s = status_re.search(block)
                if i and s:
                    agg.setdefault(i.group(1), s.group(1))
        (OUT / ("warehouse-retest-%s.json" % SKU)).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

        in_store = {k: v for k, v in agg.items() if v in ("IN_STOCK", "LOW_STOCK")}
        print("\nTOTAL stores seen: %d" % len(agg))
        print("IN STOCK: %d" % len(in_store))
        for k, v in in_store.items():
            print("  store %s: %s" % (k, v))
        print("\nFull status breakdown:")
        from collections import Counter
        for st, n in Counter(agg.values()).items():
            print("  %s: %d" % (st, n))
        await ctx.close()


asyncio.run(main())
