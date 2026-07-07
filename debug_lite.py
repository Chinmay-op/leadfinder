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
        print("Navigating to DDG Lite...")
        keyword = urllib.parse.quote("solar company site:linkedin.com/company")
        await page.goto("https://lite.duckduckgo.com/lite/", wait_until="domcontentloaded")
        await page.fill("input[name='q']", "solar company site:linkedin.com/company")
        await page.click("input[type='submit']")
        await asyncio.sleep(2)
        html = await page.content()
        print(f"HTML length: {len(html)}")
        if "result-snippet" in html or "result-url" in html:
            print("Found result snippets!")
        else:
            print("NO result snippets found!")
            print(html[:1000])
        await browser.close()

asyncio.run(run())
