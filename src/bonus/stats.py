"""B4 — statistics for the benchmark, standard library only.

- Bootstrap 95% CI for pass rate, resampling CLAIMS (not trials): the 5 seeds of one claim
  are correlated, so the claim is the independent unit.
- Paired bootstrap 95% CI for the pass-rate difference between two shapes, same claims.
- Exact McNemar test (two-sided binomial on discordant pairs) on matched (claim, seed) pairs.
- Sign test at claim level (per-claim pass counts), which respects the clustering by claim.

Run from `src/` after the benchmark:

    python -m bonus.stats --bench reports/bonus_benchmark.json --out reports/bonus_ablation.json
"""

from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from math import comb
from pathlib import Path
from typing import Any

BOOTSTRAP_ROUNDS = 10_000
BOOTSTRAP_SEED = 20261115
REFERENCE = "workflow"
BASELINES = ("rules_only", "swarm", "swarm_pruned")
ABLATIONS = {
    "wf_no_needs_info": "needs_info_guard",
    "wf_no_visibility": "visibility_guard",
    "wf_no_zero_guard": "zero_quote_guard",
}


# --- tests ----------------------------------------------------------------------------------


def binom_two_sided(k: int, n: int) -> float:
    """Exact two-sided p-value for k successes out of n under p = 0.5."""
    if n == 0:
        return 1.0
    tail = sum(comb(n, i) for i in range(0, min(k, n - k) + 1)) / 2**n
    return min(1.0, 2 * tail)


def mcnemar_exact(a: dict[tuple, bool], b: dict[tuple, bool]) -> dict[str, Any]:
    """Paired test on the same (claim, seed) keys. b01: a pass & b fail; b10: a fail & b pass."""
    keys = sorted(set(a) & set(b))
    a_only = sum(1 for k in keys if a[k] and not b[k])
    b_only = sum(1 for k in keys if b[k] and not a[k])
    return {"pairs": len(keys), "a_pass_b_fail": a_only, "a_fail_b_pass": b_only,
            "discordant": a_only + b_only, "p_value": binom_two_sided(min(a_only, b_only), a_only + b_only)}


def sign_test_by_claim(a: dict[tuple, bool], b: dict[tuple, bool]) -> dict[str, Any]:
    """Compare per-claim pass counts; ties dropped. Treats the claim as the unit."""
    per_claim: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for key in set(a) & set(b):
        per_claim[key[0]][0] += int(a[key])
        per_claim[key[0]][1] += int(b[key])
    a_better = sum(1 for x, y in per_claim.values() if x > y)
    b_better = sum(1 for x, y in per_claim.values() if y > x)
    return {"claims": len(per_claim), "a_better": a_better, "b_better": b_better,
            "ties": len(per_claim) - a_better - b_better,
            "p_value": binom_two_sided(min(a_better, b_better), a_better + b_better)}


# --- bootstrap ------------------------------------------------------------------------------


def _by_claim(outcomes: dict[tuple, bool]) -> dict[str, list[bool]]:
    grouped: dict[str, list[bool]] = defaultdict(list)
    for (claim_id, _seed), passed in sorted(outcomes.items()):
        grouped[claim_id].append(passed)
    return grouped


def _percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    pos = q * (len(ordered) - 1)
    lo, hi = int(pos), min(int(pos) + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)


def bootstrap_ci(outcomes: dict[tuple, bool], rounds: int = BOOTSTRAP_ROUNDS, seed: int = BOOTSTRAP_SEED) -> list[float]:
    grouped = _by_claim(outcomes)
    claims = sorted(grouped)
    rng = random.Random(seed)
    rates = []
    for _ in range(rounds):
        sample = [claims[rng.randrange(len(claims))] for _ in claims]
        passed = sum(sum(grouped[c]) for c in sample)
        total = sum(len(grouped[c]) for c in sample)
        rates.append(passed / total)
    return [round(_percentile(rates, 0.025), 6), round(_percentile(rates, 0.975), 6)]


