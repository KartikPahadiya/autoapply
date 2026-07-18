"""
FastAPI backend: session-scoped in-memory state + SendGrid email sending.
No Google OAuth. Users provide their email directly, and emails are sent
via SendGrid.

No database, no disk persistence. Everything lives only in server RAM.
Restarting the server drops all sessions.

Run locally:
    uvicorn main:app --reload --port 8000
"""
import asyncio
import os
import re
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from langchain_core.messages import HumanMessage, SystemMessage

import agent_service
import email_service
import job_service
import resume_utils
import tailoring_service
from session_store import SESSION_COOKIE_NAME, SESSION_TTL_SECONDS, SessionData, store


FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")
_cookie_secure_env = os.getenv("COOKIE_SECURE")
COOKIE_SECURE = (
    _cookie_secure_env.lower() == "true"
    if _cookie_secure_env is not None
    else not FRONTEND_ORIGIN.startswith(("http://localhost", "http://127.0.0.1"))
)
DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

app = FastAPI(title="Career Agent Backend")

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=[FRONTEND_ORIGIN],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://autoapply-o9u419trg-kartik-pahadiya.vercel.app",
        "https://autoapply-gamma.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def safe_filename_part(value: str | None, fallback: str = "tailored") -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", value or "").strip("_")
    return cleaned or fallback


# ---------------------------------------------------------------------------
# Session plumbing
# ---------------------------------------------------------------------------
def get_or_create_session(request: Request, response: Response) -> tuple[str, SessionData]:
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    session = store.get(session_id)
    if session is None:
        session_id, session = store.create()
        response.set_cookie(
            SESSION_COOKIE_NAME,
            session_id,
            httponly=True,
            samesite="none",
            secure=COOKIE_SECURE,
            max_age=SESSION_TTL_SECONDS,
        )
    return session_id, session


@app.on_event("startup")
async def _warm_up_llm():
    async def warmup():
        try:
            llm = agent_service.get_llm()
            await llm.ainvoke("ping")
        except Exception as exc:
            print(f"LLM warmup failed (non-fatal): {exc}")

    asyncio.create_task(warmup())


@app.on_event("startup")
async def _warm_up_embeddings():
    async def warmup():
        try:
            embeddings = job_service.get_embeddings()
            await asyncio.to_thread(embeddings.embed_query, "warmup")
        except Exception as exc:
            print(f"Embeddings warmup failed (non-fatal): {exc}")

    asyncio.create_task(warmup())


@app.on_event("startup")
async def _warm_up_mcp():
    async def warmup():
        try:
            import mcp_tools
            await mcp_tools.get_mcp_tools()
            print("MCP (CV Forge) tools warmed up successfully")
        except Exception as exc:
            print(f"MCP warmup failed (non-fatal): {exc}")

    asyncio.create_task(warmup())

# ---------------------------------------------------------------------------
# Auth (simple email-based, no OAuth)
# ---------------------------------------------------------------------------
class SetEmailRequest(BaseModel):
    email: str


@app.post("/auth/email")
def set_email(body: SetEmailRequest, request: Request, response: Response):
    """Set the user's email address. Emails are sent via SendGrid, with
    Reply-To set to this address."""
    _, session = get_or_create_session(request, response)
    if "@" not in body.email:
        raise HTTPException(400, "Invalid email address.")
    session.user_email = body.email.strip().lower()
    return {"ok": True, "email": session.user_email}


@app.post("/auth/logout")
def logout(request: Request, response: Response):
    _, session = get_or_create_session(request, response)
    session.user_email = None
    return {"ok": True}


@app.get("/auth/me")
def me(request: Request, response: Response):
    _, session = get_or_create_session(request, response)
    return {
        "logged_in": bool(session.user_email),
        "email": session.user_email,
    }


# ---------------------------------------------------------------------------
# Resume
# ---------------------------------------------------------------------------
@app.get("/resume/status")
def resume_status(request: Request, response: Response):
    _, session = get_or_create_session(request, response)
    return {
        "has_resume": bool(session.resume_text),
        "filename": session.resume_filename,
        "characters": len(session.resume_text) if session.resume_text else 0,
    }


@app.post("/resume/upload")
async def upload_resume(request: Request, response: Response, file: UploadFile = File(...)):
    _, session = get_or_create_session(request, response)
    content = await file.read()
    try:
        text = resume_utils.extract_resume_text(file.filename, content)
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    session.resume_text = text
    session.resume_bytes = content
    session.resume_filename = file.filename
    session.resume_content_type = file.content_type
    return {"ok": True, "characters": len(text)}


# ---------------------------------------------------------------------------
# Resume tailoring
# ---------------------------------------------------------------------------
class TailorRequest(BaseModel):
    job_description: str
    company: str = ""
    title: str = ""


