"""Extract the marked JSON snapshot from Flutter test output on stdin."""

from __future__ import annotations

import json
import sys


MARKER = "OSRP_SOURCE_SNAPSHOT:"


def main() -> int:
    parsed = None
    for line in sys.stdin:
        if MARKER in line and parsed is None:
            payload = line.split(MARKER, 1)[1].strip()
            parsed = json.loads(payload)
    if parsed is None:
        print(f"snapshot marker {MARKER!r} was not found", file=sys.stderr)
        return 1
    json.dump(parsed, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

