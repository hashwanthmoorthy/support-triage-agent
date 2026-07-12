"""LangGraph node implementations for the support triage agent.

Step 1: the tool-gathering step (`resolve_via_tools`) and the action executor
(`apply_decision`) use inline stubs. Step 2 replaces the stubs with real MCP
tool-server calls (ticket_lookup, knowledge_base_search, send_email).
"""
from __future__ import annotations

import logging
from typing import Literal

from langchain_anthropic import ChatAnthropic
from langgraph.types import interrupt
from pydantic import BaseModel, Field

from .state import TriageState

logger = logging.getLogger("triage.nodes")

# Fast, cheap model is plenty for a single classification call.
CLASSIFIER_MODEL = "claude-haiku-4-5-20251001"


class Classification(BaseModel):
    """Structured output for the classify_ticket node."""

    category: Literal["simple", "ambiguous"] = Field(
        description=(
            "'simple' if the ticket can be safely resolved automatically with "
            "known tools/knowledge-base answers (password resets, status checks, "
            "FAQ-style questions). 'ambiguous' if it needs human judgment "
            "(refunds, account changes, complaints, anything risky or unclear)."
        )
    )
    reasoning: str = Field(description="One or two sentences explaining the choice.")


def _classifier_llm() -> ChatAnthropic:
    # Instantiated lazily so importing this module never requires an API key
    # (keeps `import`-time side effects out; key is only needed at call time).
    return ChatAnthropic(model=CLASSIFIER_MODEL, temperature=0)


def classify_ticket(state: TriageState) -> dict:
    """Single LLM call: classify the ticket as simple or ambiguous."""
    ticket_text = state["ticket_text"]
    llm = _classifier_llm().with_structured_output(Classification)
    prompt = (
        "You are a support-ticket triage classifier. Classify the following "
        "ticket.\n\nTicket:\n"
        f"{ticket_text}"
    )
    result: Classification = llm.invoke(prompt)
    logger.info("classify_ticket -> %s: %s", result.category, result.reasoning)
    return {"category": result.category, "reasoning": result.reasoning}


def resolve_via_tools(state: TriageState) -> dict:
    """Simple tickets: gather info via tools and produce a resolution action.

    Step 1 STUB: returns canned info instead of calling MCP servers. The shape
    mirrors what the real MCP tools will return in Step 2.
    """
    ticket_id = state.get("ticket_id", "UNKNOWN")

    # --- stubbed tool calls (replaced by MCP in Step 2) ---
    gathered_info = [
        {
            "tool": "ticket_lookup",
            "result": {
                "ticket_id": ticket_id,
                "status": "open",
                "customer": "demo@example.com",
                "product": "WidgetPro",
            },
        },
        {
            "tool": "knowledge_base_search",
            "result": {
                "query": state["ticket_text"][:60],
                "snippets": ["[STUB] Follow the standard KB steps to resolve."],
            },
        },
    ]

    resolution = {
        "action": "send_response",
        "to": "demo@example.com",
        "subject": f"Re: ticket {ticket_id}",
        "body": "[STUB auto-resolution] Based on our knowledge base, here are the steps...",
        "auto_resolved": True,
    }
    logger.info("resolve_via_tools -> proposed action=%s", resolution["action"])
    return {"gathered_info": gathered_info, "resolution": resolution}


def human_approval(state: TriageState) -> dict:
    """Ambiguous tickets: pause for a human approve/reject decision.

    `interrupt()` checkpoints the graph and suspends until the graph is resumed
    with a value (via Command(resume=...)). The value is the human's decision.
    """
    payload = {
        "ticket_id": state.get("ticket_id", "UNKNOWN"),
        "ticket_text": state["ticket_text"],
        "category": state.get("category"),
        "reasoning": state.get("reasoning"),
        "question": "Approve auto-resolution, or reject to escalate?",
    }
    decision = interrupt(payload)  # <- resumes here with the submitted value

    decision = str(decision).strip().lower()
    if decision not in ("approve", "reject"):
        decision = "reject"  # fail safe: unknown input escalates
    logger.info("human_approval -> decision=%s", decision)
    return {"human_decision": decision}


def apply_decision(state: TriageState) -> dict:
    """Execute the final action based on auto-resolution or human decision.

    Step 1 STUB: the actual side effect (send_email) is mocked in Step 2 via the
    send_email MCP tool. Here we just record what would happen.
    """
    category = state.get("category")

    if category == "simple":
        action = {
            "type": state["resolution"]["action"],  # e.g. send_response
            "detail": "Auto-resolved simple ticket.",
            "resolution": state["resolution"],
        }
        status = "resolved"
    else:
        decision = state.get("human_decision", "reject")
        if decision == "approve":
            action = {
                "type": "send_response",
                "detail": "Human approved auto-resolution.",
            }
            status = "resolved"
        else:
            action = {
                "type": "escalate",
                "detail": "Human rejected; escalated to a human agent.",
            }
            status = "escalated"

    logger.info("apply_decision -> status=%s action=%s", status, action["type"])
    return {"final_action": action, "status": status}
