"""Export a deterministic range of ScrewJam runtime levels through Flutter.

The script executes the already-installed bridge test once per level, extracts
the marked JSON payload, validates its metadata, and writes a reproducible
snapshot into ``fixtures/``.  It does not modify the upstream checkout.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = PROJECT_ROOT.parents[1]
MARKER = "OSRP_SOURCE_SNAPSHOT:"


def _parse_levels(spec: str) -> tuple[int, ...]:
    levels: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_text, stop_text = part.split("-", 1)
            start, stop = int(start_text), int(stop_text)
            if start <= 0 or stop < start:
                raise ValueError(f"invalid level range: {part!r}")
            levels.update(range(start, stop + 1))
        else:
            level = int(part)
            if level <= 0:
                raise ValueError("levels must be positive")
            levels.add(level)
    if not levels:
        raise ValueError("no levels selected")
    return tuple(sorted(levels))


def _extract_snapshot(output: str) -> dict[str, object]:
    for line in output.splitlines():
        if MARKER in line:
            return json.loads(line.split(MARKER, 1)[1].strip())
    raise RuntimeError(f"snapshot marker {MARKER!r} was not found")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--levels", default="6-20")
    parser.add_argument("--waiting-capacity", type=int, default=4)
    parser.add_argument(
        "--seeds",
        help="optional comma/range list; omit to use each level's default seed",
    )
    parser.add_argument(
        "--flutter",
        type=Path,
        default=WORKSPACE_ROOT / "work" / "flutter" / "bin" / "flutter",
    )
    parser.add_argument(
        "--checkout", type=Path, default=Path("/private/tmp/cn203-screwjam")
    )
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "fixtures")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    try:
        levels = _parse_levels(args.levels)
        seeds = _parse_levels(args.seeds) if args.seeds else (None,)
    except ValueError as exc:
        parser.error(str(exc))
    if args.waiting_capacity < 0:
        parser.error("--waiting-capacity must be non-negative")
    if not args.flutter.is_file():
        parser.error(f"Flutter executable not found: {args.flutter}")
    bridge = args.checkout / "test" / "export_level_test.dart"
    if not bridge.is_file():
        parser.error(f"bridge test not found: {bridge}")

    args.output.mkdir(parents=True, exist_ok=True)
    for level in levels:
        for seed in seeds:
            suffix = "" if seed is None else f"_seed_{seed}"
            destination = args.output / f"flutter_source_level_{level}{suffix}.json"
            if destination.exists() and not args.overwrite:
                print(
                    f"skip level {level} seed={seed}: "
                    f"{destination.name} already exists"
                )
                continue
            command = [
                str(args.flutter),
                "--no-version-check",
                "--suppress-analytics",
                "test",
                "test/export_level_test.dart",
                f"--dart-define=LEVEL={level}",
                f"--dart-define=WAITING_CAPACITY={args.waiting_capacity}",
            ]
            if seed is not None:
                command.append(f"--dart-define=SEED={seed}")
            completed = subprocess.run(
                command,
                cwd=args.checkout,
                env={
                    **os.environ,
                    "CI": "true",
                    "DART_SUPPRESS_ANALYTICS": "true",
                    "FLUTTER_SUPPRESS_ANALYTICS": "true",
                },
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            if completed.returncode != 0:
                raise RuntimeError(
                    f"Flutter export failed for level {level}:\n{completed.stdout}"
                )
            snapshot = _extract_snapshot(completed.stdout)
            metadata = snapshot.get("metadata")
            if not isinstance(metadata, dict) or metadata.get("level") != level:
                raise RuntimeError(f"level {level}: malformed snapshot metadata")
            if metadata.get("seed") != seed:
                raise RuntimeError(f"level {level}: seed mismatch")
            if snapshot.get("waiting_capacity") != args.waiting_capacity:
                raise RuntimeError(f"level {level}: waiting-capacity mismatch")
            destination.write_text(
                json.dumps(snapshot, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            print(
                f"exported level {level} seed={seed}: "
                f"plates={len(snapshot['plates'])} "
                f"boxes={len(snapshot['boxes'])} "
                f"covers={len(snapshot['covers'])}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
