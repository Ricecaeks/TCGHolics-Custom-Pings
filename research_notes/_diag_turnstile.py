import asyncio, sys, time
sys.path.insert(0, ".")


async def main():
    from patchright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, channel="chrome")
        ctx = await browser.new_context(locale="en-NZ", timezone_id="Pacific/Auckland")
        page = await ctx.new_page()
        await page.goto("https://www.thewarehouse.co.nz/p/x/R3098657.html", wait_until="domcontentloaded", timeout=60_000)
        # Give the challenge ~15s to render its widget
        await asyncio.sleep(15)
        # Report any Cloudflare/Turnstile iframes and checkbox-like inputs
        frames = [f.url for f in page.frames]
        print("FRAMES:", [u for u in frames if u and u != "about:blank"])
        # Look for the Turnstile checkbox across frames
        clicked = False
        for f in page.frames:
            try:
                for sel in ["input[type=checkbox]", "#challenge-stage", ".cb-c", "iframe[src*=challenges.cloudflare.com]"]:
                    el = await f.query_selector(sel)
                    if el:
                        print(f"frame {f.url[:60]!r}: found {sel}")
            except Exception:
                pass
        # Try clicking the Turnstile checkbox in its iframe
        for f in page.frames:
            if "challenges.cloudflare.com" in (f.url or ""):
                box = await f.query_selector("input[type=checkbox]") or await f.query_selector("body")
                if box:
                    try:
                        await box.click(timeout=5000)
                        print("clicked Turnstile checkbox/body in", f.url[:60])
                        clicked = True
                    except Exception as e:
                        print("click failed:", e)
        end = time.monotonic() + 30
        while time.monotonic() < end:
            title = await page.title()
            widget = await page.evaluate("() => !!document.querySelector('gep-container-store-availability')")
            if widget and "Just a moment" not in title:
                print("RESOLVED after click (clicked=%s)" % clicked)
                break
            await asyncio.sleep(2)
        else:
            print("still challenged; title=%r clicked=%s" % (await page.title(), clicked))
        await browser.close()


asyncio.run(main())
