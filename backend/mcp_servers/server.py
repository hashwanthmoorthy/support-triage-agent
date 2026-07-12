"""MCP tool server for the support triage agent (mock data).

Exposes three tools over the Model Context Protocol using FastMCP:
    - ticket_lookup(ticket_id)          -> fake ticket record
    - knowledge_base_search(query)      -> 1-2 fake KB snippets
    - send_email(to, subject, body)     -> stub; logs and returns success

Transport is streamable-HTTP so the backend can reach it over the network
(localhost in dev, the compose service name in Docker). Host/port are
env-configurable.

Run locally (from backend/):
    ./.venv/Scripts/python.exe -m mcp_servers.server
"""
from __future__ import annotations

import logging
import os

from mcp.server.fastmcp import FastMCP

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("triage.mcp")

HOST = os.getenv("MCP_HOST", "127.0.0.1")
PORT = int(os.getenv("MCP_PORT", "8100"))

mcp = FastMCP("triage-tools", host=HOST, port=PORT)

# --- mock datastore ---------------------------------------------------------
_FAKE_TICKETS = {
    "T-1001": {"status": "open", "customer": "alice@example.com", "product": "WidgetPro", "priority": "low"},
    "T-2002": {"status": "open", "customer": "bob@example.com", "product": "WidgetPro", "priority": "high"},
}
_DEFAULT_TICKET = {"status": "open", "customer": "demo@example.com", "product": "WidgetPro", "priority": "normal"}

_KB = [
    {"title": "Reset your password", "body": "Go to Settings > Security > Reset password and follow the email link."},
    {"title": "Update billing info", "body": "Open Billing > Payment methods to add or change a card."},
    {"title": "Cancel a subscription", "body": "Subscriptions are cancelled from Billing > Plan > Cancel."},
]


@mcp.tool()
def ticket_lookup(ticket_id: str) -> dict:
    """Look up a support ticket by its ID. Returns a ticket record."""
    record = _FAKE_TICKETS.get(ticket_id, dict(_DEFAULT_TICKET))
    logger.info("ticket_lookup(%s) -> status=%s", ticket_id, record["status"])
    return {"ticket_id": ticket_id, **record}


@mcp.tool()
def knowledge_base_search(query: str) -> dict:
    """Search the knowledge base. Returns up to 2 matching snippets."""
    q = (query or "").lower()
    scored = [kb for kb in _KB if any(w in (kb["title"] + kb["body"]).lower() for w in q.split())]
    snippets = (scored or _KB)[:2]
    logger.info("knowledge_base_search(%r) -> %d snippet(s)", query, len(snippets))
    return {"query": query, "snippets": snippets}


@mcp.tool()
def send_email(to: str, subject: str, body: str) -> dict:
    """Send an email (STUB: logs the message and returns success)."""
    logger.info("send_email -> to=%s subject=%r", to, subject)
    return {"ok": True, "to": to, "subject": subject, "chars": len(body)}


if __name__ == "__main__":
    logger.info("Starting MCP triage-tools server on http://%s:%s/mcp", HOST, PORT)
    mcp.run(transport="streamable-http")
