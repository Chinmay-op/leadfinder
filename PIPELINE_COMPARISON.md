# Pipeline Comparison: Apify vs Apollo

A side-by-side breakdown of both lead discovery pipelines in the Lead Finder app.

---

## Architecture Overview

### Apify Pipeline (Default)
```
User Input → AI generates ICP → Yahoo Search (Playwright browser) → AI extracts companies from HTML
→ AI scores each company (GPT-5) → Apify LinkedIn Employee Scraper → Website scraping (Playwright)
→ Final leads with contacts & emails
```

### Apollo Pipeline
```
User Input → AI generates ICP → Apollo.io Organization Search API → AI scores each company (GPT-5)
→ Apollo.io People Search API → Website scraping (Playwright) → Final leads with contacts & emails
```

---

## Feature Comparison

| Feature | Apify Pipeline | Apollo Pipeline |
|---|---|---|
| **Company Discovery** | Yahoo Search → LinkedIn scraping | Apollo.io Organization Search API |
| **Company Data Source** | LinkedIn company profiles | Apollo's 275M+ contact database |
| **AI Scoring** | ✅ GPT-5 ICP scoring | ✅ GPT-5 ICP scoring (same) |
| **Contact Discovery** | Apify LinkedIn Employee Scraper | Apollo People Search API |
| **Email Discovery** | Apify SMTP validation + website scrape | Apollo built-in email + website scrape |
| **Phone Numbers** | Website scraping only | Apollo database + website scraping |
| **LinkedIn URLs** | ✅ Always available (scraped from LI) | ✅ Available from Apollo profiles |
| **Contact Photos** | ✅ From LinkedIn profiles | ✅ From Apollo profiles |
| **Job Title Matching** | Role expansion algorithm (20 keywords) | Direct title search via API |
| **Email Enrichment Fallback** | ✅ Playwright website scraping | ✅ Playwright website scraping (same) |
| **Browser Required** | ✅ Yes (Playwright for Yahoo + enrichment) | ⚠️ Only for email enrichment step |
| **Test Mode** | 5 companies, 3 for contacts | 5 companies, 3 for contacts |
| **Session History** | ✅ Saved to JSON | ✅ Saved to JSON (same) |
| **Excel Export** | ✅ Color-coded XLSX | ✅ Color-coded XLSX (same) |

---

## Pros & Cons

### Apify Pipeline

| Pros | Cons |
|---|---|
| ✅ **Deeper LinkedIn data** — scrapes actual LinkedIn profiles with full work history, education, skills | ❌ **Slow** — browser-based scraping takes 5-15 minutes per run |
| ✅ **SMTP-validated emails** — Apify's $12/1k mode does real email verification | ❌ **Browser dependency** — needs Playwright/Chromium for Yahoo scraping |
| ✅ **Role expansion algorithm** — expands "Plant Manager" into 20+ synonym titles | ❌ **Fragile** — Yahoo can change HTML structure, breaking the scraper |
| ✅ **More detailed profiles** — full LinkedIn work experience, education, skills | ❌ **Anti-bot risk** — Yahoo/LinkedIn can rate-limit or block scrapers |
| ✅ **Proven pipeline** — battle-tested in production | ❌ **Two API keys needed** — both Apify + Azure OpenAI |
| ✅ **Retry logic with no-filter fallback** — companies with 0 contacts get a second pass | ❌ **Higher cost per lead** — $12/1k profiles for email mode |
| ✅ **Rich contact metadata** — headline, current positions, photo | ❌ **Sequential processing** — 1 Apify call per company = slow for 10 companies |

### Apollo Pipeline

| Pros | Cons |
|---|---|
| ✅ **Fast** — pure API calls, no browser scraping for discovery | ❌ **Shallower profiles** — less detailed than full LinkedIn scrapes |
| ✅ **Free tier available** — search is free, only enrichment costs credits | ❌ **Credit limits** — free tier has ~100 credits/month |
| ✅ **No browser needed** for company/contact discovery | ❌ **Email quality varies** — some emails are "guessed" not verified |
| ✅ **Reliable** — structured API, no HTML parsing fragility | ❌ **Rate limits on free tier** — may hit 429 errors with heavy use |
| ✅ **Built-in company database** — 275M+ contacts, structured data | ❌ **Less LinkedIn depth** — no full work history or education |
| ✅ **Single API key** — just APOLLO_API_KEY + Azure OpenAI | ❌ **Database coverage gaps** — smaller companies may not be in Apollo |
| ✅ **Direct domain-based search** — no need to scrape LinkedIn URLs first | ❌ **No SMTP email verification** — relies on Apollo's own email scoring |
| ✅ **Simpler infrastructure** — works on servers without Chromium | ❌ **API changes** — Apollo occasionally deprecates endpoints |

---

## Cost Analysis

### Apify Pipeline

