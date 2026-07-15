"""Test the invalid-category gate alongside genuine tickets.

Usage (from backend/), with the MCP server running:
    ./.venv/Scripts/python.exe scripts/test_categories.py genuine
    ./.venv/Scripts/python.exe scripts/test_categories.py invalid

Split into two modes so the MCP server log can be inspected: running `invalid`
against a fresh server should produce ZERO tool calls.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

from langgraph.types import Command  # noqa: E402

from agent.graph import build_graph  # noqa: E402

GENUINE = [
    ("I forgot my password and I'm locked out. How do I reset it?", "simple"),
    ("How long does shipping take for a hardware order?", "simple"),
    ("I was charged twice this month. I want a full refund and my account closed.", "ambiguous"),
]

INVALID = [
    "tell me about u",
    "what's the weather today?",
    "hi there",
    "asdfghjkl qwerty",
]


def _cfg(t):
    return {"configurable": {"thread_id": t}}


def _interrupt(result):
    ints = result.get("__interrupt__")
    return getattr(ints[0], "value", ints[0]) if ints else None


async def run_genuine(graph):
    ok = True
    for text, expected in GENUINE:
        r = await graph.ainvoke({"ticket_text": text, "ticket_id": "T-1001"}, config=_cfg(str(uuid.uuid4())))
        cat = r.get("category")
        if expected == "simple":
            passed = cat == "simple" and r.get("status") == "resolved" and \
                {g["tool"] for g in r.get("gathered_info", [])} == {"ticket_lookup", "knowledge_base_search"}
        else:  # ambiguous -> paused
            passed = cat == "ambiguous" and _interrupt(r) is not None
        ok = ok and passed
        print(f"  [{'OK' if passed else 'FAIL'}] {expected:9} <- {cat:9} | {text[:50]!r}")
    print("GENUINE:", "ALL OK" if ok else "FAILURES")
    return ok


async def run_invalid(graph):
    ok = True
    for text in INVALID:
        r = await graph.ainvoke({"ticket_text": text, "ticket_id": "T-1001"}, config=_cfg(str(uuid.uuid4())))
        cat, status = r.get("category"), r.get("status")
        # Must be invalid, terminate with clarification, and have gathered NOTHING.
        passed = (
            cat == "invalid"
            and status == "invalid"
            and r.get("final_action", {}).get("type") == "request_clarification"
            and "gathered_info" not in r
        )
        ok = ok and passed
        print(f"  [{'OK' if passed else 'FAIL'}] invalid  <- {cat!s:9} status={status} | {text[:40]!r}")
    print("INVALID:", "ALL OK" if ok else "FAILURES")
    return ok


async def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "genuine"
    graph = build_graph()
    ok = await (run_invalid(graph) if mode == "invalid" else run_genuine(graph))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
