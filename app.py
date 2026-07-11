"""
Lead Finder — FastAPI Web Server (Simplified)
Core pipeline: ICP → LinkedIn Scrape → Contact Discovery → Email Enrichment
with SSE-based real-time progress streaming and a chat-like frontend.
"""

import asyncio
import csv
import json
import os
import time
import traceback
import sys
from pathlib import Path
from typing import Optional

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    StreamingResponse,
)
from fastapi.security import OAuth2PasswordRequestForm
from auth import (
    get_current_user, require_role, create_access_token, verify_password, get_user,
    ACCESS_TOKEN_EXPIRE_MINUTES, User, SECRET_KEY, ALGORITHM
)
import jwt
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Session output layer
from session_routes import router as session_router
from session_store import save_session

from fastapi.middleware.cors import CORSMiddleware

# ── App Setup ─────────────────────────────────────────────────────────────────
app = FastAPI(title="Lead Finder", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # For production, you may want to restrict this to the static web app origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files (CSS, JS)
STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)
(STATIC_DIR / "css").mkdir(exist_ok=True)
(STATIC_DIR / "js").mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.include_router(session_router)

# ── Global State ──────────────────────────────────────────────────────────────
class PipelineState:
    def __init__(self):
        self.status = "idle"  # idle | generating_icp | scraping | finding_contacts | enriching
        self.messages: list[str] = []
        self.listeners: list[asyncio.Queue] = []
        self._lock = asyncio.Lock()
        self._main_loop = None
        self.current_session_id: str | None = None  # Tracks the active pipeline run
        self.businesses: list = []  # In-memory storage for current session businesses
        self.cancel_requested = False

    async def set_status(self, status: str):
        self.status = status
        await self.push(f"__STATUS__:{status}")

    async def push(self, message: str):
        if self._main_loop is None:
            self._main_loop = asyncio.get_running_loop()
        async with self._lock:
            self.messages.append(message)
            for q in self.listeners:
                await q.put(message)

    def progress(self, message: str):
        """Sync callback for existing scripts — bridges to async queue."""
        if self._main_loop is None:
            print(message)
            return
        
        # Safely schedule the push on the main event loop from any background thread
        asyncio.run_coroutine_threadsafe(self.push(message), self._main_loop)

    async def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        async with self._lock:
            self.listeners.append(q)
        return q

    async def unsubscribe(self, q: asyncio.Queue):
        async with self._lock:
            if q in self.listeners:
                self.listeners.remove(q)


state = PipelineState()


class TestModeProgress:
    """Wraps state.progress to suppress noisy per-item detail messages in test mode.
    
    In normal mode this is never used — all messages pass through unfiltered.
    In test mode, only milestone messages (start/found/done/error) are emitted;
    repetitive per-company scoring, per-domain resolution, and per-contact
    lookup lines are silently counted and summarised at the end.
    """

    # Prefixes/substrings that indicate noisy per-item detail lines
    _NOISY_PATTERNS = (
        "[API]",
        "Resolving corporate domains via Clearbit for",
        "→ Found domain via Clearbit",
        "→ Clearbit error",
        "Found:",
        "Scoring...",
        "Hunting for target roles",
        "Skipping Snov for",
        "→ Found",
        "→ No contacts found via Snov",
        "→ No contacts found via Yahoo",
        "→ Snov.io lookup",
        "→ Found email",
        "Skipping",
        "Enriching emails for",
        "Error mapping to Business model",
        "Error scraping",
        "Yahoo search error",
        "API hit limits",
        "Raw AI Response",
    )

    def __init__(self, real_progress):
        self._real = real_progress
        self._suppressed = 0

    def __call__(self, message: str):
        # Always let through control messages, JSON payloads, and milestone messages
        if message.startswith("__") or message.startswith("{"):
            self._real(message)
            return

        # Check if it's a noisy detail line
        for pattern in self._NOISY_PATTERNS:
            if pattern in message:
                self._suppressed += 1
                return

        # Everything else passes through (start messages, completion, errors)
        self._real(message)

    def flush_summary(self):
        """Emit a single summary line for all suppressed messages."""
        if self._suppressed > 0:
            self._real(f"[Test Mode] Suppressed {self._suppressed} verbose log entries.")
            self._suppressed = 0


# ── Request Models ────────────────────────────────────────────────────────────
class ICPRequest(BaseModel):
    description: str

