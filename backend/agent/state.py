"""Graph state schema for the support triage agent."""
from __future__ import annotations

from typing import Any, Literal, Optional, TypedDict


class TriageState(TypedDict, total=False):
    """State passed between LangGraph nodes.

    total=False so nodes only need to return the keys they change.
    """

    # --- input ---
    ticket_id: str
    ticket_text: str

    # --- classify_ticket output ---
    category: Literal["simple", "ambiguous"]
    reasoning: str

    # --- resolve_via_tools output (Step 1: stubbed; Step 2: real MCP tools) ---
    gathered_info: list[dict[str, Any]]
    resolution: dict[str, Any]

    # --- human_approval output ---
    human_decision: Literal["approve", "reject"]

    # --- apply_decision output ---
    final_action: dict[str, Any]
    status: str
