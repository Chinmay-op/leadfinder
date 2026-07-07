"""
Apify LinkedIn Company Employees Scraper Client

Uses the Apify REST API to run the harvestapi/linkedin-company-employees actor,
which scrapes LinkedIn company employee profiles with optional email discovery.

Modes:
- Short ($4/1k) — name, URL, summary, location, current positions
- Full ($8/1k) — complete work experience, education, skills
- Full + email search ($12/1k) — everything + SMTP-validated email discovery
"""

import requests
import time
import json
from typing import Optional
from config import APIFY_API_KEY, APIFY_LINKEDIN_EMPLOYEES_ACTOR_ID, APIFY_MAX_EMPLOYEES_PER_COMPANY
from models.contact import Contact


def _default_progress(msg: str):
    print(msg)


# ── Role expansion for Apify strict matching ──────────────────────
# Apify's jobTitles field does strict search. If the ICP says
# "Chief Sustainability Officer" it will miss "Head of Sustainability",
# "Sustainability Director", etc. We expand each role into short
# keyword fragments AND add real-world synonym titles so more profiles match.

_FILLER = {"of", "the", "and", "&", "in", "for", "-", "/", ","}
_C_SUITE_MAP = {
    "chief executive officer": "CEO",
    "chief technology officer": "CTO",
    "chief operating officer": "COO",
    "chief financial officer": "CFO",
    "chief marketing officer": "CMO",
    "chief sustainability officer": "CSO",
    "chief information officer": "CIO",
    "chief revenue officer": "CRO",
    "chief product officer": "CPO",
    "vice president": "VP",
}

# Real-world synonym map: if a role contains a key phrase,
# also search for these alternate titles people actually use on LinkedIn.
_ROLE_SYNONYMS = {
    "plant manager": [
        "Plant Director", "Factory Manager", "Site Manager",
        "Production Manager", "Works Manager", "Plant Head",
        "Manufacturing Manager", "General Manager",
    ],
    "director of operations": [
        "Operations Director", "Operations Manager", "Head of Operations",
        "VP Operations", "General Manager Operations",
        "COO", "Director Operations",
    ],
    "vp of manufacturing": [
        "VP Manufacturing", "Vice President Manufacturing",
        "Manufacturing Director", "Head of Manufacturing",
        "SVP Manufacturing", "Director of Manufacturing",
        "General Manager Manufacturing",
    ],
    "facilities manager": [
        "Facilities Director", "Head of Facilities",
        "Building Manager", "Maintenance Manager",
        "Facilities Coordinator", "Facilities Superintendent",
        "Director of Facilities", "Engineering Manager",
    ],
    "chief sustainability officer": [
        "CSO", "Sustainability Director", "Head of Sustainability",
        "Sustainability Manager", "VP Sustainability",
        "Director of Sustainability", "ESG Director",
        "ESG Manager", "Environmental Manager",
        "Environmental Director", "EHS Manager",
        "EHS Director", "Energy Manager", "Energy Director",
    ],
    "cto": [
        "Technology Director", "VP Engineering",
        "Head of Engineering", "Director of Technology",
    ],
    "ceo": [
        "Managing Director", "General Manager",
        "Founder", "President", "MD",
    ],
    "coo": [
        "Operations Director", "Head of Operations",
        "VP Operations", "Director of Operations",
    ],
}


