from __future__ import annotations

from datetime import datetime
from pathlib import Path

from backend.settings import settings


EXPORT_COLUMNS = [
    "Company",
    "Industry",
    "Fit Score",
    "Pain Signals",
    "Practice Fit",
    "Contact Name",
    "Title",
    "Email",
    "Phone",
    "Website",
    "Notes",
    "Status",
    "Source URL",
    "Scraped Date",
]


def _get_gspread_client():
    import gspread
    from google.oauth2.service_account import Credentials

    creds_path = Path(settings.google_sheets_credentials_path)
    if not creds_path.exists():
        raise FileNotFoundError(
            f"Google credentials not found at {creds_path}. "
            "See README for setup instructions."
        )

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    credentials = Credentials.from_service_account_file(str(creds_path), scopes=scopes)
    return gspread.authorize(credentials)


def export_leads_to_sheet(leads: list, sheet_id: str | None = None) -> dict:
    target_sheet_id = sheet_id or settings.google_sheet_id
    if not target_sheet_id:
        raise ValueError(
            "GOOGLE_SHEET_ID is not configured. Set it in .env or pass sheet_id."
        )

    client = _get_gspread_client()
    spreadsheet = client.open_by_key(target_sheet_id)

    try:
        worksheet = spreadsheet.worksheet("Leads")
    except Exception:
        worksheet = spreadsheet.add_worksheet(title="Leads", rows=1000, cols=20)

    existing = worksheet.get_all_values()
    if not existing:
        worksheet.append_row(EXPORT_COLUMNS)

    rows = []
    for lead in leads:
        pain = "; ".join((lead.pain_signals or [])[:3])
        rows.append(
            [
                lead.company_name,
                lead.industry,
                lead.fit_score,
                pain,
                lead.practice_fit or "",
                lead.contact_name or "",
                lead.contact_title or "",
                lead.email or "",
                lead.phone or "",
                lead.website or "",
                lead.notes or "",
                lead.status.value if hasattr(lead.status, "value") else str(lead.status),
                lead.source_url or "",
                lead.scraped_at.isoformat() if lead.scraped_at else "",
            ]
        )

    if rows:
        worksheet.append_rows(rows, value_input_option="USER_ENTERED")

    return {
        "exported_count": len(rows),
        "sheet_id": target_sheet_id,
        "worksheet": worksheet.title,
        "exported_at": datetime.utcnow().isoformat(),
    }


def is_sheets_configured() -> bool:
    creds_path = Path(settings.google_sheets_credentials_path)
    return creds_path.exists() and bool(settings.google_sheet_id)
