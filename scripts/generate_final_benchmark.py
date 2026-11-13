"""Generate the frozen 60/40 OSRP development/holdout benchmark.

Selection and exact labeling use the memoized baseline only.  No BPCB solver is
imported or executed here.  The manifest records source and algorithm hashes so
the holdout evaluation can reject post-freeze algorithm changes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from osrp import (  # noqa: E402
    SearchStatus,
    level_from_source_snapshot,
    memoized_dfs,
    save_discrete_level,
    validate_solution,
)
from osrp.mutation import (  # noqa: E402
    MutationRecipe,
    mutate_level,
    profile_capacities,
    with_waiting_capacity,
)


ALGORITHM_FILES = (
    "osrp/model.py",
    "osrp/simulator.py",
    "osrp/bounds.py",
    "osrp/search.py",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _slug(snapshot_name: str) -> str:
    stem = Path(snapshot_name).stem.removeprefix("flutter_source_")
    return re.sub(r"[^A-Za-z0-9]+", "_", stem).strip("_")


def _recipe_seed(metadata: dict[str, object], attempt: int, lane: int) -> int:
    level = int(metadata["level"])
    source_seed = metadata.get("seed")
    if source_seed is None:
        return level * 10_000 + lane * 1_000 + attempt
    return level * 10_000_000 + int(source_seed) * 10_000 + lane * 1_000 + attempt


def _recipe(base, metadata: dict[str, object], attempt: int, lane: int) -> MutationRecipe:
    return MutationRecipe(
        seed=_recipe_seed(metadata, attempt, lane),
        box_swaps=1 + attempt % max(2, min(8, len(base.boxes))),
        screw_color_swaps=1 + (attempt * 3) % max(2, min(10, len(base.screws))),
    )


def _structure(level) -> dict[str, int]:
    return {
        "plates": len(level.plates),
        "screws": len(level.screws),
        "boxes": len(level.boxes),
        "colors": len({screw.color for screw in level.screws}),
        "blocker_pairs": len(level.covers),
        "waiting_capacity": level.waiting_capacity,
    }


def _label(level, *, max_nodes: int, time_limit: float):
    result = memoized_dfs(
        level,
        max_nodes=max_nodes,
        time_limit_seconds=time_limit,
    )
    if result.solution is not None:
        validation = validate_solution(level, result.solution)
        if not validation.valid_solution:
            raise AssertionError(f"baseline returned invalid solution: {validation.message}")
    return result


def _save_instance(
    *,
    level,
    output: Path,
    instance_id: str,
    split: str,
    stratum: str,
    source_snapshot: str,
    result,
    recipe: MutationRecipe | None = None,
    family_id: str | None = None,
    boundary_class: str | None = None,
) -> dict[str, object]:
    filename = f"{instance_id}.json"
    path = output / filename
    save_discrete_level(level, path)
    record: dict[str, object] = {
        "instance_id": instance_id,
        "split": split,
        "stratum": stratum,
        "source_snapshot": source_snapshot,
        "file": filename,
        "sha256": _sha256(path),
        "expected_status": result.status.value,
        "baseline_label": {
            "nodes_expanded": result.stats.nodes_expanded,
            "memo_prunes": result.stats.memo_prunes,
            "max_depth": result.stats.max_depth,
        },
        "structure": _structure(level),
    }
    if recipe is not None:
        record["recipe"] = asdict(recipe)
    if family_id is not None:
        record["family_id"] = family_id
    if boundary_class is not None:
        record["boundary_class"] = boundary_class
    return record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", type=Path, default=PROJECT_ROOT / "final_benchmark_config.json"
    )
    parser.add_argument("--fixtures", type=Path, default=PROJECT_ROOT / "fixtures")
    parser.add_argument(
        "--output", type=Path, default=PROJECT_ROOT / "generated_final_dataset"
    )
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    if args.output.exists():
        if not args.overwrite:
            parser.error(f"output already exists: {args.output}; use --overwrite")
        shutil.rmtree(args.output)
    args.output.mkdir(parents=True)

    limits = config["exact_label_limits"]
    max_nodes = int(limits["max_nodes"])
    time_limit = float(limits["time_limit_seconds"])
    capacities = tuple(int(value) for value in config["capacity_values"])
    max_attempts = int(config["max_seed_attempts"])
    common_capacity = int(config["waiting_capacity_for_raw_and_general"])
    per_base = config["instances_per_base"]

    instances: list[dict[str, object]] = []
    rejected: list[dict[str, object]] = []
    all_snapshots = [
        ("development", name) for name in config["development_snapshots"]
    ] + [("holdout", name) for name in config["holdout_snapshots"]]

    for split, snapshot_name in all_snapshots:
        snapshot_path = args.fixtures / snapshot_name
        snapshot_payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
        metadata = snapshot_payload["metadata"]
        base = level_from_source_snapshot(snapshot_path)
        base_slug = _slug(snapshot_name)
        print(f"{split} {base_slug}: raw/general/boundary labeling")

        raw = with_waiting_capacity(
            base, common_capacity, name=f"{base.name} [raw W={common_capacity}]"
        )
        raw_result = _label(raw, max_nodes=max_nodes, time_limit=time_limit)
        if raw_result.status is SearchStatus.LIMIT_REACHED:
            raise RuntimeError(f"raw baseline limit reached for {snapshot_name}")
        instances.append(
            _save_instance(
                level=raw,
                output=args.output,
                instance_id=f"{split[:3]}_{base_slug}_raw",
                split=split,
                stratum="raw_direct",
                source_snapshot=snapshot_name,
                result=raw_result,
            )
        )

        general_record = None
        for attempt in range(1, max_attempts + 1):
            recipe = _recipe(base, metadata, attempt, lane=7)
            general = mutate_level(base, recipe, waiting_capacity=common_capacity)
            result = _label(general, max_nodes=max_nodes, time_limit=time_limit)
            if result.status is SearchStatus.LIMIT_REACHED:
                rejected.append(
                    {
                        "split": split,
                        "source_snapshot": snapshot_name,
                        "stratum": "general_mutation",
                        "attempt": attempt,
                        "reason": "baseline_limit_reached",
                    }
                )
                continue
            general_record = _save_instance(
                level=general,
                output=args.output,
                instance_id=f"{split[:3]}_{base_slug}_general",
                split=split,
                stratum="general_mutation",
                source_snapshot=snapshot_name,
                result=result,
                recipe=recipe,
            )
            instances.append(general_record)
            break
        if general_record is None:
            raise RuntimeError(f"no exact-labeled general mutation for {snapshot_name}")

        family_target = int(
            per_base[
                "development_boundary_families"
                if split == "development"
                else "holdout_boundary_families"
            ]
        )
        accepted = 0
        signatures: set[tuple[object, ...]] = set()
        for attempt in range(1, max_attempts + 1):
            recipe = _recipe(base, metadata, attempt, lane=0)
            profile = profile_capacities(
                base,
                recipe,
                capacities,
                max_nodes=max_nodes,
                time_limit_seconds=time_limit,
            )
            minimum = profile.minimum_feasible_capacity
            if not profile.boundary_confirmed or minimum is None or minimum == 0:
                rejected.append(
                    {
                        "split": split,
                        "source_snapshot": snapshot_name,
                        "stratum": "capacity_boundary",
                        "attempt": attempt,
                        "reason": "boundary_not_exactly_confirmed",
                        "statuses": [run.status.value for run in profile.runs],
                    }
                )
                continue
            solvable = mutate_level(base, recipe, waiting_capacity=minimum)
            signature = (
                tuple((s.id, s.color) for s in solvable.screws),
                tuple((b.color, b.capacity) for b in solvable.boxes),
                minimum,
            )
            if signature in signatures:
                continue
            signatures.add(signature)
            accepted += 1
            family_id = f"{split[:3]}_{base_slug}_boundary_{accepted:02d}"
            solved_run = profile.run_at(minimum)
            unsolved_run = profile.run_at(minimum - 1)
            if solved_run.status is not SearchStatus.SOLVED:
                raise AssertionError("confirmed boundary lacks solved upper instance")
            if unsolved_run.status is not SearchStatus.UNSOLVABLE:
                raise AssertionError("confirmed boundary lacks unsolved lower instance")
            instances.append(
                _save_instance(
                    level=solvable,
                    output=args.output,
                    instance_id=f"{family_id}_solvable_W{minimum}",
                    split=split,
                    stratum="capacity_boundary",
                    source_snapshot=snapshot_name,
                    result=_label(
                        solvable, max_nodes=max_nodes, time_limit=time_limit
                    ),
                    recipe=recipe,
                    family_id=family_id,
                    boundary_class="solvable_at_minimum",
                )
            )
            unsolvable = mutate_level(base, recipe, waiting_capacity=minimum - 1)
            instances.append(
                _save_instance(
                    level=unsolvable,
                    output=args.output,
                    instance_id=f"{family_id}_unsolvable_W{minimum - 1}",
                    split=split,
                    stratum="capacity_boundary",
                    source_snapshot=snapshot_name,
                    result=_label(
                        unsolvable, max_nodes=max_nodes, time_limit=time_limit
                    ),
                    recipe=recipe,
                    family_id=family_id,
                    boundary_class="unsolvable_below_minimum",
                )
            )
            if accepted >= family_target:
                break
        if accepted < family_target:
            raise RuntimeError(
                f"{snapshot_name}: accepted {accepted}/{family_target} "
                "boundary families"
            )

    split_counts = Counter(str(item["split"]) for item in instances)
    stratum_counts = Counter(
        (str(item["split"]), str(item["stratum"])) for item in instances
    )
    target = config["final_target"]
    expected = {
        "development": int(target["development_instances"]),
        "holdout": int(target["holdout_instances"]),
    }
    if dict(split_counts) != expected:
        raise RuntimeError(f"split counts {dict(split_counts)} != target {expected}")

    freeze = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "config_file": args.config.name,
        "config_sha256": _sha256(args.config),
        "generator_sha256": _sha256(Path(__file__)),
        "algorithm_files": {
            relative: _sha256(PROJECT_ROOT / relative) for relative in ALGORITHM_FILES
        },
        "fixture_files": {
            name: _sha256(args.fixtures / name) for _, name in all_snapshots
        },
    }
    manifest = {
        "format": "osrp-final-benchmark-v1",
        "source_commit": config["source_commit"],
        "selection_policy": (
            "baseline-only deterministic selection; BPCB was not imported or run"
        ),
        "config": config,
        "freeze": freeze,
        "counts": {
            "total": len(instances),
            "by_split": dict(sorted(split_counts.items())),
            "by_split_and_stratum": {
                f"{split}:{stratum}": count
                for (split, stratum), count in sorted(stratum_counts.items())
            },
        },
        "instances": instances,
        "rejected_attempts": rejected,
    }
    manifest_path = args.output / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    freeze_path = args.output / "freeze.json"
    freeze_path.write_text(
        json.dumps(freeze, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        f"generated {len(instances)} instances: "
        f"development={split_counts['development']} "
        f"holdout={split_counts['holdout']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
