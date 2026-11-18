"""Rerun the public benchmark and scan fresh traces and console output."""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
SENSITIVE_FIELDS = ("phone", "address", "internal_note", "item_name")


def search_values() -> set[str]:
    world_path = SRC / "data" / "public_world_state.json"
    world = json.loads(world_path.read_text(encoding="utf-8"))
    return {"CANARY_SECRET_", "CANARY_INTERNAL_"} | {
        order[field]
        for order in world["orders"]
        for field in SENSITIVE_FIELDS
        if order[field]
    }


def scan(workspace: Path, values: set[str]) -> int:
    report_path = workspace / "benchmark.json"
    benchmark = subprocess.run(
        [
            sys.executable,
            "-m",
            "lab8.benchmark",
            "--shapes",
            "workflow,single,orchestrator,swarm",
            "--cases",
            str(SRC / "data" / "public_claims.jsonl"),
            "--world",
            str(SRC / "data" / "public_world_state.json"),
            "--seeds",
            "11,22,33,44,55",
            "--out",
            str(report_path),
        ],
        cwd=workspace,
        env={**os.environ, "PYTHONPATH": str(SRC)},
        capture_output=True,
        encoding="utf-8",
        check=True,
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    traces = sorted(path for path in (workspace / "traces").rglob("*") if path.is_file())
    expected = {workspace / "traces" / f"{trial['run_id']}.json" for trial in report["trials"]}
    missing = expected.difference(traces)
    if len(expected) != 280 or missing:
        print(f"Incomplete benchmark traces: expected {len(expected)}, missing {len(missing)}.", file=sys.stderr)
        return 1

    artifacts = [(str(path.relative_to(workspace)), path.read_text(encoding="utf-8")) for path in traces]
    artifacts.extend([("stdout", benchmark.stdout), ("stderr", benchmark.stderr)])
    total_matches = 0
    for source, body in artifacts:
        matches = sum(value in body for value in values)
        if matches:
            print(f"{source}: {matches} matched search values", file=sys.stderr)
            total_matches += matches

    print(
        f"Scanned {len(traces)} fresh trace files, stdout, and stderr "
        f"against {len(values)} search values: {total_matches} matches."
    )
    return int(total_matches > 0)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="lab8-public-scan-") as directory:
        return scan(Path(directory), search_values())


if __name__ == "__main__":
    raise SystemExit(main())
