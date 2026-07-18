"""Hunter.io company-email lookups and email sending via SendGrid.

Emails are sent from a verified SendGrid sender, with Reply-To set to
the user's own email address.

Caching happens on the SessionData object, scoped per user."""
import base64
import os
import re

import requests
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Attachment, Content, Email, FileContent, FileName, FileType, Mail, ReplyTo

HUNTER_API_KEY = os.getenv("HUNTER_API_KEY")
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
SENDGRID_FROM_EMAIL = os.getenv("SENDGRID_FROM_EMAIL", "career-agent@example.com")

_sendgrid_client: SendGridAPIClient | None = None


def _attachment_file_type(filename: str) -> str:
    lower = filename.lower()
    if lower.endswith(".pdf"):
        return "application/pdf"
    if lower.endswith(".docx"):
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return "application/octet-stream"


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
    raw = raw.strip()
    m = re.search(r"linkedin\.com/company/([A-Za-z0-9\-_%]+)", raw, re.IGNORECASE)
    if m:
        slug = requests.utils.unquote(m.group(1))
        return slug.replace("-", " ").replace("_", " ").strip().title()
    first_line = next((ln.strip() for ln in raw.splitlines() if ln.strip()), raw)
    return first_line[:80].strip()


def resolve_target(company_or_position: str, matches: list[dict]) -> dict | None:
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


def _send_via_sendgrid(
    user_email: str,
    to_addr: str,
    subject: str,
    body_text: str,
    attachment_bytes: bytes | None = None,
    attachment_filename: str | None = None,
) -> None:
    """Send email via SendGrid FROM a verified domain, with Reply-To set to user."""
    client = _get_sendgrid_client()

    full_body = f"[Sent on behalf of {user_email}]\n\n{body_text}"

    mail = Mail(
        from_email=Email(SENDGRID_FROM_EMAIL),
        to_emails=Email(to_addr),
        subject=subject,
        plain_text_content=Content("text/plain", full_body),
    )
    mail.reply_to = ReplyTo(user_email)

    if attachment_bytes and attachment_filename:
        encoded = base64.b64encode(attachment_bytes).decode()
        attachment = Attachment(
            FileContent(encoded),
            FileName(attachment_filename),
            FileType(_attachment_file_type(attachment_filename)),
            "attachment",
        )
        mail.add_attachment(attachment)

    response = client.send(mail)
    if response.status_code >= 400:
        raise RuntimeError(f"SendGrid error: {response.status_code} — {response.body}")


def send_email(
    session,
    to_addr: str,
    subject: str,
    body_text: str,
    attachment_bytes: bytes | None = None,
    attachment_filename: str | None = None,
) -> None:
    """Send an email via SendGrid, with Reply-To set to the user's address."""
    user_email = session.user_email

    if not user_email:
        raise RuntimeError("No user email set.")

    if not sendgrid_configured():
        raise RuntimeError(
            "Email sending isn't configured on the server (SENDGRID_API_KEY missing)."
        )

    _send_via_sendgrid(
        user_email, to_addr, subject, body_text,
        attachment_bytes, attachment_filename
    )
