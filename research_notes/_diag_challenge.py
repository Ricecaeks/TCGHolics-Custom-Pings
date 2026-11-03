import asyncio, sys, time
sys.path.insert(0, ".")


async def main():
    from patchright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=False, channel="chrome",
            args=["--disable-dev-shm-usage", "--no-first-run"],
        )
        ctx = await browser.new_context(
            locale="en-NZ", timezone_id="Pacific/Auckland",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36",
        )
        page = await ctx.new_page()
        url = "https://www.thewarehouse.co.nz/p/x/R3098657.html"
        print("navigating...")
        await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        end = time.monotonic() + 90
        resolved = False
        while time.monotonic() < end:
            title = await page.title()
            widget = await page.evaluate("() => !!document.querySelector('gep-container-store-availability')")
            print(f"t={int(90-(end-time.monotonic())):3d}s  title={title!r}  widget={widget}")
            if widget and "Just a moment" not in title:
                resolved = True
                break
            await asyncio.sleep(3)
        print("RESOLVED" if resolved else "STILL CHALLENGED after 90s")
        await browser.close()


asyncio.run(main())