class ICPApproveRequest(BaseModel):
    target_roles: list[str]
    target_industries: list[str]
    company_size_min: int
    company_size_max: int
    pain_points: list[str]
    search_keywords: list[str]
    exclusions: list[str]
    decision_maker_departments: list[str]
    value_proposition: str | None = None


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        content = index_path.read_text(encoding="utf-8")
        headers = {
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        }
        return HTMLResponse(content=content, headers=headers)
    return HTMLResponse("<h1>Lead Finder</h1><p>Frontend not found.</p>")


@app.get("/api/status")
async def get_status(current_user: User = Depends(get_current_user)):
    return {"status": state.status}

@app.post("/api/stop")
async def stop_pipeline(current_user: User = Depends(get_current_user)):
    """Request cancellation of the current running pipeline task."""
    state.cancel_requested = True
    # Let the backend loops catch the flag and return gracefully,
    # or just force status to idle right now (though it's safer to let loops clean up).
    # We will log a message
    state.progress("Cancellation requested. Stopping current operation soon...")
    return {"status": "cancelling"}

# ── Auth Endpoints ────────────────────────────────────────────────────────────

@app.post("/api/auth/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = get_user(form_data.username)
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    from datetime import timedelta
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username, "role": user.role}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer", "role": user.role}

@app.get("/api/auth/me")
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@app.post("/api/chat/reset")
async def reset_chat_endpoint(current_user: User = Depends(get_current_user)):
    """Save current chat to history if not empty, then reset state for a new chat."""
    from icp import load_cached_icp
    import os
    import uuid
    from session_store import save_session

    icp = load_cached_icp()
    keywords = icp.search_keywords if icp else []
    
    if state.businesses:
        try:
            save_session(
                keywords=keywords,
                icp=icp,
                source_pipeline="aborted_or_refreshed",
                session_id=state.current_session_id,
                businesses=state.businesses
            )
        except Exception:
            pass
            
    # Reset state
    state.businesses = []
    state.messages = []
    state.current_session_id = str(uuid.uuid4())
    if state.status not in ("idle", "done", "failed"):
        state.cancel_requested = True
    await state.set_status("idle")
    
    # Clear ICP cache
    if os.path.exists("session_icp.json"):
        try:
            os.remove("session_icp.json")
        except OSError:
            pass
            
    return {"status": "reset"}


# ── ICP Endpoints ─────────────────────────────────────────────────────────────

@app.post("/api/icp/generate")
async def generate_icp_endpoint(req: ICPRequest, current_user: User = Depends(get_current_user)):
    """Generate ICP from user description."""
    if state.status not in ("idle", "done", "failed"):
        return JSONResponse({"error": "Pipeline busy"}, status_code=409)

    async def _run():
        try:
            state.cancel_requested = False
            await state.set_status("generating_icp")
            loop = asyncio.get_running_loop()
            from icp import run_icp_generation
            await loop.run_in_executor(None, run_icp_generation, req.description, state)
        except Exception as e:
            state.progress(f"Error: {e}")
            await state.set_status("idle")

    asyncio.create_task(_run())
    return {"status": "started"}


@app.post("/api/icp/approve")
async def approve_icp_endpoint(req: ICPApproveRequest, current_user: User = Depends(get_current_user)):
    """Accept the final (possibly edited) ICP from the user."""
    from icp import save_icp
    from models.icp import ICP
    
    icp = ICP(**req.model_dump())
    save_icp(icp)
    
    await state.set_status("idle")
    state.progress("ICP approved and saved. Ready for LinkedIn scraping.")
    return {"status": "approved"}


@app.get("/api/icp/current")
async def get_current_icp(current_user: User = Depends(get_current_user)):
    """Return the currently cached ICP, if any."""
    from icp import load_cached_icp
    icp = load_cached_icp()
    if icp:
        return {"icp": icp.model_dump()}
    return JSONResponse({"error": "No cached ICP found"}, status_code=404)


# ── Scraping Endpoint ─────────────────────────────────────────────────────────