def _expand_roles(roles: list[str]) -> list[str]:
    """
    Aggressively expand formal ICP titles into short keyword fragments
    AND real-world title synonyms that people actually put on LinkedIn.

    Example:
        ["Chief Sustainability Officer"]
        →  ["Chief Sustainability Officer", "CSO", "Sustainability Director",
             "Head of Sustainability", "Sustainability Manager", "VP Sustainability",
             "ESG Director", "ESG Manager", "Environmental Manager",
             "Energy Manager", "Sustainability", ...]
    """
    seen: set[str] = set()
    expanded: list[str] = []

    def _add(term: str):
        key = term.strip().lower()
        if key and len(key) > 1 and key not in seen:
            seen.add(key)
            expanded.append(term.strip())

    for role in roles:
        # Always keep the original
        _add(role)

        lower = role.lower().strip()

        # Add C-suite abbreviation if applicable
        for long_form, short_form in _C_SUITE_MAP.items():
            if long_form in lower:
                _add(short_form)
            if lower == short_form.lower():
                pass

        # Replace "Vice President" with "VP" variant
        if "vice president" in lower:
            _add(role.lower().replace("vice president", "VP").title())

        # Strip filler words to make shorter variant
        words = role.split()
        core_words = [w for w in words if w.lower() not in _FILLER]
        if len(core_words) < len(words) and core_words:
            _add(" ".join(core_words))

        # Add individual meaningful keywords (≥4 chars) as standalone search terms
        for w in core_words:
            if len(w) >= 4 and w.lower() not in {"manager", "director", "head", "senior", "lead", "junior", "associate"}:
                _add(w)

        # If the role has "Manager"/"Director"/"Head", add the domain keyword alone
        for prefix in ("Manager", "Director", "Head"):
            if prefix.lower() in lower and len(core_words) > 1:
                domain_words = [w for w in core_words if w.lower() != prefix.lower()]
                if domain_words:
                    _add(" ".join(domain_words))

        # ── Add real-world synonym titles ──
        # Check if the role matches any key in _ROLE_SYNONYMS (partial match)
        for key_phrase, synonyms in _ROLE_SYNONYMS.items():
            if key_phrase in lower or lower in key_phrase:
                for syn in synonyms:
                    _add(syn)

        # ── Title level permutations ──
        # If role contains Manager, also try Director/Head/VP variant and vice versa
        _level_swaps = [
            ("manager", ["Director", "Head", "VP", "Supervisor", "Superintendent"]),
            ("director", ["Manager", "Head", "VP"]),
            ("head", ["Director", "Manager", "VP"]),
            ("vp", ["Director", "Head", "SVP"]),
            ("vice president", ["Director", "Head", "SVP"]),
        ]
        for level_word, swaps in _level_swaps:
            if level_word in lower:
                domain = " ".join(w for w in core_words if w.lower() != level_word)
                if domain:
                    for swap in swaps:
                        _add(f"{swap} {domain}")
                        _add(f"{domain} {swap}")

    return expanded




