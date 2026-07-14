"""
Resume tailoring + cover letter generation, using the Laddro Career MCP
tools. The NVIDIA Nemotron model drives a sub-agent that calls the tools,
and this module extracts structured results (PDF URLs, cover letter text)
from the tool responses — not just the agent's conversational summary.
"""
import json
import os
import re

import requests
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_nvidia_ai_endpoints import ChatNVIDIA
from langgraph.prebuilt import create_react_agent

from mcp_tools import LADDRO_MCP_API_KEY, get_laddro_tools

NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")

_nvidia_llm: ChatNVIDIA | None = None
_tailoring_agent = None


def nvidia_configured() -> bool:
    return bool(NVIDIA_API_KEY)


def _get_nvidia_llm() -> ChatNVIDIA:
    global _nvidia_llm
    if _nvidia_llm is None:
        if not nvidia_configured():
            raise RuntimeError("NVIDIA_API_KEY is not set in .env — resume tailoring is unavailable.")
        _nvidia_llm = ChatNVIDIA(
            model="nvidia/nemotron-3-ultra-550b-a55b",
            api_key=NVIDIA_API_KEY,
            temperature=1,
            top_p=0.95,
            max_tokens=16384,
        )
    return _nvidia_llm


async def _get_tailoring_agent():
    global _tailoring_agent
    if _tailoring_agent is None:
        tools = await get_laddro_tools()
        _tailoring_agent = create_react_agent(_get_nvidia_llm(), tools)
    return _tailoring_agent


TAILORING_SYSTEM_PROMPT = """You are a resume-tailoring assistant with access to the Laddro Career MCP tools.

You MUST perform these steps IN ORDER:
1. Call laddro.resumes.tailor with the candidate's resume and job description to produce a tailored resume.
2. Call laddro.resumes.export to export the tailored resume as a PDF. This will return a download URL.
3. Call laddro.coverLetters.generate with the resume and job description to produce a cover letter.

After all three tools have been called, return ONLY this exact JSON format — no extra text, no markdown, no explanation:

{
  "pdf_url": "<exact URL from the export tool>",
  "cover_letter": "<full cover letter text from the generate tool>"
}

If any tool fails, return:
{
  "pdf_url": null,
  "cover_letter": "<error message>"
}
"""


def _extract_pdf_url(text: str) -> str | None:
    """Look for a PDF URL in raw text."""
    if not text:
        return None
    match = re.search(r"https?://[^\s\"]+\.pdf[^\s\"]*", text, re.IGNORECASE)
    return match.group(0) if match else None


def _parse_json_response(text: str) -> dict:
    """Try to parse text as JSON; return empty dict on failure."""
    if not text or not text.strip():
        return {}
    try:
        data = json.loads(text.strip())
        return data if isinstance(data, dict) else {"_raw": data}
    except (json.JSONDecodeError, TypeError):
        return {}


def _extract_from_dict(data: dict) -> tuple[str | None, str | None]:
    """Scan a dict for PDF URLs and cover letter text using common field names."""
    pdf_url = None
    cover_letter = None

    # Recursively flatten the dict into key-value pairs
    def flatten(obj, prefix=""):
        items = []
        if isinstance(obj, dict):
            for k, v in obj.items():
                items.extend(flatten(v, f"{prefix}.{k}" if prefix else k))
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                items.extend(flatten(v, f"{prefix}[{i}]"))
        else:
            items.append((prefix, obj))
        return items

    for key, value in flatten(data):
        if isinstance(value, str):
            # Look for PDF URL
            if not pdf_url and ".pdf" in value.lower() and value.startswith("http"):
                pdf_url = value
            # Look for cover letter text (longer strings that aren't URLs)
            if not cover_letter and len(value) > 100 and not value.startswith("http"):
                cover_letter = value

    return pdf_url, cover_letter


async def tailor_resume_and_cover_letter(
    resume_text: str, job_description: str, company: str = "", title: str = ""
) -> dict:
    """Runs the NVIDIA-backed sub-agent with the Laddro MCP tools to
    produce a tailored resume PDF + cover letter for a specific role.

    Returns {"cover_letter": str, "tailored_resume_url": str | None,
    "raw_reply": str}. Extracts structured data from tool responses
    (JSON) rather than relying on the agent's conversational summary.
    """
    agent = await _get_tailoring_agent()

    user_prompt = (
        f"Candidate resume:\n{resume_text}\n\n"
        f"Target job description:\n{job_description}\n\n"
        f"Company: {company or 'unspecified'}\n"
        f"Job title: {title or 'unspecified'}\n\n"
        "Call the Laddro tools in order: (1) laddro.resumes.tailor, "
        "(2) laddro.resumes.export, (3) laddro.coverLetters.generate. "
        "Then return ONLY the JSON with pdf_url and cover_letter."
    )

    result = await agent.ainvoke(
        {"messages": [SystemMessage(content=TAILORING_SYSTEM_PROMPT), HumanMessage(content=user_prompt)]}
    )
    messages = result["messages"]
    final_reply = messages[-1].content if messages else ""

    pdf_url = None
    cover_letter = None

    # 1. Extract from tool messages (most reliable — actual tool outputs)
    for msg in messages:
        if isinstance(msg, ToolMessage) and isinstance(msg.content, str):
            parsed = _parse_json_response(msg.content)
            if parsed:
                pu, cl = _extract_from_dict(parsed)
                if pu and not pdf_url:
                    pdf_url = pu
                if cl and not cover_letter:
                    cover_letter = cl
            # Also try regex on raw text
            if not pdf_url:
                pdf_url = _extract_pdf_url(msg.content)
            # Raw text might be the cover letter itself
            if not cover_letter and msg.content and len(msg.content) > 200:
                cover_letter = msg.content

    # 2. Extract from final reply (agent's own output)
    if not pdf_url:
        pdf_url = _extract_pdf_url(final_reply)

    parsed_final = _parse_json_response(final_reply)
    if parsed_final:
        pu, cl = _extract_from_dict(parsed_final)
        if pu and not pdf_url:
            pdf_url = pu
        if cl and not cover_letter:
            cover_letter = cl

    # 3. Fallback: try to extract JSON block from final reply
    if not cover_letter and not parsed_final:
        json_block = re.search(r"\{[\s\S]*?\}", final_reply)
        if json_block:
            parsed_block = _parse_json_response(json_block.group(0))
            if parsed_block:
                pu, cl = _extract_from_dict(parsed_block)
                if pu and not pdf_url:
                    pdf_url = pu
                if cl and not cover_letter:
                    cover_letter = cl

    # 4. Last resort: use the entire final reply as cover letter
    if not cover_letter:
        cover_letter = final_reply

    return {
        "cover_letter": cover_letter,
        "tailored_resume_url": pdf_url,
        "raw_reply": final_reply,
    }


def download_pdf(url: str) -> bytes | None:
    """Fetch the tailored resume PDF bytes so it can be attached to an
    email or streamed to the frontend, instead of just handing back a
    link (which may require the same auth this backend has)."""
    headers = {}
    if LADDRO_MCP_API_KEY:
        headers["Authorization"] = f"Bearer {LADDRO_MCP_API_KEY}"
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        return resp.content
    except requests.RequestException:
        return None
