"""
Connects to the CV Forge MCP server (self-hosted via npm).

No API key needed. The server auto-installs via npx and runs locally
on stdio transport. Requires Node.js 18+ installed.

Tools available:
- draft_complete_application — generates CV PDF + cover letter + email
- generate_cv — generates tailored CV
- generate_cover_letter — generates cover letter
- parse_job_requirements — extracts skills from JD
"""
import asyncio
import os
import shutil
from langchain_mcp_adapters.client import MultiServerMCPClient

_client: MultiServerMCPClient | None = None
_tools_cache = None


def _has_node() -> bool:
    return shutil.which("node") is not None or shutil.which("npx") is not None


def mcp_configured() -> bool:
    return _has_node()


def _get_client() -> MultiServerMCPClient:
    global _client
    if _client is None:
        if not _has_node():
            raise RuntimeError(
                "Node.js is not installed. CV Forge MCP server requires Node.js 18+.\n"
                "Download from https://nodejs.org/ and restart the backend."
            )
        _client = MultiServerMCPClient(
            {
                "cv_forge": {
                    "transport": "stdio",
                    "command": "npx",
                    "args": ["-y", "cv-forge"],
                }
            }
        )
    return _client


async def get_mcp_tools():
    """Fetch (and cache) the MCP tools as LangChain tools."""
    global _tools_cache
    if _tools_cache is None:
        client = _get_client()
        _tools_cache = await client.get_tools()
    return _tools_cache


# Aliases so main.py's diagnostic endpoints (/test/config, /test/tailor)
# can call these under the names they expect.
laddro_configured = mcp_configured
get_laddro_tools = get_mcp_tools
LADDRO_MCP_URL = "cv-forge (npx, stdio)"
