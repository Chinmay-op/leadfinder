# Antigravity Build Prompt — AI Lead Finder v2 Upgrade

## Project Context

You are upgrading an existing Python application called **AI Lead Finder**. The project currently has these files:
- `app.py` — FastAPI server with SSE progress streaming
- `main.py` — Playwright scraper targeting Yahoo Search + LinkedIn, Groq/Azure AI scoring
- `enrich.py` — BeautifulSoup + regex contact enrichment
- `export.py` — openpyxl Excel generation
- `config.py` — env var loading, prompt constants
- `models/business.py` — Pydantic `Business` model

**Critical constraint: DO NOT break, remove, or rename any existing functionality.** All v1 features must continue to work exactly as before. Every change is additive only.

---

## What To Build

### TASK 1 — Extend the Business Pydantic model (`models/business.py`)

Add these optional fields to the existing `Business` class. Do not touch any existing fields:

```python
source: Optional[Literal["yahoo_linkedin", "google_maps"]] = "yahoo_linkedin"
address: Optional[str] = None
rating: Optional[float] = None
total_reviews: Optional[int] = None
anymail_email: Optional[str] = None
anymail_confidence: Optional[float] = None
icebreaker: Optional[str] = None
sheets_row: Optional[int] = None
status: Optional[str] = "pending"
```

Required imports to add: `from typing import Literal` (add to existing `Optional` import).

---

### TASK 2 — Create `google_maps.py`

Build a new module that scrapes Google Maps via the Apify API.

**Function: `scrape_google_maps(query, location, max_results=50, progress=None) -> list[Business]`**
- Build actor input: `{"searchStringsArray": [f"{query} {location}"], "maxCrawledPlacesPerSearch": max_results, "language": "en"}`
- Use `ApifyClient(APIFY_API_KEY).actor(APIFY_ACTOR_ID).call(run_input=actor_input)`
- Poll with `run["defaultDatasetId"]` and iterate items.
- Map each item to `Business` using this field mapping:
  - `item["title"]` → `company_name`
  - `item["website"]` → `website`
  - `item["address"]` → `address`
  - `item["phone"]` → `phone`
  - `item["categoryName"]` → `industry`
  - `item["totalScore"]` → `rating`
  - `item["reviewsCount"]` → `total_reviews`
  - `item.get("description", "")` → `description`
  - Always set `source="google_maps"`, `status="pending"`
- Discard any item where `website` is None or empty string.
- Deduplicate by `company_name.lower().strip()`.
- If `progress` is not None, call `progress(f"Fetched {len(results)} leads from Google Maps")` after completion.
- Wrap entire function in try/except; log errors and return empty list on failure.

**Function: `run_google_maps(query, location, state)`**
- Thread-safe wrapper. Calls `scrape_google_maps()`.
- Saves results to `businesses_data.csv` by converting Business list to dicts.
- Emits SSE events via `state.broadcast()` before and after.

**Imports needed:** `from apify_client import ApifyClient`, `from config import APIFY_API_KEY, APIFY_ACTOR_ID`, `from models.business import Business`

---

### TASK 3 — Create `anymail_finder.py`

Build a module that queries the AnyMail Finder REST API.

**Function: `extract_domain(website: str) -> str`**
- Use `urllib.parse.urlparse(website).netloc`.
- Strip leading `www.`.
- Return domain string.

**Function: `find_email_for_company(company_name, domain, progress=None) -> tuple[str|None, float|None]`**
- Sleep 0.5 s before every call: `import time; time.sleep(0.5)`
- POST to `https://api.anymailfinder.com/v5.0/search/company.json`
- Payload: `{"api_key": ANYMAIL_API_KEY, "company_name": company_name, "domain": domain}`
- On HTTP 200: return `(response_json["email"], response_json.get("confidence"))`
- On HTTP 404 or result `"not_found"`: return `(None, None)`
- On HTTP 429: log `"AnyMail quota exceeded"` and return `(None, None)`
- On any exception: log the error and return `(None, None)`

**Function: `enrich_leads_with_anymail(leads: list[Business], progress=None) -> list[Business]`**
- For each lead in leads:
  - Skip if `lead.website` is None or empty.
  - Extract domain, call `find_email_for_company`.
  - If email found: set `lead.anymail_email = email`, `lead.anymail_confidence = confidence`.
  - Emit progress event per lead processed.
- Return modified leads list.

**Function: `get_account_status() -> dict`**
- GET `https://api.anymailfinder.com/v5.0/account.json?api_key={ANYMAIL_API_KEY}`
- Return the JSON response dict.
- On error: return `{"error": str(e)}`

**Function: `run_anymail_enrichment(state)`**
- Reads `businesses_data.csv` into list of dicts.
- Converts to `Business` objects.
- Calls `enrich_leads_with_anymail()`.
- Writes updated list back to `enriched_leads.csv`.
- Emits start/finish SSE events.

---

### TASK 4 — Create `icebreaker.py`

Build the IceBreaker generation engine.

