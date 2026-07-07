import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        print("Navigating to Google...")
        await page.goto("https://www.google.com/search?q=solar+company+site:linkedin.com/company", wait_until="domcontentloaded")
        await asyncio.sleep(2)
        html = await page.content()
        print(f"HTML length: {len(html)}")
        if "id=\"search\"" in html or "id='search'" in html:
            print("Found '#search' in HTML!")
        else:
            print("NO '#search' found!")
        await browser.close()

asyncio.run(run())
