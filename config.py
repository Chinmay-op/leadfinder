import os
from dotenv import load_dotenv

load_dotenv()

APOLLO_API_KEY = os.getenv("APOLLO_API_KEY")
AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")


# Constants
MAX_PAGES_PER_KEYWORD = 3
MAX_COMPANIES = 100
DELAY_BETWEEN_AI_CALLS = 0.5
DELAY_BETWEEN_APOLLO_CALLS = 2.0

# v2 API keys
APIFY_API_KEY = os.getenv("APIFY_API_KEY", "")
APIFY_ACTOR_ID = os.getenv("APIFY_ACTOR_ID", "compass/crawler-google-places")

GOOGLE_SHEETS_CREDENTIALS_PATH = os.getenv("GOOGLE_SHEETS_CREDENTIALS_PATH", "credentials.json")
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")

# Apify LinkedIn Employees Scraper
APIFY_LINKEDIN_EMPLOYEES_ACTOR_ID = os.getenv(
    "APIFY_LINKEDIN_EMPLOYEES_ACTOR_ID", "harvestapi/linkedin-company-employees"
)
APIFY_EMPLOYEE_SCRAPER_MODE = os.getenv(
    "APIFY_EMPLOYEE_SCRAPER_MODE", "Full + email search ($12 per 1k)"
)
APIFY_MAX_EMPLOYEES_PER_COMPANY = int(os.getenv("APIFY_MAX_EMPLOYEES_PER_COMPANY", "10"))

ICP_SCORE_THRESHOLD = int(os.getenv("ICP_SCORE_THRESHOLD", "50"))
SESSION_ICP_PATH = "session_icp.json"

ICEBREAKER_SYSTEM_PROMPT = """
You are a senior B2B sales specialist. Given a company's website content, write a personalized 2-3 sentence cold outreach opening that references something SPECIFIC about this company, shows genuine understanding of their business, ends with a natural curiosity hook, is professional but conversational (NOT salesy), and is 40-60 words maximum. Return ONLY the icebreaker text, no preamble.
"""


# Prompts
KEYWORD_EXTRACTION_PROMPT = """
Given the user's description of the services they offer,
return 5 specific B2B industry keywords that would identify their TARGET CUSTOMERS on LinkedIn.
DO NOT return keywords for the services the user provides. We want to find the companies that NEED their services.
For example, if the user offers "medical tourism", the target companies might be "insurance provider", "corporate wellness program", "self-insured employer", NOT "medical tourism company" (which would be a competitor).
Return as JSON: {{ "keywords": ["...", "...", "...", "...", "..."] }}

Description:
{description}
"""

SCRAPING_PROMPT = """
From the following Google search result HTML, extract company info as a JSON array of objects.
Keys should exactly be: company_name, linkedin_url
Only return companies. Ignore job postings and individual profiles.
Return ONLY valid JSON array.

HTML:
{html}
"""

SCORING_PROMPT = """
Rate this company's fit as a potential client based on their profile.
Target Customer Description / Our Services:
{description}

Score guide:
80-100 = perfect fit (matches target description exactly)
60-79  = good fit (likely a match based on industry/size)
40-59  = possible fit
0-39   = poor fit (competitor, AI provider, or completely unrelated industry)

Return ONLY JSON: {{ "fit_score": number, "fit_reason": "one sentence" }}

Company Info:
{company_info}
"""

# v3 prompts
ICP_SYSTEM_PROMPT = """
You are a B2B sales strategist. The user will provide a keyword or description of the service they offer.
Your goal is to define the Ideal Customer Profile (ICP) for a cold outreach campaign to find B2B companies that NEED this service.

CRITICAL: Do NOT return keywords that describe the user's service itself. Instead, return keywords to find their TARGET CUSTOMERS on LinkedIn.

Return ONLY valid JSON (no markdown, no explanation) with these exact keys:
{{
  "target_roles": ["Return EXACTLY 15 UNIQUE job titles. These must be REAL titles that actual people use on LinkedIn — titles you would find when searching LinkedIn right now. ABSOLUTE RULES: (1) Format is ALWAYS 'Department/Function + Seniority' like 'Operations Manager', 'Plant Director', 'Procurement Head'. NEVER put seniority first like 'Director Operations' or 'VP Safety' — that is not how people write titles on LinkedIn. (2) NEVER return a bare word like 'Safety', 'Operations', 'Procurement' — those are departments, not job titles. (3) NO duplicates or reorderings — 'Safety Manager' and 'Manager Safety' are the same title, only include the natural one. (4) NO invented titles — if you wouldn't find 100+ people with that exact title on LinkedIn, don't include it. (5) Mix seniority levels: use Manager, Director, Head of, VP, Supervisor, Coordinator, Lead across your 15 titles. (6) Include at least 2-3 cross-functional titles (e.g. 'General Manager', 'COO', 'Site Director') that exist in any company. (7) GOOD: 'EHS Manager', 'Operations Director', 'Site Manager', 'Head of Procurement', 'VP Operations'. BAD: 'Safety', 'Director Safety', 'Head Safety', 'VP Safety', 'Safety VP'."],
  "target_industries": ["list of 3-5 relevant industries that need the service"],
  "company_size_min": <integer, minimum employees>,
  "company_size_max": <integer, maximum employees>,
  "pain_points": ["list of 3-5 specific pain points these target companies face that the user's service solves"],
  "search_keywords": ["list of 3-5 LinkedIn search queries to find the target companies (NOT the user's competitors)"],
  "exclusions": ["list of 2-3 company types to exclude (e.g. competitors offering the same service)"],
  "decision_maker_departments": ["list of 2-4 departments"],
  "value_proposition": "one sentence describing the value the user's service offers to this ICP"
}}

User's Service Offering:
{user_input}
"""

ICP_SCORING_PROMPT = """
You are evaluating whether a company is a good fit as a potential B2B client.

ICP criteria:
- Target industries: {target_industries}
- Target company size: {company_size_min}-{company_size_max} employees
- Pain points we solve: {pain_points}
- Exclusions (do NOT score these high): {exclusions}

Company details:
Name: {company_name}
Industry: {industry}
Size: {company_size}
Description: {description}

Score this company 0-100 on how well it matches the ICP. Return ONLY a JSON object:
{{"score": <integer 0-100>, "reason": "<one sentence referencing ICP criteria>"}}
"""

