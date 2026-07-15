"""LangGraph wiring for the support triage agent.

Flow:
    START -> classify_ticket -> (conditional on category)
        simple    -> resolve_via_tools -> apply_decision -> END
        ambiguous -> human_approval     -> apply_decision -> END

A checkpointer is required so that `interrupt()` in human_approval can suspend
the run and resume it later (same thread_id). Step 1 uses an in-memory
checkpointer (MemorySaver); a durable checkpointer can be swapped in later.
"""
from __future__ import annotations

from functools import lru_cache

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from .nodes import (
    apply_decision,
    classify_ticket,
    human_approval,
    reject_invalid,
    resolve_via_tools,
)
from .state import TriageState


def _route_after_classify(state: TriageState) -> str:
    """Conditional edge: pick the branch based on the classification."""
    category = state.get("category")
    if category == "invalid":
        return "reject_invalid"
    if category == "simple":
        return "resolve_via_tools"
    return "human_approval"


def build_graph():
    """Construct and compile the triage graph with a checkpointer."""
    builder = StateGraph(TriageState)

    builder.add_node("classify_ticket", classify_ticket)
    builder.add_node("resolve_via_tools", resolve_via_tools)
    builder.add_node("human_approval", human_approval)
    builder.add_node("reject_invalid", reject_invalid)
    builder.add_node("apply_decision", apply_decision)

    builder.add_edge(START, "classify_ticket")
    builder.add_conditional_edges(
        "classify_ticket",
        _route_after_classify,
        {
            "resolve_via_tools": "resolve_via_tools",
            "human_approval": "human_approval",
            "reject_invalid": "reject_invalid",
        },
    )
    builder.add_edge("resolve_via_tools", "apply_decision")
    builder.add_edge("human_approval", "apply_decision")
    # invalid input terminates immediately — no apply_decision, no tools.
    builder.add_edge("reject_invalid", END)
    builder.add_edge("apply_decision", END)

    return builder.compile(checkpointer=MemorySaver())


@lru_cache(maxsize=1)
def get_graph():
    """Return a process-wide singleton compiled graph.

    The MemorySaver checkpointer lives on this instance, so the same graph
    object must handle both /triage and the follow-up /resume for a thread.
    """
    return build_graph()
