"""Run the frozen final benchmark and create reproducible tables and PNG charts."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import platform
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Callable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from osrp import (  # noqa: E402
    SearchResult,
    SearchStatus,
    bpcb1_memoized_dfs,
    bpcb12_memoized_dfs,
    bpcb2_memoized_dfs,
    load_discrete_level,
    memoized_dfs,
    validate_solution,
)


METHOD_ORDER = ("baseline", "bpcb1", "bpcb2", "bpcb12")
CSV_FIELDS = (
    "instance_id",
    "split",
    "stratum",
    "expected_status",
    "method",
    "status",
    "solution_length",
    "nodes_expanded",
    "transitions_generated",
    "unique_states_seen",
    "memo_prunes",
    "terminal_dead_ends",
    "proven_dead_states",
    "max_depth",
    "bound_checks",
    "bound_prunes",
    "bound_combinations_evaluated",
    "bound_fallbacks",
    "median_ms",
    "min_ms",
    "max_ms",
    "timings_ms_json",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_freeze(dataset: Path, manifest: dict[str, object]) -> None:
    failures: list[str] = []
    freeze = manifest["freeze"]
    for relative, expected in freeze["algorithm_files"].items():
        path = PROJECT_ROOT / relative
        if not path.is_file() or sha256(path) != expected:
            failures.append(f"algorithm hash mismatch: {relative}")
    for record in manifest["instances"]:
        path = dataset / record["file"]
        if not path.is_file() or sha256(path) != record["sha256"]:
            failures.append(f"instance hash mismatch: {record['file']}")
    if failures:
        raise RuntimeError("freeze verification failed:\n- " + "\n- ".join(failures))


def method_functions(
    *, max_nodes: int, time_limit: float, max_bound_combinations: int
) -> dict[str, Callable[[object], SearchResult]]:
    return {
        "baseline": lambda level: memoized_dfs(
            level, max_nodes=max_nodes, time_limit_seconds=time_limit
        ),
        "bpcb1": lambda level: bpcb1_memoized_dfs(
            level, max_nodes=max_nodes, time_limit_seconds=time_limit
        ),
        "bpcb2": lambda level: bpcb2_memoized_dfs(
            level,
            max_nodes=max_nodes,
            time_limit_seconds=time_limit,
            max_bound_combinations=max_bound_combinations,
        ),
        "bpcb12": lambda level: bpcb12_memoized_dfs(
            level,
            max_nodes=max_nodes,
            time_limit_seconds=time_limit,
            max_bound_combinations=max_bound_combinations,
        ),
    }


def check_result(level, result: SearchResult, expected: str, context: str) -> None:
    if result.status.value != expected:
        raise AssertionError(
            f"{context}: got {result.status.value}, expected {expected}"
        )
    if result.status is SearchStatus.SOLVED:
        if result.solution is None:
            raise AssertionError(f"{context}: solved without a solution")
        validation = validate_solution(level, result.solution)
        if not validation.valid_solution:
            raise AssertionError(f"{context}: invalid solution: {validation.message}")


def run_method(
    level,
    solver: Callable[[object], SearchResult],
    *,
    expected: str,
    context: str,
    warmup: int,
    repeats: int,
) -> tuple[SearchResult, list[float]]:
    for index in range(warmup):
        result = solver(level)
        check_result(level, result, expected, f"{context} warm-up {index + 1}")

    representative: SearchResult | None = None
    timings_ms: list[float] = []
    deterministic_signature: tuple[object, ...] | None = None
    for index in range(repeats):
        started = perf_counter()
        result = solver(level)
        elapsed_ms = (perf_counter() - started) * 1000
        check_result(level, result, expected, f"{context} repeat {index + 1}")
        signature = (
            result.status,
            result.solution,
            result.stats.nodes_expanded,
            result.stats.transitions_generated,
            result.stats.bound_prunes,
            result.stats.bound_combinations_evaluated,
            result.stats.bound_fallbacks,
        )
        if deterministic_signature is None:
            deterministic_signature = signature
            representative = result
        elif signature != deterministic_signature:
            raise AssertionError(f"{context}: non-deterministic search result")
        timings_ms.append(elapsed_ms)
    assert representative is not None
    return representative, timings_ms


def result_row(
    record: dict[str, object], method: str, result: SearchResult, timings: list[float]
) -> dict[str, object]:
    stats = result.stats
    return {
        "instance_id": record["instance_id"],
        "split": record["split"],
        "stratum": record["stratum"],
        "expected_status": record["expected_status"],
        "method": method,
        "status": result.status.value,
        "solution_length": "" if result.solution is None else len(result.solution),
        "nodes_expanded": stats.nodes_expanded,
        "transitions_generated": stats.transitions_generated,
        "unique_states_seen": stats.unique_states_seen,
        "memo_prunes": stats.memo_prunes,
        "terminal_dead_ends": stats.terminal_dead_ends,
        "proven_dead_states": stats.proven_dead_states,
        "max_depth": stats.max_depth,
        "bound_checks": stats.bound_checks,
        "bound_prunes": stats.bound_prunes,
        "bound_combinations_evaluated": stats.bound_combinations_evaluated,
        "bound_fallbacks": stats.bound_fallbacks,
        "median_ms": f"{statistics.median(timings):.6f}",
        "min_ms": f"{min(timings):.6f}",
        "max_ms": f"{max(timings):.6f}",
        "timings_ms_json": json.dumps([round(value, 6) for value in timings]),
    }


def read_existing(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as source:
        return list(csv.DictReader(source))


def write_rows(path: Path, rows: list[dict[str, object]]) -> None:
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(target, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def aggregate(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    groups: dict[tuple[str, str, str], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        groups[(str(row["split"]), str(row["stratum"]), str(row["method"]))].append(row)

    baseline_nodes = {
        (str(row["instance_id"]), str(row["split"])): int(row["nodes_expanded"])
        for row in rows
        if row["method"] == "baseline"
    }
    baseline_times = {
        (str(row["instance_id"]), str(row["split"])): float(row["median_ms"])
        for row in rows
        if row["method"] == "baseline"
    }
    output: list[dict[str, object]] = []
    for (split, stratum, method), items in sorted(groups.items()):
        node_total = sum(int(item["nodes_expanded"]) for item in items)
        time_total = sum(float(item["median_ms"]) for item in items)
        paired_node_total = sum(
            baseline_nodes[(str(item["instance_id"]), split)] for item in items
        )
        paired_time_total = sum(
            baseline_times[(str(item["instance_id"]), split)] for item in items
        )
        reductions = [
            100
            * (baseline_nodes[(str(item["instance_id"]), split)] - int(item["nodes_expanded"]))
            / max(1, baseline_nodes[(str(item["instance_id"]), split)])
            for item in items
        ]
        output.append(
            {
                "split": split,
                "stratum": stratum,
                "method": method,
                "instances": len(items),
                "nodes_total": node_total,
                "node_reduction_total_pct": 100
                * (paired_node_total - node_total)
                / max(1, paired_node_total),
                "node_reduction_median_instance_pct": statistics.median(reductions),
                "median_time_total_ms": time_total,
                "speedup_ratio": paired_time_total / max(1e-12, time_total),
                "bound_prunes_total": sum(int(item["bound_prunes"]) for item in items),
                "bound_combinations_total": sum(
                    int(item["bound_combinations_evaluated"]) for item in items
                ),
                "bound_fallbacks_total": sum(
                    int(item["bound_fallbacks"]) for item in items
                ),
            }
        )
    return output


def write_aggregate(path: Path, rows: list[dict[str, object]]) -> None:
    fields = (
        "split",
        "stratum",
        "method",
        "instances",
        "nodes_total",
        "node_reduction_total_pct",
        "node_reduction_median_instance_pct",
        "median_time_total_ms",
        "speedup_ratio",
        "bound_prunes_total",
        "bound_combinations_total",
        "bound_fallbacks_total",
    )
    with path.open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(target, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def overall_summary(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for split in ("development", "holdout"):
        split_rows = [row for row in rows if row["split"] == split]
        baseline = {
            str(row["instance_id"]): row
            for row in split_rows
            if row["method"] == "baseline"
        }
        for method in METHOD_ORDER:
            items = [row for row in split_rows if row["method"] == method]
            if not items:
                continue
            base_nodes = sum(int(baseline[str(item["instance_id"])]["nodes_expanded"]) for item in items)
            nodes = sum(int(item["nodes_expanded"]) for item in items)
            base_time = sum(float(baseline[str(item["instance_id"])]["median_ms"]) for item in items)
            elapsed = sum(float(item["median_ms"]) for item in items)
            output.append(
                {
                    "split": split,
                    "method": method,
                    "instances": len(items),
                    "nodes": nodes,
                    "node_reduction": 100 * (base_nodes - nodes) / max(1, base_nodes),
                    "time_ms": elapsed,
                    "speedup": base_time / max(1e-12, elapsed),
                    "bound_prunes": sum(int(item["bound_prunes"]) for item in items),
                    "fallbacks": sum(int(item["bound_fallbacks"]) for item in items),
                }
            )
    return output


def write_summary(path: Path, rows: list[dict[str, object]], run_info: dict[str, object]) -> None:
    overall = overall_summary(rows)
    lines = [
        "# Final benchmark summary",
        "",
        f"Generated: {run_info['completed_utc']}",
        "",
        "| Split | Method | n | Nodes | Node reduction | Sum of median times | Speedup | Bound prunes | Fallbacks |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in overall:
        lines.append(
            "| {split} | {method} | {instances} | {nodes:,} | {node_reduction:.2f}% | "
            "{time_ms:.2f} ms | {speedup:.3f}x | {bound_prunes:,} | {fallbacks:,} |".format(**item)
        )
    lines.extend(
        [
            "",
            "Correctness condition: every measured status matched its frozen exact label, and every returned solution passed replay validation.",
            "",
            "Timing is the per-instance median of repeated wall-clock measurements after warm-up. Node counts are the primary machine-independent metric.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def load_pillow():
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as exc:
        raise RuntimeError("Pillow is required to generate PNG charts") from exc
    return Image, ImageDraw, ImageFont


def make_scatter(path: Path, rows: list[dict[str, object]]) -> None:
    Image, ImageDraw, ImageFont = load_pillow()
    width, height = 1400, 1000
    margin = {"left": 130, "right": 70, "top": 100, "bottom": 120}
    image = Image.new("RGB", (width, height), "#F8FAFC")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=24)
    small = ImageFont.load_default(size=18)
    title = ImageFont.load_default(size=32)
    paired: list[tuple[float, float, str]] = []
    by_key = {(str(row["instance_id"]), str(row["method"])): row for row in rows}
    for row in rows:
        if row["method"] != "baseline":
            continue
        candidate = by_key.get((str(row["instance_id"]), "bpcb12"))
        if candidate is None:
            continue
        paired.append(
            (
                math.log10(int(row["nodes_expanded"]) + 1),
                math.log10(int(candidate["nodes_expanded"]) + 1),
                str(row["split"]),
            )
        )
    maximum = max([1.0] + [max(x, y) for x, y, _ in paired])
    x0, x1 = margin["left"], width - margin["right"]
    y0, y1 = height - margin["bottom"], margin["top"]

    def px(value: float) -> float:
        return x0 + value / maximum * (x1 - x0)

    def py(value: float) -> float:
        return y0 - value / maximum * (y0 - y1)

    for tick in range(math.ceil(maximum) + 1):
        x, y = px(tick), py(tick)
        draw.line((x, y0, x, y1), fill="#DCE3EA", width=1)
        draw.line((x0, y, x1, y), fill="#DCE3EA", width=1)
        label = f"10^{tick}"
        draw.text((x - 22, y0 + 18), label, fill="#475569", font=small)
        draw.text((35, y - 10), label, fill="#475569", font=small)
    draw.line((x0, y0, x1, y1), fill="#64748B", width=3)
    colors = {"development": "#2563EB", "holdout": "#E11D48"}
    for x_value, y_value, split in paired:
        x, y = px(x_value), py(y_value)
        color = colors.get(split, "#111827")
        draw.ellipse((x - 6, y - 6, x + 6, y + 6), fill=color, outline="white", width=2)
    draw.text((margin["left"], 38), "Baseline vs BPCB-(1,2): nodes expanded", fill="#0F172A", font=title)
    draw.text((width // 2 - 160, height - 62), "Baseline nodes (log10 scale)", fill="#0F172A", font=font)
    y_label = Image.new("RGBA", (360, 42), (0, 0, 0, 0))
    y_draw = ImageDraw.Draw(y_label)
    y_draw.text(
        (0, 6),
        "BPCB-(1,2) nodes (log10 scale)",
        fill="#0F172A",
        font=small,
    )
    y_label = y_label.rotate(90, expand=True)
    image.paste(y_label, (6, (height - y_label.height) // 2), y_label)
    draw.rectangle((width - 330, 30, width - 50, 88), fill="white", outline="#CBD5E1")
    draw.ellipse((width - 310, 48, width - 298, 60), fill=colors["development"])
    draw.text((width - 290, 42), "development", fill="#334155", font=small)
    draw.ellipse((width - 175, 48, width - 163, 60), fill=colors["holdout"])
    draw.text((width - 155, 42), "holdout", fill="#334155", font=small)
    image.save(path)


def make_reduction_bars(path: Path, rows: list[dict[str, object]]) -> None:
    Image, ImageDraw, ImageFont = load_pillow()
    overall = overall_summary(rows)
    candidates = [item for item in overall if item["method"] != "baseline"]
    width, height = 1400, 900
    image = Image.new("RGB", (width, height), "#F8FAFC")
    draw = ImageDraw.Draw(image)
    title = ImageFont.load_default(size=32)
    font = ImageFont.load_default(size=22)
    small = ImageFont.load_default(size=18)
    draw.text((90, 40), "Total node reduction relative to baseline", fill="#0F172A", font=title)
    left, right, top, bottom = 260, width - 90, 130, height - 90
    draw.line((left, top, left, bottom), fill="#475569", width=2)
    draw.line((left, bottom, right, bottom), fill="#475569", width=2)
    max_value = max([1.0] + [float(item["node_reduction"]) for item in candidates])
    scale_max = max(10.0, math.ceil(max_value / 10) * 10)
    for tick in range(0, int(scale_max) + 1, 10):
        x = left + tick / scale_max * (right - left)
        draw.line((x, top, x, bottom), fill="#DCE3EA", width=1)
        draw.text((x - 12, bottom + 18), f"{tick}%", fill="#475569", font=small)
    bar_height = (bottom - top) / max(1, len(candidates)) * 0.62
    gap = (bottom - top) / max(1, len(candidates))
    colors = {"development": "#2563EB", "holdout": "#E11D48"}
    for index, item in enumerate(candidates):
        center = top + gap * (index + 0.5)
        value = float(item["node_reduction"])
        x = left + max(0.0, value) / scale_max * (right - left)
        draw.rectangle((left, center - bar_height / 2, x, center + bar_height / 2), fill=colors[str(item["split"])])
        draw.text((20, center - 13), f"{item['split']} / {item['method']}", fill="#0F172A", font=font)
        draw.text((x + 10, center - 12), f"{value:.1f}%", fill="#334155", font=font)
    image.save(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=PROJECT_ROOT / "generated_final_dataset")
    parser.add_argument("--out", type=Path, default=PROJECT_ROOT / "results" / "final")
    parser.add_argument("--splits", default="development,holdout")
    parser.add_argument("--methods", default=",".join(METHOD_ORDER))
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--max-bound-combinations", type=int, default=50_000)
    parser.add_argument("--restart", action="store_true")
    args = parser.parse_args()
    if args.warmup < 0 or args.repeats < 1:
        parser.error("warmup must be >= 0 and repeats must be >= 1")
    splits = tuple(item.strip() for item in args.splits.split(",") if item.strip())
    methods = tuple(item.strip() for item in args.methods.split(",") if item.strip())
    unknown = set(methods) - set(METHOD_ORDER)
    if unknown:
        parser.error(f"unknown methods: {sorted(unknown)}")

    manifest_path = args.dataset / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    verify_freeze(args.dataset, manifest)
    limits = manifest["config"]["exact_label_limits"]
    solvers = method_functions(
        max_nodes=int(limits["max_nodes"]),
        time_limit=float(limits["time_limit_seconds"]),
        max_bound_combinations=args.max_bound_combinations,
    )
    selected = [record for record in manifest["instances"] if record["split"] in splits]
    args.out.mkdir(parents=True, exist_ok=True)
    raw_path = args.out / "raw_results.csv"
    rows: list[dict[str, object]] = [] if args.restart else list(read_existing(raw_path))
    completed = {(str(row["instance_id"]), str(row["method"])) for row in rows}
    total = len(selected) * len(methods)
    done = sum((str(record["instance_id"]), method) in completed for record in selected for method in methods)
    print(f"freeze verified; {done}/{total} instance-method measurements already complete")

    for record in selected:
        level = load_discrete_level(args.dataset / record["file"])
        for method in methods:
            key = (str(record["instance_id"]), method)
            if key in completed:
                continue
            context = f"{record['instance_id']} / {method}"
            result, timings = run_method(
                level,
                solvers[method],
                expected=str(record["expected_status"]),
                context=context,
                warmup=args.warmup,
                repeats=args.repeats,
            )
            rows.append(result_row(record, method, result, timings))
            completed.add(key)
            done += 1
            write_rows(raw_path, rows)
            print(
                f"[{done}/{total}] {context}: {result.status.value}, "
                f"nodes={result.stats.nodes_expanded}, median={statistics.median(timings):.3f} ms",
                flush=True,
            )

    relevant = [
        row for row in rows if row["split"] in splits and row["method"] in methods
    ]
    if set(METHOD_ORDER).issubset(methods):
        aggregates = aggregate(relevant)
        write_aggregate(args.out / "aggregate_summary.csv", aggregates)
        completed_utc = datetime.now(timezone.utc).isoformat()
        run_info = {
            "completed_utc": completed_utc,
            "python": sys.version,
            "platform": platform.platform(),
            "processor": platform.processor(),
            "cpu_count": os.cpu_count(),
            "warmup": args.warmup,
            "repeats": args.repeats,
            "max_bound_combinations": args.max_bound_combinations,
            "splits": splits,
            "methods": methods,
            "manifest_sha256": sha256(manifest_path),
            "algorithm_hashes": manifest["freeze"]["algorithm_files"],
        }
        (args.out / "environment.json").write_text(
            json.dumps(run_info, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        write_summary(args.out / "summary.md", relevant, run_info)
        make_scatter(args.out / "nodes_scatter.png", relevant)
        make_reduction_bars(args.out / "node_reduction.png", relevant)
    print(f"evaluation complete: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
