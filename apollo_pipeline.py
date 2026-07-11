"""
Apollo.io Pipeline — Company Search + People Search via Apollo REST API

Free-tier aware: uses api_search (no credits) for discovery,
bulk_match (credits) only for final contact enrichment.

Flow:
1. organizations/search → find companies matching ICP
2. AI scoring (reuses existing scorer)
3. mixed_people/api_search → find decision-makers at top companies
4. people/bulk_match → enrich contacts with emails (credit-consuming)
"""

import requests
import time
import json
from typing import Optional
from config import (
    APOLLO_API_KEY,
    APOLLO_MAX_COMPANIES,
    APOLLO_MAX_CONTACTS_PER_COMPANY,
    DELAY_BETWEEN_AI_CALLS,
)
from models.business import Business
from models.contact import Contact
from models.icp import ICP


def _default_progress(msg: str):
    print(msg)


class ApolloClient:
    """Client for Apollo.io REST API v1."""

    BASE_URL = "https://api.apollo.io/api/v1"

    def __init__(self, progress=None):
        self.progress = progress or _default_progress
        if not APOLLO_API_KEY:
            raise ValueError("APOLLO_API_KEY not set in .env")

    def _headers(self):
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {APOLLO_API_KEY}",
        }

    def _request_with_retry(self, method: str, url: str, json_body: dict = None, max_retries: int = 3) -> Optional[dict]:
        """Make an API request with retry logic and rate limit handling."""
        for attempt in range(max_retries):
            try:
                if method == "POST":
                    resp = requests.post(url, headers=self._headers(), json=json_body, timeout=30)
                else:
                    resp = requests.get(url, headers=self._headers(), timeout=30)

                if resp.status_code == 200:
                    return resp.json()
                elif resp.status_code == 429:
                    # Rate limited — back off
                    wait_time = min(60, 10 * (attempt + 1))
                    self.progress(f"Apollo rate limit hit. Waiting {wait_time}s before retry...")
                    time.sleep(wait_time)
                    continue
                elif resp.status_code == 422:
                    self.progress(f"Apollo API validation error (422): {resp.text[:300]}")
                    return None
                elif resp.status_code == 401:
                    self.progress("Apollo API key is invalid or expired.")
                    return None
                else:
                    self.progress(f"Apollo API error {resp.status_code}: {resp.text[:300]}")
                    if attempt < max_retries - 1:
                        time.sleep(5 * (attempt + 1))
                    continue

            except requests.exceptions.Timeout:
                self.progress(f"Apollo API timeout (attempt {attempt + 1}/{max_retries})")
                time.sleep(5)
            except requests.exceptions.ConnectionError as e:
                self.progress(f"Apollo connection error: {e}")
                time.sleep(5)
            except Exception as e:
                self.progress(f"Apollo unexpected error: {e}")
                return None

        self.progress("Apollo API request failed after all retries.")
        return None

    # ── Organization Search ───────────────────────────────────────────

    def search_organizations(
        self,
        keywords: list[str],
        industries: list[str] = None,
        employee_min: int = None,
        employee_max: int = None,
        per_page: int = 25,
        max_pages: int = 2,
    ) -> list[dict]:
        """
        Search Apollo for organizations matching the given criteria.
        Returns a list of raw Apollo organization dicts.
        """
        url = f"{self.BASE_URL}/organizations/search"

        # Build employee range string (Apollo format: "min,max")
        num_employees_ranges = []
        if employee_min is not None and employee_max is not None:
            num_employees_ranges = [f"{employee_min},{employee_max}"]
        elif employee_min is not None:
            num_employees_ranges = [f"{employee_min},"]
        elif employee_max is not None:
            num_employees_ranges = [f",{employee_max}"]

        all_orgs = []
        seen_ids = set()

        for keyword in keywords:
            if len(all_orgs) >= APOLLO_MAX_COMPANIES:
                break

            for page in range(1, max_pages + 1):
                body = {
                    "q_organization_keyword_tags": [keyword],
                    "page": page,
                    "per_page": per_page,
                }

                if num_employees_ranges:
                    body["organization_num_employees_ranges"] = num_employees_ranges

                self.progress(f"Apollo org search: keyword=\"{keyword}\" page={page}...")

                data = self._request_with_retry("POST", url, body)
                if not data:
                    break

                orgs = data.get("organizations", [])
                if not orgs:
                    self.progress(f"No more organizations for \"{keyword}\" on page {page}.")
                    break

                for org in orgs:
                    org_id = org.get("id", "")
                    if org_id and org_id not in seen_ids:
                        seen_ids.add(org_id)
                        all_orgs.append(org)

                self.progress(f"Found {len(orgs)} organizations (page {page}).")

                # Respect rate limits — small delay between pages
                time.sleep(1)

                if len(all_orgs) >= APOLLO_MAX_COMPANIES:
                    break

        self.progress(f"Apollo org search complete: {len(all_orgs)} total organizations found.")
        return all_orgs[:APOLLO_MAX_COMPANIES]

    # ── People Search ─────────────────────────────────────────────────

    def search_people(
        self,
        organization_ids: list[str] = None,
        organization_domains: list[str] = None,
        person_titles: list[str] = None,
        per_page: int = 10,
        page: int = 1,
    ) -> list[dict]:
        """
        Search for people at specific organizations.
        Uses api_search (no credit cost on free tier for search).
        Returns raw Apollo person dicts.
        """
        url = f"{self.BASE_URL}/mixed_people/search"

        body = {
            "page": page,
            "per_page": per_page,
        }

        if organization_ids:
            body["organization_ids"] = organization_ids
        if organization_domains:
            body["q_organization_domains_list"] = organization_domains
        if person_titles:
            body["person_titles"] = person_titles

        data = self._request_with_retry("POST", url, body)
        if not data:
            return []

        people = data.get("people", [])
        return people

    # ── People Enrichment (credit-consuming) ──────────────────────────

    def enrich_person(self, person_id: str) -> Optional[dict]:
        """
        Enrich a single person by ID to get full contact data (email, phone).
        This CONSUMES Apollo credits.
        """
        url = f"{self.BASE_URL}/people/match"

        body = {
            "id": person_id,
            "reveal_personal_emails": False,
            "reveal_phone_number": True,
        }

        data = self._request_with_retry("POST", url, body)
        if data and "person" in data:
            return data["person"]
        return data

    # ── Parsing helpers ───────────────────────────────────────────────

    def parse_org_to_business(self, org: dict) -> Business:
        """Convert an Apollo organization dict to our Business model."""
        name = org.get("name", "Unknown")

        # LinkedIn URL
        linkedin_url = org.get("linkedin_url", "")

        # Website
        website = org.get("website_url", "") or org.get("primary_domain", "")

        # Industry
        industry = org.get("industry", "")

        # Description
        short_desc = org.get("short_description", "")
        seo_desc = org.get("seo_description", "")
        description = short_desc or seo_desc or ""

        # Company size
        num_employees = org.get("estimated_num_employees")
        if num_employees:
            company_size = f"{num_employees} employees"
        else:
            company_size = ""

        # Location
        city = org.get("city", "")
        state = org.get("state", "")
        country = org.get("country", "")
        location_parts = [p for p in [city, state, country] if p]
        location = ", ".join(location_parts)

        return Business(
            company_name=name,
            industry=industry,
            linkedin_url=linkedin_url,
            website=website,
            description=description[:500] if description else None,
            company_size=company_size or None,
            location=location or None,
            source="apollo",
        )

    def parse_person_to_contact(self, person: dict, company_name: str = "") -> Contact:
        """Convert an Apollo person dict to our Contact model."""
        first = person.get("first_name", "")
        last = person.get("last_name", "")
        full_name = f"{first} {last}".strip()

        title = person.get("title", "") or person.get("headline", "")
        seniority = self._infer_seniority(title)

        email = person.get("email") or None
        email_confidence = None
        email_source = None
        if email:
            email_status = person.get("email_status", "")
            if email_status == "verified":
                email_confidence = 0.95
            elif email_status == "guessed":
                email_confidence = 0.6
            else:
                email_confidence = 0.7
            email_source = "apollo"

        phone_numbers = person.get("phone_numbers", [])
        phone = None
        if phone_numbers and isinstance(phone_numbers, list):
            # Prefer direct_dial, then mobile, then any
            for ph in phone_numbers:
                if isinstance(ph, dict):
                    phone = ph.get("sanitized_number") or ph.get("raw_number")
                    if phone:
                        break
                elif isinstance(ph, str):
                    phone = ph
                    break

        linkedin_url = person.get("linkedin_url", "") or ""

        # Location
        location = ""
        city = person.get("city", "")
        state = person.get("state", "")
        country = person.get("country", "")
        loc_parts = [p for p in [city, state, country] if p]
        location = ", ".join(loc_parts)

        photo_url = person.get("photo_url", "")

        return Contact(
            first_name=first,
            last_name=last,
            full_name=full_name,
            title=title,
            seniority=seniority,
            email=email,
            email_confidence=email_confidence,
            email_source=email_source,
            phone=phone,
            linkedin_url=linkedin_url,
            company_name=company_name,
            headline=person.get("headline", ""),
            location=location,
            photo_url=photo_url,
        )

    @staticmethod
    def _infer_seniority(title: str) -> str:
        """Infer seniority level from job title."""
        if not title:
            return "Unknown"
        t = title.lower()
        if any(x in t for x in ["chief", "ceo", "cto", "cfo", "coo", "cmo", "founder", "co-founder"]):
            return "C-Level"
        if any(x in t for x in ["vp", "vice president"]):
            return "VP"
        if any(x in t for x in ["director", "head of"]):
            return "Director"
        if "manager" in t:
            return "Manager"
        return "Individual"