@app.post("/api/scrape/linkedin")
async def scrape_linkedin_endpoint(test_mode: bool = False, current_user: User = Depends(get_current_user)):
    """Start LinkedIn company scraping based on current ICP.
    
    Sequential pipeline:
    1. Scrape all companies from Yahoo/LinkedIn
    2. Sort by fit_score, select top 10
    3. Run Apify contact discovery for each (1 API call per company)
    """
    from icp import load_cached_icp
    icp = load_cached_icp()
    if not icp:
        return JSONResponse({"error": "No ICP defined. Generate and approve ICP first."}, status_code=400)
        
    if state.status not in ("idle", "done", "failed"):
        return JSONResponse({"error": "Pipeline busy"}, status_code=409)

    async def _run():
        # In test mode, wrap progress to suppress noisy per-item logs
        progress_fn = TestModeProgress(state.progress) if test_mode else state.progress
        
        # Create a thin proxy so run_linkedin_scraper sees .progress as a method
        class _ProgressProxy:
            def __init__(self, fn, parent_state):
                self._fn = fn
                self._parent_state = parent_state
            def progress(self, msg):
                self._fn(msg)
            @property
            def cancel_requested(self):
                return self._parent_state.cancel_requested
        
        proxy = _ProgressProxy(progress_fn, state)
        
        try:
            state.cancel_requested = False
            # Clear stale enriched leads from previous sessions
            if os.path.exists("enriched_leads.csv"):
                try:
                    os.remove("enriched_leads.csv")
                except OSError:
                    pass

            await state.set_status("scraping")
            loop = asyncio.get_running_loop()
            from linkedin_scraper import run_linkedin_scraper
            from apify_contacts import run_apify_contact_discovery
            
            # Reset in-memory businesses for this new session
            state.businesses = []

            # ── Step 1: Find ALL companies first ──
            businesses = await loop.run_in_executor(
                None, run_linkedin_scraper, icp, proxy, test_mode, None
            )
            
            state.businesses = businesses
            
            if state.cancel_requested:
                progress_fn("Pipeline cancelled during scraping.")
                return
            
            # ── Step 2: Select companies with fit_score >= 85 for Apify contact discovery ──
            if businesses:
                APIFY_SCORE_THRESHOLD = 85
                qualified = [
                    (idx, biz) for idx, biz in enumerate(businesses)
                    if (biz.fit_score or 0) >= APIFY_SCORE_THRESHOLD
                ]
                # Sort qualified by score descending, cap at 10 (free tier limit)
                qualified.sort(key=lambda x: (x[1].fit_score or 0), reverse=True)
                top_n = 3 if test_mode else 10
                qualified = qualified[:top_n]
                top_indices = [idx for idx, _ in qualified]
                
                if not top_indices:
                    progress_fn(f"No companies scored {APIFY_SCORE_THRESHOLD}+ — skipping Apify contact discovery to save API calls.")
                else:
                    top_names = [businesses[i].company_name for i in top_indices[:5]]
                    progress_fn(f"Selected {len(top_indices)} companies with score ≥{APIFY_SCORE_THRESHOLD} for contact discovery: {', '.join(top_names)}...")
                
                # ── Step 3: Run Apify sequentially — 1 call per company ──
                if top_indices:
                    await state.set_status("finding_contacts")
                    state.businesses = await loop.run_in_executor(
                        None,
                        run_apify_contact_discovery,
                        proxy,
                        state.businesses,
                        icp.target_roles,
                        top_indices,
                        test_mode,
                    )
            
            import uuid
            session_id = str(uuid.uuid4())
            state.current_session_id = session_id
            
            # Flush suppressed count before final messages
            if isinstance(progress_fn, TestModeProgress):
                progress_fn.flush_summary()
            
            # IMPORTANT: Set status to idle BEFORE sending __DONE__.
            # The frontend will call /api/enrich/email immediately after receiving
            # __DONE__, and that endpoint checks state.status == "idle".
            state.status = "idle"
            
            await state.push(json.dumps({"type": "session_id", "session_id": session_id}))
            await state.push("__DONE__")
        except Exception as e:
            state.progress(f"Error: {e}")
        finally:
            # Safety net — ensure status is always reset even on error
            if state.status not in ("idle", "enriching"):
                await state.set_status("idle")

    asyncio.create_task(_run())
    return {"status": "started"}


# ── Contact Cost Estimate Endpoint ────────────────────────────────────────────

class ContactRequest(BaseModel):
    selected_indices: list[int] | None = None   # which companies to enrich (None = all)

