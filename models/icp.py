from pydantic import BaseModel
from typing import Optional


class ICP(BaseModel):
    """Ideal Customer Profile — defines who we're looking for."""
    target_roles: list[str]                    # e.g. ["Head of Operations", "CTO"]
    target_industries: list[str]               # e.g. ["Logistics", "Manufacturing"]
    company_size_min: int = 50
    company_size_max: int = 5000
    pain_points: list[str]                     # e.g. ["manual tracking", "high labor"]
    search_keywords: list[str]                 # LinkedIn search queries (3–5)
    exclusions: list[str]                      # e.g. ["B2C", "startups under 10"]
    decision_maker_departments: list[str]      # e.g. ["Engineering", "Operations"]
    value_proposition: Optional[str] = None    # 1-sentence summary of what we offer
