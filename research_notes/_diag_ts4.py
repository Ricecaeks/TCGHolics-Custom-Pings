import asyncio, sys, time
sys.path.insert(0, ".")

SEL = 'iframe[src*="challenges.cloudflare.com"]'


async def main():
    from patchright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, channel="chrome")
        ctx = await browser.new_context(locale="en-NZ", timezone_id="Pacific/Auckland")
        page = await ctx.new_page()
        await page.goto("https://www.thewarehouse.co.nz/p/x/R3098657.html", wait_until="domcontentloaded", timeout=60_000)

        async def click_turnstile():
            try:
                await page.wait_for_selector(SEL, state="visible", timeout=30_000)
            except Exception as e:
                return f"no visible turnstile iframe: {e}"
            box = None
            for _ in range(5):  # bounding box can be null until layout settles
                box = await page.locator(SEL).first.bounding_box()
                if box:
                    break
                await asyncio.sleep(1)
            if not box:
                return "no bounding box"
            await page.mouse.click(box["x"] + 30, box["y"] + box["height"] / 2)
            return f"clicked at {int(box['x'])+30},{int(box['y']+box['height']/2)} (box {int(box['width'])}x{int(box['height'])})"

        print("click:", await click_turnstile())
        end = time.monotonic() + 60
        while time.monotonic() < end:
            title = await page.title()
            widget = await page.evaluate("() => !!document.querySelector('gep-container-store-availability')")
            if widget and "Just a moment" not in title:
                print("RESOLVED")
                await browser.close()
                return
            await asyncio.sleep(3)
        print("still challenged after 60s; title=%r" % (await page.title(),))
        await browser.close()


asyncio.run(main())
