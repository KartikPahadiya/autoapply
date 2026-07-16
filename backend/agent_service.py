"""
Per-session chat agent. Every tool closes over that request's SessionData
instead of module-level globals — so concurrent users' resumes, search
results, and email settings never leak into each other.

This runs alongside the plain REST endpoints in main.py, not instead of
them — a frontend can use either the direct buttons (POST /jobs/search
etc.) or this chat endpoint (POST /chat), or both.

SAFETY NOTE: the CLI script blocked on a terminal input("yes/no") before
every send. A chat agent in a stateless HTTP request/response loop can't
block like that, so the system prompt instructs the agent to show a
preview and ask the user to confirm in a normal chat reply, then only
actually call the sending tool once the user replies confirming — the
"confirmation" becomes a conversational turn instead of a blocking call.
"""
import os
import re
from urllib.parse import quote

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool as tool_decorator
from langchain_huggingface import ChatHuggingFace, HuggingFaceEndpoint
from langgraph.prebuilt import create_react_agent

import email_service
import job_service
import mcp_tools
import tailoring_service

# _llm_endpoint = HuggingFaceEndpoint(
#     repo_id="openai/gpt-oss-120b",
#     task="text-generation",
#     max_new_tokens=1024,
#     do_sample=False,
#     provider="auto",
# )
# _llm = ChatHuggingFace(llm=_llm_endpoint)
_llm = None

def get_llm():
    global _llm

    if _llm is None:
        endpoint = HuggingFaceEndpoint(
            repo_id="openai/gpt-oss-120b",
            task="text-generation",
            max_new_tokens=1024,
            do_sample=False,
            provider="auto",
        )

        _llm = ChatHuggingFace(llm=endpoint).with_retry(
            stop_after_attempt=3,
            wait_exponential_jitter=True,
        )

    return _llm
BACKEND_PUBLIC_URL = os.getenv("BACKEND_PUBLIC_URL", "http://localhost:8000")


def safe_filename_part(value: str | None, fallback: str = "tailored") -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", value or "").strip("_")
    return cleaned or fallback


SYSTEM_PROMPT = """You are a friendly career assistant chatbot with access to these tools.

Use the dynamic session context below as the source of truth for whether the
user's email address and resume are currently available.

IMPORTANT RULES:
- The dynamic session context is authoritative. If it says the uploaded resume
  is available, do not ask for another resume before tailoring. If it says no
  resume is available, explain that the current backend session cannot see the
  uploaded resume and ask the user to upload it again.
- When the user asks to tailor their resume, write a cover letter, make a CV, or customize their resume for ANY job description, you MUST call the tailor_resume_for_role tool IMMEDIATELY. Do NOT ask the user to upload their resume — it is already uploaded in their session. Do NOT ask for confirmation. Just call the tool.
- When the user asks to find/search jobs, call find_matching_jobs.
- When the user asks to look up emails, call lookup_company_email.
- NEVER invent tool results. Only report what the tools return.

1. find_matching_jobs(keywords, location) — searches LinkedIn and returns
   jobs matched against the user's resume. Only call when the user explicitly
   asks to find/search jobs. Only ever list jobs, companies, and links that
   appear verbatim in the tool's output — never invent any. Show every job
   the tool returned, not a subset of your choosing.

2. lookup_company_email(company_or_position) — looks up public emails for a
   company. Works against the last search results (company name or position
   number) OR standalone (company name or LinkedIn URL/pasted text) — no prior
   search required.
   FORMAT RULE: When showing email lookup results, DO NOT use markdown tables.
   Use one company block at a time, then bullets like:
   Company: ExampleCo
   - person@example.com — personal, 92% confidence, Jane Doe
   - info@example.com — generic, 80% confidence
   For companies with no result, write "- No public email found." This avoids
   broken columns when one company has multiple email addresses.

3. tailor_resume_for_role(job_description, company, title) — tailors the
   user's resume and writes a cover letter for a SPECIFIC role, using the
   Laddro Career tools. The user has ALREADY uploaded their resume. You do
   NOT need to ask them to upload it again. When the user says anything like
   "tailor my resume", "write a cover letter", "make a CV", or similar —
   call this tool IMMEDIATELY with the job description they provided. Pass the
   full job description text as the job_description parameter. Use the company
   name if known, otherwise leave it empty.

4. email_me_results() — emails the user's last job search results to their
   email address. Requires the user to have set their email (which they have).

5. send_cold_emails(companies, message) — sends cold outreach to companies.
   CRITICAL SAFETY RULE: before calling this tool, you MUST first show the user
   a plain-text preview of exactly who you're about to email and with what
   subject/body, and explicitly ask them to confirm. Only call this tool in a
   LATER turn, after the user has replied confirming (e.g. "yes", "send it",
   "go ahead"). Never call it in the same turn you presented the preview.

6. send_custom_email(to, subject, body, attach_resume) — sends a fully custom
   email to any recipient. Same CRITICAL SAFETY RULE as above.

Present tool results plainly and accurately — never invent details, never
claim an email was sent except exactly as the tool reports it.
"""


