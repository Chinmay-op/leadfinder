from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    page.goto("http://localhost:8000/")
    
    # Inject a lead into the state to make it appear in Done
    page.evaluate("""
        const mockLead = {
            company_name: "Super Long Company Name That Might Be Cut Off Or Invisible Ltd.",
            fit_score: 95,
            icebreaker: "Hi John, I saw your recent post about AI. It's really cool!",
            status: "pending"
        };
        state.leads.set('mock', mockLead);
        renderAllLeads();
    """)
    
    # Wait for the card to render
    page.wait_for_selector("#body-done .lead-card")
    
    # Take a screenshot
    page.screenshot(path="d:/leadOs/screenshot.png")
    
    browser.close()
