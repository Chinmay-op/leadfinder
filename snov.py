import requests
import time
import csv
import random
from typing import Optional, Tuple
from config import SNOV_USER_ID, SNOV_SECRET
from models.business import Business
from models.contact import Contact
from models.icp import ICP

def _default_progress(msg: str):
    print(msg)

class SnovClient:
    def __init__(self, progress=None):
        self.progress = progress or _default_progress
        self.access_token = None
        self.token_expiry = 0
        self.limit_reached = False

    def get_access_token(self) -> str | None:
        """Fetch and cache Snov.io OAuth token."""
        if not SNOV_USER_ID or not SNOV_SECRET:
            raise ValueError("Snov.io API keys not configured. Please add SNOV_USER_ID and SNOV_SECRET to .env")

        if self.access_token and time.time() < self.token_expiry:
            return self.access_token

        try:
            response = requests.post(
                "https://api.snov.io/v1/oauth/access_token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": SNOV_USER_ID,
                    "client_secret": SNOV_SECRET
                },
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            self.access_token = data.get("access_token")
            # Cache for 3500 seconds (expires in 3600)
            self.token_expiry = time.time() + 3500
            return self.access_token
        except Exception as e:
            raise ValueError(f"Failed to authenticate with Snov.io: {e}")

    def find_prospects_by_domain(self, domain: str, target_roles: list[str]) -> list[Contact]:
        """Use Domain Search Prospects API to find contacts matching roles."""
        if self.limit_reached:
            return []

        token = self.get_access_token()
        if not token:
            return []

        # 1. Start the search
        try:
            start_resp = requests.post(
                "https://api.snov.io/v2/domain-search/prospects/start",
                headers={"Authorization": f"Bearer {token}"},
                json={"domain": domain, "positions": target_roles},
                timeout=15
            )
            start_resp.raise_for_status()
            task_hash = start_resp.json().get("task_hash")
        except requests.exceptions.HTTPError as e:
            if getattr(e.response, "status_code", None) == 402:
                self.limit_reached = True
                self.progress("Snov.io API limit reached (402 Payment Required). Stopping Snov.io prospect search.")
                return []
            self.progress(f"Snov.io prospects start error for {domain}: {e}")
            return []
        except Exception as e:
            if "402" in str(e):
                self.limit_reached = True
                self.progress("Snov.io API limit reached (402 Payment Required). Stopping Snov.io prospect search.")
                return []
            self.progress(f"Snov.io prospects start error for {domain}: {e}")
            return []

        if not task_hash:
            return []

        # 2. Poll for results
        max_retries = 5
        for attempt in range(max_retries):
            time.sleep(2) # Wait for processing
            try:
                res_resp = requests.get(
                    f"https://api.snov.io/v2/domain-search/prospects/result/{task_hash}",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=15
                )
                if res_resp.status_code == 200:
                    data = res_resp.json()
                    if data.get("status") == "completed":
                        return self._parse_prospects(data.get("result", []))
                    if data.get("status") == "not_found":
                        return []
            except Exception as e:
                self.progress(f"Snov.io prospects poll error: {e}")
                
        return []

    def _parse_prospects(self, results: list[dict]) -> list[Contact]:
        contacts = []
        for p in results:
            first = p.get("first_name", "")
            last = p.get("last_name", "")
            title = p.get("position", "")
            email = p.get("email", None)
            
            # Infer seniority
            t_lower = title.lower()
            seniority = "Individual"
            if any(x in t_lower for x in ["chief", "ceo", "cto", "cfo", "coo", "cmo"]):
                seniority = "C-Level"
            elif any(x in t_lower for x in ["vp", "vice president"]):
                seniority = "VP"
            elif any(x in t_lower for x in ["director", "head of"]):
                seniority = "Director"
            elif "manager" in t_lower:
                seniority = "Manager"

            c = Contact(
                first_name=first,
                last_name=last,
                full_name=f"{first} {last}".strip(),
                title=title,
                seniority=seniority,
                email=email,
                email_source="snov" if email else None,
                linkedin_url=p.get("social_links", {}).get("linkedin") or p.get("source_page")
            )
            contacts.append(c)
        return contacts

    def find_email_by_name(self, first_name: str, last_name: str, domain: str) -> tuple[str|None, float|None, str|None]:
        """Use Email Finder API to get specific person's email."""
        if self.limit_reached:
            return None, None, None

        token = self.get_access_token()
        if not token:
            return None, None, None

        try:
            start_resp = requests.post(
                "https://api.snov.io/v2/emails-by-domain-by-name/start",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/x-www-form-urlencoded"},
                data={"firstName": first_name, "lastName": last_name, "domain": domain},
                timeout=15
            )
            if start_resp.status_code == 402:
                self.limit_reached = True
                self.progress("Snov.io API limit reached (402 Payment Required). Stopping email enrichment.")
                return None, None, None
            if start_resp.status_code != 200:
                return None, None, None
            task_hash = start_resp.json().get("task_hash")
            
            if not task_hash:
                return None, None, None

            # Poll
            for _ in range(5):
                time.sleep(1.5)
                res_resp = requests.get(
                    f"https://api.snov.io/v2/emails-by-domain-by-name/result?task_hash={task_hash}",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=15
                )
                if res_resp.status_code == 200:
                    data = res_resp.json()
                    if data.get("status") == "completed" and data.get("result"):
                        res = data["result"][0]
                        return res.get("email"), 1.0 if res.get("status") == "valid" else 0.5, "snov"
        except Exception:
            pass
            
        return None, None, None

