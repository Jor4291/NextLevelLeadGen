from __future__ import annotations

from datetime import datetime

from backend.config_loader import get_brand_config
from backend.settings import settings


def _default_body() -> str:
    brand = get_brand_config()
    outreach = brand.get("email_outreach", "").strip()
    if outreach:
        return (
            "Hi {contact_name},\n\n"
            + outreach
            + '\n\n---\nTo unsubscribe from future emails, reply with "unsubscribe".'
        )
    return DEFAULT_BODY_FALLBACK


DEFAULT_SUBJECT = "Scope before code — quick assessment for {company_name}"

DEFAULT_BODY_FALLBACK = """Hi {contact_name},

I'm reaching out from Next Level Studio. We help growing businesses streamline operations with custom software, web apps, and workflow automation — practical builds, not hype.

From what we can see publicly, {company_name} may be dealing with spreadsheet-driven processes, manual handoffs, or systems that don't talk to each other.

If that's accurate, we'd welcome a short call to see if there's a fit — no pitch deck, just an honest look at where software could save your team time.

Learn more: https://nextlevelstudio.com/custom-software/

Best,
{from_name}
Next Level Studio, LLC
info@nextlevelstudio.com
https://nextlevelstudio.com

---
To unsubscribe from future emails, reply with "unsubscribe".
"""


def render_template(template: str, lead, from_name: str | None = None) -> str:
    contact = lead.contact_name or "there"
    return template.format(
        company_name=lead.company_name,
        contact_name=contact,
        industry=lead.industry,
        practice_fit=lead.practice_fit or "operations",
        from_name=from_name or settings.email_from_name,
    )


def send_campaign_email(lead, subject: str, body: str) -> dict:
    if not settings.resend_api_key:
        raise ValueError(
            "RESEND_API_KEY is not configured. Add it to .env for email sending, "
            "or export leads to CSV for Instantly/GMass."
        )
    if not lead.email:
        raise ValueError(f"Lead {lead.company_name} has no email address.")

    import resend

    resend.api_key = settings.resend_api_key

    response = resend.Emails.send(
        {
            "from": f"{settings.email_from_name} <{settings.email_from}>",
            "to": [lead.email],
            "subject": subject,
            "text": body,
        }
    )

    return {
        "lead_id": lead.id,
        "email": lead.email,
        "response": response,
        "sent_at": datetime.utcnow().isoformat(),
    }


def get_default_templates() -> dict:
    brand = get_brand_config()
    return {
        "subject": DEFAULT_SUBJECT,
        "body": _default_body(),
        "instantly_workflow": {
            "description": "Export approved leads to CSV and upload to Instantly.ai",
            "steps": [
                "Filter leads with status 'approved_for_email' in the dashboard",
                "Export CSV from the Email Campaigns page",
                "Upload to Instantly.ai with warmup enabled",
                f"Use the default {brand.get('display_name', '')} template",
            ],
        },
        "gmass_workflow": {
            "description": "For small batches via Google Workspace",
            "steps": [
                "Export approved leads to Google Sheets",
                "Install GMass extension in Gmail",
                f"Mail merge from Sheet using {brand.get('contact_email', settings.email_from)}",
                "Limit to 50-200 emails/week for deliverability",
            ],
        },
    }