class ApifyEmployeeScraper:
    """Client for the Apify LinkedIn Company Employees Mass Scraper."""

    BASE_URL = "https://api.apify.com/v2"

    def __init__(self, progress=None):
        self.progress = progress or _default_progress
        if not APIFY_API_KEY:
            raise ValueError("APIFY_API_KEY not set in .env")

    def _headers(self):
        return {"Content-Type": "application/json"}

    def _params(self):
        return {"token": APIFY_API_KEY}

    def run_employee_scraper(
        self,
        company_urls: list[str],
        target_roles: list[str],
        max_items_per_company: int = 3,
        mode: str = "Full + email search ($12 per 1k)",
        batch_mode: str = "all_at_once",
    ) -> list[dict]:
        """
        Run the Apify LinkedIn Company Employees actor and return raw results.
        Sends ONE API call per company so each company gets dedicated maxItems
        coverage across all ICP roles.
        """
        if not company_urls:
            self.progress("No company URLs provided for Apify scraper.")
            return []

        # Force batch mode to all_at_once to avoid Apify free tier limits 
        # (spawning child runs per company hits concurrent limits)
        batch_mode = "all_at_once"

        # Expand target roles into short keyword fragments for better Apify matching.
        expanded = []
        if target_roles:
            expanded = _expand_roles(target_roles)
            if len(expanded) > 20:
                self.progress(f"Expanded {len(target_roles)} ICP roles → {len(expanded)} keywords, capping to Apify limit of 20")
                expanded = expanded[:20]
            else:
                self.progress(f"Expanded {len(target_roles)} ICP roles → {len(expanded)} search keywords")
            self.progress(f"Job titles sent: {', '.join(expanded)}")

        self.progress(f"Starting Apify employee scraper for {len(company_urls)} companies (1 call per company, maxItems={max_items_per_company})...")
        self.progress(f"Mode: {mode} | Roles: {', '.join(target_roles[:5])}")

        all_results = []
        
        # One API call per company — each gets its own dedicated maxItems budget
        for i, company_url in enumerate(company_urls):
            actor_input = {
                "companies": [company_url],
                "profileScraperMode": mode,
                "maxItems": max_items_per_company,
                "companyBatchMode": batch_mode,
            }
            if expanded:
                actor_input["jobTitles"] = expanded

            self.progress(f"  -> [{i+1}/{len(company_urls)}] Running Apify for: {company_url}")
            
            run_id = self._start_run(actor_input)
            if not run_id:
                continue

            dataset_id = self._poll_run(run_id)
            if not dataset_id:
                continue

            results = self._get_dataset_items(dataset_id)
            self.progress(f"  -> [{i+1}/{len(company_urls)}] Returned {len(results)} profiles.")
            all_results.extend(results)

        self.progress(f"Apify total returned {len(all_results)} employee profiles across {len(company_urls)} companies.")
        return all_results

    def _start_run(self, actor_input: dict) -> Optional[str]:
        """Start the actor run and return the run ID."""
        # ── Defensive hard cap: Apify allows at most 20 jobTitles ──
        if "jobTitles" in actor_input and len(actor_input["jobTitles"]) > 20:
            self.progress(f"[Safety] jobTitles had {len(actor_input['jobTitles'])} items — trimming to 20 before API call")
            actor_input["jobTitles"] = actor_input["jobTitles"][:20]

        actor_id = APIFY_LINKEDIN_EMPLOYEES_ACTOR_ID.replace("/", "~")
        url = f"{self.BASE_URL}/acts/{actor_id}/runs"

        try:
            resp = requests.post(
                url,
                params=self._params(),
                headers=self._headers(),
                json=actor_input,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json().get("data", {})
            run_id = data.get("id")
            if run_id:
                self.progress(f"Apify actor run started: {run_id}")
                return run_id
            else:
                self.progress(f"Apify actor failed to start. Response: {resp.text[:500]}")
                return None
        except requests.exceptions.HTTPError as e:
            self.progress(f"Apify API error: {e} — {getattr(e.response, 'text', '')[:500]}")
            return None
        except Exception as e:
            self.progress(f"Apify connection error: {e}")
            return None

    def _poll_run(self, run_id: str, max_wait: int = 600, poll_interval: int = 10) -> Optional[str]:
        """Poll the actor run until it completes. Returns the dataset ID."""
        url = f"{self.BASE_URL}/actor-runs/{run_id}"
        elapsed = 0

        while elapsed < max_wait:
            try:
                resp = requests.get(url, params=self._params(), timeout=15)
                resp.raise_for_status()
                data = resp.json().get("data", {})
                status = data.get("status")

                if status == "SUCCEEDED":
                    dataset_id = data.get("defaultDatasetId")
                    self.progress(f"Apify run completed successfully.")
                    return dataset_id

                elif status in ("FAILED", "ABORTED", "TIMED-OUT"):
                    self.progress(f"Apify run ended with status: {status}")
                    return None

                else:
                    # Still running
                    if elapsed % 30 == 0:
                        self.progress(f"Apify scraper running... ({elapsed}s elapsed, status: {status})")

            except Exception as e:
                self.progress(f"Error polling Apify run: {e}")

            time.sleep(poll_interval)
            elapsed += poll_interval

        self.progress(f"Apify run timed out after {max_wait}s")
        return None

    def _get_dataset_items(self, dataset_id: str) -> list[dict]:
        """Fetch all items from the dataset."""
        url = f"{self.BASE_URL}/datasets/{dataset_id}/items"
        try:
            resp = requests.get(
                url,
                params={**self._params(), "format": "json"},
                timeout=30,
            )
            resp.raise_for_status()
            items = resp.json()
            if isinstance(items, list):
                return items
            return []
        except Exception as e:
            self.progress(f"Error fetching Apify dataset: {e}")
            return []

    def parse_employees_to_contacts(self, raw_profiles: list[dict], company_name: str = "") -> list[Contact]:
        """
        Convert raw Apify employee profiles into Contact models.
        
        Maps the Apify output fields (firstName, lastName, headline, etc.)
        to our internal Contact model.
        """
        contacts = []
        for profile in raw_profiles:
            first = profile.get("firstName", "")
            last = profile.get("lastName", "")
            full_name = f"{first} {last}".strip()
            
            # Extract title from headline or currentPosition
            headline = profile.get("headline", "")
            current_positions = profile.get("currentPosition", [])
            title = ""
            if current_positions and isinstance(current_positions, list):
                pos = current_positions[0]
                if isinstance(pos, dict):
                    title = pos.get("position", pos.get("companyName", ""))
            if not title:
                title = headline

            # Infer seniority from title
            seniority = self._infer_seniority(title)

            # Extract email (from Apify email search)
            raw_email = profile.get("email") or profile.get("emailAddress") or None
            # Some actors put emails in a nested field
            if not raw_email and isinstance(profile.get("emails"), list) and profile["emails"]:
                raw_email = profile["emails"][0]

            email = None
            email_confidence = None
            if isinstance(raw_email, dict):
                email = raw_email.get("email")
                score = raw_email.get("qualityScore")
                if score is not None:
                    try:
                        email_confidence = float(score) / 100.0 if float(score) > 1 else float(score)
                    except (ValueError, TypeError):
                        pass
            elif isinstance(raw_email, str):
                email = raw_email
            
            if email_confidence is None and email:
                email_confidence = 0.9

            # LinkedIn URL
            linkedin_url = profile.get("linkedinUrl") or profile.get("profileUrl") or ""
            if not linkedin_url:
                public_id = profile.get("publicIdentifier", "")
                if public_id:
                    linkedin_url = f"https://www.linkedin.com/in/{public_id}"

            # Location
            location_data = profile.get("location", {})
            location_text = ""
            if isinstance(location_data, dict):
                location_text = location_data.get("linkedinText", "")
            elif isinstance(location_data, str):
                location_text = location_data

            # Phone (rarely available from LinkedIn, but just in case)
            phone = profile.get("phone") or profile.get("phoneNumber") or None

            contact = Contact(
                first_name=first,
                last_name=last,
                full_name=full_name,
                title=title,
                seniority=seniority,
                email=email,
                email_confidence=email_confidence if email else None,
                email_source="apify" if email else None,
                phone=phone,
                linkedin_url=linkedin_url,
                company_name=company_name,
                headline=headline,
                location=location_text,
                photo_url=profile.get("photo", ""),
            )
            contacts.append(contact)

        return contacts

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


def estimate_apify_cost(
    num_companies: int,
    max_items_per_company: int,
    mode: str = "Full + email search ($12 per 1k)",
    batch_mode: str = "all_at_once",
) -> dict:
    """
    Estimate the cost of running the Apify employee scraper.
    
    Returns a dict with cost breakdown.
    """
    batch_mode = "all_at_once"

    cost_per_1k = 12 if "email" in mode.lower() else (8 if "Full" in mode else 4)
    estimated_profiles = num_companies * max_items_per_company
    profile_cost = (estimated_profiles / 1000) * cost_per_1k
    batch_cost = num_companies * 0.02 if batch_mode == "one_by_one" else 0
    total_cost = profile_cost + batch_cost

    return {
        "num_companies": num_companies,
        "max_items_per_company": max_items_per_company,
        "estimated_profiles": estimated_profiles,
        "mode": mode,
        "profile_cost": round(profile_cost, 2),
        "batch_cost": round(batch_cost, 2),
        "total_cost": round(total_cost, 2),
    }


def run_apify_contact_discovery(
    state_proxy,
    businesses: list,
    target_roles: list[str],
    selected_indices: list[int] = None,
    test_mode: bool = False,
) -> list:
    """
    Main entry point: Run Apify employee scraper for selected businesses.
    
    Args:
        state_proxy: Object with .progress(msg) method
        businesses: List of Business objects
        target_roles: ICP target roles for filtering
        selected_indices: Which business indices to enrich (None = all)
        test_mode: If True, limits to 3 companies and 2 profiles each
    
    Returns:
        Updated list of Business objects with contacts populated
    """
    progress = state_proxy.progress

    # Determine which businesses to process
    if selected_indices is not None:
        selected = [(i, businesses[i]) for i in selected_indices if i < len(businesses)]
    else:
        selected = list(enumerate(businesses))

    # Sort by fit_score descending to prioritize the best companies
    selected.sort(key=lambda x: (x[1].fit_score or 0), reverse=True)

    # Cap at top 10 companies — one dedicated Apify call per company
    selected = selected[:10]

    if not selected:
        progress("No companies selected for contact discovery.")
        return businesses

    # Test mode limits
    if test_mode:
        max_companies = 3
        max_items_per_company = 2
        progress(f"[Test Mode] Limiting to {max_companies} companies, {max_items_per_company} profiles each.")
        selected = selected[:max_companies]
    else:
        # 10 profiles per company — one per ICP role — to guarantee coverage
        max_items_per_company = APIFY_MAX_EMPLOYEES_PER_COMPANY

    # Collect LinkedIn URLs
    company_map = {}  # linkedin_url -> (index, business)
    company_urls = []
    for idx, biz in selected:
        li_url = getattr(biz, "linkedin_url", "") or ""
        if li_url and "linkedin.com" in li_url:
            company_urls.append(li_url)
            company_map[li_url] = (idx, biz)
        else:
            progress(f"Skipping {biz.company_name} — no LinkedIn URL available.")

    if not company_urls:
        progress("No valid LinkedIn company URLs found. Cannot run Apify scraper.")
        return businesses

    progress(f"Running Apify scraper sequentially for {len(company_urls)} companies, searching for: {', '.join(target_roles[:5])}")

    # Run the scraper
    scraper = ApifyEmployeeScraper(progress=progress)
    raw_results = scraper.run_employee_scraper(
        company_urls=company_urls,
        target_roles=target_roles,
        max_items_per_company=max_items_per_company,
        mode="Full + email search ($12 per 1k)",
    )

    if not raw_results:
        progress("No employee profiles returned by Apify.")
        raw_results = []

    # Group results by company
    _assign_profiles_to_companies(scraper, raw_results, company_map)

    # ── Retry pass: companies with 0 contacts get a second run WITHOUT jobTitles ──
    # This guarantees at least some profile for every company if the strict role filter fails.
    if not state_proxy.cancel_requested:
        missing_urls = []
        missing_map = {}
        for url_key, (idx, biz) in company_map.items():
            if not biz.contacts:
                missing_urls.append(url_key)
                missing_map[url_key] = (idx, biz)

        if missing_urls:
            progress(f"{len(missing_urls)} companies had 0 contacts with role filter. Retrying without role filter to guarantee coverage...")
            retry_results = scraper.run_employee_scraper(
                company_urls=missing_urls,
                target_roles=[],  # No role filter — get ANY employee
                max_items_per_company=max_items_per_company,
                mode="Full + email search ($12 per 1k)",
            )
            if retry_results:
                _assign_profiles_to_companies(scraper, retry_results, missing_map)
                retried_found = sum(1 for _, b in missing_map.values() if b.contacts)
                progress(f"Retry found contacts for {retried_found}/{len(missing_urls)} previously empty companies.")

    # Log summary
    total_contacts = sum(len(b.contacts) for _, b in company_map.values())
    total_emails = sum(1 for _, b in company_map.values() for c in b.contacts if c.email)
    companies_with_contacts = sum(1 for _, b in company_map.values() if b.contacts)
    progress(f"Contact discovery complete: {total_contacts} contacts across {companies_with_contacts}/{len(company_map)} companies, {total_emails} with emails.")

    return businesses


def _assign_profiles_to_companies(scraper, raw_results: list[dict], company_map: dict):
    """Match raw Apify profiles to their parent company and populate contacts."""
    for profile in raw_results:
        matched_idx = None
        matched_biz = None

        # Gather all positions (currentPosition + experience)
        positions = []
        if isinstance(profile.get("currentPosition"), list):
            positions.extend(profile.get("currentPosition"))
        if isinstance(profile.get("experience"), list):
            positions.extend(profile.get("experience"))

        # Match by company LinkedIn URL
        for pos in positions:
            if isinstance(pos, dict):
                company_li_url = pos.get("companyLinkedinUrl", "")
                if company_li_url:
                    for url_key in company_map:
                        if _urls_match(url_key, company_li_url):
                            matched_idx, matched_biz = company_map[url_key]
                            break
                if matched_biz:
                    break
        
        # Fallback: match by company name in positions
        if not matched_biz:
            for url_key, (idx, biz) in company_map.items():
                biz_name = (biz.company_name or "").lower()
                if not biz_name:
                    continue
                for pos in positions:
                    if isinstance(pos, dict):
                        pos_company = (pos.get("companyName") or "").lower()
                        if pos_company and (pos_company in biz_name or biz_name in pos_company):
                            matched_idx, matched_biz = idx, biz
                            break
                if matched_biz:
                    break

        # Fallback 2: match by raw 'position' string (for short profiles that lack experience array)
        if not matched_biz:
            raw_pos = profile.get("position", "")
            if raw_pos and isinstance(raw_pos, str):
                raw_pos_lower = raw_pos.lower()
                for url_key, (idx, biz) in company_map.items():
                    biz_name = (biz.company_name or "").lower()
                    if biz_name and biz_name in raw_pos_lower:
                        matched_idx, matched_biz = idx, biz
                        break

        if matched_biz:
            contacts = scraper.parse_employees_to_contacts([profile], matched_biz.company_name)
            if contacts:
                if not matched_biz.contacts:
                    matched_biz.contacts = []
                matched_biz.contacts.extend(contacts)
                # Also set top-level email/phone if empty
                for c in contacts:
                    if c.email and not matched_biz.email:
                        matched_biz.email = c.email
                    if c.phone and not matched_biz.phone:
                        matched_biz.phone = c.phone


def _urls_match(url1: str, url2: str) -> bool:
    """Check if two LinkedIn URLs refer to the same company."""
    def normalize(u):
        u = u.lower().rstrip("/")
        u = u.replace("https://", "").replace("http://", "").replace("www.", "")
        return u
    return normalize(url1) == normalize(url2)
