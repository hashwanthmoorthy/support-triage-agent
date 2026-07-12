"""Client wiring that loads MCP tools for the agent.

Connects to the triage-tools MCP server over streamable-HTTP and exposes the
tools as LangChain tools via langchain-mcp-adapters. The server URL is
env-configurable so Docker can point at the compose service name.
"""
from __future__ import annotations

import os
from functools import lru_cache

from langchain_mcp_adapters.client import MultiServerMCPClient

# e.g. http://mcp:8100/mcp inside docker-compose
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://127.0.0.1:8100/mcp")


@lru_cache(maxsize=1)
def _client() -> MultiServerMCPClient:
    return MultiServerMCPClient(
        {
            "triage_tools": {
                "url": MCP_SERVER_URL,
                "transport": "streamable_http",
            }
        }
    )


async def load_tools() -> dict:
    """Return a {tool_name: tool} map loaded from the MCP server."""
    tools = await _client().get_tools()
    return {t.name: t for t in tools}


async def call_tool(name: str, args: dict):
    """Invoke a single MCP tool by name and return its (parsed) result."""
    tools = await load_tools()
    if name not in tools:
        raise KeyError(f"MCP tool {name!r} not found; available: {sorted(tools)}")
    return await tools[name].ainvoke(args)
