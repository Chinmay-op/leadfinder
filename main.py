import sys
import json
import csv
import time
import random
import asyncio
import uuid
import urllib.parse
from bs4 import BeautifulSoup

from openai import OpenAI
import os
from playwright.async_api import async_playwright
from config import (
    MAX_COMPANIES, DELAY_BETWEEN_AI_CALLS,
    KEYWORD_EXTRACTION_PROMPT, SCORING_PROMPT,
    AZURE_OPENAI_KEY, AZURE_OPENAI_ENDPOINT
)
from models.business import Business

# Default progress callback — just prints to terminal
def _default_progress(msg: str):
    print(msg)

azure_client = OpenAI(
    base_url=AZURE_OPENAI_ENDPOINT,
    api_key=AZURE_OPENAI_KEY,
    timeout=30.0
)
AZURE_MODEL = "gpt-5-chat"

def clean_json_response(text: str) -> str:
    if not text:
        return "[]"
    
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    
    try:
        json.loads(text)
        return text
    except:
        pass

    # Try finding outermost {}
    start_brace = text.find('{')
    end_brace = text.rfind('}')
    
    # Try finding outermost []
    start_bracket = text.find('[')
    end_bracket = text.rfind(']')
    
    # If both exist, pick the outermost
    if start_brace != -1 and end_brace != -1 and start_bracket != -1 and end_bracket != -1:
        if start_brace < start_bracket and end_brace > end_bracket:
            return text[start_brace:end_brace+1]
        elif start_bracket < start_brace and end_bracket > end_brace:
            return text[start_bracket:end_bracket+1]
            
    if start_brace != -1 and end_brace != -1 and start_brace < end_brace:
        return text[start_brace:end_brace+1]
        
    if start_bracket != -1 and end_bracket != -1 and start_bracket < end_bracket:
        return text[start_bracket:end_bracket+1]
        
    return text

def generate_with_retry(prompt: str, progress=None) -> str:
    if progress is None:
        progress = _default_progress
    max_retries = 3
    for attempt in range(max_retries):
        if azure_client:
            try:
                response = azure_client.chat.completions.create(
                    model=AZURE_MODEL,
                    messages=[{"role": "user", "content": prompt}]
                )
                progress("[API] Azure OpenAI success")
                return response.choices[0].message.content
            except Exception as e:
                progress(f"[API] Azure OpenAI error: {e}")
                
        # If it fails, wait and retry
        wait_time = 15 * (attempt + 1)
        progress(f"API hit limits or failed. Waiting {wait_time}s before retrying...")
        time.sleep(wait_time)
        
    return ""

def get_keywords(description: str, progress=None) -> list[str]:
    if progress is None:
        progress = _default_progress
    progress("Extracting keywords using AI...")
    prompt = KEYWORD_EXTRACTION_PROMPT.format(description=description)
    try:
        text = generate_with_retry(prompt, progress=progress)
        if not text:
            return []
        data = json.loads(clean_json_response(text))
        if isinstance(data, list):
            return data
        elif isinstance(data, dict):
            return data.get("keywords", [])
        return []
    except Exception as e:
        progress(f"Error parsing keywords: {e}")
        return []

def extract_companies_from_ddg(html: str, progress=None) -> list[dict]:
    if progress is None:
        progress = _default_progress
    # Parse HTML to reduce payload size to AI
    soup = BeautifulSoup(html, "html.parser")
    results = soup.select(".algo-sr, .compTitle, .algo")
    
    snippets = []
    for r in results:
        text = r.get_text(" ", strip=True)
        link = r.select_one("a")
        href = link.get("href") if link else "No URL"
        snippets.append(f"Text: {text} | URL: {href}")
    
    clean_text = "\n".join(snippets)
    
    # Use config prompt and format it
    from config import SCRAPING_PROMPT
    prompt = SCRAPING_PROMPT.format(html=clean_text)
    
    progress("Extracting companies from search snippets...")
    text = generate_with_retry(prompt, progress=progress)
    if not text:
        return []
        
    try:
        companies = json.loads(clean_json_response(text))
        if isinstance(companies, list):
            return companies
        return []
    except Exception as e:
        progress(f"Error parsing extraction JSON: {e}")
        progress(f"Raw AI Response: {text}")
        return []

def score_company(company_info: dict, description: str = "", progress=None) -> tuple[int, str]:
    if progress is None:
        progress = _default_progress
    prompt = SCORING_PROMPT.format(description=description, company_info=json.dumps(company_info))
    try:
        time.sleep(DELAY_BETWEEN_AI_CALLS)
        text = generate_with_retry(prompt, progress=progress)
        if not text:
            return 0, ""
        data = json.loads(clean_json_response(text))
        return data.get("fit_score", 0), data.get("fit_reason", "")
    except Exception as e:
        progress(f"Error scoring company: {e}")
        return 0, ""

