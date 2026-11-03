import asyncio, sys, time
sys.path.insert(0, ".")


async def main():
    from patchright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, channel="chrome")
        ctx = await browser.new_context(locale="en-NZ", timezone_id="Pacific/Auckland")
        page = await ctx.new_page()
        await page.goto("https://www.thewarehouse.co.nz/p/x/R3098657.html", wait_until="domcontentloaded", timeout=60_000)
        await asyncio.sleep(12)  # let Turnstile render

        async def try_click():
            iframe = page.locator("iframe[src*=challenges.cloudflare.com]").first
            try:
                box = await iframe.bounding_box()
            except Exception:
                box = None
            if box:
                # Checkbox sits ~30px in from the left, vertically centred in the widget
                await page.mouse.click(box["x"] + 30, box["y"] + box["height"] / 2)
                return f"mouse-click at iframe {int(box['x'])},{int(box['y'])} {int(box['width'])}x{int(box['height'])}"
            return "no iframe box"

        print("click:", await try_click())
        end = time.monotonic() + 75
        while time.monotonic() < end:
            title = await page.title()
            widget = await page.evaluate("() => !!document.querySelector('gep-container-store-availability')")
            if widget and "Just a moment" not in title:
                print("RESOLVED")
                await browser.close()
                return
            await asyncio.sleep(3)
        print("still challenged after 75s; title=%r" % (await page.title(),))
        await browser.close()


asyncio.run(main())
