import json
from pathlib import Path

import pytest

from lab8.config_loader import pricing
from lab8.db import connect
from lab8.durability import InjectedCrash, committed_audit_count, get_refund
from lab8.handoff import READONLY_TOOLS
from lab8.metrics import check_trace
from lab8.shapes import single


def test_unknown_claim_fails_with_valid_trace_and_no_refund(public_db):
    result = single.run_claim("UNKNOWN", seed=11, store_path=str(public_db))
    assert result.status == "failed"
    assert result.error_reason == "unknown_claim"
    assert result.proposal_amount == 0
    assert result.refund_effects == []
    assert result.committed_audit_count == 0
    assert check_trace(result.as_dict()) == (True, "ok")
    conn = connect(public_db)
    try:
        assert get_refund(conn, "UNKNOWN") is None
    finally:
        conn.close()


def test_budget_records_actual_model_usage_and_tool_cost(public_db, monkeypatch):
    complete = single.complete
    calls = []

    def record_complete(budget, **kwargs):
        response = complete(budget, **kwargs)
        calls.append((kwargs["prompt"], response))
        return response

    monkeypatch.setattr(single, "complete", record_complete)
    result = single.run_claim("C-001", seed=11, store_path=str(public_db))
    assert result.status == "resolved"
    assert calls
    assert result.model_calls == len(calls)
    assert result.input_tokens > 0
    assert result.output_tokens > 0
    trace = json.loads(Path(result.trace_path).read_text(encoding="utf-8"))
    tool_actions = [event for event in trace["events"] if event["kind"] == "action" and "tool" in event["payload"]]
    assert result.tool_calls == len(tool_actions) == 3
    prices = pricing()
    cost = (
        result.input_tokens * prices["input_per_1k_tokens_vnd"] / 1000
        + result.output_tokens * prices["output_per_1k_tokens_vnd"] / 1000
        + result.tool_calls * prices["tool_call_vnd"]
    )
    assert result.cost_estimate == pytest.approx(cost, abs=0.000001)


@pytest.mark.parametrize("crash_at", ["before_effect", "after_effect_before_checkpoint", "after_checkpoint"])
def test_crash_propagates_and_resume_keeps_one_refund(public_db, crash_at):
    with pytest.raises(InjectedCrash, match=crash_at):
        single.run_claim("C-001", seed=11, store_path=str(public_db), crash_at=crash_at)
    conn = connect(public_db)
    try:
        assert (get_refund(conn, "C-001") is None) == (crash_at == "before_effect")
    finally:
        conn.close()
    result = single.run_claim("C-001", seed=11, store_path=str(public_db))
    assert result.status == "resolved"
    assert len(result.refund_effects) == result.committed_audit_count == 1
    conn = connect(public_db)
    try:
        assert get_refund(conn, "C-001")["amount_vnd"] == 35000
        assert committed_audit_count(conn, "C-001") == 1
    finally:
        conn.close()


def test_changed_quote_conflicts_without_replacing_committed_refund(public_db):
    first = single.run_claim("C-001", seed=11, store_path=str(public_db))
    assert first.status == "resolved"
    conn = connect(public_db)
    try:
        conn.execute("UPDATE orders SET shipping_fee_vnd = 10000 WHERE order_id = 'O-107'")
        conn.commit()
    finally:
        conn.close()
    result = single.run_claim("C-001", seed=11, store_path=str(public_db))
    assert result.status == "failed"
    assert result.error_reason == "amount_conflict"
    assert result.proposal_amount == 10000
    assert result.refund_effects == first.refund_effects
    assert result.committed_audit_count == 1
    conn = connect(public_db)
    try:
        assert get_refund(conn, "C-001")["amount_vnd"] == 35000
        assert committed_audit_count(conn, "C-001") == 1
    finally:
        conn.close()


def test_react_uses_read_tools_and_commits_only_after_loop(public_db, monkeypatch):
    run_react = single.run_react
    selected_tools = []

    def inspect_react(conn, budget, **kwargs):
        assert kwargs["max_steps"] == 8
        assert kwargs["worker"] is True
        decide = kwargs["decide"]

        def inspect_decide(observation):
            assert get_refund(conn, "C-001") is None
            action = decide(observation)
            if "tool" in action:
                selected_tools.append(action["tool"])
                assert action["tool"] in READONLY_TOOLS
            assert get_refund(conn, "C-001") is None
            return action

        kwargs["decide"] = inspect_decide
        outcome = run_react(conn, budget, **kwargs)
        assert get_refund(conn, "C-001") is None
        return outcome

    monkeypatch.setattr(single, "run_react", inspect_react)
    result = single.run_claim("C-001", seed=11, store_path=str(public_db))
    assert selected_tools
    assert result.status == "resolved"
    assert len(result.refund_effects) == result.committed_audit_count == 1


def test_step_cap_fails_without_refund_and_writes_trace(public_db, monkeypatch):
    run_react = single.run_react

    def limited_react(conn, budget, **kwargs):
        kwargs["max_steps"] = 1
        return run_react(conn, budget, **kwargs)

    monkeypatch.setattr(single, "run_react", limited_react)
    result = single.run_claim("C-001", seed=11, store_path=str(public_db))
    assert result.status == "failed"
    assert result.error_reason == "step_cap"
    assert result.proposal_amount == 0
    assert result.refund_effects == []
    assert result.committed_audit_count == 0
    assert check_trace(result.as_dict()) == (True, "ok")
    conn = connect(public_db)
    try:
        assert get_refund(conn, "C-001") is None
    finally:
        conn.close()
