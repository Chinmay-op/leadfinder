import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        page.on('console', lambda msg: print('CONSOLE:', msg.type, msg.text))
        page.on('pageerror', lambda exc: print('PAGE_ERROR:', exc))
        await page.goto('http://localhost:8000/')
        await page.fill('#input-desc', 'test')
        await page.click('#btn-start')
        await asyncio.sleep(2)
        await browser.close()
asyncio.run(main())
