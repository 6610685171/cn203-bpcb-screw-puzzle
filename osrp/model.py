"""Immutable data model for the discrete Ordered Screw-Removal Puzzle."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Iterable, Mapping


Color = str
ScrewId = str
PlateId = str
Tray = tuple[tuple[Color, int], ...]


class InvalidLevel(ValueError):
    """Raised when a level violates the formal input invariants."""


class InvalidState(ValueError):
    """Raised when a state is inconsistent with its level."""


@dataclass(frozen=True, slots=True)
class Screw:
    id: ScrewId
    plate_id: PlateId
    color: Color

    def __post_init__(self) -> None:
        if not self.id:
            raise InvalidLevel("screw id must not be empty")
        if not self.plate_id:
            raise InvalidLevel(f"screw {self.id!r} has an empty plate id")
        if not self.color:
            raise InvalidLevel(f"screw {self.id!r} has an empty color")


@dataclass(frozen=True, slots=True)
class Plate:
    id: PlateId
    layer: int
    order: int

    def __post_init__(self) -> None:
        if not self.id:
            raise InvalidLevel("plate id must not be empty")

    @property
    def height_key(self) -> tuple[int, int]:
        """Higher layer wins; order breaks ties within the same layer."""
        return (self.layer, self.order)


@dataclass(frozen=True, slots=True)
class Box:
    color: Color
    capacity: int = 3

    def __post_init__(self) -> None:
        if not self.color:
            raise InvalidLevel("box color must not be empty")
        if self.capacity <= 0:
            raise InvalidLevel("box capacity must be positive")


@dataclass(frozen=True, slots=True)
class Level:
    """A geometry-independent level after coverage preprocessing.

    ``covers`` contains pairs ``(blocking_plate_id, target_screw_id)``.
    Only a plate that is strictly higher than the target screw's owner may
    appear as a blocker.
    """

    name: str
    screws: tuple[Screw, ...]
    plates: tuple[Plate, ...]
    boxes: tuple[Box, ...]
    waiting_capacity: int
    covers: frozenset[tuple[PlateId, ScrewId]] = frozenset()
    _screw_lookup: Mapping[ScrewId, Screw] = field(
        init=False, repr=False, compare=False, hash=False
    )
    _plate_lookup: Mapping[PlateId, Plate] = field(
        init=False, repr=False, compare=False, hash=False
    )
    _screws_on_plate: Mapping[PlateId, frozenset[ScrewId]] = field(
        init=False, repr=False, compare=False, hash=False
    )
    _blockers_of_screw: Mapping[ScrewId, frozenset[PlateId]] = field(
        init=False, repr=False, compare=False, hash=False
    )

    def __post_init__(self) -> None:
        if not self.name:
            raise InvalidLevel("level name must not be empty")
        if self.waiting_capacity < 0:
            raise InvalidLevel("waiting capacity must be non-negative")
        if not self.screws:
            raise InvalidLevel("a level must contain at least one screw")
        if not self.plates:
            raise InvalidLevel("a level must contain at least one plate")
        if not self.boxes:
            raise InvalidLevel("a level must contain at least one box")

        screw_ids = [s.id for s in self.screws]
        if len(screw_ids) != len(set(screw_ids)):
            raise InvalidLevel("screw ids must be unique")

        plate_ids = [p.id for p in self.plates]
        if len(plate_ids) != len(set(plate_ids)):
            raise InvalidLevel("plate ids must be unique")

        heights = [p.height_key for p in self.plates]
        if len(heights) != len(set(heights)):
            raise InvalidLevel("each plate must have a unique (layer, order) pair")

        plate_map = {p.id: p for p in self.plates}
        screw_map = {s.id: s for s in self.screws}

        screws_per_plate: Counter[PlateId] = Counter()
        for screw in self.screws:
            if screw.plate_id not in plate_map:
                raise InvalidLevel(
                    f"screw {screw.id!r} references unknown plate {screw.plate_id!r}"
                )
            screws_per_plate[screw.plate_id] += 1

        empty_plates = [p.id for p in self.plates if screws_per_plate[p.id] == 0]
        if empty_plates:
            raise InvalidLevel(
                "plates must initially contain a screw; empty plates: "
                + ", ".join(sorted(empty_plates))
            )

        for blocker_id, target_id in self.covers:
            if blocker_id not in plate_map:
                raise InvalidLevel(f"coverage references unknown plate {blocker_id!r}")
            if target_id not in screw_map:
                raise InvalidLevel(f"coverage references unknown screw {target_id!r}")

            blocker = plate_map[blocker_id]
            owner = plate_map[screw_map[target_id].plate_id]
            if blocker.height_key <= owner.height_key:
                raise InvalidLevel(
                    f"plate {blocker_id!r} cannot cover {target_id!r}: "
                    "the blocker is not strictly higher"
                )

        screw_colors = Counter(s.color for s in self.screws)
        box_colors: Counter[Color] = Counter()
        for box in self.boxes:
            box_colors[box.color] += box.capacity
        if screw_colors != box_colors:
            raise InvalidLevel(
                "color conservation failed: "
                f"screws={dict(screw_colors)}, boxes={dict(box_colors)}"
            )

        screw_sets: dict[PlateId, set[ScrewId]] = {
            plate.id: set() for plate in self.plates
        }
        for screw in self.screws:
            screw_sets[screw.plate_id].add(screw.id)
        blocker_sets: dict[ScrewId, set[PlateId]] = {
            screw.id: set() for screw in self.screws
        }
        for blocker_id, target_id in self.covers:
            blocker_sets[target_id].add(blocker_id)

        object.__setattr__(self, "_screw_lookup", MappingProxyType(screw_map))
        object.__setattr__(self, "_plate_lookup", MappingProxyType(plate_map))
        object.__setattr__(
            self,
            "_screws_on_plate",
            MappingProxyType(
                {plate_id: frozenset(ids) for plate_id, ids in screw_sets.items()}
            ),
        )
        object.__setattr__(
            self,
            "_blockers_of_screw",
            MappingProxyType(
                {
                    screw_id: frozenset(ids)
                    for screw_id, ids in blocker_sets.items()
                }
            ),
        )

    def screw_map(self) -> Mapping[ScrewId, Screw]:
        return self._screw_lookup

    def plate_map(self) -> Mapping[PlateId, Plate]:
        return self._plate_lookup

    def screws_by_plate(self) -> Mapping[PlateId, frozenset[ScrewId]]:
        return self._screws_on_plate

    def blockers_by_screw(self) -> Mapping[ScrewId, frozenset[PlateId]]:
        return self._blockers_of_screw


def canonical_tray(values: Mapping[Color, int] | Iterable[Color] = ()) -> Tray:
    """Return the canonical, hashable multiset representation of a tray."""
    if isinstance(values, Mapping):
        counts = Counter(values)
    else:
        counts = Counter(values)

    for color, count in counts.items():
        if not color:
            raise InvalidState("tray colors must not be empty")
        if count < 0:
            raise InvalidState(f"negative tray count for color {color!r}")

    return tuple(sorted((color, count) for color, count in counts.items() if count))


def tray_counter(tray: Tray) -> Counter[Color]:
    return Counter(dict(tray))


@dataclass(frozen=True, slots=True)
class State:
    remaining: frozenset[ScrewId]
    box_index: int
    box_fill: int
    tray: Tray = ()

    def __post_init__(self) -> None:
        if self.box_index < 0:
            raise InvalidState("box index must be non-negative")
        if self.box_fill < 0:
            raise InvalidState("box fill must be non-negative")
        if self.tray != canonical_tray(dict(self.tray)):
            raise InvalidState("tray must be sorted, unique, positive, and canonical")

    @property
    def tray_size(self) -> int:
        return sum(count for _, count in self.tray)

