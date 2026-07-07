import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        
        # Capture console logs to find JS errors
        page.on("console", lambda msg: print(f"CONSOLE [{msg.type}]: {msg.text}"))
        page.on("pageerror", lambda err: print(f"PAGE ERROR: {err}"))
        
        await page.goto("http://localhost:8000")
        
        # Login
        print("Logging in...")
        await page.fill("#login-username", "admin")
        await page.fill("#login-password", "admin123")
        await page.click("button[type='submit']")
        await page.wait_for_selector("#session-list .session-item", timeout=5000)
        
        # Click the first session
        print("Clicking first session...")
        await page.click("#session-list .session-item:first-child")
        
        # Wait for "View Leads" button
        print("Waiting for View Leads button...")
        await page.wait_for_selector("button:has-text('View Leads')", timeout=5000)
        
        # Click View Leads
        print("Clicking View Leads...")
        await page.click("button:has-text('View Leads')")
        
        # Wait a bit to see if leads render or error happens
        await asyncio.sleep(2)
        
        # Check if leads rendered
        cards = await page.locator(".company-card").count()
        print(f"Company cards rendered: {cards}")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run())
