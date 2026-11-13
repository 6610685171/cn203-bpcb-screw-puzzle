"""Auditable reconstruction of public ScrewJam level 1 from source formulas.

This is not a substitute for comparing against a Flutter export. It provides a
realistic, source-derived benchmark now: level 1's geometry, palette selection,
constructive color assignment, and box sequence do not consume random values.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from .model import Level
from .source_import import level_from_source_snapshot, preprocess_source_coverage


def _hole(hole_id: str, dx: float, dy: float) -> dict[str, Any]:
    return {"id": hole_id, "dx": dx, "dy": dy, "color": None}


def reconstruct_source_level_1_snapshot() -> tuple[dict[str, Any], tuple[str, ...]]:
    """Return the level-1 bridge snapshot and its constructive witness."""
    level_number = 1
    board_x = 180.0
    board_y = 250.0
    rows = 3
    cols = 3
    spacing = 56.0  # clamp(180 / (3 - 1), 38, 56)
    bar_length = 204.0  # clamp(3 * 56 + 36, 190, 250)
    plates: list[dict[str, Any]] = []

    for row in range(rows):
        y = board_y - (rows - 1) * spacing / 2 + row * spacing
        plates.append(
            {
                "id": f"lat_h_{row}",
                "shape_type": "linkBar4",
                "width": bar_length,
                "height": 34.0,
                "layer": row % 2,
                "order": len(plates),
                "x": board_x,
                "y": y,
                "angle": 0.0,
                "holes": [
                    _hole(f"lh_{row}_0", -75.0, 0.0),
                    _hole(f"lh_{row}_1", -25.0, 0.0),
                    _hole(f"lh_{row}_2", 25.0, 0.0),
                    _hole(f"lh_{row}_3", 75.0, 0.0),
                ],
            }
        )

    for column in range(cols):
        x = board_x - (cols - 1) * spacing / 2 + column * spacing
        plates.append(
            {
                "id": f"lat_v_{column}",
                "shape_type": "linkBar4",
                "width": 34.0,
                "height": bar_length,
                "layer": 2 + column % 2,
                "order": len(plates),
                "x": x,
                "y": board_y,
                "angle": 0.0,
                "holes": [
                    _hole(f"lv_{column}_0", 0.0, -75.0),
                    _hole(f"lv_{column}_1", 0.0, -25.0),
                    _hole(f"lv_{column}_2", 0.0, 25.0),
                    _hole(f"lv_{column}_3", 0.0, 75.0),
                ],
            }
        )

    # The source generator checks coverage before colors are assigned. The
    # snapshot preprocessor normally skips empty holes, so mark them briefly to
    # obtain the geometry-only relation and then clear the marker.
    for plate in plates:
        for hole in plate["holes"]:
            hole["color"] = "__unassigned__"
    initial_covers = preprocess_source_coverage(plates)
    for plate in plates:
        for hole in plate["holes"]:
            hole["color"] = None

    # The source's level-1 palette selection is deterministic:
    # first pink, then yellow, after indexed removals from allAvailableColors.
    palette = ("pink", "yellow")
    blockers: dict[str, set[str]] = {}
    for blocker_id, screw_id in initial_covers:
        blockers.setdefault(screw_id, set()).add(blocker_id)

    hole_by_id: dict[str, dict[str, Any]] = {}
    hole_plate: dict[str, str] = {}
    unassigned: list[str] = []
    for plate in plates:
        plate_id = str(plate["id"])
        for raw_hole in plate["holes"]:
            hole = raw_hole
            hole_id = str(hole["id"])
            hole_by_id[hole_id] = hole
            hole_plate[hole_id] = plate_id
            unassigned.append(hole_id)

    active_plate_ids = [str(plate["id"]) for plate in plates]
    boxes: list[dict[str, Any]] = []
    witness: list[str] = []
    color_index = 0

    while unassigned:
        chosen_color = palette[color_index % len(palette)]
        color_index += 1
        needed = min(3, len(unassigned))
        assigned_this_box = 0

        while needed > 0 and unassigned:
            active = set(active_plate_ids)
            exposed = [
                hole_id
                for hole_id in unassigned
                if blockers.get(hole_id, set()).isdisjoint(active)
            ]
            if not exposed:
                # The audited source has a highest-layer fallback. Level 1 does
                # not need it, so reaching this branch indicates reconstruction
                # drift and should fail loudly instead of silently diverging.
                raise RuntimeError("level-1 reconstruction found no exposed hole")

            counts = Counter(hole_plate[hole_id] for hole_id in unassigned)
            exposed.sort(key=lambda hole_id: counts[hole_plate[hole_id]])
            selected = exposed[0]
            hole_by_id[selected]["color"] = chosen_color
            unassigned.remove(selected)
            witness.append(selected)
            assigned_this_box += 1
            needed -= 1

            selected_plate = hole_plate[selected]
            if not any(hole_plate[hole_id] == selected_plate for hole_id in unassigned):
                active_plate_ids.remove(selected_plate)

        boxes.append(
            {"color": chosen_color, "capacity": assigned_this_box, "collected": []}
        )

    snapshot: dict[str, Any] = {
        "name": "Reconstructed ScrewJam level 1",
        "metadata": {
            "level": level_number,
            "source_commit": "5ee0b84970eba12d4fd7f937bae162bf75ba61f3",
            "reconstruction": True,
        },
        "waiting_capacity": 4,
        "plates": plates,
        "boxes": boxes,
    }
    return snapshot, tuple(witness)


def reconstruct_source_level_1() -> tuple[Level, tuple[str, ...]]:
    snapshot, witness = reconstruct_source_level_1_snapshot()
    return level_from_source_snapshot(snapshot), witness

