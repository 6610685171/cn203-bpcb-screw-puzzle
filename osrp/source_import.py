"""Import static ScrewJam snapshots and preprocess source-like coverage.

The bridge format mirrors the public Flutter models but is deliberately plain
JSON. Coverage uses the same 17 world-space sample points as the audited source.
Curved Flutter paths are evaluated with deterministic polygonal approximations;
an export may instead include an explicit ``covers`` list to bypass this step.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .model import Box, Level, Plate, Screw


class SourceSnapshotError(ValueError):
    pass


Point = tuple[float, float]


def _quadratic(p0: Point, p1: Point, p2: Point, steps: int = 24) -> list[Point]:
    points: list[Point] = []
    for i in range(1, steps + 1):
        t = i / steps
        u = 1.0 - t
        points.append(
            (
                u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0],
                u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1],
            )
        )
    return points


def _cubic(
    p0: Point, p1: Point, p2: Point, p3: Point, steps: int = 32
) -> list[Point]:
    points: list[Point] = []
    for i in range(1, steps + 1):
        t = i / steps
        u = 1.0 - t
        points.append(
            (
                u**3 * p0[0]
                + 3 * u * u * t * p1[0]
                + 3 * u * t * t * p2[0]
                + t**3 * p3[0],
                u**3 * p0[1]
                + 3 * u * u * t * p1[1]
                + 3 * u * t * t * p2[1]
                + t**3 * p3[1],
            )
        )
    return points


def _point_on_segment(point: Point, a: Point, b: Point, eps: float = 1e-8) -> bool:
    px, py = point
    ax, ay = a
    bx, by = b
    cross = (px - ax) * (by - ay) - (py - ay) * (bx - ax)
    if abs(cross) > eps:
        return False
    dot = (px - ax) * (px - bx) + (py - ay) * (py - by)
    return dot <= eps


def _point_in_polygon(point: Point, polygon: list[Point]) -> bool:
    if len(polygon) < 3:
        return False
    inside = False
    x, y = point
    previous = polygon[-1]
    for current in polygon:
        if _point_on_segment(point, previous, current):
            return True
        x1, y1 = previous
        x2, y2 = current
        if (y1 > y) != (y2 > y):
            crossing_x = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < crossing_x:
                inside = not inside
        previous = current
    return inside


def _in_ellipse(point: Point, cx: float, cy: float, width: float, height: float) -> bool:
    if width <= 0 or height <= 0:
        return False
    x, y = point
    return ((x - cx) / (width / 2)) ** 2 + ((y - cy) / (height / 2)) ** 2 <= 1.0 + 1e-12


def _in_rounded_rect(point: Point, width: float, height: float, radius: float) -> bool:
    x, y = map(abs, point)
    half_w = width / 2
    half_h = height / 2
    if x > half_w or y > half_h:
        return False
    radius = max(0.0, min(radius, half_w, half_h))
    dx = max(x - (half_w - radius), 0.0)
    dy = max(y - (half_h - radius), 0.0)
    return dx * dx + dy * dy <= radius * radius + 1e-12


def _ellipse_arc(
    width: float, height: float, start: float, sweep: float, steps: int = 40
) -> list[Point]:
    return [
        (
            width / 2 * math.cos(start + sweep * i / steps),
            height / 2 * math.sin(start + sweep * i / steps),
        )
        for i in range(steps + 1)
    ]


def _contains_local(shape: str, width: float, height: float, point: Point) -> bool:
    w = width
    h = height
    x, y = point

    if shape in {"linkBar2", "linkBar3", "linkBar4", "popsicleStick", "capsule"}:
        return _in_rounded_rect(point, w, h, min(w, h) / 2)

    if shape == "roundedRect":
        return _in_rounded_rect(point, w, h, 18.0)

    if shape in {"circle", "donut"}:
        return _in_ellipse(point, 0.0, 0.0, w, h)

    if shape == "iceCreamScoop":
        return _in_ellipse(point, 0.0, 0.0, w, h * 0.95)

    if shape == "flower":
        for i in range(6):
            angle = i * 2 * math.pi / 6
            cx = math.cos(angle) * w * 0.28
            cy = math.sin(angle) * h * 0.28
            if _in_ellipse(point, cx, cy, w * 0.45, h * 0.45):
                return True
        return _in_ellipse(point, 0.0, 0.0, w * 0.5, h * 0.5)

    polygon: list[Point]
    if shape == "lBracket":
        thick = min(w, h) * 0.36
        polygon = [
            (-w / 2, -h / 2),
            (-w / 2 + thick, -h / 2),
            (-w / 2 + thick, h / 2 - thick),
            (w / 2, h / 2 - thick),
            (w / 2, h / 2),
            (-w / 2, h / 2),
        ]
    elif shape == "tBracket":
        thick = min(w, h) * 0.34
        polygon = [
            (-w / 2, -h / 2),
            (w / 2, -h / 2),
            (w / 2, -h / 2 + thick),
            (thick / 2, -h / 2 + thick),
            (thick / 2, h / 2),
            (-thick / 2, h / 2),
            (-thick / 2, -h / 2 + thick),
            (-w / 2, -h / 2 + thick),
        ]
    elif shape == "uBracket":
        thick = min(w, h) * 0.32
        polygon = [
            (-w / 2, -h / 2),
            (-w / 2 + thick, -h / 2),
            (-w / 2 + thick, h / 2 - thick),
            (w / 2 - thick, h / 2 - thick),
            (w / 2 - thick, -h / 2),
            (w / 2, -h / 2),
            (w / 2, h / 2),
            (-w / 2, h / 2),
        ]
    elif shape == "cogwheel":
        polygon = []
        for i in range(16):
            angle = i * math.pi / 8 - math.pi / 2
            radius = w / 2 if i % 2 == 0 else w / 2 * 0.76
            polygon.append((radius * math.cos(angle), radius * math.sin(angle)))
    elif shape == "star":
        polygon = []
        for i in range(10):
            radius = w / 2 if i % 2 == 0 else w / 2 * 0.58
            angle = i * math.pi / 5 - math.pi / 2
            polygon.append((radius * math.cos(angle), radius * math.sin(angle)))
    elif shape == "crossBar":
        bw = w * 0.35
        bh = h * 0.35
        polygon = [
            (-w / 2, -bh / 2),
            (-bw / 2, -bh / 2),
            (-bw / 2, -h / 2),
            (bw / 2, -h / 2),
            (bw / 2, -bh / 2),
            (w / 2, -bh / 2),
            (w / 2, bh / 2),
            (bw / 2, bh / 2),
            (bw / 2, h / 2),
            (-bw / 2, h / 2),
            (-bw / 2, bh / 2),
            (-w / 2, bh / 2),
        ]
    elif shape == "triangle":
        polygon = [(0, -h * 0.48), (w * 0.48, h * 0.48), (-w * 0.48, h * 0.48)]
    elif shape == "curvedArc":
        polygon = _ellipse_arc(w, h, -math.pi * 0.95, math.pi * 0.90)
        polygon.extend(
            _ellipse_arc(w * 0.65, h * 0.65, -math.pi * 0.05, -math.pi * 0.90)
        )
    elif shape == "iceCreamCone":
        start = (0.0, h * 0.52)
        edge = (w * 0.5, -h * 0.42)
        polygon = [start, edge]
        polygon.extend(
            _quadratic(edge, (0.0, -h * 0.48), (-w * 0.5, -h * 0.42))
        )
    elif shape in {"iceCreamScoopLeft", "iceCreamScoopRight"}:
        start = (-w * 0.48, 0.0)
        polygon = [start]
        current = start
        segments = [
            ((-w * 0.48, -h * 0.48), (0.0, -h * 0.48)),
            ((w * 0.48, -h * 0.48), (w * 0.48, 0.0)),
            ((w * 0.35, h * 0.48), (w * 0.18, h * 0.25)),
            ((0.0, h * 0.52), (-w * 0.18, h * 0.25)),
            ((-w * 0.35, h * 0.48), (-w * 0.48, 0.0)),
        ]
        for control, end in segments:
            polygon.extend(_quadratic(current, control, end))
            current = end
    elif shape == "heart":
        start = (0.0, h * 0.35)
        middle = (0.0, -h * 0.25)
        polygon = [start]
        polygon.extend(
            _cubic(
                start,
                (-w * 0.55, -h * 0.1),
                (-w * 0.45, -h * 0.45),
                middle,
            )
        )
        polygon.extend(
            _cubic(
                middle,
                (w * 0.45, -h * 0.45),
                (w * 0.55, -h * 0.1),
                start,
            )
        )
    else:
        raise SourceSnapshotError(f"unsupported source shape {shape!r}")

    return _point_in_polygon((x, y), polygon)


def _as_float(record: Mapping[str, Any], key: str) -> float:
    value = record.get(key)
    if not isinstance(value, (int, float)):
        raise SourceSnapshotError(f"{key!r} must be numeric")
    return float(value)


def _global_hole_position(plate: Mapping[str, Any], hole: Mapping[str, Any]) -> Point:
    angle = _as_float(plate, "angle")
    dx = _as_float(hole, "dx")
    dy = _as_float(hole, "dy")
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    return (
        _as_float(plate, "x") + dx * cos_a - dy * sin_a,
        _as_float(plate, "y") + dx * sin_a + dy * cos_a,
    )


def _point_inside_source_plate(point: Point, plate: Mapping[str, Any]) -> bool:
    rel_x = point[0] - _as_float(plate, "x")
    rel_y = point[1] - _as_float(plate, "y")
    angle = -_as_float(plate, "angle")
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    local = (
        rel_x * cos_a - rel_y * sin_a,
        rel_x * sin_a + rel_y * cos_a,
    )
    shape = plate.get("shape_type")
    if not isinstance(shape, str):
        raise SourceSnapshotError("shape_type must be a string")
    return _contains_local(
        shape,
        _as_float(plate, "width"),
        _as_float(plate, "height"),
        local,
    )


def _sample_offsets(radius: float = 15.0) -> tuple[Point, ...]:
    offsets: list[Point] = [(0.0, 0.0)]
    for i in range(8):
        angle = i * math.pi / 4
        offsets.append((math.cos(angle) * radius, math.sin(angle) * radius))
        offsets.append(
            (math.cos(angle) * radius * 0.65, math.sin(angle) * radius * 0.65)
        )
    return tuple(offsets)


def preprocess_source_coverage(
    source_plates: list[Mapping[str, Any]],
) -> frozenset[tuple[str, str]]:
    """Compute source-like ``(blocker plate, target screw)`` pairs."""
    covers: set[tuple[str, str]] = set()
    offsets = _sample_offsets()

    for target_index, target_plate in enumerate(source_plates):
        target_id = target_plate.get("id")
        if not isinstance(target_id, str):
            raise SourceSnapshotError("plate id must be a string")
        target_layer = int(target_plate.get("layer"))
        holes = target_plate.get("holes")
        if not isinstance(holes, list):
            raise SourceSnapshotError(f"plate {target_id!r} holes must be a list")

        for hole in holes:
            if not isinstance(hole, Mapping) or hole.get("color") is None:
                continue
            hole_id = hole.get("id")
            if not isinstance(hole_id, str):
                raise SourceSnapshotError("hole id must be a string")
            global_pos = _global_hole_position(target_plate, hole)

            for blocker_index, blocker in enumerate(source_plates):
                blocker_id = blocker.get("id")
                if not isinstance(blocker_id, str):
                    raise SourceSnapshotError("plate id must be a string")
                if blocker_id == target_id:
                    continue
                blocker_layer = int(blocker.get("layer"))
                is_higher = blocker_layer > target_layer or (
                    blocker_layer == target_layer and blocker_index > target_index
                )
                if not is_higher:
                    continue
                if any(
                    _point_inside_source_plate(
                        (global_pos[0] + offset[0], global_pos[1] + offset[1]),
                        blocker,
                    )
                    for offset in offsets
                ):
                    covers.add((blocker_id, hole_id))

    return frozenset(covers)


def _load_payload(source: str | Path | Mapping[str, Any]) -> Mapping[str, Any]:
    if isinstance(source, Mapping):
        return source
    path = Path(source)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SourceSnapshotError(f"cannot read source snapshot {path}: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise SourceSnapshotError("snapshot root must be a JSON object")
    return payload


def level_from_source_snapshot(
    source: str | Path | Mapping[str, Any],
    *,
    trust_precomputed_coverage: bool = True,
) -> Level:
    """Convert a Flutter bridge snapshot to the immutable OSRP model."""
    payload = _load_payload(source)
    source_plates_raw = payload.get("plates")
    source_boxes_raw = payload.get("boxes")
    if not isinstance(source_plates_raw, list) or not isinstance(source_boxes_raw, list):
        raise SourceSnapshotError("snapshot needs list fields 'plates' and 'boxes'")

    source_plates: list[Mapping[str, Any]] = []
    for plate in source_plates_raw:
        if not isinstance(plate, Mapping):
            raise SourceSnapshotError("every plate must be a JSON object")
        source_plates.append(plate)

    screws: list[Screw] = []
    nonempty_plate_ids: set[str] = set()
    for plate in source_plates:
        plate_id = plate.get("id")
        holes = plate.get("holes")
        if not isinstance(plate_id, str) or not isinstance(holes, list):
            raise SourceSnapshotError("each plate needs a string id and a holes list")
        for hole in holes:
            if not isinstance(hole, Mapping):
                raise SourceSnapshotError("every hole must be a JSON object")
            color = hole.get("color")
            if color is None:
                continue
            hole_id = hole.get("id")
            if not isinstance(hole_id, str) or not isinstance(color, str):
                raise SourceSnapshotError("colored holes need string id and color")
            screws.append(Screw(hole_id, plate_id, color))
            nonempty_plate_ids.add(plate_id)

    retained_source_plates = [
        plate for plate in source_plates if plate.get("id") in nonempty_plate_ids
    ]
    plates = tuple(
        Plate(str(plate["id"]), int(plate["layer"]), order)
        for order, plate in enumerate(retained_source_plates)
    )

    boxes: list[Box] = []
    for record in source_boxes_raw:
        if not isinstance(record, Mapping):
            raise SourceSnapshotError("every box must be a JSON object")
        collected = record.get("collected", [])
        if collected:
            raise SourceSnapshotError("only initial snapshots with empty boxes are supported")
        color = record.get("color")
        capacity = record.get("capacity")
        if not isinstance(color, str) or not isinstance(capacity, int):
            raise SourceSnapshotError("box color must be string and capacity integer")
        boxes.append(Box(color, capacity))

    explicit_covers = payload.get("covers")
    if trust_precomputed_coverage and isinstance(explicit_covers, list):
        covers = frozenset(
            (str(record["plate_id"]), str(record["screw_id"]))
            for record in explicit_covers
        )
    else:
        covers = preprocess_source_coverage(retained_source_plates)

    name = payload.get("name", "ScrewJam source snapshot")
    waiting_capacity = payload.get("waiting_capacity")
    if not isinstance(name, str) or not isinstance(waiting_capacity, int):
        raise SourceSnapshotError("name must be string and waiting_capacity integer")

    return Level(
        name=name,
        screws=tuple(screws),
        plates=plates,
        boxes=tuple(boxes),
        waiting_capacity=waiting_capacity,
        covers=covers,
    )


def level_to_json_dict(level: Level) -> dict[str, Any]:
    return {
        "format": "osrp-level-v1",
        "name": level.name,
        "waiting_capacity": level.waiting_capacity,
        "plates": [
            {"id": plate.id, "layer": plate.layer, "order": plate.order}
            for plate in level.plates
        ],
        "screws": [
            {"id": screw.id, "plate_id": screw.plate_id, "color": screw.color}
            for screw in level.screws
        ],
        "boxes": [
            {"color": box.color, "capacity": box.capacity} for box in level.boxes
        ],
        "covers": [
            {"plate_id": plate_id, "screw_id": screw_id}
            for plate_id, screw_id in sorted(level.covers)
        ],
    }


def save_discrete_level(level: Level, destination: str | Path) -> None:
    Path(destination).write_text(
        json.dumps(level_to_json_dict(level), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def load_discrete_level(source: str | Path | Mapping[str, Any]) -> Level:
    payload = _load_payload(source)
    if payload.get("format") != "osrp-level-v1":
        raise SourceSnapshotError("unsupported or missing discrete level format")
    plates_raw = payload.get("plates")
    screws_raw = payload.get("screws")
    boxes_raw = payload.get("boxes")
    covers_raw = payload.get("covers", [])
    if not all(isinstance(value, list) for value in (plates_raw, screws_raw, boxes_raw, covers_raw)):
        raise SourceSnapshotError("malformed discrete level lists")
    return Level(
        name=str(payload["name"]),
        plates=tuple(
            Plate(str(p["id"]), int(p["layer"]), int(p["order"]))
            for p in plates_raw
        ),
        screws=tuple(
            Screw(str(s["id"]), str(s["plate_id"]), str(s["color"]))
            for s in screws_raw
        ),
        boxes=tuple(Box(str(b["color"]), int(b["capacity"])) for b in boxes_raw),
        waiting_capacity=int(payload["waiting_capacity"]),
        covers=frozenset(
            (str(c["plate_id"]), str(c["screw_id"])) for c in covers_raw
        ),
    )

