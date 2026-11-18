"""C3 and C4 checks through the chosen Workflow entry point."""

import json
import time
from contextlib import closing

import pytest

from lab8.db import connect
from lab8.durability import InjectedCrash
from lab8.metrics import trial_pass
from lab8.policy import order_refunded_vnd
from lab8.shapes.workflow import run_claim
from tests.conftest import BY_ID


@pytest.mark.parametrize(
    ("crash_at", "total_at_crash", "checkpoint_written"),
    [
        ("before_effect", 30_000, False),
        ("after_effect_before_checkpoint", 150_000, False),
        ("after_checkpoint", 150_000, True),
    ],
)
def test_workflow_resumes_partial_refund(
    public_db, monkeypatch, crash_at, total_at_crash, checkpoint_written
):
    monkeypatch.chdir(public_db.parent)
    claim_id = "C-014"
    order_id = BY_ID[claim_id]["order_id"]
    expected = BY_ID[claim_id]["expected"]
    checkpoint = "SELECT 1 FROM checkpoints WHERE claim_id = ? AND step = 'issue_refund'"

    with pytest.raises(InjectedCrash, match=crash_at):
        run_claim(claim_id, seed=11, store_path=str(public_db), crash_at=crash_at)

    with closing(connect(public_db)) as conn:
        assert order_refunded_vnd(conn, order_id) == total_at_crash
        assert (conn.execute(checkpoint, (claim_id,)).fetchone() is not None) == checkpoint_written

    for seed in (11, 22):
        started_at = time.time()
        result = run_claim(claim_id, seed=seed, store_path=str(public_db))
        with closing(connect(public_db)) as conn:
            passed, reason = trial_pass(result.as_dict(), expected, conn, started_at=started_at)
            assert passed, reason
            assert order_refunded_vnd(conn, order_id) == 150_000
            assert conn.execute(checkpoint, (claim_id,)).fetchone() is not None


@pytest.mark.parametrize(
    ("approval_id", "status", "expires_at", "denial_reason"),
    [
        (None, "valid", "2027-12-31", "missing_approval"),
        ("A-001", "valid", "2020-01-01", "approval_expired"),
        ("A-001", "revoked", "2027-12-31", "approval_revoked"),
        ("A-002", "valid", "2027-12-31", "approval_claim_mismatch"),
    ],
    ids=["missing", "expired", "revoked", "wrong-claim"],
)
def test_workflow_rejects_invalid_approval_on_retry(
    public_db, monkeypatch, approval_id, status, expires_at, denial_reason
):
    monkeypatch.chdir(public_db.parent)
    claim_id = "C-001"
    expected = {
        "status": "denied",
        "proposal_amount": 35_000,
        "refund_vnd": 0,
        "refund_count": 0,
        "audit_refund_committed": 0,
        "policy_denied": True,
        "forbid_substrings": BY_ID[claim_id]["expected"]["forbid_substrings"],
    }
    with closing(connect(public_db)) as conn:
        conn.execute("UPDATE claims SET approval_id = ? WHERE claim_id = ?", (approval_id, claim_id))
        conn.execute(
            "UPDATE approvals SET status = ?, expires_at = ? WHERE approval_id = 'A-001'",
            (status, expires_at),
        )
        conn.commit()

    for seed in (11, 22):
        started_at = time.time()
        result = run_claim(claim_id, seed=seed, store_path=str(public_db))
        assert result.error_reason == denial_reason
        with closing(connect(public_db)) as conn:
            passed, reason = trial_pass(result.as_dict(), expected, conn, started_at=started_at)
            assert passed, reason
            rows = conn.execute(
                "SELECT details_json FROM audit_events WHERE claim_id = ? AND event_type = 'policy_denied'",
                (claim_id,),
            ).fetchall()
            assert [json.loads(row["details_json"])["reason"] for row in rows] == [denial_reason]
