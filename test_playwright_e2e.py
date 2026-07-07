import asyncio
from playwright.async_api import async_playwright

async def run_test():
    print("Starting Playwright E2E Test...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        print("Navigating to http://localhost:8000/")
        await page.goto("http://localhost:8000/")
        
        # Make sure we're on the Yahoo/LinkedIn source
        await page.click('button[data-source="yahoo_linkedin"]')
        
        # Fill in the description
        await page.fill('#input-desc', 'AI services in New York')
        
        # Ensure toggles are ON (by default they have class "toggle-switch on", but let's just run it)
        print("Clicking Start Pipeline...")
        await page.click('#btn-start')
        
        print("Pipeline started. Waiting for leads to appear in Done or Failed columns (timeout 90s)...")
        try:
            # Wait until at least 1 lead is done or failed
            await page.wait_for_function(
                "() => { const d = parseInt(document.getElementById('count-done').innerText); const f = parseInt(document.getElementById('count-failed').innerText); return d > 0 || f > 0; }",
                timeout=90000
            )
            print("Pipeline completed processing at least some leads.")
            
            # Let's wait a bit more for pipeline to finish completely, or just check the current state
            await asyncio.sleep(5)
            
            done_count = await page.locator('#count-done').inner_text()
            failed_count = await page.locator('#count-failed').inner_text()
            print(f"Done leads: {done_count}")
            print(f"Failed leads: {failed_count}")
            
            done_cards = await page.locator('#body-done .lead-card').all()
            for i, card in enumerate(done_cards):
                text = await card.inner_text()
                print(f"--- Done Card {i+1} ---")
                print(text)
                
            print("Test Complete.")
        except Exception as e:
            print(f"Error during test: {e}")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run_test())
