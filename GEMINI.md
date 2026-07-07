# AI Lead Finder — Project Blueprint

## What this project does
This is a Python tool (with a FastAPI web interface) for an AI services company.
It finds potential client companies by searching LinkedIn via Yahoo Search,
scores each company using AI (Groq / Azure OpenAI), enriches contact data via custom web scraping,
and exports a ranked list to CSV and a formatted Excel file.

## Our company context
We are an AI services company providing:
- Custom AI agent development
- AI workflow automation  
- AI chatbot development
- Machine learning model development
- Data pipeline automation

Our ideal customers are mid-size to enterprise companies (50–5000 employees)
with manual repetitive processes, large data volumes, or customer service
operations that could benefit from AI automation.

## Two input modes
Mode A: User describes their service → AI extracts search keywords
Mode B: User types a keyword directly → used as-is

## Tech stack
- Python 3.11+
- FastAPI & Server-Sent Events (Web UI and Progress Streaming)
- playwright (browser automation)
- bs4 / BeautifulSoup (HTML parsing and contact scraping)
- groq & openai (AI Extraction & Scoring using Llama 3.1 and GPT-5)
- requests (Custom web scraping for contacts)
- python-dotenv (env vars)
- pydantic (data models)
- openpyxl (Excel export)

## API keys needed
- GROQ_API_KEY → For primary AI extraction/scoring
- AZURE_OPENAI_KEY → For fallback AI extraction/scoring
(Stored in .env file only. Never hardcoded, except Azure fallback endpoints if explicitly configured).

## File structure
.env                  - API keys
requirements.txt      - all pip dependencies
GEMINI.md             - this file
config.py             - all settings, prompts, constants
models/business.py    - Pydantic data model for a company
app.py                - FastAPI web server and background task orchestrator
main.py               - Yahoo scraper + AI keyword extractor + AI scorer
enrich.py             - Custom contact enrichment (emails and phones)
export.py             - CSV + Excel export with color coding and summary sheets
static/               - Frontend assets (HTML, CSS, JS)

## Data model (models/business.py)
Each company record has:
company_name, industry, linkedin_url, website,
description, company_size, location,
email, phone, fit_score (0-100), fit_reason

## Scraping logic (main.py)
- Search URL: `https://search.yahoo.com/search?p={keyword}+site:linkedin.com/company`
- Generates 3 keyword variations per query to pull ~30 results total.
- Max total companies: 100.
- Deduplicate by company_name (case insensitive).
- Parse HTML down to text snippets using BeautifulSoup.
- Pass text to Groq/Azure AI to extract structured company JSON.
- Score each company with a second AI call.
- Save to `businesses_data.csv`.

## AI prompt for keyword extraction
Given a description of an AI services company,
return 5 specific B2B industry keywords to find potential customers.
Return as JSON: { "keywords": ["...", "...", "...", "...", "..."] }

## AI prompt for scraping
From search result text, extract company info as JSON array:
[{ company_name, linkedin_url, website, industry, description, company_size }]
Only return companies. Ignore job postings and individual profiles.
Strip any markdown code blocks before parsing JSON.

## AI scoring prompt
Rate each company's fit for our AI services on a scale of 0-100.
Return JSON: { "fit_score": number, "fit_reason": "one sentence" }
Score guide:
80-100 = perfect fit (clear AI automation use cases)
60-79  = good fit (likely pain points)
40-59  = possible fit
0-39   = poor fit

## Contact Enrichment (enrich.py)
- Reads `businesses_data.csv`.
- Uses `requests` and `BeautifulSoup` to visit each company's website directly.
- Scrapes the homepage (and attempts to find a Contact page) for emails and phones using Regex.
- Skips rows where website is empty.
- Respectful 1-second delay between domains.
- Save to `enriched_leads.csv`.

## Export (export.py)
1. Print top 20 companies as a table in terminal.
2. Save to `final_leads.xlsx` containing two sheets:
   - **Lead Results**: Bold header row, auto-sized columns, color-coded rows (Green 80+, Yellow 60-79, Orange 40-59, Red <40).
   - **Score Summary**: Aggregated tiers (Perfect, Good, Possible, Poor) with total counts and company names.
3. Print summary: total / avg score / emails found / phones found.

## Error handling rules
- Retry AI calls with exponential backoff and fallback providers (Groq -> Azure OpenAI).
- Aggressively clean JSON responses to strip ` ```json ` blocks.
- If scraping fails, keep original values and continue.
- Print clear progress messages, which are piped to the Web UI via SSE.

## Run order
Using Web UI:
`python app.py` -> Open http://localhost:8000/

Using CLI:
`python main.py`              # scrape + score → businesses_data.csv
`python main.py "keyword"`    # same but with direct keyword
`python enrich.py`            # enrich → enriched_leads.csv
`python export.py`            # export → final_leads.xlsx