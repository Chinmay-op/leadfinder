from pydantic import BaseModel
from typing import Optional, Literal


class Contact(BaseModel):
    """A person discovered at a target company."""
    first_name: str
    last_name: str
    full_name: str
    title: str
    department: Optional[str] = None
    seniority: Optional[Literal[
        "C-Level", "VP", "Director", "Manager", "Individual", "Unknown"
    ]] = "Unknown"
    linkedin_url: Optional[str] = None
    email: Optional[str] = None
    email_confidence: Optional[float] = None    # 0.0–1.0
    email_source: Optional[str] = None          # "apify" | "snov" | "regex" | "website_scrape"
    phone: Optional[str] = None
    icebreaker: Optional[str] = None
    company_name: Optional[str] = None          # denormalised for export
    # Apify enrichment fields
    headline: Optional[str] = None              # LinkedIn headline
    location: Optional[str] = None              # Profile location
    photo_url: Optional[str] = None             # Profile photo URL

