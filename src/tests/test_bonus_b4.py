"""B4 — fair baselines, ablation and statistics.

Run from `src/`:  python -m pytest -q tests/test_bonus_b4.py
"""

from __future__ import annotations

import pytest

from bonus import ablation, stats, swarm_pruned
from lab8.benchmark import run_benchmark
from lab8.db import connect
from lab8.shapes import SHAPES
from lab8.shapes.workflow import run_claim as workflow
from tests.conftest import BY_ID, CLAIMS, WORLD
from tests.test_public_matrix import _store

ALL_CLAIMS = [row["claim_id"] for row in CLAIMS]


def _run(fn, claim_id, tmp_path, name, seed=11):
    store = _store(tmp_path, f"{name}-{claim_id}-{seed}.sqlite")
    result = fn(claim_id, seed=seed, store_path=str(store))
    conn = connect(store)
    try:
        audits = sorted(
            r["event_type"] for r in conn.execute("SELECT event_type FROM audit_events WHERE claim_id = ?", (claim_id,))
        )
    finally:
        conn.close()
    return result, audits


def _decision(result):
    return result.status, result.proposal_amount, [e["amount_vnd"] for e in result.refund_effects], result.error_reason


# --- Fair comparison: the ablation code path is the workflow code path ----------------------


@pytest.mark.parametrize("claim_id", ALL_CLAIMS)
def test_rules_only_baseline_matches_workflow(tmp_path, claim_id):
    ours, ours_audits = _run(ablation.rules_only, claim_id, tmp_path, "rules")
    ref, ref_audits = _run(workflow, claim_id, tmp_path, "wf")
    assert _decision(ours) == _decision(ref)
    assert ours_audits == ref_audits
    assert ours.model_calls == 0
    assert ours.tool_calls == ref.tool_calls


@pytest.mark.parametrize(
    ("fn", "broken", "wrong_status"),
    [
        (ablation.no_needs_info_guard, "C-004", "escalated"),
        (ablation.no_visibility_guard, "C-005", "denied"),
    ],
)
def test_each_ablation_changes_only_its_own_case(tmp_path, fn, broken, wrong_status):
    for claim_id in ALL_CLAIMS:
        ours, _ = _run(fn, claim_id, tmp_path, "abl")
        ref, _ = _run(workflow, claim_id, tmp_path, "wf")
        if claim_id == broken:
            assert ours.status == wrong_status != BY_ID[claim_id]["expected"]["status"]
            assert ours.refund_effects == []  # a removed guard must not create money
        else:
            assert _decision(ours) == _decision(ref), claim_id


def test_zero_guard_removal_keeps_metrics_but_adds_spurious_policy_denied(tmp_path):
    # Metric-invisible side effect: the host now logs policy_denied for every zero quote.
    ours, ours_audits = _run(ablation.no_zero_quote_guard, "C-006", tmp_path, "nozero")
    ref, ref_audits = _run(workflow, "C-006", tmp_path, "wf")
    assert (ours.status, ours.proposal_amount, ours.refund_effects) == (ref.status, ref.proposal_amount, ref.refund_effects)
    assert ref_audits == []
    assert ours_audits == ["policy_denied"]


def test_unknown_component_is_rejected(tmp_path):
    store = _store(tmp_path, "bad.sqlite")
    with pytest.raises(ValueError):
        ablation._workflow("C-001", seed=11, store_path=str(store), crash_at=None, shape="x", skip=frozenset({"nope"}))


# --- swarm_pruned baseline ------------------------------------------------------------------


def test_pruning_coin_is_deterministic_and_near_half():
    coins = [swarm_pruned.keep_call(seed, c, p) for seed in (11, 22, 33, 44, 55) for c in ALL_CLAIMS for p in swarm_pruned.PRUNABLE]
    assert coins == [swarm_pruned.keep_call(seed, c, p) for seed in (11, 22, 33, 44, 55) for c in ALL_CLAIMS for p in swarm_pruned.PRUNABLE]
    assert 0.3 < sum(coins) / len(coins) < 0.7


def test_dropping_parse_removes_the_seed55_override(tmp_path, monkeypatch):
    kept, _ = _run(swarm_pruned.run_claim, "C-002", tmp_path, "kept", seed=55)
    monkeypatch.setattr(swarm_pruned, "keep_call", lambda *a, **k: False)
    pruned, _ = _run(swarm_pruned.run_claim, "C-002", tmp_path, "pruned", seed=55)
    assert kept.status == "resolved"  # same weakness as the reference swarm when parse is kept
    assert pruned.status == "denied" == BY_ID["C-002"]["expected"]["status"]
    assert pruned.model_calls < kept.model_calls


# --- statistics -----------------------------------------------------------------------------


def test_exact_binomial_and_mcnemar_known_values():
    assert stats.binom_two_sided(0, 5) == pytest.approx(0.0625)
    assert stats.binom_two_sided(0, 0) == 1.0
    assert stats.binom_two_sided(1, 2) == 1.0
    a = {("C-1", s): True for s in range(5)}
    b = {("C-1", s): False for s in range(5)}
    result = stats.mcnemar_exact(a, b)
    assert (result["a_pass_b_fail"], result["a_fail_b_pass"], result["p_value"]) == (5, 0, pytest.approx(0.0625))


def test_claim_level_sign_test_counts_one_claim_once():
    a = {("C-1", s): True for s in range(5)} | {("C-2", s): True for s in range(5)}
    b = {("C-1", s): False for s in range(5)} | {("C-2", s): True for s in range(5)}
    result = stats.sign_test_by_claim(a, b)
    assert (result["claims"], result["a_better"], result["ties"], result["p_value"]) == (2, 1, 1, 1.0)


def test_bootstrap_resamples_claims_and_is_reproducible():
    all_pass = {(f"C-{i}", s): True for i in range(10) for s in range(5)}
    assert stats.bootstrap_ci(all_pass, rounds=500) == [1.0, 1.0]
    mixed = dict(all_pass) | {("C-0", s): False for s in range(5)}
    ci = stats.bootstrap_ci(mixed, rounds=2000)
    assert ci == stats.bootstrap_ci(mixed, rounds=2000)
    assert ci[0] < 0.9 < ci[1] <= 1.0
    assert stats.bootstrap_diff_ci(all_pass, mixed, rounds=2000)[0] >= 0.0


def test_analyse_end_to_end_on_small_benchmark(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setitem(SHAPES, "rules_only", ablation.rules_only)
    monkeypatch.setitem(SHAPES, "wf_no_visibility", ablation.no_visibility_guard)
    claims = [row for row in CLAIMS if row["claim_id"] in {"C-001", "C-005", "C-006"}]
    bench = run_benchmark(world=WORLD, claims=claims, shapes=["workflow", "rules_only", "wf_no_visibility"], seeds=[11, 22])
    report = stats.analyse(bench, {row["claim_id"]: row["expected"] for row in CLAIMS})
    assert report["comparisons_vs_workflow"]["rules_only"]["mcnemar_exact_trial_pairs"]["discordant"] == 0
    abl = report["ablation"]["visibility_guard"]
    assert abl["broken_claims"] == ["C-005"]
    assert abl["removable_without_metric_change"] is False
    for shape in report["shapes"].values():
        assert shape["safety"]["secret_leak_trials"] == 0
