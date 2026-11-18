from __future__ import annotations

from typing import Any

from lab8.db import connect
from lab8.durability import issue_refund
from lab8.mock_llm import complete
from lab8.runtime import run_react
from lab8.schemas import Budget, RunResult, make_run_id
from lab8.shapes.common import finish
from lab8.trace import Trace


def run_claim(
    claim_id: str,
    *,
    seed: int,
    store_path: str,
    crash_at: str | None = None,
) -> RunResult:
    conn = connect(store_path)
    budget = Budget()
    trace = Trace(make_run_id("single", claim_id, seed))

    def decide(observation: dict[str, Any]) -> dict[str, Any]:
        last_tool = observation.get("last_tool")
        result = observation.get("last_result") or {}
        complete(budget, seed=seed, purpose="decide", prompt=f"last_tool={last_tool}")
        if last_tool:
            payload = result
            if last_tool == "get_claim_view":
                payload = {key: result[key] for key in ("found", "claim_id", "order_id") if key in result}
            trace.add("observation", {"tool": last_tool, "result": payload})

        final = {"status": "failed", "proposal_amount": 0, "error_reason": None}
        if last_tool is None:
            action = {"tool": "get_claim_view", "args": {"claim_id": claim_id}}
        elif last_tool == "get_claim_view":
            if not result.get("found"):
                final["error_reason"] = "unknown_claim"
                action = {"final": final}
            elif not result.get("order_id"):
                final.update(status="needs_info", error_reason="missing_order_id")
                action = {"final": final}
            else:
                action = {
                    "tool": "lookup_order",
                    "args": {"order_id": result["order_id"], "principal_id": result["principal_id"]},
                }
        elif last_tool == "lookup_order":
            if not result.get("visible"):
                final.update(status="escalated", error_reason=result.get("reason"))
                action = {"final": final}
            else:
                action = {"tool": "compute_compensation", "args": {"order": result["order"]}}
        elif last_tool == "compute_compensation":
            final.update(
                status="denied",
                proposal_amount=int(result["amount_vnd"]),
                error_reason=result.get("reason"),
            )
            action = {"final": final}
        else:
            final["error_reason"] = "unexpected_observation"
            action = {"final": final}
        trace.add("action", action)
        return action

    try:
        reacted = run_react(conn, budget, observation={}, decide=decide, max_steps=8, worker=True)
        final = reacted["final"]
        status = final["status"]
        proposal = int(final.get("proposal_amount", 0))
        error_reason = final.get("error_reason")
        if reacted["stopped"] == "final" and proposal > 0:
            outcome = issue_refund(conn, claim_id, proposal, crash_at=crash_at)
            trace.add("refund", outcome)
            if outcome["ok"]:
                status = "resolved"
                error_reason = None
            else:
                status = "failed" if outcome["conflict"] else "denied"
                error_reason = outcome["reason"]
        trace.add("decision", {"status": status, "proposal_amount": proposal, "reason": error_reason})
        return finish(
            conn,
            shape="single",
            claim_id=claim_id,
            seed=seed,
            status=status,
            proposal_amount=proposal,
            budget=budget,
            trace=trace,
            error_reason=error_reason,
        )
    finally:
        conn.close()