async def scrape_duckduckgo(context, keyword: str, seen_companies: set, description: str = "", session_id: str = None, progress=None, limit: int = None, on_company_found=None) -> list[Business]:
    if progress is None:
        progress = _default_progress
    businesses = []
    
    url = f"https://search.yahoo.com/search?p={urllib.parse.quote(keyword)}+site:linkedin.com/company"
    msg = f"Scraping Yahoo Search for keyword: {keyword}...\nURL: {url}"
    progress(msg)
    print(msg)
    
    try:
        await asyncio.sleep(random.uniform(2, 4))
        
        # Robust retry logic for network flakes
        html = None
        max_retries = 3
        for attempt in range(max_retries):
            page = None
            try:
                page = await context.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                try:
                    await page.wait_for_selector(".algo-sr, .compTitle, .algo", timeout=10000)
                except Exception:
                    pass # might not be results
                
                await asyncio.sleep(2.0)
                html = await page.content()
                await page.close()
                break # Success, break out of retry loop
            except Exception as e:
                err_msg = str(e)
                progress(f"Network error (attempt {attempt+1}/{max_retries}). Retrying in 5s... ({err_msg})")
                if page:
                    try:
                        await page.close()
                    except Exception:
                        pass
                await asyncio.sleep(5)
        
        if not html:
            progress("Failed to fetch page. No HTML returned.")
            return businesses
            
        raw_companies = extract_companies_from_ddg(html, progress=progress)
        
        for c_data in raw_companies:
            if limit is not None and len(businesses) >= limit:
                break
            c_name = c_data.get("company_name", "")
            if not c_name or c_name.lower() in seen_companies:
                continue
                
            seen_companies.add(c_name.lower())
            progress(f"Found: {c_name}. Scoring...")
            score, reason = score_company(c_data, description, progress=progress)
            c_data["fit_score"] = score
            c_data["fit_reason"] = reason
            if session_id:
                c_data["session_id"] = session_id
            
            try:
                business = Business(**c_data)
                businesses.append(business)
                if on_company_found:
                    on_company_found(business)
            except Exception as e:
                progress(f"Error mapping to Business model: {e}")
    except Exception as e:
        progress(f"Error scraping DuckDuckGo: {e}")
            
    return businesses



async def run_main(keywords: list[str], description: str = "", session_id: str = None, progress=None, test_mode: bool = False, on_company_found=None) -> list[Business]:
    if progress is None:
        progress = _default_progress

    # Each run is isolated — start fresh with a unique session_id
    if not session_id:
        session_id = str(uuid.uuid4())
    all_businesses = []
    seen_companies: set = set()
    
    progress(f"Starting fresh search (session: {session_id[:8]}…)")
    
    max_companies_limit = 5 if test_mode else MAX_COMPANIES
    
    # We create 3 variations of each keyword to get ~30 companies total
    # In test mode, skip expansion to avoid unnecessary requests for just 5 results
    if test_mode:
        expanded_keywords = keywords[:2]  # Only use first 2 keywords, no variations
    else:
        expanded_keywords = []
        for kw in keywords:
            expanded_keywords.append(f"{kw}")
            expanded_keywords.append(f"{kw} software")
            expanded_keywords.append(f"{kw} services")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        for kw in expanded_keywords:
            remaining = max_companies_limit - len(all_businesses)
            if remaining <= 0:
                break
            results = await scrape_duckduckgo(context, kw, seen_companies, description, session_id=session_id, progress=progress, limit=remaining, on_company_found=on_company_found)
            all_businesses.extend(results)
        await browser.close()
        
    # Truncate to limit
    all_businesses = all_businesses[:max_companies_limit]
    
    # We no longer save to CSV; we just return the businesses for the in-memory pipeline.
    if not all_businesses:
        progress("No companies found.")
    else:
        progress(f"Found {len(all_businesses)} companies.")
        
    return all_businesses

if __name__ == "__main__":
    if len(sys.argv) > 1:
        keyword = " ".join(sys.argv[1:])
        print(f"Using direct keyword: {keyword}")
        keywords = [keyword]
    else:
        print("Mode A: Enter a description of your AI services to generate keywords.")
        desc = input("Description: ")
        if not desc.strip():
            desc = "We provide custom AI agent development and workflow automation for mid-size companies."
        keywords = get_keywords(desc)
        print(f"Generated keywords: {keywords}")
        
    asyncio.run(run_main(keywords, desc if 'desc' in locals() else ""))
