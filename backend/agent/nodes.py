"""LangGraph node implementations for the support triage agent.

Step 2: `resolve_via_tools` and `apply_decision` now call the real MCP tool
servers (ticket_lookup, knowledge_base_search, send_email) via the MCP client.
Nodes are async so they can await MCP tool calls and the LLM.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Literal

from langchain_anthropic import ChatAnthropic
from langgraph.types import interrupt
from pydantic import BaseModel, Field

from .mcp_client import call_tool
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
    # Instantiated lazily so importing this module never requires an API key.
    return ChatAnthropic(model=CLASSIFIER_MODEL, temperature=0)


def _parse(result: Any) -> Any:
    """Normalize an MCP tool result to a Python object.

    langchain-mcp-adapters may return a dict, a JSON string, or a list of
    content blocks like [{"type": "text", "text": "<json>"}]. Unwrap all three.
    """
    if isinstance(result, dict):
        return result
    if isinstance(result, list):
        texts = [b.get("text", "") for b in result if isinstance(b, dict) and b.get("type") == "text"]
        result = texts[0] if texts else (result[0] if result else "")
    if isinstance(result, str):
        try:
            return json.loads(result)
        except (ValueError, TypeError):
            return result
    return result


async def classify_ticket(state: TriageState) -> dict:
    """Single LLM call: classify the ticket as simple or ambiguous."""
    ticket_text = state["ticket_text"]
    llm = _classifier_llm().with_structured_output(Classification)
    prompt = (
        "You are a support-ticket triage classifier. Classify the following "
        "ticket.\n\nTicket:\n"
        f"{ticket_text}"
    )
    result: Classification = await llm.ainvoke(prompt)
    logger.info("classify_ticket -> %s: %s", result.category, result.reasoning)
    return {"category": result.category, "reasoning": result.reasoning}


async def resolve_via_tools(state: TriageState) -> dict:
    """Simple tickets: gather info via MCP tools and propose a resolution."""
    ticket_id = state.get("ticket_id", "UNKNOWN")

    ticket = _parse(await call_tool("ticket_lookup", {"ticket_id": ticket_id}))
    kb = _parse(await call_tool("knowledge_base_search", {"query": state["ticket_text"]}))

    gathered_info = [
        {"tool": "ticket_lookup", "result": ticket},
        {"tool": "knowledge_base_search", "result": kb},
    ]

    customer = ticket.get("customer", "demo@example.com") if isinstance(ticket, dict) else "demo@example.com"
    snippets = kb.get("snippets", []) if isinstance(kb, dict) else []
    kb_body = snippets[0]["body"] if snippets else "Please see our knowledge base."

    resolution = {
        "action": "send_response",
        "to": customer,
        "subject": f"Re: ticket {ticket_id}",
        "body": f"Thanks for reaching out. {kb_body}",
        "auto_resolved": True,
    }
    logger.info("resolve_via_tools -> proposed action=%s to=%s", resolution["action"], customer)
    return {"gathered_info": gathered_info, "resolution": resolution}


async def human_approval(state: TriageState) -> dict:
    """Ambiguous tickets: pause for a human approve/reject decision.

    `interrupt()` checkpoints the graph and suspends until it is resumed with a
    value (via Command(resume=...)). That value is the human's decision.
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


async def apply_decision(state: TriageState) -> dict:
    """Execute the final action; sending a response calls the send_email MCP tool."""
    category = state.get("category")

    if category == "simple":
        resolution = state["resolution"]
        email = _parse(
            await call_tool(
                "send_email",
                {"to": resolution["to"], "subject": resolution["subject"], "body": resolution["body"]},
            )
        )
        action = {"type": resolution["action"], "detail": "Auto-resolved simple ticket.", "email": email}
        status = "resolved"
    else:
        decision = state.get("human_decision", "reject")
        if decision == "approve":
            ticket_id = state.get("ticket_id", "UNKNOWN")
            email = _parse(
                await call_tool(
                    "send_email",
                    {
                        "to": "demo@example.com",
                        "subject": f"Re: ticket {ticket_id}",
                        "body": "A support agent has approved handling your request.",
                    },
                )
            )
            action = {"type": "send_response", "detail": "Human approved auto-resolution.", "email": email}
            status = "resolved"
        else:
            action = {"type": "escalate", "detail": "Human rejected; escalated to a human agent."}
            status = "escalated"

    logger.info("apply_decision -> status=%s action=%s", status, action["type"])
    return {"final_action": action, "status": status}
