"""
Session Routes — FastAPI APIRouter for browsing session history.

Endpoints:
  GET /sessions              → list all sessions (metadata only)
  GET /sessions/{id}         → full JSON for one session
  GET /sessions/{id}/view    → rendered HTML report for one session
"""

import html as html_lib
from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse, JSONResponse

from session_store import list_sessions, get_session
from auth import get_current_user, User

router = APIRouter(
    prefix="/sessions",
    tags=["sessions"],
    dependencies=[Depends(get_current_user)]
)


@router.get("")
async def sessions_list():
    """Return all sessions with metadata (no company data)."""
    sessions = list_sessions()
    return {"sessions": sessions, "total": len(sessions)}


@router.get("/{session_id}")
async def session_detail(session_id: str):
    """Return the full JSON data for a single session."""
    data = get_session(session_id)
    if data is None:
        return JSONResponse(
            status_code=404,
            content={"error": f"Session '{session_id}' not found."},
        )
    return data


@router.get("/{session_id}/view")
async def session_html_view(session_id: str):
    """Render a clean, readable HTML report for a single session."""
    data = get_session(session_id)
    if data is None:
        return HTMLResponse(
            content="<h1>404 — Session not found</h1>",
            status_code=404,
        )
    return HTMLResponse(content=_render_session_html(data))


# ── HTML Renderer ─────────────────────────────────────────────────────────────

def _esc(value) -> str:
    """HTML-escape a value, returning empty string for None."""
    if value is None:
        return ""
    return html_lib.escape(str(value))


def _score_color(score: int) -> tuple[str, str, str]:
    """Return (bg_color, text_color, label) for a score."""
    if score >= 80:
        return "#d6f4e3", "#1a7f4b", "Perfect Fit"
    elif score >= 60:
        return "#fff3cd", "#7a5c00", "Good Fit"
    elif score >= 40:
        return "#ffe5cc", "#8a3a00", "Possible Fit"
    else:
        return "#ffd6d6", "#8b1a1a", "Poor Fit"


def _confidence_badge(conf) -> str:
    """Return a small HTML badge for email confidence."""
    if conf is None:
        return '<span class="badge badge-unknown">—</span>'
    try:
        conf = float(conf)
    except (ValueError, TypeError):
        return '<span class="badge badge-unknown">—</span>'
    if conf >= 0.8:
        return f'<span class="badge badge-high">{conf:.0%}</span>'
    elif conf >= 0.5:
        return f'<span class="badge badge-med">{conf:.0%}</span>'
    else:
        return f'<span class="badge badge-low">{conf:.0%}</span>'


