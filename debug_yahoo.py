import asyncio
from playwright.async_api import async_playwright
import urllib.parse

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        print("Navigating to Yahoo...")
        url = f"https://search.yahoo.com/search?p={urllib.parse.quote('solar company site:linkedin.com/company')}"
        await page.goto(url, wait_until="domcontentloaded")
        await asyncio.sleep(2)
        html = await page.content()
        print(f"HTML length: {len(html)}")
        if "algo-sr" in html or "compTitle" in html:
            print("Found Yahoo result snippets!")
        else:
            print("NO result snippets found!")
            print(html[:1000])
        await browser.close()

asyncio.run(run())