**Constants:**
```python
MIN_CONTENT_LENGTH = 100
MAX_CONTENT_LENGTH = 1500
```

**Function: `scrape_website_for_icebreaker(website: str) -> str | None`**
- `requests.get(website, headers=BROWSER_HEADERS, timeout=10)` where `BROWSER_HEADERS` is the same headers dict used in `enrich.py`.
- Parse with BeautifulSoup.
- Remove all `<script>`, `<style>`, `<nav>`, `<footer>` tags using `tag.decompose()`.
- Get text: `soup.get_text(separator=" ", strip=True)`.
- Collapse multiple spaces/newlines with regex: `re.sub(r'\s+', ' ', text)`.
- Truncate to `MAX_CONTENT_LENGTH` characters.
- Return None if `len(text) < MIN_CONTENT_LENGTH` or request raises an exception.

**Function: `generate_icebreaker(company_name, website_text, progress=None) -> str | None`**
- Import `generate_with_retry` from `main.py`.
- Construct prompt:
  ```
  f"Company: {company_name}\n\nWebsite content:\n{website_text}\n\nGenerate a personalized B2B cold outreach icebreaker (2-3 sentences, 40-60 words, professional but conversational, references something specific about this company, ends with a curiosity hook). Return ONLY the icebreaker text."
  ```
- Call `generate_with_retry(prompt, progress)`. The response is plain text, not JSON — use it directly.
- Validate: `10 < len(result.strip()) < 500`. Return `result.strip()` or None if invalid.
- On any exception: return None.

**Function: `run_icebreaker_generation(state)`**
- Read `enriched_leads.csv`; fall back to `businesses_data.csv` if it doesn't exist.
- Convert CSV rows to Business objects.
- Counter: `generated = 0`, `eligible = 0`
- For each lead with a non-empty `website`:
  - `eligible += 1`
  - `text = scrape_website_for_icebreaker(lead.website)`
  - If text: `lead.icebreaker = generate_icebreaker(lead.company_name, text, progress)`, `generated += 1`
  - Emit SSE event: `f"IceBreaker [{generated}/{eligible}]: {lead.company_name}"`
- Write updated leads back to `enriched_leads.csv` (add/update `icebreaker` column).
- Final SSE event: `f"IceBreaker complete: {generated}/{eligible} generated"`

---

### TASK 5 — Create `sheets.py`

Build Google Sheets read/write integration.

**Constants:**
```python
SHEET_COLUMNS = [
    "company_name", "website", "industry", "location", "address",
    "phone", "email", "anymail_email", "anymail_confidence",
    "fit_score", "fit_reason", "icebreaker", "source", "status", "last_updated"
]
```

**Function: `get_worksheet() -> gspread.Worksheet`**
- Authenticate: `gspread.service_account(filename=GOOGLE_SHEETS_CREDENTIALS_PATH)`
- Open: `client.open_by_key(GOOGLE_SHEET_ID).sheet1`
- Return worksheet.

**Function: `read_pending_rows() -> list[Business]`**
- `ws = get_worksheet()`
- `rows = ws.get_all_records()` — returns list of dicts using header row as keys.
- Filter: keep rows where `row.get("status", "").lower() == "pending"`.
- For each pending row: create `Business(**{k: v for k, v in row.items() if k in Business.model_fields})`.
- Set `business.sheets_row = index + 2` (1-indexed header + 1-indexed data).
- Return list.

**Function: `update_row_status(worksheet, row_index, status)`**
- Find column index of "status" in header row (row 1).
- `worksheet.update_cell(row_index, status_col, status)`
- Find column index of "last_updated". `worksheet.update_cell(row_index, ts_col, datetime.utcnow().isoformat())`

**Function: `write_business_to_sheet(worksheet, business: Business)`**
- If `business.sheets_row` is not None: update specific cells for enriched fields.
- Else: `worksheet.append_row([getattr(business, col, "") or "" for col in SHEET_COLUMNS])`

**Function: `run_sheets_trigger(state)`**
- Call `read_pending_rows()`.
- If no pending rows: emit SSE `"No pending rows in Google Sheet"` and return.
- Save businesses to `businesses_data.csv`.
- Emit SSE `f"Found {len(businesses)} pending rows in Google Sheet"`.

**Function: `run_sheets_push(state)`**
- Read `enriched_leads.csv`.
- Convert to Business list.
- Call `write_business_to_sheet()` for each.
- Emit SSE progress every 10 rows.

**Imports:** `import gspread`, `from config import GOOGLE_SHEETS_CREDENTIALS_PATH, GOOGLE_SHEET_ID`, `from datetime import datetime`

---

### TASK 6 — Update `app.py` (additive only)

Add the following to `app.py` without touching any existing endpoints or functions:

**New imports at top:**
```python
from google_maps import run_google_maps
from anymail_finder import run_anymail_enrichment, get_account_status as get_anymail_status
from icebreaker import run_icebreaker_generation
from sheets import run_sheets_trigger, run_sheets_push
```

**New request model:**
```python
class MapsRequest(BaseModel):
    query: str
    location: str = ""
    max_results: int = 50
```

