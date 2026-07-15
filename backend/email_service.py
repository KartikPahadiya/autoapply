"""Hunter.io company-email lookups and SendGrid email sending.
No Google OAuth required. Users provide their email address directly,
and emails are sent via SendGrid with their address as the From field.
Caching happens on the SessionData object passed in, so it's scoped per
user, not global."""
import base64
import os
import re

import requests
import re

import requests
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Attachment, Content, Email, FileContent, FileName, FileType, Mail, Personalization

HUNTER_API_KEY = os.getenv("HUNTER_API_KEY")
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")

_sendgrid_client: SendGridAPIClient | None = None


def _get_sendgrid_client() -> SendGridAPIClient:
    global _sendgrid_client
    if _sendgrid_client is None:
        if not SENDGRID_API_KEY:
            raise RuntimeError("SENDGRID_API_KEY is not set in .env — email sending is unavailable.")
        _sendgrid_client = SendGridAPIClient(SENDGRID_API_KEY)
    return _sendgrid_client


def sendgrid_configured() -> bool:
    return bool(SENDGRID_API_KEY)


def extract_company_name(raw: str) -> str:
    """Best-effort extraction of a plain company name from free-form input
    that didn't match a last-search result — a LinkedIn company URL, a
    pasted chunk of a LinkedIn page, or a company name typed directly."""
    raw = raw.strip()
    m = re.search(r"linkedin\.com/company/([A-Za-z0-9\-_%]+)", raw, re.IGNORECASE)
    if m:
        slug = requests.utils.unquote(m.group(1))
        return slug.replace("-", " ").replace("_", " ").strip().title()
    first_line = next((ln.strip() for ln in raw.splitlines() if ln.strip()), raw)
    return first_line[:80].strip()


def resolve_target(company_or_position: str, matches: list[dict]) -> dict | None:
    """Find a job from the last search results by position number or
    company name."""
    stripped = company_or_position.strip()
    if stripped.isdigit():
        idx = int(stripped) - 1
        if 0 <= idx < len(matches):
            return matches[idx]
    for m in matches:
        if m["company"].strip().lower() == stripped.lower():
            return m
    return None


def find_emails_for_company(company: str, limit: int = 5) -> list[dict]:
    if not HUNTER_API_KEY:
        return []
    resp = requests.get(
        "https://api.hunter.io/v2/domain-search",
        params={"company": company, "api_key": HUNTER_API_KEY, "limit": limit},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json().get("data", {}) or {}
    emails = data.get("emails", []) or []
    return [
        {
            "value": e.get("value"),
            "type": e.get("type"),
            "confidence": e.get("confidence"),
            "name": " ".join(filter(None, [e.get("first_name"), e.get("last_name")])),
            "position": e.get("position"),
        }
        for e in emails
    ]


def get_or_fetch_emails(session, company: str) -> list[dict]:
    if company not in session.email_cache:
        session.email_cache[company] = find_emails_for_company(company)
    return session.email_cache[company]


def send_email(
    from_addr: str,
    to_addr: str,
    subject: str,
    body_text: str,
    attachment_bytes: bytes | None = None,
    attachment_filename: str | None = None,
) -> None:
    """Send an email via SendGrid. from_addr is the user's email address
    (shown as the sender)."""
    client = _get_sendgrid_client()

    mail = Mail(
        from_email=Email(from_addr),
        to_emails=Email(to_addr),
        subject=subject,
        plain_text_content=Content("text/plain", body_text),
    )

    if attachment_bytes and attachment_filename:
        encoded = base64.b64encode(attachment_bytes).decode()
        attachment = Attachment(
            FileContent(encoded),
            FileName(attachment_filename),
            FileType("application/pdf" if attachment_filename.endswith(".pdf") else "application/octet-stream"),
            "attachment",
        )
        mail.add_attachment(attachment)

    response = client.send(mail)
    if response.status_code >= 400:
        raise RuntimeError(f"SendGrid error: {response.status_code} — {response.body}")