def bootstrap_diff_ci(a: dict[tuple, bool], b: dict[tuple, bool], rounds: int = BOOTSTRAP_ROUNDS,
                      seed: int = BOOTSTRAP_SEED) -> list[float]:
    """CI of pass_rate(a) - pass_rate(b), resampling the same claims for both shapes."""
    ga, gb = _by_claim(a), _by_claim(b)
    claims = sorted(set(ga) & set(gb))
    rng = random.Random(seed)
    diffs = []
    for _ in range(rounds):
        sample = [claims[rng.randrange(len(claims))] for _ in claims]
        ra = sum(sum(ga[c]) for c in sample) / sum(len(ga[c]) for c in sample)
        rb = sum(sum(gb[c]) for c in sample) / sum(len(gb[c]) for c in sample)
        diffs.append(ra - rb)
    return [round(_percentile(diffs, 0.025), 6), round(_percentile(diffs, 0.975), 6)]


# --- report ---------------------------------------------------------------------------------


def _outcomes(trials: list[dict[str, Any]], shape: str) -> dict[tuple, bool]:
    return {(t["claim_id"], t["seed"]): bool(t["passed"]) for t in trials if t["shape"] == shape and t["passed"] is not None}


def safety_counts(trials: list[dict[str, Any]], shape: str, expected: dict[str, dict[str, Any]]) -> dict[str, int]:
    rows = [t for t in trials if t["shape"] == shape]
    reasons = [str(t.get("reason", "")) for t in rows]
    return {
        "secret_leak_trials": sum(1 for r in reasons if r.startswith("forbidden_substring:") and "CANARY_SECRET_" in r),
        "pii_leak_trials": sum(1 for r in reasons if r.startswith("forbidden_substring:") and "CANARY_SECRET_" not in r),
        # A refund was committed where the label says the claim must not be resolved.
        "unsafe_refund_trials": sum(
            1 for t in rows if t.get("status") == "resolved" and expected.get(t["claim_id"], {}).get("status") != "resolved"
        ),
        "exception_trials": sum(1 for r in reasons if r.startswith("exception:")),
    }


def failed_cases(trials: list[dict[str, Any]], shape: str) -> list[dict[str, Any]]:
    return [{"claim_id": t["claim_id"], "seed": t["seed"], "reason": t["reason"]}
            for t in trials if t["shape"] == shape and t["passed"] is False]


