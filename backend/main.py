"""FastAPI app exposing the support triage agent.

Endpoints:
    GET  /health   -> liveness check
    POST /triage   -> run a ticket through the graph; may pause for approval
    POST /resume   -> resume a paused (interrupted) run with approve/reject

Load order matters: `.env` is loaded before importing the graph so that
LangSmith tracing env vars take effect, and so the ANTHROPIC_API_KEY is present
when the classifier LLM is first used.

LangSmith tracing is enabled purely via env vars (no custom code):
LANGCHAIN_TRACING_V2=true, LANGCHAIN_API_KEY, LANGCHAIN_PROJECT. langsmith
honors both the LANGSMITH_* and LANGCHAIN_* namespaces, so the spec's
LANGCHAIN_* names work as-is.
"""
from __future__ import annotations

import logging
import uuid
from pathlib import Path

from dotenv import load_dotenv

# Explicitly load the repo-root .env regardless of the current working directory
# (uvicorn may be launched from anywhere). Must run before graph/LLM imports.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")  # noqa: E402

import os  # noqa: E402

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from langgraph.types import Command  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from agent.graph import get_graph  # noqa: E402

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Support Triage Agent", version="0.1.0")

# CORS for the frontend (demo: no auth). Override origins via CORS_ORIGINS
# (comma-separated); defaults cover the Vite dev server.
_default_origins = "http://localhost:5173,http://127.0.0.1:5173"
_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", _default_origins).split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


class TriageRequest(BaseModel):
    ticket_text: str = Field(..., min_length=1)
    ticket_id: str | None = None


class ResumeRequest(BaseModel):
    thread_id: str
    decision: str = Field(..., description="'approve' or 'reject'")


def _config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


def _extract_interrupt(result: dict):
    """Return the interrupt payload if the run paused, else None."""
    interrupts = result.get("__interrupt__")
    if not interrupts:
        return None
    intr = interrupts[0]
    # Interrupt objects expose .value; be defensive across versions.
    return getattr(intr, "value", intr)


def _extract_sources(result: dict) -> list[dict]:
    """Pull the KB docs used by knowledge_base_search from the run state.

    Returns [{"source": <doc>, "distance": <float>}], deduped by doc (best
    distance kept), in retrieval order. Empty when RAG wasn't used.
    """
    seen: dict[str, float] = {}
    order: list[str] = []
    for entry in result.get("gathered_info", []) or []:
        if entry.get("tool") != "knowledge_base_search":
            continue
        for snip in (entry.get("result", {}) or {}).get("snippets", []):
            src = snip.get("source")
            if not src:
                continue
            dist = snip.get("distance")
            if src not in seen:
                seen[src] = dist
                order.append(src)
            elif dist is not None and (seen[src] is None or dist < seen[src]):
                seen[src] = dist
    return [{"source": s, "distance": seen[s]} for s in order]


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/triage")
async def triage(req: TriageRequest) -> dict:
    graph = get_graph()
    thread_id = str(uuid.uuid4())
    ticket_id = req.ticket_id or f"T-{thread_id[:8]}"

    result = await graph.ainvoke(
        {"ticket_text": req.ticket_text, "ticket_id": ticket_id},
        config=_config(thread_id),
    )

    payload = _extract_interrupt(result)
    if payload is not None:
        return {
            "thread_id": thread_id,
            "ticket_id": ticket_id,
            "status": "pending_approval",
            "category": payload.get("category"),
            "reasoning": payload.get("reasoning"),
            "approval_request": payload,
        }

    return {
        "thread_id": thread_id,
        "ticket_id": ticket_id,
        "status": result.get("status"),
        "category": result.get("category"),
        "reasoning": result.get("reasoning"),
        "final_action": result.get("final_action"),
        "resolution": result.get("resolution"),
        "sources": _extract_sources(result),
    }


@app.post("/resume")
async def resume(req: ResumeRequest) -> dict:
    decision = req.decision.strip().lower()
    if decision not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="decision must be 'approve' or 'reject'")

    graph = get_graph()
    config = _config(req.thread_id)

    # Guard: the thread must exist and actually be waiting on an interrupt.
    snapshot = await graph.aget_state(config)
    if not snapshot.created_at:
        raise HTTPException(status_code=404, detail="unknown thread_id")
    if not snapshot.next:
        raise HTTPException(status_code=409, detail="run already completed; nothing to resume")

    result = await graph.ainvoke(Command(resume=decision), config=config)

    return {
        "thread_id": req.thread_id,
        "status": result.get("status"),
        "category": result.get("category"),
        "reasoning": result.get("reasoning"),
        "human_decision": result.get("human_decision"),
        "final_action": result.get("final_action"),
        "resolution": result.get("resolution"),
        "sources": _extract_sources(result),
    }