def _render_session_html(data: dict) -> str:
    """Build a complete, self-contained HTML page from session data."""

    sid = _esc(data.get("session_id", ""))
    created = _esc(data.get("created_at", ""))
    pipeline = _esc(data.get("source_pipeline", ""))
    keywords = data.get("search_keywords", [])
    icp = data.get("icp_summary") or {}
    stats = data.get("stats", {})
    companies = data.get("companies", [])

    # ── ICP section ───────────────────────────────────────────────────────
    icp_html = ""
    if icp:
        roles = ", ".join(_esc(r) for r in icp.get("target_roles", []))
        industries = ", ".join(_esc(i) for i in icp.get("target_industries", []))
        size_min = icp.get("company_size_min", "—")
        size_max = icp.get("company_size_max", "—")
        vp = _esc(icp.get("value_proposition", ""))
        icp_html = f"""
        <div class="icp-card">
            <h2>Ideal Customer Profile</h2>
            <div class="icp-grid">
                <div><strong>Target Roles</strong><br>{roles or '—'}</div>
                <div><strong>Target Industries</strong><br>{industries or '—'}</div>
                <div><strong>Company Size</strong><br>{size_min}–{size_max} employees</div>
                <div><strong>Value Proposition</strong><br>{vp or '—'}</div>
            </div>
        </div>
        """

    # ── Stats bar ─────────────────────────────────────────────────────────
    stats_html = f"""
    <div class="stats-bar">
        <div class="stat"><span class="stat-num">{stats.get('total_companies', 0)}</span><span class="stat-label">Companies</span></div>
        <div class="stat"><span class="stat-num">{stats.get('emails_found', 0)}</span><span class="stat-label">Emails Found</span></div>
        <div class="stat"><span class="stat-num">{stats.get('phones_found', 0)}</span><span class="stat-label">Phones Found</span></div>
        <div class="stat"><span class="stat-num">{stats.get('avg_score', 0)}</span><span class="stat-label">Avg Score</span></div>
    </div>
    """

    # ── Company cards ─────────────────────────────────────────────────────
    company_cards = []
    for comp in companies:
        score = comp.get("fit_score", 0)
        bg, fg, label = _score_color(score)

        contacts_rows = ""
        for ct in comp.get("contacts", []):
            email = _esc(ct.get("email", ""))
            phone = _esc(ct.get("phone", ""))
            name = _esc(ct.get("name", ""))
            title = _esc(ct.get("title", ""))
            source = _esc(ct.get("contact_source", ""))
            conf_badge = _confidence_badge(ct.get("email_confidence"))

            contacts_rows += f"""
            <tr>
                <td>{name or '—'}</td>
                <td>{title or '—'}</td>
                <td>{email or '—'}</td>
                <td>{phone or '—'}</td>
                <td>{conf_badge}</td>
                <td><span class="source-tag">{source or '—'}</span></td>
            </tr>
            """

        contacts_table = ""
        if contacts_rows:
            contacts_table = f"""
            <table class="contacts-table">
                <thead>
                    <tr>
                        <th>Name</th><th>Title</th><th>Email</th><th>Phone</th><th>Confidence</th><th>Source</th>
                    </tr>
                </thead>
                <tbody>{contacts_rows}</tbody>
            </table>
            """
        else:
            contacts_table = '<p class="no-contacts">No contacts found for this company.</p>'

        website = _esc(comp.get("website", ""))
        website_link = ""
        if website:
            href = website if website.startswith("http") else f"http://{website}"
            website_link = f'<a href="{_esc(href)}" target="_blank" rel="noopener">{website}</a>'

        card = f"""
        <div class="company-card">
            <div class="company-header">
                <div>
                    <h3>{_esc(comp.get('company_name', 'Unknown'))}</h3>
                    <span class="company-meta">
                        {_esc(comp.get('industry', ''))}
                        {' · ' + _esc(comp.get('company_size', '')) if comp.get('company_size') else ''}
                        {' · ' + _esc(comp.get('location', '')) if comp.get('location') else ''}
                    </span>
                    {f'<div class="company-website">{website_link}</div>' if website_link else ''}
                </div>
                <div class="score-badge" style="background:{bg};color:{fg};">
                    <span class="score-num">{score}</span>
                    <span class="score-label">{label}</span>
                </div>
            </div>
            {f'<p class="fit-reason">{_esc(comp.get("fit_reason", ""))}</p>' if comp.get("fit_reason") else ''}
            {contacts_table}
        </div>
        """
        company_cards.append(card)

    companies_html = "\n".join(company_cards) if company_cards else '<p class="empty">No companies found in this session.</p>'

    # ── Keywords display ──────────────────────────────────────────────────
    kw_tags = " ".join(f'<span class="kw-tag">{_esc(k)}</span>' for k in keywords)

    # ── Full page ─────────────────────────────────────────────────────────
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Session Report — {sid[:8]}</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #f4f6fb; color: #1e1e2e; line-height: 1.5;
    padding: 2rem; max-width: 1100px; margin: 0 auto;
  }}
  header {{
    background: #1e1e2e; color: #fff; padding: 1.5rem 2rem; border-radius: 12px;
    margin-bottom: 1.5rem;
  }}
  header h1 {{ font-size: 1.4rem; font-weight: 600; margin-bottom: 0.5rem; }}
  header .meta {{ font-size: 0.85rem; opacity: 0.7; }}
  header .meta span {{ margin-right: 1.5rem; }}
  .kw-bar {{ margin-top: 0.75rem; }}
  .kw-tag {{
    display: inline-block; background: rgba(255,255,255,0.15); color: #fff;
    padding: 0.2rem 0.65rem; border-radius: 20px; font-size: 0.8rem; margin: 0.2rem 0.3rem 0.2rem 0;
  }}
  .icp-card {{
    background: #fff; border: 1px solid #e2e6ef; border-radius: 10px;
    padding: 1.25rem 1.5rem; margin-bottom: 1rem;
  }}
  .icp-card h2 {{ font-size: 1rem; margin-bottom: 0.75rem; color: #555; }}
  .icp-grid {{
    display: grid; grid-template-columns: 1fr 1fr;
    gap: 0.75rem; font-size: 0.9rem;
  }}
  .stats-bar {{
    display: flex; gap: 1rem; margin-bottom: 1.5rem;
  }}
  .stat {{
    flex: 1; background: #fff; border: 1px solid #e2e6ef; border-radius: 10px;
    padding: 1rem; text-align: center;
  }}
  .stat-num {{ display: block; font-size: 1.6rem; font-weight: 700; color: #1e1e2e; }}
  .stat-label {{ font-size: 0.78rem; color: #888; }}
  .company-card {{
    background: #fff; border: 1px solid #e2e6ef; border-radius: 10px;
    padding: 1.25rem 1.5rem; margin-bottom: 1rem;
  }}
  .company-header {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; }}
  .company-header h3 {{ font-size: 1.05rem; margin-bottom: 0.15rem; }}
  .company-meta {{ font-size: 0.82rem; color: #777; }}
  .company-website {{ margin-top: 0.25rem; font-size: 0.82rem; }}
  .company-website a {{ color: #4a7cff; text-decoration: none; }}
  .company-website a:hover {{ text-decoration: underline; }}
  .score-badge {{
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    padding: 0.5rem 0.9rem; border-radius: 8px; min-width: 70px; text-align: center;
    flex-shrink: 0;
  }}
  .score-num {{ font-size: 1.4rem; font-weight: 700; line-height: 1; }}
  .score-label {{ font-size: 0.65rem; font-weight: 500; text-transform: uppercase; letter-spacing: 0.03em; }}
  .fit-reason {{ font-size: 0.85rem; color: #666; margin: 0.5rem 0; font-style: italic; }}
  .contacts-table {{
    width: 100%; border-collapse: collapse; margin-top: 0.75rem; font-size: 0.85rem;
  }}
  .contacts-table th {{
    text-align: left; padding: 0.5rem 0.6rem; background: #f8f9fc;
    border-bottom: 2px solid #e2e6ef; font-weight: 600; color: #555; font-size: 0.78rem;
  }}
  .contacts-table td {{
    padding: 0.45rem 0.6rem; border-bottom: 1px solid #f0f1f5;
  }}
  .contacts-table tr:last-child td {{ border-bottom: none; }}
  .badge {{
    display: inline-block; padding: 0.15rem 0.5rem; border-radius: 12px;
    font-size: 0.75rem; font-weight: 600;
  }}
  .badge-high {{ background: #d6f4e3; color: #1a7f4b; }}
  .badge-med {{ background: #fff3cd; color: #7a5c00; }}
  .badge-low {{ background: #ffd6d6; color: #8b1a1a; }}
  .badge-unknown {{ background: #eee; color: #999; }}
  .source-tag {{
    display: inline-block; background: #f0f1f5; color: #666;
    padding: 0.1rem 0.45rem; border-radius: 4px; font-size: 0.75rem;
  }}
  .no-contacts {{ font-size: 0.85rem; color: #aaa; margin-top: 0.5rem; }}
  .empty {{ text-align: center; color: #aaa; padding: 3rem; }}
  @media (max-width: 700px) {{
    body {{ padding: 1rem; }}
    .icp-grid {{ grid-template-columns: 1fr; }}
    .stats-bar {{ flex-wrap: wrap; }}
    .stat {{ min-width: 45%; }}
    .company-header {{ flex-direction: column; }}
  }}
</style>
</head>
<body>
  <header>
    <h1>Lead Finder — Session Report</h1>
    <div class="meta">
      <span>ID: {sid[:8]}…</span>
      <span>Created: {created}</span>
      <span>Pipeline: {pipeline}</span>
    </div>
    <div class="kw-bar">{kw_tags}</div>
  </header>

  {icp_html}
  {stats_html}

  <h2 style="font-size:1.1rem;margin-bottom:1rem;color:#444;">Companies ({len(companies)})</h2>
  {companies_html}

  <footer style="text-align:center;padding:2rem;color:#bbb;font-size:0.8rem;">
    Generated by Lead Finder · {created}
  </footer>
</body>
</html>"""