@app.post("/api/contacts/estimate")
async def estimate_contacts_cost(req: ContactRequest = ContactRequest(), current_user: User = Depends(get_current_user)):
    """Return estimated Apify cost before running the scraper."""
    from apify_contacts import estimate_apify_cost
    from icp import load_cached_icp
    from config import APIFY_MAX_EMPLOYEES_PER_COMPANY
    
    icp = load_cached_icp()
    target_roles = icp.target_roles if icp else ["CEO", "CTO", "Founder"]
    
    if req.selected_indices:
        num_companies = len(req.selected_indices)
    else:
        num_companies = len(state.businesses)
    
    # Use config value (matches run_apify_contact_discovery logic)
    max_items_per_company = APIFY_MAX_EMPLOYEES_PER_COMPANY
    
    # In test mode, override
    is_test = False
    if is_test:
        num_companies = min(num_companies, 3)
        max_items_per_company = 2
    
    estimate = estimate_apify_cost(num_companies, max_items_per_company)
    # Account for possible retry pass (companies with 0 contacts get a second run)
    estimate["note"] = "May run a second pass without role filter for companies with 0 results"
    return estimate


# ── Apollo Pipeline Endpoint ──────────────────────────────────────────────────

@app.post("/api/scrape/apollo")
async def scrape_apollo_endpoint(test_mode: bool = False, current_user: User = Depends(get_current_user)):
    """Start Apollo.io pipeline: org search → AI score → people search.
    
    This is the Apollo alternative to /api/scrape/linkedin.
    Uses Apollo.io REST API instead of Yahoo scraping + Apify.
    """
    from icp import load_cached_icp
    icp = load_cached_icp()
    if not icp:
        return JSONResponse({"error": "No ICP defined. Generate and approve ICP first."}, status_code=400)
        
    if state.status not in ("idle", "done", "failed"):
        return JSONResponse({"error": "Pipeline busy"}, status_code=409)

    async def _run():
        # In test mode, wrap progress to suppress noisy per-item logs
        progress_fn = TestModeProgress(state.progress) if test_mode else state.progress
        
        # Create a thin proxy so apollo pipeline sees .progress as a method
        class _ProgressProxy:
            def __init__(self, fn, parent_state):
                self._fn = fn
                self._parent_state = parent_state
            def progress(self, msg):
                self._fn(msg)
            @property
            def cancel_requested(self):
                return self._parent_state.cancel_requested
        
        proxy = _ProgressProxy(progress_fn, state)
        
        try:
            state.cancel_requested = False
            # Clear stale enriched leads from previous sessions
            if os.path.exists("enriched_leads.csv"):
                try:
                    os.remove("enriched_leads.csv")
                except OSError:
                    pass

            await state.set_status("scraping")
            loop = asyncio.get_running_loop()
            from apollo_pipeline import run_apollo_full_pipeline
            
            # Reset in-memory businesses for this new session
            state.businesses = []

            # Run the full Apollo pipeline in a thread executor
            businesses = await loop.run_in_executor(
                None, run_apollo_full_pipeline, icp, proxy, test_mode
            )
            
            state.businesses = businesses
            
            if state.cancel_requested:
                progress_fn("Pipeline cancelled during Apollo search.")
                return
            
            import uuid
            session_id = str(uuid.uuid4())
            state.current_session_id = session_id
            
            # Flush suppressed count before final messages
            if isinstance(progress_fn, TestModeProgress):
                progress_fn.flush_summary()
            
            # Set status to idle BEFORE sending __DONE__
            state.status = "idle"
            
            await state.push(json.dumps({"type": "session_id", "session_id": session_id}))
            await state.push("__DONE__")
        except Exception as e:
            state.progress(f"Error: {e}")
        finally:
            # Safety net — ensure status is always reset even on error
            if state.status not in ("idle", "enriching"):
                await state.set_status("idle")

    asyncio.create_task(_run())
    return {"status": "started"}


# ── Email Enrichment Endpoint (Website Scraping Only) ─────────────────────────

