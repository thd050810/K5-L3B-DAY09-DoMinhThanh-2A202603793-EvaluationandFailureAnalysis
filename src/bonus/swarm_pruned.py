"""B4 — "swarm pruned" baseline: the reference swarm with peer/parse model calls dropped at random.

Same steps as `lab8/shapes/swarm_reference.py` (which is not modified). Before each of the two
auxiliary model calls (`peer`, `parse`) a coin seeded by (seed, claim_id, purpose) decides
whether the call is kept. A dropped call costs nothing and returns nothing; a dropped `parse`
means the swarm has no ticket delay to trust. The `draft` call and all tool calls are kept.

Source claim (EMNLP 2026, slide 44/59): random pruning of agent interaction can keep
performance, so an "efficiency gain" must be compared against such a baseline.
"""

from __future__ import annotations

import random

from lab8.db import connect
from lab8.durability import InjectedCrash, issue_refund
from lab8.handoff import make_handoff
from lab8.mock_llm import complete, parse_delay_days
from lab8.runtime import run_readonly_investigators
from lab8.schemas import Budget, RunResult, make_run_id
from lab8.shapes.common import finish, safe_dump
from lab8.tools import compute_compensation, tool_cost
from lab8.trace import Trace

SHAPE = "swarm_pruned"
KEEP_PROBABILITY = 0.5
PRUNABLE = ("peer", "parse")


def keep_call(seed: int, claim_id: str, purpose: str, p: float = KEEP_PROBABILITY) -> bool:
    """Deterministic coin: same (seed, claim, purpose) -> same decision on every machine."""
    return random.Random(f"{seed}|{claim_id}|{purpose}").random() < p


def run_claim(claim_id: str, *, seed: int, store_path: str, crash_at: str | None = None) -> RunResult:
    conn = connect(store_path)
    try:
        budget = Budget()
        trace = Trace(make_run_id(SHAPE, claim_id, seed))

        def done(status: str, proposal: int, reason: str | None) -> RunResult:
            return finish(conn, shape=SHAPE, claim_id=claim_id, seed=seed, status=status,
                          proposal_amount=proposal, budget=budget, trace=trace, error_reason=reason)

        budget.add_tool(tool_cost())
        row = conn.execute(
            "SELECT claim_id, principal_id, order_id, ticket FROM claims WHERE claim_id = ?", (claim_id,)
        ).fetchone()
        if row is None:
            trace.add("error", {"reason": "unknown_claim"})
            return done("failed", 0, "unknown_claim")

        ticket = row["ticket"]
        # The coin is reproducible from keep_call(); no extra trace event, so steps stay comparable.
        kept = {purpose: keep_call(seed, claim_id, purpose) for purpose in PRUNABLE}
        if kept["peer"]:
            complete(budget, seed=seed, purpose="peer", prompt=ticket)
        parsed_delay = None
        if kept["parse"]:
            parsed_delay = parse_delay_days(ticket)
            complete(budget, seed=seed, purpose="parse", prompt=ticket)

        if not row["order_id"]:
            complete(budget, seed=seed, purpose="draft", prompt="needs_info")
            trace.add("decision", {"status": "needs_info"})
            return done("needs_info", 0, "missing_order_id")

        handoff = make_handoff(
            request_id=f"REQ-{claim_id}",
            claim_id=claim_id,
            task="check_applicable_policy",
            facts={},
            allowed_tools=["lookup_order", "lookup_policy", "compute_compensation"],
        )
        trace.add("handoff", safe_dump(handoff))
        investigated = run_readonly_investigators(conn, budget, handoff, principal_id=row["principal_id"])
        order_view = investigated["tools"].get("lookup_order", {})
        trace.add("investigator", {"lookup_order": order_view})
        if not order_view.get("visible"):
            complete(budget, seed=seed, purpose="draft", prompt="escalated")
            return done("escalated", 0, order_view.get("reason"))

        order = dict(order_view["order"])
        # Same weakness as the reference swarm: on seed % 5 == 0 trust the ticket delay.
        if parsed_delay is not None and parsed_delay != int(order["delay_days"]) and seed % 5 == 0:
            order["delay_days"] = parsed_delay
            trace.add("model_override", {"delay_days": parsed_delay})

        quote = investigated["tools"]["compute_compensation"]
        if order["delay_days"] != order_view["order"]["delay_days"]:
            budget.add_tool(tool_cost())
            quote = compute_compensation(conn, order)
        proposal = int(quote["amount_vnd"])
        trace.add("quote", quote)
        complete(budget, seed=seed, purpose="draft", prompt=f"proposal={proposal}")

        if proposal <= 0:
            return done("denied", 0, quote.get("reason"))
        try:
            outcome = issue_refund(conn, claim_id, proposal, crash_at=crash_at)
        except InjectedCrash:
            trace.add("crash", {"at": crash_at})
            trace.write()
            raise
        if not outcome["ok"]:
            return done("failed" if outcome["conflict"] else "denied", proposal, outcome["reason"])
        return done("resolved", proposal, None)
    finally:
        conn.close()
