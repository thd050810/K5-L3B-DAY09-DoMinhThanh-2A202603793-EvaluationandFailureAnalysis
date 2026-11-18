"""Shape C — orchestrator plus read-only investigators. Student work.

1. Build a handoff with `lab8.handoff.make_handoff`. Allowed tools are read-only.
   Never put parent_secret, raw headers, or the full claim row into facts.
2. `lab8.runtime.run_readonly_investigators` runs those tools.
3. The orchestrator quotes from the investigator's order view and calls
   `durability.issue_refund`. Investigators have no write registry.
   Pass the full quote; the host subtracts earlier refunds on the same order.
   `lookup_refund_history` is a read-only tool you may hand to an investigator.
4. Trace the sanitized handoff, not the parent context.

An LLM summary of the parent context is not a sanitizer. Use the allowlist.

Trace contract v1 (docs/contracts.md): return a trace_path to a JSON file written in this run,
{"run_id": <same run_id>, "events": [...]}, on every return path including early
ones. `lab8.trace.Trace` does this; your own tracer is fine if it matches.
"""

from __future__ import annotations

import sqlite3

from lab8.db import connect
from lab8.durability import InjectedCrash, issue_refund
from lab8.handoff import make_handoff
from lab8.mock_llm import complete
from lab8.runtime import run_readonly_investigators
from lab8.schemas import Budget, RunResult, make_run_id
from lab8.shapes.common import finish, safe_dump
from lab8.tools import compute_compensation, get_claim_view, tool_cost
from lab8.trace import Trace

SHAPE = "orchestrator"

# Investigators only get read tools. Quoting stays with the orchestrator (code),
# so the money decision never crosses the handoff boundary.
INVESTIGATOR_TOOLS = ["lookup_order", "lookup_refund_history"]


def run_claim(
    claim_id: str,
    *,
    seed: int,
    store_path: str,
    crash_at: str | None = None,
) -> RunResult:
    conn = connect(store_path)
    try:
        return _run(conn, claim_id, seed=seed, crash_at=crash_at)
    finally:
        conn.close()


def _run(conn: sqlite3.Connection, claim_id: str, *, seed: int, crash_at: str | None) -> RunResult:
    budget = Budget()
    trace = Trace(make_run_id(SHAPE, claim_id, seed))

    def done(status: str, proposal: int, reason: str | None) -> RunResult:
        trace.add("decision", {"status": status, "proposal_amount": int(proposal), "reason": reason})
        return finish(
            conn,
            shape=SHAPE,
            claim_id=claim_id,
            seed=seed,
            status=status,
            proposal_amount=proposal,
            budget=budget,
            trace=trace,
            error_reason=reason,
        )

    # Orchestrator reads the claim through the allowlisted view (no parent_secret).
    budget.add_tool(tool_cost())
    claim = get_claim_view(conn, claim_id)
    if not claim.get("found"):
        return done("failed", 0, "unknown_claim")

    # One planning call. Ticket text is user data: it is never parsed for numbers
    # and never copied into the handoff or the trace.
    complete(budget, seed=seed, purpose="plan", prompt=claim["ticket"] or "")
    trace.add("plan", {"claim_id": claim_id, "has_order_id": bool(claim.get("order_id"))})

    # Missing order_id -> needs_info. Do not guess an order id from the ticket.
    if not claim.get("order_id"):
        complete(budget, seed=seed, purpose="draft", prompt="needs_info")
        return done("needs_info", 0, "missing_order_id")

    # Handoff: allowlist only. facts stays empty: the orchestrator has no verified
    # facts yet, and ticket claims ("trễ 9 ngày") are not facts.
    handoff = make_handoff(
        request_id=f"REQ-{claim_id}",
        claim_id=claim_id,
        task="verify_order_and_refund_history",
        facts={},
        allowed_tools=list(INVESTIGATOR_TOOLS),
    )
    trace.add("handoff", safe_dump(handoff))

    investigated = run_readonly_investigators(conn, budget, handoff, principal_id=claim["principal_id"])
    tools = investigated["tools"]
    order_view = tools.get("lookup_order") or {}
    history = tools.get("lookup_refund_history") or {}
    trace.add(
        "investigator",
        {
            "visible": bool(order_view.get("visible")),
            "reason": order_view.get("reason"),
            # lookup_order already returns an allowlisted order (no phone/address/note/item).
            "order": order_view.get("order"),
            "refunded_vnd": history.get("refunded_vnd"),
            "refund_count": history.get("refund_count"),
        },
    )

    # Not found or not owned by this principal -> escalated. Copy nothing else.
    if not order_view.get("visible"):
        complete(budget, seed=seed, purpose="draft", prompt="escalated")
        return done("escalated", 0, order_view.get("reason"))

    # Money is decided by code from the structured order row, never by the model.
    budget.add_tool(tool_cost())
    quote = compute_compensation(conn, dict(order_view["order"]))
    proposal = int(quote["amount_vnd"])
    trace.add("quote", safe_dump(quote))
    complete(budget, seed=seed, purpose="draft", prompt=f"proposal={proposal}")

    # Quote 0 -> denied without calling the host (no policy_denied audit expected).
    if proposal <= 0:
        return done("denied", 0, quote.get("reason"))

    # Pass the FULL quote. The host checks approval and subtracts earlier refunds
    # on the same order (T13, T14). InjectedCrash is not swallowed: flush the trace
    # and re-raise so the crash suite sees a real crash and can resume.
    try:
        outcome = issue_refund(conn, claim_id, proposal, crash_at=crash_at)
    except InjectedCrash:
        trace.add("crash", {"at": crash_at})
        trace.write()
        raise

    if not outcome["ok"]:
        status = "failed" if outcome.get("conflict") else "denied"
        return done(status, proposal, outcome.get("reason"))
    return done("resolved", proposal, None)
