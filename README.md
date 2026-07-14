# Career Agent — Full Stack

A multi-user AI career assistant with **no persistence** — sessions live only in server RAM and expire after 1 hour of inactivity. The chat agent can search LinkedIn jobs, match them to your resume, tailor resumes via AI, look up company emails, and send cold outreach emails from your Gmail.

---

## Project Structure

```
├── backend/          # FastAPI + Python backend
│   ├── main.py               # FastAPI app + all REST endpoints
│   ├── agent_service.py      # Per-session chat agent (ReAct on openai/gpt-oss-120b)
│   ├── tailoring_service.py  # Resume tailoring sub-agent (NVIDIA Nemotron-3-Ultra-550B + Laddro MCP)
│   ├── job_service.py        # LinkedIn scraping (Apify) + ChromaDB vector matching
│   ├── email_service.py      # Hunter.io email lookup + Gmail API sending
│   ├── oauth_google.py       # Google OAuth2 web flow
│   ├── session_store.py      # In-memory session store (RAM-only, no disk)
│   ├── resume_utils.py       # PDF/DOCX parsing from bytes
│   ├── mcp_tools.py          # Laddro Career MCP server connection
│   ├── requirements.txt      # Python dependencies
│   └── .env.example          # All required env vars
│
├── frontend/         # React + Vite frontend
│   ├── index.html
│   ├── vite.config.js
│   ├── package.json
│   ├── .env.example          # VITE_API_BASE_URL
│   ├── README.md
│   └── src/
│       ├── main.jsx
│       ├── App.jsx            # Gate: OAuth → Resume → Chat
│       ├── api.js             # Thin fetch client (credentials: include)
│       ├── index.css          # Dark ink-navy theme (brass accents)
│       ├── components/
│       │   ├── AccessPanel.jsx  # Two-step clearance panel (lights + trace)
│       │   ├── AccessPanel.css
│       │   ├── Chat.jsx         # Chat console with suggestions
│       │   └── Chat.css
└── README.md         # This file
```

---

## Quick Start

### 1. Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate       # Windows
# source venv/bin/activate  # macOS/Linux
pip install -r requirements.txt
cp .env.example .env
# Fill in all API keys (see backend/README.md for details)
# Set FRONTEND_ORIGIN=http://localhost:3000
# Set COOKIE_SECURE=false (for local http testing)
uvicorn main:app --reload --port 8000
```

Backend runs at: `http://localhost:8000`

### 2. Frontend

```bash
cd frontend
npm install
cp .env.example .env   # VITE_API_BASE_URL=http://localhost:8000
npm run dev
```

Frontend runs at: `http://localhost:3000`

---

## How It Works

1. **Access Panel** — User connects Gmail (OAuth redirect) and uploads a resume. Two "clearance lights" must both turn green.
2. **Chat Agent** — Once cleared, the user enters a chat console that routes to `POST /chat`. The AI agent on the backend has 6 tools: find jobs, look up emails, tailor resumes, email results, send cold emails, send custom emails.
3. **No data stored** — OAuth tokens, resume text, search results, email cache all live in server RAM only. Sessions expire after 1 hour of inactivity. No database, no disk writes.

---

## API Keys Required

| Service | Key | Purpose |
|---------|-----|---------|
| Apify | `APIFY_API_TOKEN` | LinkedIn job scraping |
| HuggingFace | `HUGGINGFACEHUB_API_TOKEN` | Main chat agent LLM |
| Hunter.io | `HUNTER_API_KEY` | Company email lookup |
| NVIDIA AI | `NVIDIA_API_KEY` | Resume tailoring sub-agent |
| Laddro/Smithery | `LADDRO_MCP_API_KEY` | Resume tailoring tools |
| Google Cloud | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | OAuth + Gmail sending |

See `backend/README.md` for detailed setup of each.

---

## Architecture Notes

- **2 LLMs**: `openai/gpt-oss-120b` (main chat) + `nvidia/nemotron-3-ultra-550b-a55b` (tailoring sub-agent)
- **1 embedding model**: `sentence-transformers/all-MiniLM-L6-v2` (job matching via ChromaDB)
- **Session-only**: No database. Restarting the server logs everyone out.
- **Single-instance**: Session store is one Python process's memory. Scale → add Redis or sticky sessions.
- **Preview-before-send**: Cold emails always show a preview first; user confirms via chat turn or clicking "Send" in the UI.
