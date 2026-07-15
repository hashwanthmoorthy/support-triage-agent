"""Isolation test for the RAG retriever (no LLM, no MCP server, no graph).

Ensures the index exists, then runs several queries and prints the actual
retrieved chunks + source docs so retrieval quality can be eyeballed. Also
asserts that the expected source doc ranks #1 for each query.

Run (from backend/):
    ./.venv/Scripts/python.exe scripts/test_retriever.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from knowledge_base.index import build_index  # noqa: E402
from knowledge_base.retriever import search  # noqa: E402

# (query, expected top-ranked source doc)
CASES = [
    ("how do I turn on two-factor authentication", "account_security.txt"),
    ("I got an email about a login from a new device I don't recognize", "account_security.txt"),
    ("the app keeps crashing every time I open it", "technical_troubleshooting.txt"),
    ("if I upgrade my plan will I be charged right away", "upgrade_downgrade.txt"),
    ("my international order is stuck in customs and hasn't arrived", "shipping_delivery.txt"),
    ("I was billed twice this month, can I get the extra charge back", "refund_policy.txt"),
    ("how do I download a copy of all my data", "data_privacy.txt"),
    ("does cancelling my subscription also delete my account", "cancel_subscription.txt"),
    ("my 2FA code keeps getting rejected when I sign in", "login_troubleshooting.txt"),
]


def main() -> int:
    build_index()  # idempotent: indexes if empty

    failures = []
    for query, expected in CASES:
        hits = search(query, k=3)
        print(f"\n=== QUERY: {query!r} ===")
        if not hits:
            print("  (no results)")
            failures.append((query, expected, None))
            continue
        for rank, h in enumerate(hits, 1):
            preview = h["text"].replace("\n", " ")
            if len(preview) > 160:
                preview = preview[:160] + "..."
            print(f"  #{rank} [{h['source']}] dist={h['distance']}")
            print(f"       {preview}")
        top = hits[0]["source"]
        status = "OK" if top == expected else "MISMATCH"
        print(f"  -> top={top} expected={expected} [{status}]")
        if top != expected:
            failures.append((query, expected, top))

    print("\n" + ("RETRIEVER TEST: OK" if not failures else f"RETRIEVER TEST: {len(failures)} MISMATCH(ES)"))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
