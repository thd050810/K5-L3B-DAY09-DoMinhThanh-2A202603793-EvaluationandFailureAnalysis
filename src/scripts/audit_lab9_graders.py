from __future__ import annotations

import json
from pathlib import Path

from pydantic_evals.evaluators import EvaluatorContext

from lab8.shapes import SHAPES
from lab9.evalset import ITEMS, sha12
from lab9.graders import GRADERS
from lab9.trace_case import investigate
from lab9.variant_agent import make_shape

SEEDS = (11, 22, 33, 44, 55)
FAULT_CASES = (
    ("leaky_trace", "C-010"),
    ("ignore_denied", "C-007"),
    ("ticket_trust", "C-002"),
    ("sum_parts", "C-014"),
    ("pre_deducted", "C-014"),
    ("stale_clause", "C-006"),
    ("sibling_refund", "C-001"),
    ("misreport", "C-008"),
)
SAFETY = {"secret_leak", "approval_bypass"}


def failed_metrics(case: dict) -> list[str]:
    context = EvaluatorContext(
        name="m3-audit", inputs={}, metadata=None, expected_output=case["label"],
        output=case["trial"], duration=0.0, _span_tree=None, attributes={}, metrics={},
    )
    failed = []
    for metric, grader in GRADERS.items():
        if metric == "pass_rate":
            continue
        value = grader().evaluate(context).value
        if bool(value) == (metric in SAFETY):
            failed.append(metric)
    return failed


def main() -> int:
    faults = []
    unaffected = []
    for bug, _ in FAULT_CASES:
        shape = f"m3_audit_{bug}"
        SHAPES[shape] = make_shape(shape, {"no_override", bug})
        for n in range(1, 15):
            claim = f"C-{n:03d}"
            for seed in SEEDS:
                case = investigate(shape, claim, seed)
                # These switches report the proposal instead of the host's committed amount.
                faulty = not case["trial"]["lab8_pass"] or (
                    bug in {"misreport", "pre_deducted"} and claim in {"C-008", "C-014"}
                )
                rows = faults if faulty else unaffected
                rows.append({"bug": bug, "claim_id": claim, "seed": seed,
                             "failed_metrics": failed_metrics(case)})
    controls = []
    for shape in ("fixed", "honest_refactor"):
        for n in range(1, 15):
            for seed in SEEDS:
                claim = f"C-{n:03d}"
                controls.append({"shape": shape, "claim_id": claim, "seed": seed,
                                 "failed_metrics": failed_metrics(investigate(shape, claim, seed))})
    detection = sum(bool(row["failed_metrics"]) for row in faults) / len(faults)
    false_positive = sum(bool(row["failed_metrics"]) for row in controls) / len(controls)
    report = {
        "eval_set_sha": sha12(ITEMS), "seeds": list(SEEDS),
        "scope": "14 public claims with 8 individual public bug switches; detection excludes TrialPass",
        "oracle": "Lab 8 failures plus confirmed FM-08 for misreport/pre_deducted on C-008/C-014",
        "fault_trials": len(faults), "control_trials": len(controls),
        "detection_rate": detection, "false_positive_rate": false_positive,
        "unaffected_variant_trials": len(unaffected),
        "unaffected_false_positive_rate": sum(bool(row["failed_metrics"]) for row in unaffected) / len(unaffected),
        "faults": faults, "controls": controls, "unaffected": unaffected,
    }
    out = Path("reports/m3_grader_audit.json")
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Faults detected: {detection:.1%} ({len(faults)} trials)")
    print(f"Control false positives: {false_positive:.1%} ({len(controls)} trials)")
    print(f"wrote {out}")
    return 0 if detection >= 0.8 and false_positive <= 0.1 else 1


if __name__ == "__main__":
    raise SystemExit(main())
