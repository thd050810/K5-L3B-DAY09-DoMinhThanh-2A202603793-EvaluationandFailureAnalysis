"""Duc Hieu: benchmark isolation, seed order and reproducibility.

Use the reference swarm so these checks run before student shapes are ready.
Keep traces in pytest's temporary directory, separate from baseline evidence.
"""

from pathlib import Path

import pytest

from lab8.benchmark import run_benchmark
from lab8.db import connect
from lab8.shapes import SHAPES
from lab8.shapes.swarm_reference import run_claim as swarm
from tests.conftest import CLAIMS, WORLD


SEEDS = [11, 22, 33, 44, 55]


@pytest.fixture
def evaluation_cases(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # Include a normal refund, the seed-sensitive miss and a seeded prior refund.
    return [row for row in CLAIMS if row["claim_id"] in {"C-001", "C-002", "C-014"}]


def test_every_trial_starts_with_only_seeded_refunds(evaluation_cases, monkeypatch):
    stores = []
    prior_rows = sorted(
        (row["claim_id"], row["order_id"], int(row["amount_vnd"]))
        for row in WORLD.get("prior_refunds", [])
    )

    def observed_swarm(claim_id, *, seed, store_path, crash_at=None):
        stores.append(Path(store_path))
        conn = connect(store_path)
        try:
            before = sorted(
                tuple(row)
                for row in conn.execute(
                    "SELECT claim_id, order_id, amount_vnd FROM refund_ledger"
                )
            )
        finally:
            conn.close()
        assert before == prior_rows, "another trial's refund contaminated this DB"
        result = swarm(claim_id, seed=seed, store_path=store_path, crash_at=crash_at)
        assert len(result.refund_effects) == 1
        assert result.committed_audit_count == 1
        return result

    monkeypatch.setitem(SHAPES, "swarm", observed_swarm)
    claims = [row for row in evaluation_cases if row["claim_id"] != "C-002"]
    report = run_benchmark(world=WORLD, claims=claims, shapes=["swarm"], seeds=[11, 55])

    assert len(stores) == len(claims) * 2
    assert len(set(stores)) == len(stores), "each trial must use a distinct SQLite path"
    assert all(row["passed"] for row in report["trials"]), report["trials"]


def test_reordering_seeds_preserves_trial_results_and_metrics(evaluation_cases):
    forward = run_benchmark(world=WORLD, claims=evaluation_cases, shapes=["swarm"], seeds=SEEDS)
    reverse = run_benchmark(
        world=WORLD, claims=evaluation_cases, shapes=["swarm"], seeds=list(reversed(SEEDS))
    )

    def keyed_trials(report):
        return {
            (row["shape"], row["claim_id"], row["seed"]): row
            for row in report["trials"]
        }

    assert keyed_trials(forward) == keyed_trials(reverse)
    # Adding floating-point costs in a different order may change the last bit.
    for field, value in forward["by_shape"]["swarm"].items():
        actual = reverse["by_shape"]["swarm"][field]
        if isinstance(value, (int, float)):
            assert actual == pytest.approx(value), field
        else:
            assert actual == value, field


def test_repeated_benchmark_reproduces_results_and_simulated_cost(evaluation_cases):
    first = run_benchmark(world=WORLD, claims=evaluation_cases, shapes=["swarm"], seeds=SEEDS)
    second = run_benchmark(world=WORLD, claims=evaluation_cases, shapes=["swarm"], seeds=SEEDS)

    assert first == second
    assert len(first["trials"]) == len(evaluation_cases) * len(SEEDS)
    assert first["by_shape"]["swarm"]["total_simulated_cost_vnd"] > 0
    # Reproducible does not mean correct: retain the reference's known failure.
    failures = [row for row in first["trials"] if not row["passed"]]
    assert [(row["claim_id"], row["seed"]) for row in failures] == [("C-002", 55)]