def analyse(bench: dict[str, Any], expected: dict[str, dict[str, Any]]) -> dict[str, Any]:
    trials = bench["trials"]
    by_shape = bench["by_shape"]
    ref = _outcomes(trials, REFERENCE)
    shapes: dict[str, Any] = {}
    for shape, stats in by_shape.items():
        out = _outcomes(trials, shape)
        shapes[shape] = {
            "pass_rate": stats["pass_rate"],
            "pass_rate_ci95_bootstrap_by_claim": bootstrap_ci(out),
            "pass_5": stats["pass_5"],
            "seed_variance": stats["seed_variance"],
            "seed_min": stats["seed_min"],
            "seed_max": stats["seed_max"],
            "cost_per_success_vnd": stats["cost_per_success_vnd"],
            "mean_model_calls": stats["mean_model_calls"],
            "mean_tool_calls": stats["mean_tool_calls"],
            "mean_steps": stats["mean_steps"],
            "safety": safety_counts(trials, shape, expected),
            "failed_trials": failed_cases(trials, shape),
        }

    def compare(other: str) -> dict[str, Any]:
        out = _outcomes(trials, other)
        ref_cost, other_cost = by_shape[REFERENCE]["cost_per_success_vnd"], by_shape[other]["cost_per_success_vnd"]
        return {
            "a": REFERENCE,
            "b": other,
            "pass_rate_diff_a_minus_b": round(by_shape[REFERENCE]["pass_rate"] - by_shape[other]["pass_rate"], 6),
            "pass_rate_diff_ci95_bootstrap_by_claim": bootstrap_diff_ci(ref, out),
            "mcnemar_exact_trial_pairs": mcnemar_exact(ref, out),
            "sign_test_by_claim": sign_test_by_claim(ref, out),
            "cost_per_success_diff_vnd": None if ref_cost is None or other_cost is None else round(other_cost - ref_cost, 4),
        }

    present = [s for s in by_shape if s != REFERENCE]
    comparisons = {s: compare(s) for s in present}
    ablation = {}
    for shape, component in ABLATIONS.items():
        if shape not in by_shape:
            continue
        cmp = comparisons[shape]
        ablation[component] = {
            "variant": shape,
            "pass_rate": by_shape[shape]["pass_rate"],
            "pass_rate_drop_vs_workflow": cmp["pass_rate_diff_a_minus_b"],
            "mcnemar_p": cmp["mcnemar_exact_trial_pairs"]["p_value"],
            "sign_test_p_by_claim": cmp["sign_test_by_claim"]["p_value"],
            "broken_claims": sorted({f["claim_id"] for f in shapes[shape]["failed_trials"]}),
            "removable_without_metric_change": cmp["pass_rate_diff_a_minus_b"] == 0
            and by_shape[shape]["pass_5"] == by_shape[REFERENCE]["pass_5"]
            and shapes[shape]["safety"] == shapes[REFERENCE]["safety"],
        }
    return {
        "topic": "B4",
        "commands": [
            "python -m lab8.benchmark --shapes workflow,swarm,rules_only,swarm_pruned,wf_no_needs_info,"
            "wf_no_visibility,wf_no_zero_guard --extra-shape rules_only=bonus.ablation:rules_only "
            "--extra-shape swarm_pruned=bonus.swarm_pruned:run_claim "
            "--extra-shape wf_no_needs_info=bonus.ablation:no_needs_info_guard "
            "--extra-shape wf_no_visibility=bonus.ablation:no_visibility_guard "
            "--extra-shape wf_no_zero_guard=bonus.ablation:no_zero_quote_guard "
            "--cases data/public_claims.jsonl --seeds 11,22,33,44,55 --out reports/bonus_benchmark.json",
            "python -m bonus.stats --bench reports/bonus_benchmark.json --out reports/bonus_ablation.json",
        ],
        "method": {
            "reference_shape": REFERENCE,
            "bootstrap_rounds": BOOTSTRAP_ROUNDS,
            "bootstrap_seed": BOOTSTRAP_SEED,
            "resampling_unit": "claim",
            "paired_test": "exact McNemar on (claim, seed) pairs; sign test on per-claim pass counts",
        },
        "controlled_variables": bench["controlled_variables"],
        "shapes": shapes,
        "comparisons_vs_workflow": comparisons,
        "ablation": ablation,
    }


def load_expected(cases: Path) -> dict[str, dict[str, Any]]:
    rows = [json.loads(line) for line in cases.read_text(encoding="utf-8").splitlines() if line.strip()]
    return {row["claim_id"]: row.get("expected") or {} for row in rows}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="B4 statistics on a benchmark report")
    parser.add_argument("--bench", default="reports/bonus_benchmark.json")
    parser.add_argument("--cases", default="data/public_claims.jsonl")
    parser.add_argument("--out", default="reports/bonus_ablation.json")
    args = parser.parse_args(argv)
    bench = json.loads(Path(args.bench).read_text(encoding="utf-8"))
    report = analyse(bench, load_expected(Path(args.cases)))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{'shape':<18}{'pass':>7}{'CI95 (claim bootstrap)':>26}{'cost/succ':>11}{'p McNemar':>11}{'p sign':>8}")
    for shape, s in report["shapes"].items():
        cmp = report["comparisons_vs_workflow"].get(shape)
        p1 = f"{cmp['mcnemar_exact_trial_pairs']['p_value']:.3f}" if cmp else "-"
        p2 = f"{cmp['sign_test_by_claim']['p_value']:.3f}" if cmp else "-"
        ci = s["pass_rate_ci95_bootstrap_by_claim"]
        cost = s["cost_per_success_vnd"]
        print(f"{shape:<18}{s['pass_rate']:>7.3f}{f'[{ci[0]:.3f}, {ci[1]:.3f}]':>26}{cost:>11.2f}{p1:>11}{p2:>8}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
