"""Summarize imported Flutter snapshots and replay the raw exact baseline."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from osrp import level_from_source_snapshot, memoized_dfs, validate_solution  # noqa: E402


def _level_number(path: Path) -> int:
    match = re.search(r"level_(\d+)", path.stem)
    if not match:
        raise ValueError(f"cannot infer level number from {path.name}")
    return int(match.group(1))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", type=Path, default=PROJECT_ROOT / "fixtures")
    parser.add_argument("--max-nodes", type=int, default=500_000)
    parser.add_argument("--time-limit", type=float, default=10.0)
    args = parser.parse_args()

    snapshots = sorted(
        args.fixtures.glob("flutter_source_level_*.json"), key=_level_number
    )
    print("level\tplates\tscrews\tboxes\tcolors\tblockers\tstatus\tnodes\tvalid")
    failures = 0
    for snapshot in snapshots:
        level_number = _level_number(snapshot)
        level = level_from_source_snapshot(snapshot)
        result = memoized_dfs(
            level,
            max_nodes=args.max_nodes,
            time_limit_seconds=args.time_limit,
        )
        valid = result.solution is None or validate_solution(
            level, result.solution
        ).valid_solution
        failures += not valid
        print(
            level_number,
            len(level.plates),
            len(level.screws),
            len(level.boxes),
            len({s.color for s in level.screws}),
            len(level.covers),
            result.status.value,
            result.stats.nodes_expanded,
            valid,
            sep="\t",
        )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
