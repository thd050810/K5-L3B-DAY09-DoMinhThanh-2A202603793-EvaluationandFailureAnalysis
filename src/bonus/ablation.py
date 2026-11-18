"""B4 — workflow with switchable components, for the rules-only baseline and the ablation.

`_workflow` follows `lab8/shapes/workflow.py` step by step. Each ablation removes exactly one
component and changes nothing else, so a metric change can be attributed to that component.
The shape file itself is not modified; variants are registered with `--extra-shape`.

Components that can be removed:

- needs_info_guard:  missing order_id -> needs_info (without it the claim goes on to lookup_order)
- visibility_guard:  order not found / not owned -> escalated (without it the shape quotes an empty order)
- zero_quote_guard:  quote 0 -> denied without calling the host (without it the host is called with 0)

The workflow makes no model call and has no investigator, so "draft model call" and
"investigator" are not components of this shape; their cost is the gap to single/orchestrator.
"""

from __future__ import annotations

from lab8.db import connect
from lab8.durability import InjectedCrash, issue_refund
from lab8.schemas import Budget, RunResult, make_run_id
from lab8.shapes.common import finish
from lab8.tools import compute_compensation, get_claim_view, lookup_order, tool_cost
from lab8.trace import Trace

COMPONENTS = ("needs_info_guard", "visibility_guard", "zero_quote_guard")


def _workflow(
    claim_id: str,
    *,
    seed: int,
    store_path: str,
    crash_at: str | None,
    shape: str,
    skip: frozenset[str] = frozenset(),
) -> RunResult:
    unknown = set(skip) - set(COMPONENTS)
    if unknown:
        raise ValueError(f"unknown components: {sorted(unknown)}")
    conn = connect(store_path)
    try:
        budget = Budget()
        # No extra "ablation" event: steps = trace events, so an extra event would bias the metric.
        trace = Trace(make_run_id(shape, claim_id, seed))

        def done(status: str, proposal: int, reason: str | None) -> RunResult:
            trace.add("decision", {"status": status, "proposal_amount": int(proposal)})
            return finish(
                conn,
                shape=shape,
                claim_id=claim_id,
                seed=seed,
                status=status,
                proposal_amount=proposal,
                budget=budget,
                trace=trace,
                error_reason=reason,
            )

        budget.add_tool(tool_cost())
        claim = get_claim_view(conn, claim_id)
        if not claim.get("found"):
            return done("failed", 0, "unknown_claim")

        if "needs_info_guard" not in skip and not claim.get("order_id"):
            return done("needs_info", 0, "missing_order_id")

        budget.add_tool(tool_cost())
        order_view = lookup_order(conn, claim.get("order_id"), principal_id=claim["principal_id"])
        trace.add("lookup_order", {"visible": order_view.get("visible"), "reason": order_view.get("reason")})
        if "visibility_guard" not in skip and not order_view.get("visible"):
            return done("escalated", 0, order_view.get("reason"))

        budget.add_tool(tool_cost())
        quote = compute_compensation(conn, dict(order_view.get("order") or {}))
        proposal = int(quote["amount_vnd"])
        trace.add("quote", {"amount_vnd": proposal, "reason": quote.get("reason"), "clause_ids": quote.get("clause_ids")})

        if "zero_quote_guard" not in skip and proposal <= 0:
            return done("denied", 0, quote.get("reason"))

        try:
            outcome = issue_refund(conn, claim_id, proposal, crash_at=crash_at)
        except InjectedCrash:
            trace.add("crash", {"at": crash_at})
            trace.write()
            raise
        if not outcome["ok"]:
            return done("failed" if outcome.get("conflict") else "denied", proposal, outcome.get("reason"))
        return done("resolved", proposal, None)
    finally:
        conn.close()


def rules_only(claim_id: str, *, seed: int, store_path: str, crash_at: str | None = None) -> RunResult:
    """Baseline: pure rules, zero model calls, every guard on."""
    return _workflow(claim_id, seed=seed, store_path=store_path, crash_at=crash_at, shape="rules_only")


def no_needs_info_guard(claim_id: str, *, seed: int, store_path: str, crash_at: str | None = None) -> RunResult:
    return _workflow(
        claim_id, seed=seed, store_path=store_path, crash_at=crash_at,
        shape="wf_no_needs_info", skip=frozenset({"needs_info_guard"}),
    )


def no_visibility_guard(claim_id: str, *, seed: int, store_path: str, crash_at: str | None = None) -> RunResult:
    return _workflow(
        claim_id, seed=seed, store_path=store_path, crash_at=crash_at,
        shape="wf_no_visibility", skip=frozenset({"visibility_guard"}),
    )


def no_zero_quote_guard(claim_id: str, *, seed: int, store_path: str, crash_at: str | None = None) -> RunResult:
    return _workflow(
        claim_id, seed=seed, store_path=store_path, crash_at=crash_at,
        shape="wf_no_zero_guard", skip=frozenset({"zero_quote_guard"}),
    )