**New endpoints (add after existing endpoints):**
```python
@app.post("/api/scrape/maps")
async def scrape_maps(request: MapsRequest, background_tasks: BackgroundTasks):
    if state.status not in ("idle", "done", "failed"):
        return JSONResponse({"error": "Pipeline busy"}, status_code=409)
    background_tasks.add_task(
        lambda: asyncio.get_event_loop().run_in_executor(
            None, run_google_maps, request.query, request.location, state
        )
    )
    return {"status": "started"}

@app.post("/api/enrich/anymail")
async def enrich_anymail_endpoint(background_tasks: BackgroundTasks):
    background_tasks.add_task(
        lambda: asyncio.get_event_loop().run_in_executor(None, run_anymail_enrichment, state)
    )
    return {"status": "started"}

@app.post("/api/icebreaker")
async def icebreaker_endpoint(background_tasks: BackgroundTasks):
    background_tasks.add_task(
        lambda: asyncio.get_event_loop().run_in_executor(None, run_icebreaker_generation, state)
    )
    return {"status": "started"}

@app.post("/api/sheets/trigger")
async def sheets_trigger_endpoint(background_tasks: BackgroundTasks):
    background_tasks.add_task(
        lambda: asyncio.get_event_loop().run_in_executor(None, run_sheets_trigger, state)
    )
    return {"status": "started"}

@app.post("/api/sheets/push")
async def sheets_push_endpoint(background_tasks: BackgroundTasks):
    background_tasks.add_task(
        lambda: asyncio.get_event_loop().run_in_executor(None, run_sheets_push, state)
    )
    return {"status": "started"}

@app.get("/api/anymail/status")
async def anymail_status_endpoint():
    result = await asyncio.get_event_loop().run_in_executor(None, get_anymail_status)
    return result
```

---

### TASK 7 — Update `export.py` (additive only)

In the Sheet 1 "Lead Results" section:

1. Add `"icebreaker"` to the headers list, after `"fit_reason"`.
2. Add `"anymail_confidence"` to the headers list, after `"email"`.
3. Add `"source"` to the headers list at the end.
4. Update `COL_WIDTH_MAP` to include:
   - `"icebreaker": 60`
   - `"anymail_confidence": 18`
   - `"source": 15`
5. In the CLI summary at the end, add:
   ```python
   icebreakers_generated = sum(1 for r in rows if r.get("icebreaker"))
   print(f"  Icebreakers Generated : {icebreakers_generated}")
   ```

---

### TASK 8 — Update `config.py` (additive only)

Add these lines after the existing `os.getenv` calls. Do not modify existing lines:

```python
APIFY_API_KEY = os.getenv("APIFY_API_KEY", "")
APIFY_ACTOR_ID = os.getenv("APIFY_ACTOR_ID", "compass/crawler-google-places")
ANYMAIL_API_KEY = os.getenv("ANYMAIL_API_KEY", "")
GOOGLE_SHEETS_CREDENTIALS_PATH = os.getenv("GOOGLE_SHEETS_CREDENTIALS_PATH", "credentials.json")
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")

ICEBREAKER_SYSTEM_PROMPT = """
You are a senior B2B sales specialist. Given a company's website content, write a personalized 2-3 sentence cold outreach opening that references something SPECIFIC about this company, shows genuine understanding of their business, ends with a natural curiosity hook, is professional but conversational (NOT salesy), and is 40-60 words maximum. Return ONLY the icebreaker text, no preamble.
"""
```

---

### TASK 9 — Update `requirements.txt`

Append these lines (do not remove any existing lines):
```
apify-client>=1.7.0
gspread>=6.0.0
google-auth>=2.28.0
```

---

## Code Quality Rules

- All new functions must have a docstring.
- All external API calls must be wrapped in try/except.
- Never overwrite an existing CSV field with an empty/None value — check before writing.
- Never import from files that would create circular imports (`icebreaker.py` imports from `main.py`; `main.py` must NOT import from `icebreaker.py`).
- Use `from __future__ import annotations` at the top of any file using `X | Y` union types.
- Match the existing code style in each file (spacing, naming conventions, comment style).

## Testing Checklist (verify before submitting)

- [ ] `POST /api/scrape` still works (v1 Yahoo/LinkedIn unchanged)
- [ ] `POST /api/enrich` still works (v1 regex unchanged)
- [ ] `GET /api/export` or export CLI still produces correct `final_leads.xlsx`
- [ ] `GET /api/progress` SSE stream still connects and receives events
- [ ] `POST /api/scrape/maps` runs without error when `APIFY_API_KEY` is set
- [ ] `POST /api/enrich/anymail` runs without error when `ANYMAIL_API_KEY` is set
- [ ] `POST /api/icebreaker` generates icebreakers for leads with websites
- [ ] `GET /api/anymail/status` returns account info JSON
- [ ] Google Sheets endpoints gracefully fail (log + SSE error event) when credentials are missing
- [ ] `Business` model is backward-compatible (v1 CSVs load without errors)
