import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        page.on("console", lambda msg: print(f"CONSOLE {msg.type}: {msg.text}"))
        page.on("pageerror", lambda err: print(f"ERROR: {err}"))
        
        await page.goto("http://localhost:8000/")
        await asyncio.sleep(1) 
        
        # Type in description
        await page.fill("#input-desc", "test description")
        await asyncio.sleep(0.5)
        
        # Click the button
        print("Clicking button...")
        await page.click("#btn-start")
        
        await asyncio.sleep(2)
        print("Done.")
        
        await browser.close()

asyncio.run(main())
