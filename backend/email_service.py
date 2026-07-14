"""Hunter.io company-email lookups and Gmail sending. Caching happens on
the SessionData object passed in, so it's scoped per user, not global."""
import base64
import os
import re
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests
from googleapiclient.discovery import build as google_build

HUNTER_API_KEY = os.getenv("HUNTER_API_KEY")


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


def send_gmail(
    creds,
    to_addr: str,
    subject: str,
    body_text: str,
    attachment_bytes: bytes | None = None,
    attachment_filename: str | None = None,
) -> None:
    if attachment_bytes:
        message = MIMEMultipart()
        message.attach(MIMEText(body_text))
        attachment = MIMEApplication(attachment_bytes)
        attachment.add_header("Content-Disposition", "attachment", filename=attachment_filename or "resume")
        message.attach(attachment)
    else:
        message = MIMEText(body_text)

    message["to"] = to_addr
    message["subject"] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

    service = google_build("gmail", "v1", credentials=creds)
    service.users().messages().send(userId="me", body={"raw": raw}).execute()
