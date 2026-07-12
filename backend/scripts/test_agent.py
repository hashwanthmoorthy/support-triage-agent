"""Local smoke test for the triage graph (no HTTP server needed).

Runs a clearly-simple ticket end-to-end (which now calls the real MCP tools),
then an ambiguous ticket that must pause at human_approval; resumes it once
with 'reject' and once with 'approve'.

Prereq: start the MCP server first (from backend/):
    ./.venv/Scripts/python.exe -m mcp_servers.server
Then run (from backend/):
    ./.venv/Scripts/python.exe scripts/test_agent.py
Requires ANTHROPIC_API_KEY in ../.env or the environment.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid

# Make `agent` importable when run from backend/.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

from langgraph.types import Command  # noqa: E402

from agent.graph import build_graph  # noqa: E402


def _config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


def _interrupt_payload(result: dict):
    interrupts = result.get("__interrupt__")
    if not interrupts:
        return None
    intr = interrupts[0]
    return getattr(intr, "value", intr)


def show(label: str, obj) -> None:
    print(f"\n=== {label} ===")
    print(json.dumps(obj, indent=2, default=str))


async def run_simple(graph) -> None:
    tid = str(uuid.uuid4())
    result = await graph.ainvoke(
        {
            "ticket_text": "I forgot my password and need to reset it to log in.",
            "ticket_id": "T-1001",
        },
        config=_config(tid),
    )
    assert _interrupt_payload(result) is None, "simple ticket should NOT pause"
    assert result.get("category") == "simple", f"expected simple, got {result.get('category')}"
    assert result.get("status") == "resolved", f"expected resolved, got {result.get('status')}"
    # Confirm the MCP tools actually ran.
    tools_used = {g["tool"] for g in result.get("gathered_info", [])}
    assert tools_used == {"ticket_lookup", "knowledge_base_search"}, tools_used
    assert result["final_action"].get("email", {}).get("ok") is True, "send_email MCP tool should have run"
    show("SIMPLE ticket -> auto-resolved (via MCP tools)", result)


async def run_ambiguous(graph, decision: str, expected_status: str) -> None:
    tid = str(uuid.uuid4())
    result = await graph.ainvoke(
        {
            "ticket_text": (
                "I was charged twice for my subscription this month and I'm very "
                "upset. I want a full refund AND my account closed permanently."
            ),
            "ticket_id": f"T-AMBIG-{decision.upper()}",
        },
        config=_config(tid),
    )
    payload = _interrupt_payload(result)
    assert payload is not None, "ambiguous ticket MUST pause for approval"
    show(f"AMBIGUOUS ticket -> paused (will {decision})", payload)

    resumed = await graph.ainvoke(Command(resume=decision), config=_config(tid))
    assert resumed.get("human_decision") == decision
    assert resumed.get("status") == expected_status, (
        f"expected {expected_status}, got {resumed.get('status')}"
    )
    show(f"AMBIGUOUS resumed with '{decision}' -> {resumed.get('status')}", resumed)


async def main() -> int:
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY not set (put it in .env). Cannot run LLM classify.")
        return 1

    graph = build_graph()
    await run_simple(graph)
    await run_ambiguous(graph, "reject", "escalated")
    await run_ambiguous(graph, "approve", "resolved")
    print("\nALL ASSERTIONS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
