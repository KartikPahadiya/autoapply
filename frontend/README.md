# Career Agent — Frontend

React (Vite) frontend for the resume/jobs backend in `main.py`. Gates
access behind two requirements before the chat agent is reachable:

1. **Gmail access** — real Google OAuth2 redirect (`GET /auth/google/login`
   → Google → `GET /auth/google/callback` → back here).
2. **Resume upload** — `POST /resume/upload` (PDF or DOCX).

Only once both are done can the user open the chat console (`POST /chat`),
matching how the backend's own tools are gated (`agent_service.py` checks
`session.google_creds` and `session.resume_text` before letting the agent
search, tailor, or send anything).

## Setup

```bash
npm install
cp .env.example .env   # set VITE_API_BASE_URL to your backend's URL
npm run dev            # http://localhost:3000
```

The backend's `FRONTEND_ORIGIN` / `FRONTEND_POST_LOGIN_URL` env vars must
point back at wherever this app is served, and `COOKIE_SECURE` must be
`false` for local `http://` testing (the session cookie is httponly and
won't be usable cross-origin otherwise). See the backend's `README.md`
and `.env.example` for the full list.

## How the pieces fit together

- **`src/api.js`** — every request goes through `fetch(..., { credentials:
  "include" })` so the backend's httponly session cookie is sent/stored
  even though frontend and backend are different origins. This is the
  only thing that ties a browser tab to its `SessionData` on the server.
- **`src/App.jsx`** — checks `GET /auth/me` on load, and tracks whether a
  resume has been uploaded this browser session in `sessionStorage` (the
  backend has no "has a resume" endpoint to poll, and this flag needs to
  survive the full-page redirect to Google and back). Renders
  `AccessPanel` until both checks pass and the user clicks through, then
  renders `Chat`.
- **`src/components/AccessPanel.jsx`** — the two-step checklist (Gmail,
  resume). "Connect Gmail" is a real `window.location.href` navigation,
  not a fetch — OAuth consent screens can't happen inside an XHR.
- **`src/components/Chat.jsx`** — a plain chat UI over `POST /chat`. All
  the "should I actually send this email" judgment lives in the backend's
  agent (`agent_service.py`'s system prompt: preview first, send only
  after the user confirms in the next message) — this component doesn't
  need any special-casing for that, it just displays whatever the agent
  replies.

## Design notes

Visual direction is a "launch console" — two clearance lights joined by a
circuit trace that fills in brass as each requirement clears, since the
core mechanic of this screen really is arming a two-stage lock. Ink-navy
background, brass accent, warm paper text; `Space Grotesk` for display,
`Inter` for body copy, `IBM Plex Mono` for status/console text. The chat
console keeps the same palette so entering it doesn't feel like a
different product.

## Known limitations (intentional, matches the backend's own trade-offs)

- No polling/websocket — `POST /chat` is a plain request/response, so the
  UI shows a typing indicator but can't stream partial tokens.
- "Resume uploaded" is inferred client-side (`sessionStorage`), not
  fetched from the backend, because there's no `GET /resume/status`
  endpoint. If you add one, swap the `useState` initializer in `App.jsx`
  for a real check.
- Single backend instance, in-memory sessions — same caveat as the
  backend's own README: horizontally scaling the backend needs sticky
  sessions or a shared session store.
