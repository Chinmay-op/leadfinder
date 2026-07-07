"""
Google Sheets Integration — Read/Write lead data to Google Sheets.
Supports reading pending rows as triggers and pushing enriched results back.
"""
from __future__ import annotations

import csv
from datetime import datetime

import gspread

from config import GOOGLE_SHEETS_CREDENTIALS_PATH, GOOGLE_SHEET_ID
from models.business import Business

SHEET_COLUMNS = [
    "company_name", "website", "industry", "location", "address",
    "phone", "email",
    "fit_score", "fit_reason", "icebreaker", "source", "status", "last_updated",
]


def _default_progress(msg: str):
    """Default progress callback — prints to terminal."""
    print(msg)


def get_worksheet() -> gspread.Worksheet:
    """Authenticate with Google Sheets and return the first worksheet.

    Returns:
        gspread.Worksheet object for the configured sheet.
    """
    client = gspread.service_account(filename=GOOGLE_SHEETS_CREDENTIALS_PATH)
    sheet = client.open_by_key(GOOGLE_SHEET_ID).sheet1
    return sheet


def read_pending_rows() -> list[Business]:
    """Read all rows from Google Sheet that have status == 'pending'.

    Returns:
        List of Business objects with sheets_row populated for later updates.
    """
    ws = get_worksheet()
    rows = ws.get_all_records()

    pending: list[Business] = []
    for index, row in enumerate(rows):
        if str(row.get("status", "")).lower() == "pending":
            filtered = {k: v for k, v in row.items() if k in Business.model_fields}
            try:
                business = Business(**filtered)
                business.sheets_row = index + 2  # 1-indexed header + 1-indexed data
                pending.append(business)
            except Exception:
                pass

    return pending


def update_row_status(worksheet: gspread.Worksheet, row_index: int, status: str) -> None:
    """Update the status and last_updated timestamp for a specific row.

    Args:
        worksheet: Active gspread Worksheet object.
        row_index: 1-indexed row number in the sheet.
        status: New status string to write.
    """
    header_row = worksheet.row_values(1)

    if "status" in header_row:
        status_col = header_row.index("status") + 1
        worksheet.update_cell(row_index, status_col, status)

    if "last_updated" in header_row:
        ts_col = header_row.index("last_updated") + 1
        worksheet.update_cell(row_index, ts_col, datetime.utcnow().isoformat())


def write_business_to_sheet(worksheet: gspread.Worksheet, business: Business) -> None:
    """Write or update a Business record in the Google Sheet.

    If the business has a sheets_row, updates the existing row.
    Otherwise, appends a new row.

    Args:
        worksheet: Active gspread Worksheet object.
        business: Business object to write.
    """
    if business.sheets_row is not None:
        # Update specific cells for enriched fields
        header_row = worksheet.row_values(1)
        data = business.model_dump()
        for col_name in SHEET_COLUMNS:
            if col_name in header_row and col_name in data:
                val = data[col_name]
                if val is not None:
                    col_idx = header_row.index(col_name) + 1
                    worksheet.update_cell(business.sheets_row, col_idx, str(val) if val else "")
    else:
        row_values = [str(getattr(business, col, "") or "") for col in SHEET_COLUMNS]
        worksheet.append_row(row_values)


def run_sheets_trigger(state) -> None:
    """Read pending rows from Google Sheet and save them as the scraping input.

    Args:
        state: PipelineState instance for SSE broadcasting.
    """
    state.progress("Reading pending rows from Google Sheet...")

    try:
        businesses = read_pending_rows()
    except Exception as e:
        state.progress(f"Error reading Google Sheet: {e}")
        return

    if not businesses:
        state.progress("No pending rows in Google Sheet")
        return

    state.progress(f"Found {len(businesses)} pending rows in Google Sheet")

    # Save to businesses_data.csv
    keys = list(businesses[0].model_dump().keys())
    try:
        with open("businesses_data.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
            writer.writeheader()
            for b in businesses:
                d = b.model_dump()
                writer.writerow({k: (v if v is not None else "") for k, v in d.items()})
        state.progress(f"Saved {len(businesses)} companies to businesses_data.csv")
    except Exception as e:
        state.progress(f"Error saving to CSV: {e}")


def run_sheets_push(state) -> None:
    """Push enriched leads from CSV back to Google Sheet.

    Args:
        state: PipelineState instance for SSE broadcasting.
    """
    state.progress("Pushing enriched leads to Google Sheet...")

    try:
        with open("enriched_leads.csv", "r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    except FileNotFoundError:
        state.progress("enriched_leads.csv not found. Please run enrichment first.")
        return

    leads: list[Business] = []
    for row in rows:
        try:
            leads.append(Business(**{k: v for k, v in row.items() if k in Business.model_fields}))
        except Exception:
            pass

    try:
        ws = get_worksheet()
    except Exception as e:
        state.progress(f"Error connecting to Google Sheet: {e}")
        return

    for i, lead in enumerate(leads):
        try:
            write_business_to_sheet(ws, lead)
        except Exception as e:
            state.progress(f"Error writing row for {lead.company_name}: {e}")

        if (i + 1) % 10 == 0:
            state.progress(f"Pushed {i+1}/{len(leads)} rows to Google Sheet")

    state.progress(f"Sheet push complete: {len(leads)} rows written")
