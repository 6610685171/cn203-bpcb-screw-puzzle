"""Verify frozen files and exact baseline labels in the final benchmark."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from osrp import SearchStatus, load_discrete_level, memoized_dfs, validate_solution  # noqa: E402


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "dataset", type=Path, nargs="?", default=PROJECT_ROOT / "generated_final_dataset"
    )
    parser.add_argument("--max-nodes", type=int)
    parser.add_argument(
        "--time-limit",
        type=float,
        default=None,
        help=(
            "optional wall-clock limit per instance; disabled by default so "
            "verification is independent of machine speed"
        ),
    )
    args = parser.parse_args()

    manifest_path = args.dataset / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    limits = manifest["config"]["exact_label_limits"]
    max_nodes = (
        args.max_nodes
        if args.max_nodes is not None
        else int(limits["max_nodes"])
    )
    time_limit = args.time_limit

    failures: list[str] = []
    counts: Counter[tuple[str, str, str]] = Counter()
    for relative, expected in manifest["freeze"]["algorithm_files"].items():
        actual = _sha256(PROJECT_ROOT / relative)
        if actual != expected:
            failures.append(f"algorithm hash mismatch: {relative}")

    for index, record in enumerate(manifest["instances"], start=1):
        path = args.dataset / record["file"]
        if _sha256(path) != record["sha256"]:
            failures.append(f"instance hash mismatch: {record['file']}")
            continue
        level = load_discrete_level(path)
        result = memoized_dfs(
            level, max_nodes=max_nodes, time_limit_seconds=time_limit
        )
        expected = SearchStatus(record["expected_status"])
        valid = result.status is expected
        if result.solution is not None:
            valid = valid and validate_solution(level, result.solution).valid_solution
        if not valid:
            failures.append(
                f"{record['instance_id']}: got {result.status.value}, "
                f"expected {expected.value}"
            )
        counts[(record["split"], record["stratum"], result.status.value)] += 1
        if index % 10 == 0:
            print(f"verified {index}/{len(manifest['instances'])}")

    expected_counts = manifest["config"]["final_target"]
    split_counts = Counter(item["split"] for item in manifest["instances"])
    if split_counts["development"] != expected_counts["development_instances"]:
        failures.append("development count mismatch")
    if split_counts["holdout"] != expected_counts["holdout_instances"]:
        failures.append("holdout count mismatch")

    print("split\tstratum\tstatus\tcount")
    for key, count in sorted(counts.items()):
        print(*key, count, sep="\t")
    if failures:
        print("FAILURES", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print("final benchmark verification: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