# ══════════════════════════════════════════════════════════════════════
# Pipeline entry points — called from app.py
# ══════════════════════════════════════════════════════════════════════


def run_apollo_org_search(icp: ICP, state_proxy, test_mode: bool = False) -> list[Business]:
    """
    Step 1: Search Apollo for organizations matching the ICP.
    Returns list of Business objects (unscored).
    """
    progress = state_proxy.progress

    try:
        client = ApolloClient(progress=progress)
    except ValueError as e:
        progress(f"Error: {e}")
        return []

    # Use ICP search keywords for org search
    keywords = icp.search_keywords or []
    if not keywords:
        progress("No search keywords in ICP. Cannot search Apollo.")
        return []

    # Free tier limits — be conservative
    if test_mode:
        max_pages = 1
        per_page = 5
    else:
        max_pages = 2
        per_page = 25

    raw_orgs = client.search_organizations(
        keywords=keywords,
        industries=icp.target_industries,
        employee_min=icp.company_size_min,
        employee_max=icp.company_size_max,
        per_page=per_page,
        max_pages=max_pages,
    )

    if not raw_orgs:
        progress("Apollo returned no organizations.")
        return []

    # Convert to Business models
    businesses = []
    seen_names = set()
    # We store Apollo-specific metadata in a separate map (keyed by list index)
    # since Pydantic models don't allow arbitrary attributes.
    domain_map = {}  # idx -> primary_domain (used for people search later)

    for org in raw_orgs:
        try:
            biz = client.parse_org_to_business(org)
            # Deduplicate by company name
            name_key = biz.company_name.lower().strip()
            if name_key in seen_names:
                continue
            seen_names.add(name_key)

            idx = len(businesses)
            domain_map[idx] = org.get("primary_domain", "")
            businesses.append(biz)
        except Exception as e:
            progress(f"Error parsing Apollo org: {e}")

    # Stash domain_map on the state proxy so people search can access it
    if hasattr(state_proxy, '_apollo_domain_map'):
        state_proxy._apollo_domain_map = domain_map
    else:
        state_proxy._apollo_domain_map = domain_map

    progress(f"Parsed {len(businesses)} unique companies from Apollo.")
    return businesses


