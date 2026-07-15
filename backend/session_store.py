"""
In-memory, non-persistent session store.

Sessions live only in server RAM, keyed by a random session ID that's
handed to the browser as an httponly cookie. Nothing here is written to
disk or a database — restarting the server, or a session going idle past
SESSION_TTL_SECONDS, wipes the data for good. This is deliberate: the
whole point is that no user data (OAuth tokens, resume text, search
results) persists anywhere beyond an active session.

CAVEAT (be honest with yourself about this before deploying): this store
is a single Python process's memory. It works great for one backend
instance. If you ever scale to multiple instances behind a load balancer,
a session created on instance A won't be visible on instance B unless you
either (a) use sticky sessions at the load balancer, or (b) move this to
a shared store like Redis (which reintroduces a "server holds user data"
component, just an ephemeral one with TTL). For a single-instance
deployment, this file is all you need.
"""
import time
import secrets
import threading
from dataclasses import dataclass, field
from typing import Any, Optional

SESSION_COOKIE_NAME = "session_id"
SESSION_TTL_SECONDS = 60 * 60  # 1 hour of inactivity -> session is dropped


@dataclass
class SessionData:
    created_at: float = field(default_factory=time.time)
    last_active_at: float = field(default_factory=time.time)

    # User's email address and optional Gmail App Password for SMTP sending
    user_email: Optional[str] = None
    smtp_password: Optional[str] = None  # Gmail App Password (16-char)

    # Resume — kept in memory only; never written to disk.
    resume_text: Optional[str] = None
    resume_filename: Optional[str] = None
    resume_bytes: Optional[bytes] = None
    resume_content_type: Optional[str] = None

    # Last job search results for this session
    last_matches: list = field(default_factory=list)    # list[dict]
    vector_collection_name: Optional[str] = None          # ephemeral, in-memory Chroma collection

    # Hunter.io lookup cache, scoped to this session only
    email_cache: dict = field(default_factory=dict)

    # Chat agent conversation history for this session (list[BaseMessage])
    chat_history: list = field(default_factory=list)

    # Tailored resume/cover-letter results, keyed by company name (or
    # "_default" for a standalone JD with no company given). Each value is
    # {"cover_letter": str, "tailored_resume_url": str | None, "raw_reply": str}
    tailored_cache: dict = field(default_factory=dict)

class SessionData:
    created_at: float = field(default_factory=time.time)
    last_active_at: float = field(default_factory=time.time)

    # Google OAuth — the Credentials object and email live only here,
    # only for this session, only in memory.
    google_creds: Optional[Any] = None          # google.oauth2.credentials.Credentials
    google_email: Optional[str] = None
    oauth_flow: Optional[Any] = None             # in-flight google_auth_oauthlib.flow.Flow
    oauth_state: Optional[str] = None

    # Resume — kept in memory only; never written to disk.
    resume_text: Optional[str] = None
    resume_filename: Optional[str] = None
    resume_bytes: Optional[bytes] = None
    resume_content_type: Optional[str] = None

    # Last job search results for this session
    last_matches: list = field(default_factory=list)    # list[dict]
    vector_collection_name: Optional[str] = None          # ephemeral, in-memory Chroma collection

    # Hunter.io lookup cache, scoped to this session only
    email_cache: dict = field(default_factory=dict)

    # Chat agent conversation history for this session (list[BaseMessage])
    chat_history: list = field(default_factory=list)

    # Tailored resume/cover-letter results, keyed by company name (or
    # "_default" for a standalone JD with no company given). Each value is
    # {"cover_letter": str, "tailored_resume_url": str | None, "raw_reply": str}
    tailored_cache: dict = field(default_factory=dict)


class SessionStore:
    def __init__(self):
        self._sessions: dict[str, SessionData] = {}
        self._lock = threading.Lock()

    def create(self) -> tuple[str, SessionData]:
        session_id = secrets.token_urlsafe(32)
        data = SessionData()
        with self._lock:
            self._sessions[session_id] = data
        return session_id, data

    def get(self, session_id: Optional[str]) -> Optional[SessionData]:
        if not session_id:
            return None
        with self._lock:
            data = self._sessions.get(session_id)
            if data is None:
                return None
            if time.time() - data.last_active_at > SESSION_TTL_SECONDS:
                # Idle too long — drop it rather than silently reusing stale creds/data.
                del self._sessions[session_id]
                return None
            data.last_active_at = time.time()
            return data

    def destroy(self, session_id: Optional[str]) -> None:
        if not session_id:
            return
        with self._lock:
            self._sessions.pop(session_id, None)

    def sweep_expired(self) -> int:
        """Remove idle-expired sessions. Call this periodically (main.py
        runs it every 5 minutes in a background task)."""
        now = time.time()
        removed = 0
        with self._lock:
            expired = [sid for sid, d in self._sessions.items() if now - d.last_active_at > SESSION_TTL_SECONDS]
            for sid in expired:
                del self._sessions[sid]
                removed += 1
        return removed


store = SessionStore()
