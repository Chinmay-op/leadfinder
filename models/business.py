from pydantic import BaseModel, Field
from typing import Optional, Literal
from models.contact import Contact


class Business(BaseModel):
    company_name: str
    industry: Optional[str] = None
    linkedin_url: Optional[str] = None
    website: Optional[str] = None
    description: Optional[str] = None
    company_size: Optional[str] = None
    location: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    fit_score: Optional[int] = None
    fit_reason: Optional[str] = None
    source: Optional[Literal["yahoo_linkedin", "google_maps", "linkedin"]] = "yahoo_linkedin"
    address: Optional[str] = None
    rating: Optional[float] = None
    total_reviews: Optional[int] = None
    icebreaker: Optional[str] = None
    sheets_row: Optional[int] = None
    status: Optional[str] = "pending"
    session_id: Optional[str] = None
    # v3 fields
    contacts: list[Contact] = []
    icp_match_score: Optional[int] = None
    icp_match_reason: Optional[str] = None