def run_apollo_score_companies(businesses: list[Business], icp: ICP, state_proxy, test_mode: bool = False) -> list[Business]:
    """
    Step 2: Score each company against the ICP using AI.
    Reuses the existing AI scoring from main.py.
    """
    progress = state_proxy.progress
    from main import score_company
    from config import ICP_SCORING_PROMPT

    progress(f"Scoring {len(businesses)} companies against ICP...")

    for i, biz in enumerate(businesses):
        if hasattr(state_proxy, 'cancel_requested') and state_proxy.cancel_requested:
            progress("Scoring cancelled.")
            break

        company_info = {
            "company_name": biz.company_name,
            "industry": biz.industry or "",
            "company_size": biz.company_size or "",
            "description": biz.description or "",
            "location": biz.location or "",
        }

        # Use ICP-specific scoring prompt
        prompt = ICP_SCORING_PROMPT.format(
            target_industries=", ".join(icp.target_industries),
            company_size_min=icp.company_size_min,
            company_size_max=icp.company_size_max,
            pain_points=", ".join(icp.pain_points),
            exclusions=", ".join(icp.exclusions),
            company_name=biz.company_name,
            industry=biz.industry or "Unknown",
            company_size=biz.company_size or "Unknown",
            description=biz.description or "No description",
        )

        from main import generate_with_retry, clean_json_response
        try:
            time.sleep(DELAY_BETWEEN_AI_CALLS)
            text = generate_with_retry(prompt, progress=progress)
            if text:
                data = json.loads(clean_json_response(text))
                biz.fit_score = data.get("score", data.get("fit_score", 0))
                biz.icp_match_score = biz.fit_score
                biz.fit_reason = data.get("reason", data.get("fit_reason", ""))
                biz.icp_match_reason = biz.fit_reason
                progress(f"[{i+1}/{len(businesses)}] {biz.company_name}: score={biz.fit_score}")
        except Exception as e:
            progress(f"Error scoring {biz.company_name}: {e}")
            biz.fit_score = 0
            biz.icp_match_score = 0

    return businesses


