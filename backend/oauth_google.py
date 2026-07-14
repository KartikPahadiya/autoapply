"""
Google OAuth2 (web-app authorization-code flow) for the production backend.

Unlike a desktop/CLI flow, this is a real redirect: the frontend sends the
user to /auth/google/login, Google redirects back to
/auth/google/callback on YOUR domain, and the resulting credentials are
stored only inside that user's in-memory SessionData — never written to
disk, never shared across sessions.
"""
import os
import secrets

import requests
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.credentials import Credentials

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI")  # e.g. https://yourapp.com/auth/google/callback

GOOGLE_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/gmail.send",
]


def google_configured() -> bool:
    return bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET and GOOGLE_REDIRECT_URI)


def build_flow() -> Flow:
    client_config = {
        "web": {
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [GOOGLE_REDIRECT_URI],
        }
    }
    return Flow.from_client_config(client_config, scopes=GOOGLE_SCOPES, redirect_uri=GOOGLE_REDIRECT_URI)


def start_login(session, state: str = None) -> str:
    """Create a Flow tied to this session and return the Google consent URL.
    If `state` is provided, it is used as the OAuth state param (useful when
    the session ID is embedded in it for callback recovery without a cookie).
    The Flow (and its PKCE code_verifier) is stashed on the session so the
    later callback can complete the same flow."""
    flow = build_flow()
    auth_state = state or secrets.token_urlsafe(24)
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=auth_state,
    )
    session.oauth_flow = flow
    session.oauth_state = auth_state
    return auth_url

    """Create a Flow tied to this session and return the Google consent URL.
    The Flow (and its PKCE code_verifier) is stashed on the session so the
    later callback, which arrives as a separate HTTP request, can complete
    the same flow."""
    flow = build_flow()
    state = secrets.token_urlsafe(24)
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=state,
    )
    session.oauth_flow = flow
    session.oauth_state = state
    return auth_url


def complete_login(session, code: str, state: str) -> str:
    """Exchange the authorization code for credentials, store them on the
    session (in memory only), and return the logged-in email address."""
    if session.oauth_flow is None or state != session.oauth_state:
        raise ValueError(
            "No matching login attempt for this session (it may have expired, "
            "or you're mixing up two browser tabs) — start 'login' again."
        )

    flow = session.oauth_flow
    flow.fetch_token(code=code)
    creds = flow.credentials

    email = _fetch_email(creds)
    session.google_creds = creds
    session.google_email = email
    session.oauth_flow = None
    session.oauth_state = None
    return email


def _fetch_email(creds: Credentials) -> str:
    if creds.expired and creds.refresh_token:
        creds.refresh(GoogleAuthRequest())
    resp = requests.get(
        "https://www.googleapis.com/oauth2/v2/userinfo",
        headers={"Authorization": f"Bearer {creds.token}"},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json().get("email", "unknown")


def logout(session) -> None:
    session.google_creds = None
    session.google_email = None
    session.oauth_flow = None
    session.oauth_state = None