@app.post("/api/enrich/email")
async def enrich_email_endpoint(current_user: User = Depends(get_current_user)):
    """Start email enrichment via website scraping (fallback for contacts without emails)."""
    if state.status not in ("idle", "done", "failed"):
        return JSONResponse({"error": "Pipeline busy"}, status_code=409)

    async def _run():
        # Detect if this session was a test run (heuristic: ≤5 businesses)
        is_test = False
        progress_fn = TestModeProgress(state.progress) if is_test else state.progress
        
        try:
            state.cancel_requested = False
            await state.set_status("enriching")
            loop = asyncio.get_running_loop()
            
            # Website Scraping for emails/phones (fallback for those missing after Apify/Apollo)
            from playwright.async_api import async_playwright
            from enrich import scrape_company_website
            from models.contact import Contact
            
            def website_worker():
                import asyncio
                worker_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(worker_loop)
                
                async def _scrape_all():
                    async with async_playwright() as p:
                        browser = await p.chromium.launch(headless=True)
                        context = await browser.new_context(
                            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                        )
                        
                        sem = asyncio.Semaphore(5)
                        
                        async def process_row(i, row):
                            website = getattr(row, "website", "")
                            if not website:
                                return
                                
                            async with sem:
                                if state.cancel_requested:
                                    progress_fn("Email enrichment cancelled.")
                                    return
                                    
                                progress_fn(f"[{i+1}/{len(state.businesses)}] Scraping website for contacts: {row.company_name} ({website})...")
                                contacts_dict = await scrape_company_website(context, website, progress=progress_fn)
                                
                                emails_found = list(dict.fromkeys(contacts_dict.get("emails", [])))
                                phones_found = list(dict.fromkeys(contacts_dict.get("phones", [])))
                                
                                if emails_found:
                                    row.email = emails_found[0]
                                if phones_found:
                                    row.phone = phones_found[0]
                                
                                if emails_found or phones_found:
                                    if not getattr(row, "contacts", None):
                                        row.contacts = []
                                    
                                    max_len = max(len(emails_found), len(phones_found))
                                    for j in range(max_len):
                                        e = emails_found[j] if j < len(emails_found) else ""
                                        ph = phones_found[j] if j < len(phones_found) else ""
                                        if e or ph:
                                            c = Contact(
                                                first_name="",
                                                last_name="Contact",
                                                full_name="Company Contact",
                                                title="Website Scraping",
                                                seniority="Unknown",
                                                email=e,
                                                email_confidence=0.5 if e else None,
                                                email_source="website_scrape" if e else None,
                                                phone=ph,
                                                linkedin_url=""
                                            )
                                            row.contacts.append(c)

                        tasks = [process_row(i, row) for i, row in enumerate(state.businesses)]
                        if tasks:
                            await asyncio.gather(*tasks)
                        await browser.close()
                try:
                    worker_loop.run_until_complete(_scrape_all())
                finally:
                    worker_loop.close()

            await loop.run_in_executor(None, website_worker)
            
            if isinstance(progress_fn, TestModeProgress):
                progress_fn.flush_summary()
            
            # Snapshot enriched results as a session to preserve history
            from icp import load_cached_icp
            icp = load_cached_icp()
            keywords = icp.search_keywords if icp else []
            try:
                sid = save_session(
                    keywords=keywords,
                    icp=icp,
                    source_pipeline="enrichment",
                    session_id=state.current_session_id,
                    businesses=state.businesses
                )
                state.progress(f"Session saved to history: {sid[:8]}…")
            except Exception as se:
                state.progress(f"Warning: session snapshot failed: {se}")
            
            await state.push("__DONE__")
        except Exception as e:
            err_str = traceback.format_exc()
            state.progress(f"Error: {repr(e)}")
            print(err_str)
        finally:
            await state.set_status("idle")

    asyncio.create_task(_run())
    return {"status": "started"}


# ── Apify Status Endpoint ─────────────────────────────────────────────────────

@app.get("/api/apify/status")
async def apify_status_endpoint(current_user: User = Depends(require_role("admin"))):
    """Check if Apify is correctly configured. Admin only."""
    from config import APIFY_API_KEY, APIFY_LINKEDIN_EMPLOYEES_ACTOR_ID
    if APIFY_API_KEY:
        return {
            "status": "ok",
            "configured": True,
            "actor_id": APIFY_LINKEDIN_EMPLOYEES_ACTOR_ID
        }
    return {"status": "error", "configured": False, "message": "APIFY_API_KEY not set in .env"}


@app.get("/api/apollo/status")
async def apollo_status_endpoint(current_user: User = Depends(get_current_user)):
    """Check if Apollo.io is correctly configured."""
    from config import APOLLO_API_KEY
    if APOLLO_API_KEY:
        return {
            "status": "ok",
            "configured": True,
        }
    return {"status": "error", "configured": False, "message": "APOLLO_API_KEY not set in .env"}


