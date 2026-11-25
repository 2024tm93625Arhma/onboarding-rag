"""MCP server exposing the onboarding RAG service as assistant tools.

Run by an MCP client (VS Code, Claude Code) over stdio. The FastAPI service
must already be running on API_BASE.

    python mcp_server.py
"""
import os

import httpx
from mcp.server.mcpserver import MCPServer

API_BASE = os.environ.get("ONBOARDING_API", "http://localhost:8000")
TIMEOUT = float(os.environ.get("ONBOARDING_TIMEOUT", "300"))

mcp = MCPServer("Onboarding RAG")


@mcp.tool()
def ask_policy_question(question: str, user_id: str) -> dict:
    """Answer an employee's HR or IT policy question.

    The answer depends on who is asking: different employees are governed by
    different versions of the same policy, so user_id is required and must not
    be guessed. Call list_employee_profiles first if it is not known.

    Returns the answer mode (answer, answer_conditionally or abstain), the
    answer text with inline citations, the cited chunk ids, and the ranked
    evidence with each document's authority for this employee.
    """
    r = httpx.post(
        f"{API_BASE}/ask",
        json={"question": question, "user_id": user_id},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    d = r.json()
    return {
        "mode": d["mode"],
        "answer": d["answer"],
        "citations": d["citations"],
        "flagged": d["flagged"],
        "evidence": [
            {
                "chunk_id": h["chunk_id"],
                "title": h["title"],
                "version": h["version"],
                "effective_date": h["effective_date"],
                "authority": h["authority"],
                "score": round(h["score"], 4),
            }
            for h in d["hits"]
        ],
        "latency_ms": d["latency_ms"],
    }


@mcp.tool()
def list_employee_profiles() -> list:
    """List the employees questions can be asked as.

    Each profile carries the department, grade, location, employment type and
    joining date that decide which policy versions govern that employee.
    """
    r = httpx.get(f"{API_BASE}/profiles", timeout=30)
    r.raise_for_status()
    return r.json()


if __name__ == "__main__":
    mcp.run(transport="stdio")