def build_session_tools(session):
    @tool_decorator
    def find_matching_jobs(keywords: str, location: str = "") -> str:
        """Search LinkedIn for jobs matching keywords/location, and return
        the ones most relevant to the user's resume."""
        try:
            matches = job_service.search_and_match(session, keywords, location)
        except ValueError as exc:
            return str(exc)
        if not matches:
            return "No relevant jobs were found. Tell the user plainly and suggest broadening the search."
        lines = [
            f"- {m['title']} at {m['company']} ({m['location']})\n  Link: {m['url']}\n  Summary: {m['summary']}"
            for m in matches
        ]
        return "\n\n".join(lines)

    @tool_decorator
    def lookup_company_email(company_or_position: str) -> str:
        """Look up public emails for a company — from the last search
        results (name or position number) or standalone (company name or
        LinkedIn URL/pasted text)."""
        if not email_service.HUNTER_API_KEY:
            return "Email lookup isn't configured on the server (HUNTER_API_KEY missing)."
        target = email_service.resolve_target(company_or_position, session.last_matches)
        company = target["company"] if target else email_service.extract_company_name(company_or_position)
        if not company:
            return "Couldn't determine a company name from that."
        emails = email_service.get_or_fetch_emails(session, company)
        if not emails:
            return f"No public emails found for {company}."
        lines = [f"Company: {company}"]
        for e in emails:
            details = [e.get("type") or "unknown type"]
            if e.get("confidence") is not None:
                details.append(f"{e['confidence']}% confidence")
            if e.get("name"):
                details.append(e["name"])
            lines.append(f"- {e['value']} — {', '.join(details)}")
        return "\n".join(lines)

    @tool_decorator
    async def tailor_resume_for_role(job_description: str, company: str = "", title: str = "") -> str:
        """Tailor the user's resume and write a cover letter for a
        specific job description, via the Laddro Career tools."""
        if not session.resume_text:
            return "No resume has been uploaded yet — ask the user to upload one first."
        if not tailoring_service.nvidia_configured():
            return "Resume tailoring isn't configured on the server (NVIDIA_API_KEY missing)."
        try:
            if not mcp_tools.mcp_configured():
                return "Resume tailoring isn't configured on the server (Node.js/npx is required for CV Forge)."
            result = await tailoring_service.tailor_resume_and_cover_letter(
                session.resume_text, job_description, company, title
            )
        except Exception as exc:
            return f"Tailoring failed: {exc}"
        key = company or "_default"
        session.tailored_cache[key] = result
        download_url = f"{BACKEND_PUBLIC_URL}/resume/tailored/{quote(key, safe='')}/download"
        resume_note = f"Tailored resume DOCX: {download_url}" if result.get("docx_bytes") else "Tailored resume DOCX: unavailable"
        return f"{resume_note}\n\nCover letter:\n{result['cover_letter']}"

    @tool_decorator
    def email_me_results() -> str:
        """Email the last job search results to the user's email address."""
        if not session.user_email:
            return "No email address set. Ask the user to set their email first."
        if not session.last_matches:
            return "No recent job search results to email."
        lines = ["Here are your matched jobs:\n"]
        for i, m in enumerate(session.last_matches, start=1):
            lines.append(f"{i}. {m['title']} at {m['company']} ({m['location']})\n   {m['url']}")
        try:
            email_service.send_email(
                session=session,
                to_addr=session.user_email,
                subject="Your matched LinkedIn jobs",
                body_text="\n\n".join(lines),
            )
        except Exception as exc:
            return f"Failed to send email: {exc}"
        return f"Sent to {session.user_email}."

    @tool_decorator
    async def send_cold_emails(companies: str, message: str = "") -> str:
        """Send cold outreach, attaching a resume tailored to each
        company's role. Only call after the user has confirmed a preview
        you showed them in an earlier turn."""
        if not session.user_email:
            return "No email address set. Ask the user to set their email first."
        if not session.resume_bytes:
            return "No resume uploaded."
        if not email_service.HUNTER_API_KEY:
            return "Hunter.io isn't configured on the server."

        if companies.strip().lower() == "all":
            if not session.last_matches:
                return "No recent job search results to target with 'all'."
            targets = session.last_matches
        else:
            targets = []
            for part in companies.split(","):
                part = part.strip()
                if not part:
                    continue
                resolved = email_service.resolve_target(part, session.last_matches)
                entry = resolved or {"company": email_service.extract_company_name(part), "title": None}
                if entry not in targets:
                    targets.append(entry)

        if not targets:
            return f"Couldn't determine any company to target from '{companies}'."

        results = []
        for target in targets:
            company = target["company"]
            title = target.get("title")
            jd = target.get("summary", "")

            emails = email_service.get_or_fetch_emails(session, company)
            if not emails:
                results.append(f"- {company}: no public email found, skipped")
                continue
            best = sorted(emails, key=lambda e: (e["type"] != "personal", -(e["confidence"] or 0)))[0]
            recipient = best["value"]

            attachment_bytes, attachment_filename = session.resume_bytes, session.resume_filename
            used_tailored = False
            cover_letter_text = None

            cached = session.tailored_cache.get(company)
            tailored = cached
            if tailored is None and jd and tailoring_service.nvidia_configured():
                try:
                    tailored = await tailoring_service.tailor_resume_and_cover_letter(
                        session.resume_text or "", jd, company, title or ""
                    )
                    session.tailored_cache[company] = tailored
                except Exception:
                    tailored = None

            if tailored and tailored.get("docx_bytes"):
                attachment_bytes = tailored["docx_bytes"]
                attachment_filename = f"resume_{safe_filename_part(company)}.docx"
                used_tailored = True
                cover_letter_text = tailored.get("cover_letter")

            subject = f"Application Interest: {title} at {company}" if title else f"Interest in Opportunities at {company}"
            body = message.strip() or cover_letter_text or (
                f"Hi,\n\nI came across {company} and wanted to reach out directly. I've attached my "
                "resume for your consideration and would welcome the chance to discuss opportunities "
                "further.\n\nThanks for your time,\n"
            )

            try:
                email_service.send_email(
                    session=session,
                    to_addr=recipient,
                    subject=subject,
                    body_text=body,
                    attachment_bytes=attachment_bytes,
                    attachment_filename=attachment_filename,
                )
                note = "tailored DOCX resume" if used_tailored else "generic resume (tailoring unavailable/failed)"
                results.append(f"- {company}: sent to {recipient} ({note})")
            except Exception as exc:
                results.append(f"- {company}: failed to send ({exc})")

        return "Cold email results:\n" + "\n".join(results)

    @tool_decorator
    def send_custom_email(to: str, subject: str, body: str, attach_resume: bool = False) -> str:
        """Send a fully custom email to any recipient. Only call after the
        user has confirmed a preview you showed them in an earlier turn."""
        if not session.user_email:
            return "No email address set. Ask the user to set their email first."
        if "@" not in to:
            return f"'{to}' doesn't look like a valid email address."
        attachment_bytes = session.resume_bytes if attach_resume else None
        try:
            email_service.send_email(
                session=session,
                to_addr=to,
                subject=subject,
                body_text=body,
                attachment_bytes=attachment_bytes,
                attachment_filename=session.resume_filename,
            )
        except Exception as exc:
            return f"Failed to send: {exc}"
        return f"Sent to {to}."

    return [
        find_matching_jobs,
        lookup_company_email,
        tailor_resume_for_role,
        email_me_results,
        send_cold_emails,
        send_custom_email,
    ]


async def chat(session, message: str) -> str:
    tools = build_session_tools(session)
    llm = get_llm()
    agent = create_react_agent(llm, tools)

    context_lines = []
    if session.resume_text:
        resume_snippet = session.resume_text[:2000]
        if len(session.resume_text) > 2000:
            resume_snippet += "\n... [truncated]"
        context_lines.append(
            f"\n--- USER'S UPLOADED RESUME (already available) ---\n{resume_snippet}\n--- END RESUME ---"
        )
    else:
        context_lines.append("\nNOTE: The user has NOT uploaded a resume yet.")

    if session.user_email:
        context_lines.append(f"\nUser email: {session.user_email}")
    else:
        context_lines.append("\nNOTE: The user has NOT set their email address yet.")

    if session.last_matches:
        context_lines.append(f"\nLast job search: {len(session.last_matches)} results stored.")

    dynamic_prompt = SYSTEM_PROMPT + "\n".join(context_lines)

    session.chat_history.append(HumanMessage(content=message))
    result = await agent.ainvoke(
        {"messages": [SystemMessage(content=dynamic_prompt)] + session.chat_history}
    )
    reply = result["messages"][-1]
    session.chat_history.append(AIMessage(content=reply.content))
    return reply.content
