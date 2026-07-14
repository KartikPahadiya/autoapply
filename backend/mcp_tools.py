"""
Loads the Laddro Career MCP server's tools (resume tailoring, cover
letter generation, PDF export, etc.) as real LangChain tools, via the
official langchain-mcp-adapters package — not a hand-rolled MCP client.

Loaded once and cached for the whole process: this is the app's own
Laddro/Smithery account (one bearer token from .env), not per-user data,
so sharing the connection across sessions is fine — same treatment as the
Apify/Hunter/HuggingFace credentials elsewhere in this backend.

NOTE: the exact tool names/schemas this server exposes aren't hardcoded
here on purpose — get_laddro_tools() just returns whatever the server
advertises, and the sub-agent in tailoring_service.py is the one that
reads each tool's description and decides how to call it. If you know the
exact tool names (e.g. from docs.laddro.com/docs/mcp) and want tighter,
non-agentic control, you can call the LangChain tool objects returned
here directly by name instead of going through the agent.
"""
import os

from langchain_mcp_adapters.client import MultiServerMCPClient

LADDRO_MCP_URL = os.getenv("LADDRO_MCP_URL", "https://mcp.smithery.run/kartikpahadiya122004")
LADDRO_MCP_API_KEY = os.getenv("LADDRO_MCP_API_KEY")

_client: MultiServerMCPClient | None = None
_tools_cache = None


def laddro_configured() -> bool:
    return bool(LADDRO_MCP_API_KEY)


def _get_client() -> MultiServerMCPClient:
    global _client
    if _client is None:
        if not laddro_configured():
            raise RuntimeError("LADDRO_MCP_API_KEY is not set in .env — Laddro Career tools are unavailable.")
        _client = MultiServerMCPClient(
            {
                "laddro_career": {
                    "transport": "streamable_http",
                    "url": LADDRO_MCP_URL,
                    "headers": {"Authorization": f"Bearer {LADDRO_MCP_API_KEY}"},
                }
            }
        )
    return _client


async def get_laddro_tools():
    """Fetch (and cache) the Laddro Career MCP tools as LangChain tools."""
    global _tools_cache
    if _tools_cache is None:
        client = _get_client()
        _tools_cache = await client.get_tools()
    return _tools_cache
