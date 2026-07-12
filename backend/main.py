"""FastAPI app exposing the support triage agent.

Endpoints:
    GET  /health   -> liveness check
    POST /triage   -> run a ticket through the graph; may pause for approval
    POST /resume   -> resume a paused (interrupted) run with approve/reject

Load order matters: `.env` is loaded before importing the graph so that
LangSmith tracing env vars (wired in Step 3) take effect, and so the
ANTHROPIC_API_KEY is present when the classifier LLM is first used.
"""
from __future__ import annotations

import logging
import uuid

from dotenv import load_dotenv

load_dotenv()  # noqa: E402 -- must run before graph/LLM imports

from fastapi import FastAPI, HTTPException  # noqa: E402
from langgraph.types import Command  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from agent.graph import get_graph  # noqa: E402

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Support Triage Agent", version="0.1.0")


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


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/triage")
def triage(req: TriageRequest) -> dict:
    graph = get_graph()
    thread_id = str(uuid.uuid4())
    ticket_id = req.ticket_id or f"T-{thread_id[:8]}"

    result = graph.invoke(
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
    }


@app.post("/resume")
def resume(req: ResumeRequest) -> dict:
    decision = req.decision.strip().lower()
    if decision not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="decision must be 'approve' or 'reject'")

    graph = get_graph()
    config = _config(req.thread_id)

    # Guard: the thread must exist and actually be waiting on an interrupt.
    snapshot = graph.get_state(config)
    if not snapshot.created_at:
        raise HTTPException(status_code=404, detail="unknown thread_id")
    if not snapshot.next:
        raise HTTPException(status_code=409, detail="run already completed; nothing to resume")

    result = graph.invoke(Command(resume=decision), config=config)

    return {
        "thread_id": req.thread_id,
        "status": result.get("status"),
        "category": result.get("category"),
        "reasoning": result.get("reasoning"),
        "human_decision": result.get("human_decision"),
        "final_action": result.get("final_action"),
    }