| Component | Cost | Notes |
|---|---|---|
| Yahoo Search | **Free** | Browser scraping, no API cost |
| AI Scoring (Azure GPT-5) | **~$0.01/company** | ~100 tokens per scoring call |
| Apify Employee Scraper | **$12 per 1,000 profiles** | "Full + email search" mode |
| Website Enrichment | **Free** | Playwright scraping |
| **Typical run (10 companies, 10 contacts each)** | **~$1.30** | 100 profiles × $12/1k + AI |

### Apollo Pipeline

| Component | Cost | Notes |
|---|---|---|
| Organization Search | **Free** | No credit cost |
| AI Scoring (Azure GPT-5) | **~$0.01/company** | Same as Apify pipeline |
| People Search | **Free** | api_search doesn't consume credits |
| People Enrichment | **1 credit per contact** | Only if using bulk_match |
| Website Enrichment | **Free** | Playwright scraping |
| **Typical run (10 companies, 5 contacts each)** | **~$0.50** | 50 credits + AI costs |
| **Free tier budget** | **~100 credits/month** | ~2 full runs per month |

---

## Data Quality Comparison

| Dimension | Apify | Apollo | Winner |
|---|---|---|---|
| **Company name accuracy** | ⭐⭐⭐⭐ (from LinkedIn) | ⭐⭐⭐⭐⭐ (structured DB) | Apollo |
| **Company description** | ⭐⭐⭐ (AI-extracted from snippets) | ⭐⭐⭐⭐ (Apollo's own descriptions) | Apollo |
| **Industry classification** | ⭐⭐⭐ (AI-inferred) | ⭐⭐⭐⭐⭐ (Apollo's taxonomy) | Apollo |
| **Employee count** | ⭐⭐ (sometimes missing) | ⭐⭐⭐⭐ (estimated_num_employees) | Apollo |
| **Contact name accuracy** | ⭐⭐⭐⭐⭐ (from LinkedIn) | ⭐⭐⭐⭐ (from Apollo DB) | Apify |
| **Job title accuracy** | ⭐⭐⭐⭐⭐ (current LinkedIn title) | ⭐⭐⭐⭐ (may be outdated) | Apify |
| **Email accuracy** | ⭐⭐⭐⭐⭐ (SMTP validated) | ⭐⭐⭐ (mix of verified/guessed) | Apify |
| **Phone numbers** | ⭐⭐ (rare from LinkedIn) | ⭐⭐⭐ (Apollo has some) | Apollo |
| **LinkedIn profile URLs** | ⭐⭐⭐⭐⭐ (always present) | ⭐⭐⭐⭐ (usually present) | Apify |
| **Overall freshness** | ⭐⭐⭐⭐⭐ (real-time scrape) | ⭐⭐⭐ (database may lag) | Apify |

---

## Speed Comparison

| Phase | Apify Pipeline | Apollo Pipeline |
|---|---|---|
| ICP Generation | ~5 seconds | ~5 seconds |
| Company Discovery | **3-8 minutes** (browser scraping) | **10-30 seconds** (API calls) |
| AI Scoring | ~30 seconds (same) | ~30 seconds (same) |
| Contact Discovery | **5-15 minutes** (Apify actor runs) | **30-60 seconds** (API calls) |
| Email Enrichment | 1-3 minutes (same) | 1-3 minutes (same) |
| **Total** | **10-25 minutes** | **3-6 minutes** |

---

## When to Use Which

### Use **Apify Pipeline** when:
- 🎯 You need **verified emails** (SMTP-validated)
- 📋 You want **detailed LinkedIn profiles** (work history, education, skills)
- 💰 You have Apify credits/budget and time isn't critical
- 🔍 You need the **freshest data** (real-time LinkedIn scrape)
- 🏢 Targeting companies that are well-represented on LinkedIn

### Use **Apollo Pipeline** when:
- ⚡ You need results **fast** (minutes instead of 15-25 min)
- 💸 You're on a **tight budget** or using the free tier
- 🖥️ Running on a server **without Chromium** (API-only for discovery)
- 📊 You want **structured company data** (industry, size, location)
- 📞 You need **phone numbers** (Apollo has more than LinkedIn scraping)
- 🧪 You're **testing/iterating** on ICP and need quick feedback

---

## Technical Differences

| Aspect | Apify | Apollo |
|---|---|---|
| **Dependencies** | Playwright, BeautifulSoup, Apify API | requests only (for discovery) |
| **Server Requirements** | Chromium browser required | No browser for discovery |
| **Deployment Complexity** | Higher (browser + API) | Lower (API-only for core) |
| **Failure Modes** | HTML changes, anti-bot, timeouts | Rate limits, API deprecation |
| **Scalability** | Limited by browser resources | Limited by API credits |
| **Offline Capability** | None | None |

---

## Recommendation

> **For production cold outreach**: Use **Apify** — the SMTP-validated emails are worth the extra time and cost. Bad emails = bounces = damaged sender reputation.
>
> **For research & prospecting**: Use **Apollo** — fast iteration, good enough data quality, and free tier lets you explore without cost commitment.
>
> **Best of both worlds**: Use **Apollo for discovery**, then cherry-pick the best 5-10 companies and run them through **Apify for deep contact enrichment**.