@app.post("/resume/tailor")
async def tailor_resume(body: TailorRequest, request: Request, response: Response):
    _, session = get_or_create_session(request, response)
    if not session.resume_text:
        raise HTTPException(400, "Upload a resume first.")
    try:
        result = await tailoring_service.tailor_resume_and_cover_letter(
            session.resume_text, body.job_description, body.company, body.title
        )
    except Exception as exc:
        raise HTTPException(500, f"Tailoring failed: {exc}")

    key = body.company or "_default"
    session.tailored_cache[key] = result
    return {
        "cover_letter": result["cover_letter"],
        "tailored_resume_url": result["tailored_resume_url"],
        "tailored_resume_download_url": f"/resume/tailored/{key}/download",
        "tailored_resume_format": "docx",
        "download_key": key,
    }


@app.get("/resume/tailored/{key}/download")
def download_tailored_resume(key: str, request: Request, response: Response):
    _, session = get_or_create_session(request, response)
    cached = session.tailored_cache.get(key)
    if not cached or not cached.get("docx_bytes"):
        raise HTTPException(404, "No tailored resume found for that key.")
    filename = f"tailored_resume_{safe_filename_part(key)}.docx"
    return Response(
        content=cached["docx_bytes"],
        media_type=DOCX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Chat agent
# ---------------------------------------------------------------------------
class ChatRequest(BaseModel):
    message: str


@app.post("/chat")
async def chat_endpoint(body: ChatRequest, request: Request, response: Response):
    _, session = get_or_create_session(request, response)
    try:
        reply = await agent_service.chat(session, body.message)
    except Exception as exc:
        raise HTTPException(502, f"The AI service is temporarily unavailable, please try again: {exc}")
    return {"reply": reply}


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------
class JobSearchRequest(BaseModel):
    keywords: str
    location: str = ""


@app.post("/jobs/search")
def search_jobs(body: JobSearchRequest, request: Request, response: Response):
    _, session = get_or_create_session(request, response)
    try:
        matches = job_service.search_and_match(session, body.keywords, body.location)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"matches": matches}


class EmailLookupRequest(BaseModel):
    company_or_position: str


@app.post("/jobs/email-lookup")
def lookup_email(body: EmailLookupRequest, request: Request, response: Response):
    _, session = get_or_create_session(request, response)
    target = email_service.resolve_target(body.company_or_position, session.last_matches)
    company = target["company"] if target else email_service.extract_company_name(body.company_or_position)
    if not company:
        raise HTTPException(400, "Couldn't determine a company name from that input.")
    emails = email_service.get_or_fetch_emails(session, company)
    return {"company": company, "emails": emails}


class EmailMeRequest(BaseModel):
    recipient: Optional[str] = None


@app.post("/jobs/email-me")
def email_me(body: EmailMeRequest, request: Request, response: Response):
    _, session = get_or_create_session(request, response)
    if not session.user_email:
        raise HTTPException(401, "Set your email address first.")
    if not email_service.sendgrid_configured():
        raise HTTPException(500, "Email sending isn't configured on the server.")
    if not session.last_matches:
        raise HTTPException(400, "No recent job search results to email.")

    to_addr = body.recipient or session.user_email
    lines = ["Here are your matched jobs:\n"]
    for i, m in enumerate(session.last_matches, start=1):
        lines.append(f"{i}. {m['title']} at {m['company']} ({m['location']})\n   {m['url']}")
    body_text = "\n\n".join(lines)

    email_service.send_email(
        session=session,
        to_addr=to_addr,
        subject="Your matched LinkedIn jobs",
        body_text=body_text,
    )
    return {"ok": True, "sent_to": to_addr}


# --- Cold email: preview-then-send
class ColdEmailPreviewRequest(BaseModel):
    companies: str
    message: str = ""