def _extract_domain(website: str) -> str:
    if not website:
        return ""
    from urllib.parse import urlparse
    if not website.startswith("http"):
        website = "http://" + website
    netloc = urlparse(website).netloc
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return netloc

async def _guess_domain_async(business, session, progress=None) -> Tuple[str, bool]:
    import re
    import urllib.parse

    if progress is None:
        progress = _default_progress

    # 1. Try the explicit website field
    domain = _extract_domain(getattr(business, 'website', '') or '')
    if domain:
        return domain, False

    # 2. Try Clearbit API for Domain Resolution
    name = getattr(business, 'company_name', '') or ''
    if name:
        progress(f"Resolving corporate domains via Clearbit for {name}...")
        
        # Sanitize name
        suffixes = [r'\binc\.?', r'\bllc\b', r'\bpvt\b', r'\bltd\.?', r'\bsoftware\b', r'\bservices\b', r'\bcorp\.?']
        cleaned = name
        for suffix in suffixes:
            cleaned = re.sub(suffix, '', cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.strip(' ,.-')
        
        if cleaned:
            try:
                # Query Clearbit
                url = f"https://autocomplete.clearbit.com/v1/companies/suggest?query={urllib.parse.quote(cleaned)}"
                async with session.get(url, timeout=5) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if isinstance(data, list) and len(data) > 0:
                            domain = data[0].get("domain")
                            if domain:
                                progress(f"  → Found domain via Clearbit: {domain}")
                                return domain, False
            except Exception as e:
                progress(f"  → Clearbit error: {e}")

    # 3. Fallback (Removed to prevent bogus domains)
    return "", False

def _guess_domain(business, progress=None) -> Tuple[str, bool]:
    """Synchronous wrapper for domain guessing."""
    import asyncio
    import aiohttp
    async def _run():
        async with aiohttp.ClientSession() as session:
            return await _guess_domain_async(business, session, progress)
    return asyncio.run(_run())

def enrich_businesses_with_contacts(businesses: list[Business], target_roles: list[str], progress=None) -> list[Business]:
    """Find prospects for each business using Snov.io."""
    if progress is None:
        progress = _default_progress
        
    # Sort businesses by fit_score descending to prioritize Snov.io credits for top leads
    businesses.sort(key=lambda b: getattr(b, 'fit_score', 0) or 0, reverse=True)
        
    snov = SnovClient(progress)
    
    import asyncio
    import aiohttp
    
    async def resolve_all():
        async with aiohttp.ClientSession() as session:
            tasks = [_guess_domain_async(b, session, progress) for b in businesses]
            return await asyncio.gather(*tasks)
            
    # Resolve domains concurrently
    if businesses:
        progress("Resolving corporate domains via Clearbit...")
        domains = asyncio.run(resolve_all())
    else:
        domains = []
    
    import concurrent.futures

    def process_business(i, b, domain, is_estimated):
        if not domain:
            progress(f"[{i+1}/{len(businesses)}] Skipping {b.company_name} — no domain found.")
            return b

        # Store the guessed domain back on the business so enrichment can use it later
        if not b.website and not is_estimated:
            b.website = domain
            
        # Only use Snov API for the top 10 scoring companies to save credits
        if i < 10:
            progress(f"[{i+1}/{len(businesses)}] Hunting for target roles on {domain} via Snov...")
            contacts = snov.find_prospects_by_domain(domain, target_roles)
        else:
            progress(f"[{i+1}/{len(businesses)}] Skipping Snov for {domain} (reserving credits).")
            contacts = []
        
        if contacts:
            progress(f"  → Found {len(contacts)} contacts via Snov.")
            b.contacts = contacts
        else:
            progress(f"  → No contacts found via Snov.")
            
        time.sleep(0.5) # rate limiting
        return b

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = []
        for i, b in enumerate(businesses):
            domain, is_estimated = domains[i] if i < len(domains) else ("", False)
            futures.append(executor.submit(process_business, i, b, domain, is_estimated))
        
        for future in concurrent.futures.as_completed(futures):
            future.result()


        
    return businesses

def run_contact_discovery(state, target_roles: list[str] = None, businesses: list[Business] = None):
    """Thread-executor wrapper to run contact discovery."""
    if target_roles is None:
        target_roles = ["CEO", "Founder", "VP", "Director", "Head", "Manager"]
    if businesses is None:
        businesses = []
        
    state.progress("Starting Snov.io Contact Discovery...")
    businesses = enrich_businesses_with_contacts(businesses, target_roles, state.progress)
    return businesses

def run_email_enrichment(state, businesses: list[Business] = None):
    """Snov.io email enrichment."""
    state.progress("Starting Email Enrichment...")
    if businesses is None:
        businesses = []

    snov = SnovClient(state.progress)
    
    import concurrent.futures
    def enrich_emails_for_business(b):
        domain, is_estimated = _guess_domain(b, state.progress)
        if not domain or not b.contacts:
            return
            
        state.progress(f"Enriching emails for {b.company_name}...")
        for c in b.contacts:
            if c.email:
                continue # Already found by prospect search
                
            # 1. Snov.io Email Finder
            state.progress(f"  → Snov.io lookup for {c.first_name} {c.last_name}")
            email, conf, source = snov.find_email_by_name(c.first_name, c.last_name, domain)
            
            if email:
                c.email = email
                c.email_confidence = conf
                c.email_source = source
                state.progress(f"  → Found email: {email} via {source}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(enrich_emails_for_business, b) for b in businesses]
        for future in concurrent.futures.as_completed(futures):
            future.result()

    return businesses
