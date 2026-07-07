"""
IceBreaker Generator — AI-powered cold outreach opener
Scrapes company websites and uses AI to generate personalized icebreakers.
"""
from __future__ import annotations

import csv
import re
import requests
from bs4 import BeautifulSoup

from models.business import Business

# Constants
MIN_CONTENT_LENGTH = 100
MAX_CONTENT_LENGTH = 1500

# Reuse the same browser headers as enrich.py
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def _default_progress(msg: str):
    """Default progress callback — prints to terminal."""
    print(msg)


import asyncio
from playwright.async_api import async_playwright

async def scrape_website_for_icebreaker(context, website: str) -> str | None:
    """Scrape a company website and return cleaned text suitable for icebreaker generation.

    Args:
        context: Playwright BrowserContext
        website: Full URL of the company website.

    Returns:
        Cleaned text string, or None if scraping fails or content is too short.
    """
    if not website.startswith("http"):
        website = "http://" + website

    try:
        page = await context.new_page()
        await page.goto(website, wait_until="domcontentloaded", timeout=15000)
        await asyncio.sleep(1)
        html = await page.content()
        await page.close()

        soup = BeautifulSoup(html, "html.parser")

        # Remove non-content elements
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()

        text = soup.get_text(separator=" ", strip=True)
        text = re.sub(r'\s+', ' ', text)
        text = text[:MAX_CONTENT_LENGTH]

        if len(text) < MIN_CONTENT_LENGTH:
            return None

        return text

    except Exception:
        return None


def generate_icebreaker(
    company_name: str,
    website_text: str,
    contact_title: str = "",
    pain_points: list[str] = None,
    progress=None
) -> str | None:
    """Generate a personalized cold outreach icebreaker using AI."""
    if progress is None:
        progress = _default_progress
        
    if pain_points is None:
        pain_points = []

    try:
        from main import generate_with_retry

        prompt = (
            f"Company: {company_name}\n"
            f"Contact's role: {contact_title}\n"
            f"Their likely pain points: {', '.join(pain_points)}\n\n"
            f"Website content:\n{website_text}\n\n"
            f"Write a personalized B2B cold outreach icebreaker "
            f"addressed to someone in the role of \"{contact_title}\" "
            f"(2-3 sentences, 40-60 words, professional but conversational). "
            f"Reference something specific about this company and connect it "
            f"to a likely pain point for their role. End with a curiosity hook. "
            f"Return ONLY the icebreaker text."
        )

        result = generate_with_retry(prompt, progress)

        if result and 10 < len(result.strip()) < 500:
            return result.strip()

        return None

    except Exception as e:
        progress(f"Error generating icebreaker for {company_name}: {e}")
        return None


def run_icebreaker_generation(state) -> None:
    """Thread-safe wrapper that generates icebreakers for all leads with websites."""
    state.progress("IceBreaker generation started...")
    
    from icp import load_cached_icp
    icp = load_cached_icp()
    pain_points = icp.pain_points if icp else []

    # Read CSV
    rows = []
    source_file = "enriched_leads.csv"
    try:
        with open(source_file, "r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    except FileNotFoundError:
        source_file = "businesses_data.csv"
        try:
            with open(source_file, "r", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
        except FileNotFoundError:
            state.progress("No CSV files found. Please run scraping first.")
            return

    import json
    leads: list[Business] = []
    for row in rows:
        try:
            if 'contacts' in row and isinstance(row['contacts'], str) and row['contacts']:
                try:
                    row['contacts'] = json.loads(row['contacts'])
                except:
                    row['contacts'] = []
            leads.append(Business(**{k: v for k, v in row.items() if k in Business.model_fields}))
        except Exception:
            pass

    generated = 0
    eligible = 0

    for lead in leads:
        if not lead.website or not lead.contacts:
            continue

        text = scrape_website_for_icebreaker(lead.website)
        if not text:
            continue

        for contact in lead.contacts:
            eligible += 1
            icebreaker = generate_icebreaker(
                lead.company_name, 
                text, 
                contact_title=contact.title,
                pain_points=pain_points,
                progress=state.progress
            )
            if icebreaker:
                contact.icebreaker = icebreaker
                generated += 1
            state.progress(f"IceBreaker [{generated}/{eligible}]: {contact.full_name} at {lead.company_name}")

    # Write updated leads back to enriched_leads.csv
    if leads:
        keys = list(leads[0].model_dump().keys())
        with open("enriched_leads.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
            writer.writeheader()
            for lead in leads:
                d = lead.model_dump()
                d['contacts'] = json.dumps([c.model_dump() for c in d['contacts']])
                writer.writerow({k: (v if v is not None else "") for k, v in d.items()})

    state.progress(f"IceBreaker complete: {generated}/{eligible} generated")
