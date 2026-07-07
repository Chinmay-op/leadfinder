import csv
import sys
import time
import requests
import re
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup

# Headers to prevent blocking
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Regex patterns
EMAIL_PATTERN = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')
# Basic phone pattern: looks for + followed by digits/spaces/dashes, or (123) 456-7890
PHONE_PATTERN = re.compile(r'(?:\+?\d{1,3}[\s-]?)?\(?\d{2,4}\)?[\s-]?\d{3,4}[\s-]?\d{3,4}')

def extract_contacts_from_html(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    # Remove script and style elements
    for script in soup(["script", "style"]):
        script.extract()
    text = soup.get_text(separator=" ")
    
    # Find all emails
    raw_emails = EMAIL_PATTERN.findall(text)
    # Filter out fake emails like example@domain or .png extensions
    emails = []
    for e in raw_emails:
        if "example" not in e.lower() and not e.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
            emails.append(e)
            
    # Find all phones
    raw_phones = PHONE_PATTERN.findall(text)
    phones = [p.strip() for p in raw_phones if len(re.sub(r'\D', '', p)) >= 10]
    
    # Return all found
    return {
        "emails": emails,
        "phones": phones
    }

import asyncio
from playwright.async_api import async_playwright

async def scrape_company_website(context, website: str, progress=None) -> dict:
    if progress is None:
        progress = print
    if not website or " " in website or "." not in website:
        return {}
        
    if not website.startswith("http"):
        website = "http://" + website
        
    try:
        page = await context.new_page()
        # Visit Homepage
        await page.goto(website, wait_until="domcontentloaded", timeout=8000)
        await asyncio.sleep(0.2) # Allow slight render time
        html = await page.content()
        contacts = extract_contacts_from_html(html)
        
        # If no emails found, try to find a Contact page and scrape that
        if not contacts["emails"] or not contacts["phones"]:
            soup = BeautifulSoup(html, "html.parser")
            contact_link = None
            for a in soup.find_all("a", href=True):
                if "contact" in a.text.lower() or "contact" in a["href"].lower():
                    contact_link = urljoin(website, a["href"])
                    break
                    
            if contact_link:
                try:
                    await page.goto(contact_link, wait_until="domcontentloaded", timeout=8000)
                    await asyncio.sleep(0.2)
                    c_html = await page.content()
                    c_contacts = extract_contacts_from_html(c_html)
                    if not contacts["emails"]: contacts["emails"] = c_contacts["emails"]
                    if not contacts["phones"]: contacts["phones"] = c_contacts["phones"]
                except Exception:
                    pass
                    
        await page.close()
        return contacts
    except Exception as e:
        progress(f"Error scraping {website}: {e}")
        return {}

import os

async def run_enrichment(progress=None, session_id=None):
    if progress is None:
        progress = print
    try:
        # Always read from businesses_data.csv — it contains only the current session's data
        input_file = "businesses_data.csv"
        with open(input_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
    except FileNotFoundError:
        progress("businesses_data.csv not found. Please run main.py first.")
        return

    enriched_rows = []
    progress(f"Loaded {len(rows)} companies. Starting custom web scraping for contacts using Playwright...")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        
        target_rows = []
        other_rows = []
        for row in rows:
            if session_id and row.get("session_id") != session_id:
                other_rows.append(row)
            else:
                target_rows.append(row)
                
        progress(f"Loaded {len(target_rows)} companies to scrape (from {len(rows)} total).")
        
        sem = asyncio.Semaphore(5)
        
        async def process_row(i, row):
            if "contacts" not in row:
                row["contacts"] = "[]"
                
            website = row.get("website", "")
            if not website:
                enriched_rows.append(row)
                return
                
            async with sem:
                progress(f"[{i+1}/{len(rows)}] Scraping: {row.get('company_name')} ({website})...")
                contacts = await scrape_company_website(context, website, progress=progress)
                
                emails_found = list(dict.fromkeys(contacts.get("emails", [])))
                phones_found = list(dict.fromkeys(contacts.get("phones", [])))
                
                if emails_found:
                    row["email"] = emails_found[0]
                if phones_found:
                    row["phone"] = phones_found[0]
                    
                try:
                    import json
                    existing_contacts = json.loads(row.get("contacts", "[]")) if row.get("contacts") else []
                except:
                    existing_contacts = []
                    
                max_len = max(len(emails_found), len(phones_found))
                new_contacts = []
                for j in range(max_len):
                    e = emails_found[j] if j < len(emails_found) else ""
                    p = phones_found[j] if j < len(phones_found) else ""
                    if e or p:
                        new_contacts.append({
                            "first_name": "",
                            "last_name": "",
                            "full_name": "",
                            "title": "Website Contact",
                            "seniority": "Unknown",
                            "email": e,
                            "email_confidence": 0.5 if e else None,
                            "email_source": "website_scrape" if e else None,
                            "phone": p
                        })
                
                existing_contacts.extend(new_contacts)
                row["contacts"] = json.dumps(existing_contacts)
                    
                enriched_rows.append(row)

        tasks = [process_row(i, row) for i, row in enumerate(target_rows)]
        if tasks:
            await asyncio.gather(*tasks)
            
        await browser.close()
        
    if enriched_rows or other_rows:
        # Combine them back
        final_rows = other_rows + enriched_rows
        all_keys = []
        for r in final_rows:
            for k in r.keys():
                if k not in all_keys:
                    all_keys.append(k)
        
        with open("businesses_data.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=all_keys)
            writer.writeheader()
            writer.writerows(final_rows)
        progress(f"Saved {len(enriched_rows)} enriched companies to businesses_data.csv")

if __name__ == "__main__":
    asyncio.run(run_enrichment())