def run_apollo_people_search(businesses: list[Business], icp: ICP, state_proxy, test_mode: bool = False) -> list[Business]:
    """
    Step 3: Search Apollo for people at top-scored companies.
    Uses the free api_search endpoint (no credits consumed for search).
    """
    progress = state_proxy.progress

    try:
        client = ApolloClient(progress=progress)
    except ValueError as e:
        progress(f"Error: {e}")
        return businesses

    # Select top companies (score >= 50 or top 10, whichever is more inclusive)
    SCORE_THRESHOLD = 50
    qualified = [(i, biz) for i, biz in enumerate(businesses) if (biz.fit_score or 0) >= SCORE_THRESHOLD]
    qualified.sort(key=lambda x: (x[1].fit_score or 0), reverse=True)

    max_companies = 3 if test_mode else 10
    qualified = qualified[:max_companies]

    if not qualified:
        progress(f"No companies scored {SCORE_THRESHOLD}+ — skipping contact search.")
        return businesses

    progress(f"Searching for contacts at {len(qualified)} top companies...")

    target_roles = icp.target_roles or []
    # Apollo free tier: keep role list manageable
    search_titles = target_roles[:10]

    max_contacts = 2 if test_mode else APOLLO_MAX_CONTACTS_PER_COMPANY

    for idx, biz in qualified:
        if hasattr(state_proxy, 'cancel_requested') and state_proxy.cancel_requested:
            progress("Contact search cancelled.")
            break

        progress(f"Searching contacts for: {biz.company_name}...")

        # Build search parameters — use domain_map stashed during org search
        org_domains = []
        domain_map = getattr(state_proxy, '_apollo_domain_map', {})
        domain = domain_map.get(idx, '')
        website = biz.website or ''
        if domain:
            org_domains = [domain]
        elif website:
            # Extract domain from website URL
            from urllib.parse import urlparse
            parsed = urlparse(website if website.startswith('http') else f'http://{website}')
            if parsed.netloc:
                org_domains = [parsed.netloc.replace('www.', '')]

        if not org_domains:
            progress(f"  → Skipping {biz.company_name} — no domain available.")
            continue

        people = client.search_people(
            organization_domains=org_domains,
            person_titles=search_titles if search_titles else None,
            per_page=max_contacts,
        )

        if not people:
            # Retry without role filter
            progress(f"  → No contacts with role filter. Retrying without filter...")
            people = client.search_people(
                organization_domains=org_domains,
                per_page=max_contacts,
            )

        if people:
            contacts = []
            for person in people:
                try:
                    contact = client.parse_person_to_contact(person, biz.company_name)
                    contacts.append(contact)

                    # Set top-level email/phone on business if empty
                    if contact.email and not biz.email:
                        biz.email = contact.email
                    if contact.phone and not biz.phone:
                        biz.phone = contact.phone
                except Exception as e:
                    progress(f"  → Error parsing contact: {e}")

            biz.contacts = contacts
            progress(f"  → Found {len(contacts)} contacts for {biz.company_name}")
        else:
            progress(f"  → No contacts found for {biz.company_name}")

        # Rate limit respect — small delay between companies
        time.sleep(1.5)

    # Summary
    total_contacts = sum(len(biz.contacts) for _, biz in qualified)
    total_emails = sum(1 for _, biz in qualified for c in biz.contacts if c.email)
    companies_with_contacts = sum(1 for _, biz in qualified if biz.contacts)
    progress(f"Apollo contact search complete: {total_contacts} contacts across {companies_with_contacts}/{len(qualified)} companies, {total_emails} with emails.")

    return businesses


def run_apollo_full_pipeline(icp: ICP, state_proxy, test_mode: bool = False) -> list[Business]:
    """
    Complete Apollo pipeline: org search → AI score → people search.
    Called from app.py's /api/scrape/apollo endpoint.
    """
    progress = state_proxy.progress

    # Step 1: Organization search
    progress("Step 1/3: Searching Apollo for organizations...")
    businesses = run_apollo_org_search(icp, state_proxy, test_mode)

    if not businesses:
        return []

    if hasattr(state_proxy, 'cancel_requested') and state_proxy.cancel_requested:
        progress("Pipeline cancelled during org search.")
        return businesses

    # Step 2: AI scoring
    progress("Step 2/3: Scoring companies against ICP...")
    businesses = run_apollo_score_companies(businesses, icp, state_proxy, test_mode)

    if hasattr(state_proxy, 'cancel_requested') and state_proxy.cancel_requested:
        progress("Pipeline cancelled during scoring.")
        return businesses

    # Step 3: People search
    progress("Step 3/3: Finding contacts at top companies...")
    businesses = run_apollo_people_search(businesses, icp, state_proxy, test_mode)

    return businesses
