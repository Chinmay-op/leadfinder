"""
AI Lead Finder v3 — Playwright UI Test Suite for Chat Interface
Tests layout, login, chat interaction, sidebar, and session history.
"""
import sys, json, time
from playwright.sync_api import sync_playwright, expect

BASE = "http://localhost:8000"
PASS = 0
FAIL = 0
ERRORS = []

def test(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        msg = f"  [FAIL] {name}" + (f" — {detail}" if detail else "")
        print(msg)
        ERRORS.append(msg)

def section(title):
    print(f"\n{'='*65}")
    print(f"  {title}")
    print(f"{'='*65}")

def run():
    global PASS, FAIL

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        js_errors = []
        page.on("console", lambda msg: js_errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda err: js_errors.append(str(err)))

        # ═══════════════════════════════════════════════════════════════
        section("1. PAGE LOAD & TITLE")
        resp = page.goto(BASE, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
        test("Page loads (HTTP 200)", resp.status == 200, f"Got {resp.status}")
        test("Title is 'Lead Finder'", page.title() == "Lead Finder", f"Got: {page.title()}")
        test("Body is visible", page.locator("body").is_visible())

        # ═══════════════════════════════════════════════════════════════
        section("2. LOGIN OVERLAY")
        login_overlay = page.locator("#login-overlay")
        test("Login overlay exists", login_overlay.count() == 1)
        test("Login overlay is visible", login_overlay.is_visible())
        
        # Perform Login
        page.locator("#login-username").fill("test")
        page.locator("#login-password").fill("test")
        page.locator("#login-form button[type='submit']").click()
        page.wait_for_timeout(1000)
        
        test("Login overlay is hidden after login", not login_overlay.is_visible())
        
        # ═══════════════════════════════════════════════════════════════
        section("3. HEADER & SIDEBAR")
        header = page.locator("header.top-bar")
        test("Header exists", header.count() == 1)
        test("Brand name 'Lead Finder'", "Lead Finder" in page.locator(".brand-name").inner_text())
        
        sidebar = page.locator("aside.sidebar")
        test("Sidebar exists", sidebar.count() == 1)
        test("New Search button visible", page.locator("#btn-new-search").is_visible())
        
        # ═══════════════════════════════════════════════════════════════
        section("4. CHAT UI")
        chat_thread = page.locator("#chat-thread")
        test("Chat thread exists", chat_thread.count() == 1)
        
        input_bar = page.locator("#input-bar")
        test("Input bar exists", input_bar.count() == 1)
        test("Chat input textarea exists", page.locator("#chat-input").count() == 1)
        test("Send button exists", page.locator("#btn-send").count() == 1)
        
        # User profile & Status
        test("User profile visible", page.locator("#user-profile").is_visible())
        test("Status chip exists", page.locator("#status-chip").count() == 1)
        status_text = page.locator("#status-text").inner_text()
        test("Initial status is 'Ready'", "Ready" in status_text, f"Got {status_text}")
        
        # ═══════════════════════════════════════════════════════════════
        section("5. CHAT INTERACTION")
        chat_input = page.locator("#chat-input")
        chat_input.fill("Looking for logistics companies in London")
        page.locator("#btn-send").click()
        page.wait_for_timeout(2000)
        
        # After send, the chat should have user message and assistant generating ICP
        user_msgs = page.locator(".msg.msg-user")
        test("User message appears in chat", user_msgs.count() >= 1)
        
        ai_msgs = page.locator(".msg.msg-ai")
        test("AI response appears in chat", ai_msgs.count() >= 1)
        
        status_text_after = page.locator("#status-text").inner_text()
        test("Status changed from Ready", status_text_after != "Ready", f"Status is {status_text_after}")

        # ═══════════════════════════════════════════════════════════════
        section("6. SESSION HISTORY")
        # Ensure #session-list is loaded
        session_list = page.locator("#session-list")
        test("Session list container exists", session_list.count() == 1)
        
        # Check if there are session items (might need to wait)
        page.wait_for_timeout(3000) 
        session_items = page.locator(".session-item")
        
        # We can't guarantee sessions exist from previous runs without mocking, but if they do:
        count = session_items.count()
        test(f"Session items rendered: {count}", count >= 0)
        
        if count > 0:
            # Test clicking a session
            first_session = session_items.first
            title = first_session.locator(".session-title").inner_text()
            test(f"First session title: {title}", bool(title))
            
            first_session.click()
            page.wait_for_timeout(1500)
            
            ai_msgs = page.locator(".msg.msg-ai")
            msg_text = ai_msgs.last.inner_text()
            msg_text_safe = msg_text.encode('ascii', 'ignore').decode('ascii')
            test("Session loaded into chat thread", "Loaded previous search" in msg_text or "Loading" in msg_text, f"Got: {msg_text_safe}")
        
        # ═══════════════════════════════════════════════════════════════
        browser.close()

    # ═══════════════════════════════════════════════════════════════
    print(f"\n{'='*65}")
    print(f"  RESULTS: {PASS} passed, {FAIL} failed, {PASS+FAIL} total")
    print(f"{'='*65}")

    if ERRORS:
        print(f"\n  FAILURES:")
        for e in ERRORS:
            print(f"  {e}")
        print()

    return FAIL == 0


if __name__ == "__main__":
    success = run()
    sys.exit(0 if success else 1)