@app.post("/jobs/cold-email/preview")
async def cold_email_preview(body: ColdEmailPreviewRequest, request: Request, response: Response):
    _, session = get_or_create_session(request, response)
    if not session.user_email:
        raise HTTPException(401, "Set your email address first.")
    if not session.resume_bytes:
        raise HTTPException(400, "Upload a resume first.")
    if not email_service.HUNTER_API_KEY:
        raise HTTPException(500, "Email lookup isn't configured on the server.")

    if body.companies.strip().lower() == "all":
        if not session.last_matches:
            raise HTTPException(400, "No recent job search results to target with 'all'.")
        targets = session.last_matches
    else:
        targets = []
        for part in body.companies.split(","):
            part = part.strip()
            if not part:
                continue
            resolved = email_service.resolve_target(part, session.last_matches)
            entry = resolved or {"company": email_service.extract_company_name(part), "title": None}
            if entry not in targets:
                targets.append(entry)

    previews = []
    for target in targets:
        company = target["company"]
        title = target.get("title")
        jd = target.get("summary", "")

        emails = email_service.get_or_fetch_emails(session, company)
        if not emails:
            previews.append({"company": company, "recipient": None, "note": "no public email found"})
            continue
        best = sorted(emails, key=lambda e: (e["type"] != "personal", -(e["confidence"] or 0)))[0]

        if title:
            subject = f"Application Interest: {title} at {company}"
            default_body = (
                f"Hi,\n\nI came across the {title} opening at {company} on LinkedIn and wanted to "
                "reach out directly. I've attached my resume for your consideration and would "
                "welcome the chance to discuss the role further.\n\nThanks for your time,\n"
            )
        else:
            subject = f"Interest in Opportunities at {company}"
            default_body = (
                f"Hi,\n\nI came across {company} and wanted to reach out directly. I've attached "
                "my resume for your consideration and would welcome the chance to discuss any "
                "suitable opportunities.\n\nThanks for your time,\n"
            )

        tailored_resume_key = None
        note = "using generic resume (no job description available to tailor from)"
        if jd and tailoring_service.nvidia_configured():
            try:
                tailored = session.tailored_cache.get(company) or await tailoring_service.tailor_resume_and_cover_letter(
                    session.resume_text or "", jd, company, title or ""
                )
                session.tailored_cache[company] = tailored
                if tailored.get("docx_bytes"):
                    tailored_resume_key = company
                    default_body = tailored["cover_letter"] or default_body
                    note = "tailored DOCX resume + cover letter generated"
                else:
                    note = "tailoring ran but returned no PDF — using generic resume"
            except Exception as exc:
                note = f"tailoring failed ({exc}) — using generic resume"

        previews.append(
            {
                "company": company,
                "recipient": best["value"],
                "subject": subject,
                "body": body.message.strip() or default_body,
                "tailored_resume_key": tailored_resume_key,
                "tailored_resume_format": "docx" if tailored_resume_key else None,
                "note": note,
            }
        )
    return {"previews": previews}


class ColdEmailSendRequest(BaseModel):
    items: list[dict]


@app.post("/jobs/cold-email/send")
def cold_email_send(body: ColdEmailSendRequest, request: Request, response: Response):
    _, session = get_or_create_session(request, response)
    if not session.user_email:
        raise HTTPException(401, "Set your email address first.")
    if not session.resume_bytes:
        raise HTTPException(400, "Upload a resume first.")

    results = []
    for item in body.items:
        recipient = item.get("recipient")
        if not recipient:
            results.append({"company": item.get("company"), "status": "skipped", "reason": "no recipient"})
            continue

        attachment_bytes = session.resume_bytes
        attachment_filename = session.resume_filename
        used_tailored = False
        tailored_key = item.get("tailored_resume_key") or item.get("company")
        tailored = session.tailored_cache.get(tailored_key) if tailored_key else None
        if tailored and tailored.get("docx_bytes"):
            attachment_bytes = tailored["docx_bytes"]
            attachment_filename = f"resume_{safe_filename_part(item.get('company'), 'tailored')}.docx"
            used_tailored = True

        try:
            email_service.send_email(
                session=session,
                to_addr=recipient,
                subject=item.get("subject", ""),
                body_text=item.get("body", ""),
                attachment_bytes=attachment_bytes,
                attachment_filename=attachment_filename,
            )
            results.append(
                {
                    "company": item.get("company"),
                    "status": "sent",
                    "recipient": recipient,
                    "resume_used": "tailored" if used_tailored else "generic",
                }
            )
        except Exception as exc:
            results.append({"company": item.get("company"), "status": "failed", "error": str(exc)})
    return {"results": results}


# ---------------------------------------------------------------------------
# Custom email
# ---------------------------------------------------------------------------
class CustomEmailRequest(BaseModel):
    to: str
    subject: str
    body: str
    attach_resume: bool = False


@app.post("/email/custom/send")
def custom_email_send(body: CustomEmailRequest, request: Request, response: Response):
    _, session = get_or_create_session(request, response)
    if not session.user_email:
        raise HTTPException(401, "Set your email address first.")
    if "@" not in body.to:
        raise HTTPException(400, "Invalid recipient email address.")

    attachment_bytes = session.resume_bytes if body.attach_resume else None
    if body.attach_resume and not attachment_bytes:
        raise HTTPException(400, "No resume uploaded to attach.")

    try:
        email_service.send_email(
            session=session,
            to_addr=body.to,
            subject=body.subject,
            body_text=body.body,
            attachment_bytes=attachment_bytes,
            attachment_filename=session.resume_filename,
        )
    except Exception as exc:
        raise HTTPException(500, f"Failed to send: {exc}")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Diagnostic / test endpoints