# ── Data Endpoints ────────────────────────────────────────────────────────────

@app.get("/api/leads")
async def get_leads(source: str = "auto", session_id: str = None, current_user: User = Depends(get_current_user)):
    """Return all leads as JSON. Uses in-memory state or historical sessions."""
    rows = []
    
    # If requesting current active session (or no session_id given), use in-memory state
    if session_id and session_id == state.current_session_id:
        rows = [b.model_dump() for b in state.businesses]
    elif session_id:
        # Requesting a specific older session
        from session_store import get_session
        sess = get_session(session_id)
        if sess and "companies" in sess:
            rows = sess["companies"]
    
    # Fallback: if no rows found and we have in-memory businesses, return those
    if not rows and state.businesses:
        rows = [b.model_dump() for b in state.businesses]

    if rows:
        # Normalize scores and contacts for response
        for r in rows:
            if 'contacts' not in r or not isinstance(r['contacts'], list):
                r['contacts'] = []

            try:
                val = r.get("icp_match_score") or r.get("fit_score", 0) or 0
                r["fit_score"] = int(val)
                r["icp_match_score"] = int(val)
            except (ValueError, TypeError):
                r["fit_score"] = 0
                r["icp_match_score"] = 0
                
        # Sort by score descending
        rows.sort(key=lambda x: x["icp_match_score"], reverse=True)
        return {"leads": rows, "source": "memory" if session_id == state.current_session_id else "history", "total": len(rows)}

    return {"leads": [], "source": None, "total": 0}


@app.get("/api/leads/stats")
async def get_stats(session_id: str = None, current_user: User = Depends(get_current_user)):
    """Return summary statistics for the leads."""
    result = await get_leads(session_id=session_id, current_user=current_user)
    leads = result["leads"]

    if not leads:
        return {
            "total": 0, "avg_score": 0,
            "emails_found": 0, "phones_found": 0,
            "perfect": 0, "good": 0, "possible": 0, "poor": 0,
            "source": None
        }

    total = len(leads)
    scores = [l.get("fit_score", 0) for l in leads]
    avg_score = sum(scores) / total if total else 0

    return {
        "total": total,
        "avg_score": round(avg_score, 1),
        "emails_found": sum(1 for l in leads if l.get("email")),
        "phones_found": sum(1 for l in leads if l.get("phone")),
        "perfect": sum(1 for s in scores if s >= 80),
        "good": sum(1 for s in scores if 60 <= s < 80),
        "possible": sum(1 for s in scores if 40 <= s < 60),
        "poor": sum(1 for s in scores if s < 40),
        "source": result["source"]
    }


@app.get("/api/export")
async def export_excel(session_id: str = None, current_user: User = Depends(get_current_user)):
    """Generate and return the Excel file from memory or history."""
    businesses_to_export = []
    
    if session_id and session_id == state.current_session_id:
        # Requesting active session
        businesses_to_export = state.businesses
    elif session_id:
        # Requesting older session
        from session_store import get_session
        from models.business import Business
        sess = get_session(session_id) if session_id else None
        if sess and "companies" in sess:
            businesses_to_export = [Business(**c) for c in sess["companies"]]
    
    # Fallback: use in-memory businesses if nothing found yet
    if not businesses_to_export and state.businesses:
        businesses_to_export = state.businesses
            
    if not businesses_to_export:
        return JSONResponse(status_code=404, content={"error": "No data to export. Run a search first."})

    from export import run_export
    output = run_export(businesses=businesses_to_export, progress=state.progress)
    if output and os.path.exists(output):
        return FileResponse(
            path=output,
            filename="final_leads.xlsx",
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    return JSONResponse(status_code=404, content={"error": "Export failed"})


# ── SSE Progress Stream ──────────────────────────────────────────────────────

@app.get("/api/progress")
async def progress_stream(request: Request):
    """SSE endpoint — streams real-time progress messages to the frontend."""
    # SSE does not support Authorization headers easily, read token from query
    token = request.query_params.get("token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    queue = await state.subscribe()

    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f"data: {json.dumps({'message': message})}\n\n"
                except asyncio.TimeoutError:
                    # Send keepalive
                    yield f"data: {json.dumps({'keepalive': True})}\n\n"
        finally:
            await state.unsubscribe(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


# ── Run ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
