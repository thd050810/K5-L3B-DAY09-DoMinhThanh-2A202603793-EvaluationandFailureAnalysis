"""Check refund durability and the per-order cap across the three student shapes."""

import json
import time
from contextlib import closing

import pytest

from lab8.db import connect
from lab8.metrics import trial_pass
from lab8.policy import order_refunded_vnd
from lab8.shapes import SHAPES
from tests.conftest import BY_ID


@pytest.mark.parametrize("shape", ["workflow", "single", "orchestrator"])
@pytest.mark.parametrize(
    ("claim_id", "order_total", "denial_reasons"),
    [
        ("C-013", 35_000, ["order_already_refunded"]),
        ("C-014", 150_000, []),
    ],
    ids=["T13-fully-refunded", "T14-partial-refund"],
)
def test_per_order_refund_cap(public_db, monkeypatch, shape, claim_id, order_total, denial_reasons):
    monkeypatch.chdir(public_db.parent)
    claim = BY_ID[claim_id]
    started_at = time.time()
    result = SHAPES[shape](claim_id, seed=11, store_path=str(public_db))

    with closing(connect(public_db)) as conn:
        passed, reason = trial_pass(result.as_dict(), claim["expected"], conn, started_at=started_at)
        assert passed, reason
        assert order_refunded_vnd(conn, claim["order_id"]) == order_total
        denials = conn.execute(
            "SELECT details_json FROM audit_events WHERE claim_id = ? AND event_type = 'policy_denied'",
            (claim_id,),
        ).fetchall()
        assert [json.loads(row["details_json"])["reason"] for row in denials] == denial_reasons


@pytest.mark.parametrize("shape", ["workflow", "single", "orchestrator"])
def test_three_calls_keep_one_refund(public_db, monkeypatch, shape):
    monkeypatch.chdir(public_db.parent)
    claim_id = "C-011"

    for _ in range(3):
        started_at = time.time()
        result = SHAPES[shape](claim_id, seed=11, store_path=str(public_db))
        with closing(connect(public_db)) as conn:
            passed, reason = trial_pass(
                result.as_dict(), BY_ID[claim_id]["expected"], conn, started_at=started_at
            )
            assert passed, reason
            refunds = conn.execute(
                "SELECT idempotency_key FROM refund_ledger WHERE claim_id = ?", (claim_id,)
            ).fetchall()
            assert [row["idempotency_key"] for row in refunds] == [f"refund:{claim_id}"]
