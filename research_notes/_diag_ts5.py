"""Robust wait-or-click resolution test in the adapter's persistent profile (data/browser/warehouse-probe).

Cloudflare serves two interstitial variants:
  - interactive: a Turnstile iframe with a checkbox -> click it.
  - managed: a hidden cf-turnstile-response input, no checkbox -> it auto-solves, just wait.
Loop up to 60s: click any turnstile iframe that appears (at most a few times), and stop as soon as
the product widget is present and the title leaves 'Just a moment'. Reports cf_clearance presence.
"""
import asyncio
import pathlib
import sys
import time

sys.path.insert(0, ".")

PROFILE = pathlib.Path("data/browser/warehouse-probe")
URL = "https://www.thewarehouse.co.nz/p/x/R3098657.html"
TS = 'iframe[src*="challenges.cloudflare.com"]'


async def main() -> None:
    from patchright.async_api import async_playwright

    async with async_playwright() as pw:
        ctx = await pw.chromium.launch_persistent_context(
            str(PROFILE), channel="chrome", headless=False, no_viewport=True,
            locale="en-NZ", timezone_id="Pacific/Auckland",
            args=["--disable-dev-shm-usage", "--no-first-run", "--no-default-browser-check"],
        )
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await page.goto(URL, wait_until="domcontentloaded", timeout=60_000)

        clicks = 0
        last_click = 0.0
        end = time.monotonic() + 60
        last_title = ""
        while time.monotonic() < end:
            title = await page.title()
            last_title = title
            if "just a moment" not in title.lower():
                widget = await page.evaluate("() => !!document.querySelector('gep-container-store-availability')")
                if widget:
                    cf = await page.evaluate("() => document.cookie.includes('cf_clearance')")
                    print("RESOLVED title=%r cf_clearance=%s clicks=%d" % (title, cf, clicks))
                    break
            # Only click an interactive turnstile, at most once per ~5s, max 3 times.
            if "just a moment" in title.lower() and clicks < 3 and (time.monotonic() - last_click) > 5:
                await page.wait_for_timeout(3000)  # let the turnstile render
                try:
                    loc = page.locator(TS).first
                    if await loc.count():
                        box = await loc.bounding_box()
                        if box:
                            await page.mouse.click(box["x"] + 30, box["y"] + box["height"] / 2)
                            clicks += 1
                            last_click = time.monotonic()
                            print("clicked turnstile #%d" % clicks)
                except Exception as exc:  # noqa: BLE001
                    print("no turnstile clickable: %s" % exc)
                    last_click = time.monotonic()
            await asyncio.sleep(1.5)
        else:
            cf = await page.evaluate("() => document.cookie.includes('cf_clearance')")
            print("NOT RESOLVED in 60s; title=%r cf_clearance=%s clicks=%d" % (last_title, cf, clicks))
        await ctx.close()


asyncio.run(main())

