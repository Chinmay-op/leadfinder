"""
Session Store — flat-file JSON persistence for pipeline run snapshots.

Each pipeline completion creates a session JSON file under ./sessions/
containing metadata, ICP context, stats, and the full company+contact list
for that specific run.
"""

import csv
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from models.icp import ICP

# ── Constants ─────────────────────────────────────────────────────────────────
SESSIONS_DIR = Path(__file__).parent / "sessions"


def _ensure_dir():
    """Create the sessions directory if it doesn't exist."""
    SESSIONS_DIR.mkdir(exist_ok=True)


def _read_csv(path: str) -> list[dict]:
    """Read a CSV file and return rows as dicts. Returns [] on error."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except (FileNotFoundError, Exception):
        return []


def _parse_contacts(raw: str) -> list[dict]:
    """Parse a JSON-encoded contacts string into a list of contact dicts."""
    if not raw or not raw.strip():
        return []
    try:
        contacts = json.loads(raw)
        if isinstance(contacts, list):
            return contacts
    except (json.JSONDecodeError, TypeError):
        pass
    return []


def _build_company_entry(row: dict) -> dict:
    """Transform a CSV row into the session JSON company schema."""
    raw_contacts = row.get("contacts", "[]")
    parsed_contacts = _parse_contacts(raw_contacts) if isinstance(raw_contacts, str) else raw_contacts

    # Normalize contacts to the session schema
    session_contacts = []
    for c in parsed_contacts:
        if isinstance(c, dict):
            conf = c.get("email_confidence")
            if conf is not None:
                try:
                    conf = float(conf)
                except (ValueError, TypeError):
                    conf = None

            session_contacts.append({
                "name": c.get("full_name") or f"{c.get('first_name', '')} {c.get('last_name', '')}".strip(),
                "title": c.get("title", ""),
                "email": c.get("email") or None,
                "phone": c.get("phone") or None,
                "email_confidence": conf,
                "email_verified": "unknown",
                "contact_source": c.get("email_source") or "unknown",
            })

    # If no structured contacts but row has top-level email/phone, create one
    if not session_contacts and (row.get("email") or row.get("phone")):
        session_contacts.append({
            "name": "",
            "title": "",
            "email": row.get("email") or None,
            "phone": row.get("phone") or None,
            "email_confidence": None,
            "email_verified": "unknown",
            "contact_source": "website_scrape",
        })

    # Parse score
    score = 0
    for key in ("icp_match_score", "fit_score"):
        val = row.get(key)
        if val is not None and val != "":
            try:
                score = int(val)
                break
            except (ValueError, TypeError):
                pass

    return {
        "company_name": row.get("company_name", ""),
        "website": row.get("website", ""),
        "industry": row.get("industry", ""),
        "company_size": row.get("company_size", ""),
        "location": row.get("location", ""),
        "source": row.get("source", ""),
        "fit_score": score,
        "fit_reason": row.get("icp_match_reason") or row.get("fit_reason", ""),
        "contacts": session_contacts,
    }

def _build_company_entry_from_business(b) -> dict:
    """Transform a Business object into the session JSON company schema."""
    d = b.model_dump()
    session_contacts = []
    
    for c in d.get("contacts", []):
        conf = c.get("email_confidence")
        if conf is not None:
            try:
                conf = float(conf)
            except (ValueError, TypeError):
                conf = None

        session_contacts.append({
            "name": c.get("full_name") or f"{c.get('first_name', '')} {c.get('last_name', '')}".strip(),
            "title": c.get("title", ""),
            "email": c.get("email") or None,
            "phone": c.get("phone") or None,
            "email_confidence": conf,
            "email_verified": "unknown",
            "contact_source": c.get("email_source") or "unknown",
        })

    # If no structured contacts but top-level email/phone, create one
    if not session_contacts and (d.get("email") or d.get("phone")):
        session_contacts.append({
            "name": "",
            "title": "",
            "email": d.get("email") or None,
            "phone": d.get("phone") or None,
            "email_confidence": None,
            "email_verified": "unknown",
            "contact_source": "website_scrape",
        })

    score = d.get("icp_match_score") or d.get("fit_score", 0)

    return {
        "company_name": d.get("company_name", ""),
        "website": d.get("website", ""),
        "industry": d.get("industry", ""),
        "company_size": d.get("company_size", ""),
        "location": d.get("location", ""),
        "source": d.get("source", ""),
        "fit_score": score,
        "fit_reason": d.get("icp_match_reason") or d.get("fit_reason", ""),
        "contacts": session_contacts,
    }


def save_session(
    keywords: list[str],
    icp: Optional[ICP] = None,
    source_pipeline: str = "unknown",
    session_id: Optional[str] = None,
    businesses: list = None
) -> str:
    """
    Snapshot the current pipeline results into a session JSON file.

    Args:
        keywords: The search keywords used for this run.
        icp: The ICP model used (if any).
        source_pipeline: Which pipeline produced this data.
        session_id: If provided, filter CSV rows to only this session's data.
        businesses: The list of Business objects to save.

    Returns:
        The session_id of the created session.
    """
    _ensure_dir()

    sid = session_id or str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()

    # Build company entries
    companies = []
    if businesses:
        companies = [_build_company_entry_from_business(b) for b in businesses]

    # Compute stats
    total = len(companies)
    emails_found = sum(
        1 for c in companies
        if any(ct.get("email") for ct in c["contacts"])
    )
    phones_found = sum(
        1 for c in companies
        if any(ct.get("phone") for ct in c["contacts"])
    )
    scores = [c["fit_score"] for c in companies if c["fit_score"] > 0]
    avg_score = round(sum(scores) / len(scores), 1) if scores else 0

    # Build ICP summary
    icp_summary = None
    if icp:
        icp_summary = {
            "target_roles": icp.target_roles,
            "target_industries": icp.target_industries,
            "company_size_min": icp.company_size_min,
            "company_size_max": icp.company_size_max,
            "value_proposition": icp.value_proposition,
        }

    session_data = {
        "session_id": sid,
        "created_at": created_at,
        "source_pipeline": source_pipeline,
        "search_keywords": keywords,
        "icp_summary": icp_summary,
        "stats": {
            "total_companies": total,
            "emails_found": emails_found,
            "phones_found": phones_found,
            "avg_score": avg_score,
        },
        "companies": companies,
    }

    # Write to disk
    out_path = SESSIONS_DIR / f"{sid}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(session_data, f, indent=2, ensure_ascii=False)

    return sid


def list_sessions() -> list[dict]:
    """
    List all saved sessions, returning metadata only (no company data).
    Sorted by created_at descending (newest first).
    """
    _ensure_dir()
    sessions = []

    for fname in os.listdir(SESSIONS_DIR):
        if not fname.endswith(".json"):
            continue
        fpath = SESSIONS_DIR / fname
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            sessions.append({
                "session_id": data.get("session_id", fname.replace(".json", "")),
                "created_at": data.get("created_at", ""),
                "source_pipeline": data.get("source_pipeline", ""),
                "search_keywords": data.get("search_keywords", []),
                "icp_summary": data.get("icp_summary"),
                "stats": data.get("stats", {}),
            })
        except (json.JSONDecodeError, Exception):
            continue

    sessions.sort(key=lambda s: s.get("created_at", ""), reverse=True)
    return sessions


def get_session(session_id: str) -> Optional[dict]:
    """Load and return the full session data for a given session_id."""
    _ensure_dir()
    fpath = SESSIONS_DIR / f"{session_id}.json"
    if not fpath.exists():
        return None
    try:
        with open(fpath, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, Exception):
        return None
