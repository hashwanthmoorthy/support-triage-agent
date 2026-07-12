"""Isolation test for the MCP tool server (no LLM, no graph).

Connects to the running triage-tools MCP server, lists the tools, and calls
each one directly to confirm the mock payloads.

Prereq: start the server first (from backend/):
    ./.venv/Scripts/python.exe -m mcp_servers.server
Then run (from backend/):
    ./.venv/Scripts/python.exe scripts/test_mcp_tools.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.mcp_client import call_tool, load_tools  # noqa: E402


def show(label, obj):
    print(f"\n=== {label} ===")
    print(json.dumps(obj, indent=2, default=str))


async def main() -> int:
    tools = await load_tools()
    names = sorted(tools)
    show("tools discovered", names)
    assert set(names) == {"ticket_lookup", "knowledge_base_search", "send_email"}, names

    t = await call_tool("ticket_lookup", {"ticket_id": "T-2002"})
    show("ticket_lookup(T-2002)", t)

    kb = await call_tool("knowledge_base_search", {"query": "reset password"})
    show("knowledge_base_search('reset password')", kb)

    email = await call_tool(
        "send_email", {"to": "x@example.com", "subject": "Hi", "body": "hello there"}
    )
    show("send_email(...)", email)

    print("\nMCP ISOLATION TEST: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
