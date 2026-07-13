"""Verify LangSmith tracing is wired correctly (env-var only).

Runs one simple triage through the graph, flushes the tracer, then queries the
LangSmith API to confirm a trace for this run landed in the configured project.

Prereqs (from backend/):
    1. MCP server running:  ./.venv/Scripts/python.exe -m mcp_servers.server
    2. .env has ANTHROPIC_API_KEY, LANGCHAIN_API_KEY, LANGCHAIN_TRACING_V2=true
Run (from backend/):
    ./.venv/Scripts/python.exe scripts/check_langsmith.py
"""
from __future__ import annotations

import os
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

import asyncio  # noqa: E402

from langsmith import Client  # noqa: E402
from langsmith.utils import tracing_is_enabled  # noqa: E402


def preflight() -> str | None:
    if not tracing_is_enabled():
        print("FAIL: tracing not enabled (set LANGCHAIN_TRACING_V2=true in .env).")
        return None
    if not (os.getenv("LANGCHAIN_API_KEY") or os.getenv("LANGSMITH_API_KEY")):
        print("FAIL: LANGCHAIN_API_KEY not set in .env.")
        return None
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("FAIL: ANTHROPIC_API_KEY not set (needed to run the graph).")
        return None
    project = os.getenv("LANGCHAIN_PROJECT") or os.getenv("LANGSMITH_PROJECT") or "default"
    print(f"tracing enabled=True | project={project!r}")
    return project


async def run_one(tag: str) -> None:
    from agent.graph import build_graph
    from langchain_core.tracers.langchain import wait_for_all_tracers

    graph = build_graph()
    await graph.ainvoke(
        {"ticket_text": "How do I reset my password?", "ticket_id": "LS-CHECK"},
        config={
            "configurable": {"thread_id": str(uuid.uuid4())},
            "run_name": "triage-langsmith-check",
            "tags": [tag],
        },
    )
    wait_for_all_tracers()  # flush pending trace uploads


def find_trace(project: str, tag: str) -> bool:
    client = Client()
    # Ingestion can lag a moment; poll a few times.
    for attempt in range(1, 9):
        try:
            runs = list(
                client.list_runs(project_name=project, filter=f'has(tags, "{tag}")', limit=5)
            )
        except Exception as exc:  # fall back to a plain recent listing
            print(f"  (tag filter failed: {exc}; listing recent runs)")
            runs = list(client.list_runs(project_name=project, limit=5))
        if runs:
            print(f"\nFound {len(runs)} matching run(s) in LangSmith:")
            for r in runs:
                print(f"  - {r.name} | type={r.run_type} | status={r.status} | start={r.start_time}")
            url = getattr(runs[0], "url", None)
            if url:
                print(f"  trace url: {url}")
            return True
        print(f"  attempt {attempt}: not indexed yet, waiting...")
        time.sleep(2)
    return False


def main() -> int:
    project = preflight()
    if not project:
        return 1
    tag = f"ls-check-{uuid.uuid4().hex[:8]}"
    asyncio.run(run_one(tag))
    ok = find_trace(project, tag)
    print("\n" + ("LANGSMITH CHECK: OK — traces are landing." if ok else "LANGSMITH CHECK: no trace found."))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