# ---------------------------------------------------------------------------
@app.get("/test/config")
def test_config():
    """Return which API keys and services are configured."""
    import email_service
    import mcp_tools
    import tailoring_service
    return {
        "hunter_io": bool(email_service.HUNTER_API_KEY),
        "sendgrid": email_service.sendgrid_configured(),
        "sendgrid_from_email": email_service.SENDGRID_FROM_EMAIL,
        "laddro_mcp": mcp_tools.laddro_configured(),
        "laddro_mcp_url": mcp_tools.LADDRO_MCP_URL,
        "nvidia": tailoring_service.nvidia_configured(),
    }


class TestTailorRequest(BaseModel):
    resume_text: str = "Python developer with 3 years of experience in machine learning and NLP."
    job_description: str = "We are looking for a Senior ML Engineer with expertise in Python, PyTorch, and NLP."


@app.post("/test/tailor")
async def test_tailor(body: TestTailorRequest, request: Request, response: Response):
    """Run the Laddro MCP tailoring pipeline with a small test input and
    return detailed diagnostics — tool list, raw agent responses, and
    parsed results. Use this to debug why tailoring is failing."""
    import mcp_tools
    import tailoring_service

    diagnostics = {
        "credentials": {},
        "tool_list": [],
        "agent_run": {},
        "parsed_result": {},
    }

    # 1. Check credentials
    diagnostics["credentials"] = {
        "nvidia_api_key_set": bool(os.getenv("NVIDIA_API_KEY")),
        "laddro_mcp_api_key_set": mcp_tools.laddro_configured(),
        "laddro_mcp_url": mcp_tools.LADDRO_MCP_URL,
    }

    if not diagnostics["credentials"]["nvidia_api_key_set"]:
        raise HTTPException(500, "NVIDIA_API_KEY is not set in .env")
    if not diagnostics["credentials"]["laddro_mcp_api_key_set"]:
        raise HTTPException(500, "LADDRO_MCP_API_KEY is not set in .env")

    # 2. Try to list tools from Laddro MCP server
    try:
        tools = await mcp_tools.get_laddro_tools()
        diagnostics["tool_list"] = [t.name for t in tools]
        diagnostics["tool_count"] = len(tools)
    except Exception as exc:
        diagnostics["tool_list_error"] = str(exc)
        raise HTTPException(500, f"Failed to connect to Laddro MCP server: {exc}")

    # 3. Run the tailoring agent with the test input
    try:
        result = await tailoring_service.tailor_resume_and_cover_letter(
            body.resume_text, body.job_description, company="TestCo", title="Test Role"
        )
        diagnostics["parsed_result"] = result
    except Exception as exc:
        diagnostics["agent_run_error"] = str(exc)
        raise HTTPException(500, f"Tailoring agent failed: {exc}")

    # 4. Also try to get the raw agent messages for deeper inspection
    try:
        agent = await tailoring_service._get_tailoring_agent()
        user_prompt = (
            f"Candidate resume:\n{body.resume_text}\n\n"
            f"Target job description:\n{body.job_description}\n\n"
            "Call the Laddro tools in order: (1) laddro.resumes.tailor, "
            "(2) laddro.resumes.export, (3) laddro.coverLetters.generate. "
            "Then return ONLY the JSON with pdf_url and cover_letter."
        )
        raw_result = await agent.ainvoke(
            {"messages": [
                SystemMessage(content=tailoring_service.TAILORING_SYSTEM_PROMPT),
                HumanMessage(content=user_prompt)
            ]}
        )
        messages = raw_result["messages"]
        diagnostics["agent_run"] = {
            "message_count": len(messages),
            "messages": [],
        }
        for i, msg in enumerate(messages):
            msg_info = {
                "index": i,
                "type": type(msg).__name__,
                "content_preview": str(msg.content)[:500] if hasattr(msg, "content") else "N/A",
            }
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                msg_info["tool_calls"] = [
                    {"name": tc.get("name"), "args_preview": str(tc.get("args", {}))[:200]}
                    for tc in msg.tool_calls
                ]
            diagnostics["agent_run"]["messages"].append(msg_info)
    except Exception as exc:
        diagnostics["raw_agent_error"] = str(exc)

    return diagnostics


@app.get("/test/tailor")
async def test_tailor_get(request: Request, response: Response):
    """Same as POST /test/tailor but with default test data — visit in
    your browser for quick diagnostics."""
    from pydantic import create_model
    # Re-use the POST logic with defaults
    default = TestTailorRequest()
    return await test_tailor(default, request, response)
