from __future__ import annotations

import argparse
import json
from pathlib import Path
from math import isfinite
from statistics import mean

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, load_spec, per_item
from lab9.graders import GRADERS


def _threshold_loosened(current: dict, previous: dict) -> bool:
    if "min" in previous and ("min" not in current or current["min"] < previous["min"]):
        return True
    for key in ("max", "max_increase"):
        if key in previous and (key not in current or current[key] > previous[key]):
            return True
    return bool(previous.get("no_significant_drop") and not current.get("no_significant_drop"))


def _ratchet_problems(spec: dict, base_spec: dict) -> list[str]:
    if spec.get("eval_set_version") != base_spec.get("eval_set_version"):
        return []
    problems = []
    for section, fields in (("metrics", ("id",)), ("slices", ("name", "metric"))):
        current = {tuple(entry[field] for field in fields): entry for entry in spec.get(section, [])}
        for old in base_spec.get(section, []):
            key = tuple(old[field] for field in fields)
            entry = current.get(key)
            if section == "metrics":
                old_threshold = old.get("threshold", {})
                new_threshold = (entry or {}).get("threshold", {})
            else:
                old_threshold, new_threshold = old, entry or {}
            if entry is None or (old.get("blocking") and not entry.get("blocking")) or (
                _threshold_loosened(new_threshold, old_threshold)
            ):
                problems.append(f"ratchet: removed or loosened {section} {'/'.join(key)}")
    return problems


def _report_index(report: dict, name: str, graded: set[str], problems: list[str]) -> dict:
    manifest = report["manifest"]
    rows = report["rows"]
    seeds = set(manifest["seeds"])
    items = {row["item_id"] for row in rows}
    expected = {(item, seed) for item in items for seed in seeds}
    index = {}
    tags_by_item = {}
    for row in rows:
        item = row["item_id"]
        key = (item, row["seed"])
        tags = frozenset(row.get("slices") or [])
        if key in index:
            problems.append(f"{name}: duplicate trial {key}")
        if tags_by_item.setdefault(item, tags) != tags:
            problems.append(f"{name}: inconsistent slice tags for {item}")
        index[key] = tags
        for metric in sorted(graded):
            if not isinstance(row.get(metric), bool):
                problems.append(f"{name}: invalid or missing grader result {metric} at {key}")
    if not rows or not seeds or len(seeds) != len(manifest["seeds"]) or (
        len(items) != manifest["items"] or len(rows) != len(expected) or index.keys() != expected
    ):
        problems.append(f"{name}: rows do not cover the manifest item × seed grid")
    if report.get("evaluator_failures"):
        problems.append(f"{name}: evaluator failures")
    for metric, value in report["metrics"].items():
        if value is not None and (not isinstance(value, (int, float)) or not isfinite(value)):
            problems.append(f"{name}: non-finite or invalid metric {metric}")
    return index


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    problems = _ratchet_problems(spec, base_spec) if base_spec is not None else []
    graded = {metric["id"] for metric in spec["metrics"] if metric["id"] in GRADERS}
    pr_index = _report_index(pr, "PR", graded, problems)
    base_index = _report_index(base, "baseline", graded, problems)
    if pr_index.keys() != base_index.keys():
        problems.append("PR and baseline have different item/seed pairs")
    elif pr_index != base_index:
        problems.append("PR and baseline have different slice tags")
    return problems


def _paired_interval(pr: dict, base: dict, options: dict) -> tuple[float, float, float]:
    keys = sorted(pr)
    return stats.paired_bootstrap(
        [pr[key] for key in keys], [base[key] for key in keys],
        n_resamples=options.get("n_resamples", 1000),
        rng=options.get("rng", 2027),
        confidence=options.get("confidence", 0.95),
    )


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    blocked, lines = [], []
    for entry in spec.get("slices", []):
        name, metric = entry["name"], entry["metric"]
        key = f"slice:{name}/{metric}"
        scores = per_item(pr, metric, slice_name=name)
        baseline = per_item(base, metric, slice_name=name)
        min_score = entry.get("min")
        value = mean(scores.values()) if scores else None
        failed = value is None or scores.keys() != baseline.keys()
        note = "missing or unpaired scores" if failed else ""
        if not failed and min_score is not None:
            failed = value < min_score
        if scores and scores.keys() == baseline.keys() and entry.get("no_significant_drop"):
            if len(scores) < 2:
                failed, note = True, "at least two paired items required"
            else:
                delta, low, high = _paired_interval(scores, baseline, spec.get("bootstrap", {}))
                note = f"Δ {delta:+.3f} CI [{low:+.3f}, {high:+.3f}]"
                failed = failed or high < 0
        if failed and entry.get("blocking"):
            blocked.append(key)
        verdict = "BLOCK" if key in blocked else ("warn" if failed else "ok")
        lines.append(f"  {key} {value!s} min={min_score!s} {note} {verdict}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            if len(a) < 2 or a.keys() != b.keys():
                verdict, note = "missing", "insufficient paired scores"
            else:
                d, lo, hi = _paired_interval(a, b, bs)
                note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
                if hi < 0:
                    verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
