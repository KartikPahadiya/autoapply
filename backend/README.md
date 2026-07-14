# Resume-Jobs Backend (multi-user, no persistence)

This is a scaffold for a real multi-user backend, built out of the logic
from the original single-user CLI script (`linkedin_jobs_chatbot.py`).

## Core design decision

**Nothing persists.** No database, no files written to disk. Every piece
of per-user data — Google OAuth tokens, resume text/bytes, job search
results, Hunter.io email cache — lives only inside that user's
`SessionData` object in server RAM (`session_store.py`), for as long as
their session is active. Logging out, or 1 hour of inactivity, wipes it
for good. Restarting the server logs everyone out and forgets everyone.

This is genuinely different from the CLI script, which used module-level
globals shared by the whole process (fine for one person, one terminal;
not fine for concurrent users).

## What's NOT persisted, and what that costs you

- No "remember me" across browser restarts beyond the session cookie's
  1-hour lifetime — the user re-authenticates with Google each time.
- No history of past searches or sent emails once a session ends.
- **Single-instance only.** The session store is one Python process's
  memory. If you horizontally scale to multiple backend instances behind
  a load balancer, sessions won't be visible across instances unless you
  add sticky sessions or move the store to something shared (e.g. Redis
  with a TTL — still ephemeral, just no longer single-process).

If any of that is unacceptable for your product, that's a legitimate
reason to add a real database — just know it's a deliberate trade-off,
not an oversight.

## Files

- `session_store.py` — in-memory session store, keyed by a random ID in
  an httponly cookie. Auto-expires idle sessions.
- `oauth_google.py` — Google OAuth2 web flow. `/auth/google/login`
  redirects to Google; `/auth/google/callback` (on YOUR real domain,
  registered in Google Cloud Console) completes it.
- `resume_utils.py` — parses PDF/DOCX resumes directly from uploaded
  bytes (no disk writes).
- `job_service.py` — LinkedIn scraping (Apify) + resume matching, using a
  per-session **in-memory** Chroma collection (`chromadb.Client()` with no
  `persist_directory`), dropped on each new search or session end.
- `email_service.py` — Hunter.io company-email lookups and Gmail sending.
- `mcp_tools.py` — loads the Laddro Career MCP server's tools as real
  LangChain tools via `langchain-mcp-adapters` (streamable_http + bearer
  auth). Shared across sessions — it's the app's own Laddro account, not
  per-user data.
- `tailoring_service.py` — resume tailoring + cover letter generation, run
  by a dedicated sub-agent on `ChatNVIDIA` (`nvidia/nemotron-3-ultra-550b-a55b`)
  with the Laddro tools bound to it. Pulls the tailored PDF URL from the
  actual tool call results, not just the agent's own summary.
- `agent_service.py` — the main per-session chat agent (same design as the
  original CLI script, `openai/gpt-oss-120b` via HuggingFace), with tools
  that close over that request's session instead of module globals.
- `main.py` — FastAPI app wiring it all together.

## Setup

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env   # fill in your real values
uvicorn main:app --reload --port 8000
```

In Google Cloud Console, add your `GOOGLE_REDIRECT_URI` (e.g.
`https://yourapp.com/auth/google/callback`, or `http://localhost:8000/auth/google/callback`
for local dev) as an Authorized redirect URI on your OAuth client, and
make sure the OAuth consent screen includes the `gmail.send` and
`userinfo.email` scopes (or is in Testing mode with your account added as
a test user).

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/auth/google/login` | Redirects the browser to Google's consent screen |
| GET | `/auth/google/callback` | Google redirects here; completes login, redirects to `FRONTEND_POST_LOGIN_URL` |
| POST | `/auth/logout` | Clears this session's Google credentials |
| GET | `/auth/me` | `{logged_in, email}` — for the frontend to check status |
| POST | `/resume/upload` | Multipart file upload (`file` field); extracts + stores text in the session |
| POST | `/resume/tailor` | `{job_description, company, title}` → tailors resume + writes cover letter via Laddro/NVIDIA, standalone (no search needed) |
| GET | `/resume/tailored/{key}/download` | Streams the tailored PDF bytes for a given company key (or `_default`) |
| POST | `/jobs/search` | `{keywords, location}` → scrapes + matches, returns top-5 jobs |
| POST | `/jobs/email-lookup` | `{company_or_position}` → Hunter.io lookup (standalone or against last search) |
| POST | `/jobs/email-me` | Emails the last search results to the logged-in user (or `{recipient}`) |
| POST | `/jobs/cold-email/preview` | `{companies, message}` → tailors resume + cover letter per company automatically (using that job's description), returns recipient/subject/body/tailored-PDF-URL previews, **doesn't send** |
| POST | `/jobs/cold-email/send` | `{items}` (the reviewed/edited preview list) → sends, attaching the tailored PDF when one was found, generic resume otherwise |
| POST | `/email/custom/send` | `{to, subject, body, attach_resume}` → sends directly; the frontend's own "Send" button click is the confirmation |
| POST | `/chat` | `{message}` → natural-language layer on top of everything above, via `agent_service.py` |

## The "confirmation before sending" pattern

Two different mechanisms, depending on the interface:

- **REST endpoints**: split into `preview` (no side effects) and `send`
  (actually sends, called only when the user clicks "Send" in your UI on
  the previewed content).
- **Chat agent** (`/chat`): can't block on a terminal prompt like the CLI
  script did. Instead, the system prompt instructs the agent to show a
  preview in a normal chat reply and wait for the user's explicit
  confirmation in a *later* message before calling `send_cold_emails` or
  `send_custom_email`. This is enforced by prompting, not by code — treat
  it as a strong nudge, not an ironclad guarantee, if you need hard
  guarantees consider adding an explicit confirmation token the frontend
  must pass back.

## Resume tailoring → cold email chain

When you call `/jobs/cold-email/preview` (or the chat agent's
`send_cold_emails`), each targeted company's job description (from the
last search results) is automatically run through
`tailoring_service.tailor_resume_and_cover_letter()`:
1. A sub-agent on `ChatNVIDIA` with the Laddro MCP tools tailors the
   resume for that specific JD and exports it as a PDF.
2. The same run generates a cover letter, used as the email body.
3. The eventual send attaches the tailored PDF instead of the user's
   generic uploaded resume.

If tailoring isn't configured (`LADDRO_MCP_API_KEY`/`NVIDIA_API_KEY`
missing) or fails for a given company, it falls back to the generic
resume + template body and says so plainly in the preview/result — it
never silently pretends tailoring happened.

**Caveat on Laddro tool names:** the exact tools this MCP server exposes
(under `resumes`, `coverLetters`, etc.) weren't inspected directly — the
sub-agent discovers and calls them itself based on their descriptions,
rather than this code hardcoding specific tool names/call sequences. If
you know the exact schema (e.g. from docs.laddro.com/docs/mcp) and want
tighter, non-agentic control instead, `mcp_tools.get_laddro_tools()`
returns the raw LangChain tool objects you can call directly by name.

## What's intentionally NOT built here

- Rate limiting, request validation hardening, structured logging,
  auth on top of the session cookie (CSRF protection), and production
  ASGI server config (workers, TLS termination) are all still needed
  before this is actually production-ready — this scaffold gets the
  session/OAuth/agent architecture right, but deployment hardening is a
  separate pass.
- Hard (code-enforced, not just prompted) confirmation gating for the
  chat agent's send tools — see the caveat above.

