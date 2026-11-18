"""Tests for Shape A (workflow) implementation."""

import time

from lab8.db import connect
from lab8.metrics import trial_pass
from lab8.shapes.workflow import run_claim
from tests.conftest import BY_ID
from tests.test_public_matrix import _store


def test_workflow_handles_standard_claim(tmp_path):
    store = _store(tmp_path, "workflow-standard.sqlite")
    started_at = time.time()
    result = run_claim("C-001", seed=42, store_path=str(store))
    conn = connect(store)
    try:
        passed, reason = trial_pass(
            result.as_dict(),
            BY_ID["C-001"]["expected"],
            conn,
            started_at=started_at,
        )
    finally:
        conn.close()
    assert passed, reason
    assert result.status == "resolved"
    assert result.proposal_amount == 35000


def test_workflow_missing_order_needs_info(tmp_path):
    store = _store(tmp_path, "workflow-missing-order.sqlite")
    started_at = time.time()
    result = run_claim("C-004", seed=42, store_path=str(store))
    conn = connect(store)
    try:
        passed, reason = trial_pass(
            result.as_dict(),
            BY_ID["C-004"]["expected"],
            conn,
            started_at=started_at,
        )
    finally:
        conn.close()
    assert passed, reason
    assert result.status == "needs_info"
    assert result.proposal_amount == 0


def test_workflow_outside_principal_scope_escalates(tmp_path):
    store = _store(tmp_path, "workflow-escalate.sqlite")
    started_at = time.time()
    result = run_claim("C-005", seed=42, store_path=str(store))
    conn = connect(store)
    try:
        passed, reason = trial_pass(
            result.as_dict(),
            BY_ID["C-005"]["expected"],
            conn,
            started_at=started_at,
        )
    finally:
        conn.close()
    assert passed, reason
    assert result.status == "escalated"
    assert result.proposal_amount == 0


def test_workflow_unknown_claim_fails(tmp_path):
    store = _store(tmp_path, "workflow-unknown.sqlite")
    result = run_claim("NON_EXISTENT_CLAIM", seed=42, store_path=str(store))
    assert result.status == "failed"
    assert result.error_reason == "unknown_claim"
    assert result.proposal_amount == 0
