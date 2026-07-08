import asyncio
from urllib.parse import quote_plus

from playwright.async_api import async_playwright


async def main():
    q = quote_plus("manufacturing company Houston TX")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(
            f"https://www.bing.com/search?q={q}",
            wait_until="networkidle",
            timeout=60000,
        )
        print("bing title:", await page.title())
        html = await page.content()
        print("has b_algo:", "b_algo" in html)
        print("has captcha:", "captcha" in html.lower())

        await page.goto(
            "https://www.google.com/maps/search/manufacturing+company+Houston+TX",
            wait_until="domcontentloaded",
            timeout=60000,
        )
        await page.wait_for_timeout(5000)
        print("maps title:", await page.title())
        print("feed count:", await page.locator('[role="feed"]').count())
        links = await page.locator('a[href*="maps/place"]').all()
        print("place links:", len(links))
        for link in links[:8]:
            print("-", await link.get_attribute("aria-label"))
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
