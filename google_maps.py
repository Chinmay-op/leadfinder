"""
Google Maps Lead Scraper — via Apify API
Fetches business listings from Google Maps and converts them to Business objects.
"""
from __future__ import annotations

import csv
from apify_client import ApifyClient
from config import APIFY_API_KEY, APIFY_ACTOR_ID
from models.business import Business


def _default_progress(msg: str):
    """Default progress callback — prints to terminal."""
    print(msg)


def scrape_google_maps(query: str, location: str, max_results: int = 50, progress=None) -> list[Business]:
    """Scrape Google Maps via Apify and return a list of Business objects.

    Args:
        query: Search query string (e.g. "restaurants").
        location: Geographic location filter (e.g. "New York").
        max_results: Maximum number of places to crawl.
        progress: Optional callback for progress messages.

    Returns:
        Deduplicated list of Business objects with websites.
    """
    if progress is None:
        progress = _default_progress

    try:
        progress(f"Starting Google Maps scrape for: {query} {location}")

        actor_input = {
            "searchStringsArray": [f"{query} {location}"],
            "maxCrawledPlacesPerSearch": max_results,
            "language": "en",
        }

        client = ApifyClient(APIFY_API_KEY)
        run = client.actor(APIFY_ACTOR_ID).call(run_input=actor_input)

        results: list[Business] = []
        seen: set[str] = set()

        dataset_items = client.dataset(run["defaultDatasetId"]).iterate_items()
        for item in dataset_items:
            website = item.get("website") or ""
            if not website:
                continue

            name = item.get("title", "")
            name_key = name.lower().strip()
            if name_key in seen:
                continue
            seen.add(name_key)

            business = Business(
                company_name=name,
                website=website,
                address=item.get("address"),
                phone=item.get("phone"),
                industry=item.get("categoryName"),
                rating=item.get("totalScore"),
                total_reviews=item.get("reviewsCount"),
                description=item.get("description", ""),
                source="google_maps",
                status="pending",
            )
            results.append(business)

        progress(f"Fetched {len(results)} leads from Google Maps")
        return results

    except Exception as e:
        if progress:
            progress(f"Error scraping Google Maps: {e}")
        return []


def run_google_maps(query: str, location: str, state) -> None:
    """Thread-safe wrapper that scrapes Google Maps and saves results to CSV.

    Args:
        query: Search query string.
        location: Geographic location filter.
        state: PipelineState instance for SSE broadcasting.
    """
    state.progress("Google Maps scrape started...")

    results = scrape_google_maps(query, location, progress=state.progress)

    if not results:
        state.progress("Google Maps scrape returned no results.")
        return

    keys = [
        "company_name", "linkedin_url", "website", "industry", "description",
        "company_size", "location", "email", "phone", "fit_score", "fit_reason",
        "source", "address", "rating", "total_reviews",
        "icebreaker", "status",
    ]

    try:
        with open("businesses_data.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
            writer.writeheader()
            for b in results:
                writer.writerow(b.model_dump())
        state.progress(f"Saved {len(results)} companies to businesses_data.csv")
    except Exception as e:
        state.progress(f"Error saving Google Maps results: {e}")

    state.progress("Google Maps scrape complete.")
