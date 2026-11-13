"""Deterministic transition rules and solution validation for OSRP."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Iterable

from .model import (
    Color,
    InvalidState,
    Level,
    ScrewId,
    State,
    canonical_tray,
    tray_counter,
)


class RuleViolation(ValueError):
    """Base class for an illegal puzzle action."""


class UnknownOrRemovedScrew(RuleViolation):
    pass


class CoveredScrew(RuleViolation):
    pass


class TrayOverflow(RuleViolation):
    pass


class GameAlreadyWon(RuleViolation):
    pass


@dataclass(frozen=True, slots=True)
class ValidationResult:
    legal: bool
    won: bool
    steps_applied: int
    final_state: State
    message: str

    @property
    def valid_solution(self) -> bool:
        return self.legal and self.won


def initial_state(level: Level) -> State:
    state = State(
        remaining=frozenset(s.id for s in level.screws),
        box_index=0,
        box_fill=0,
        tray=(),
    )
    validate_state(level, state)
    return state


def _active_plates(level: Level, state: State) -> frozenset[str]:
    screw_map = level.screw_map()
    return frozenset(screw_map[screw_id].plate_id for screw_id in state.remaining)


def validate_state(level: Level, state: State) -> None:
    screw_map = level.screw_map()
    all_screws = frozenset(screw_map)
    if not state.remaining <= all_screws:
        unknown = sorted(state.remaining - all_screws)
        raise InvalidState(f"state contains unknown screws: {unknown}")

    if state.box_index >= len(level.boxes):
        raise InvalidState("box index is outside the box sequence")

    active_box = level.boxes[state.box_index]
    if state.box_fill > active_box.capacity:
        raise InvalidState("active box is over capacity")

    tray = tray_counter(state.tray)
    if sum(tray.values()) > level.waiting_capacity:
        raise InvalidState("tray exceeds waiting capacity")

    known_colors = {s.color for s in level.screws}
    unknown_colors = set(tray) - known_colors
    if unknown_colors:
        raise InvalidState(f"tray contains unknown colors: {sorted(unknown_colors)}")

    # Conservation across remaining screws, completed boxes, active-box fill,
    # and waiting tray catches malformed hand-built states early.
    accounted: Counter[Color] = Counter(screw_map[s].color for s in state.remaining)
    accounted.update(tray)
    for box in level.boxes[: state.box_index]:
        accounted[box.color] += box.capacity
    accounted[active_box.color] += state.box_fill

    expected = Counter(s.color for s in level.screws)
    if accounted != expected:
        raise InvalidState(
            "state violates color conservation: "
            f"accounted={dict(accounted)}, expected={dict(expected)}"
        )


def normalize(level: Level, state: State) -> State:
    """Auto-drain matching tray screws and advance boxes to a fixed point."""
    validate_state(level, state)
    box_index = state.box_index
    box_fill = state.box_fill
    tray = tray_counter(state.tray)

    while True:
        box = level.boxes[box_index]
        available = tray[box.color]
        if available and box_fill < box.capacity:
            moved = min(available, box.capacity - box_fill)
            tray[box.color] -= moved
            box_fill += moved
            if tray[box.color] == 0:
                del tray[box.color]

        if box_fill == box.capacity and box_index + 1 < len(level.boxes):
            box_index += 1
            box_fill = 0
            continue
        break

    result = State(
        remaining=state.remaining,
        box_index=box_index,
        box_fill=box_fill,
        tray=canonical_tray(tray),
    )
    validate_state(level, result)
    return result


def is_goal(level: Level, state: State) -> bool:
    validate_state(level, state)
    return not state.remaining and state.tray_size == 0


def is_accessible(level: Level, state: State, screw_id: ScrewId) -> bool:
    validate_state(level, state)
    if screw_id not in state.remaining:
        return False
    active_plates = _active_plates(level, state)
    blockers = level.blockers_by_screw()[screw_id]
    return blockers.isdisjoint(active_plates)


def accessible_screws(level: Level, state: State) -> tuple[ScrewId, ...]:
    validate_state(level, state)
    active_plates = _active_plates(level, state)
    blockers = level.blockers_by_screw()
    return tuple(
        sorted(
            screw_id
            for screw_id in state.remaining
            if blockers[screw_id].isdisjoint(active_plates)
        )
    )


def _can_route_without_overflow(level: Level, state: State, screw_id: ScrewId) -> bool:
    screw = level.screw_map()[screw_id]
    box = level.boxes[state.box_index]
    goes_directly = screw.color == box.color and state.box_fill < box.capacity
    return goes_directly or state.tray_size < level.waiting_capacity


def legal_moves(level: Level, state: State) -> tuple[ScrewId, ...]:
    state = normalize(level, state)
    if is_goal(level, state):
        return ()
    return tuple(
        screw_id
        for screw_id in accessible_screws(level, state)
        if _can_route_without_overflow(level, state, screw_id)
    )


def apply_move(level: Level, state: State, screw_id: ScrewId) -> State:
    """Apply one screw removal, then normalize all automatic box actions."""
    state = normalize(level, state)
    if is_goal(level, state):
        raise GameAlreadyWon("cannot move after the goal state")
    if screw_id not in state.remaining:
        raise UnknownOrRemovedScrew(f"screw {screw_id!r} is unknown or already removed")
    if not is_accessible(level, state, screw_id):
        raise CoveredScrew(f"screw {screw_id!r} is covered by an active higher plate")

    screw = level.screw_map()[screw_id]
    box = level.boxes[state.box_index]
    remaining = state.remaining - {screw_id}
    tray = tray_counter(state.tray)
    box_fill = state.box_fill

    if screw.color == box.color and box_fill < box.capacity:
        box_fill += 1
    else:
        if state.tray_size >= level.waiting_capacity:
            raise TrayOverflow(
                f"screw {screw_id!r} cannot enter the full waiting tray"
            )
        tray[screw.color] += 1

    next_state = State(
        remaining=frozenset(remaining),
        box_index=state.box_index,
        box_fill=box_fill,
        tray=canonical_tray(tray),
    )
    return normalize(level, next_state)


def validate_solution(level: Level, sequence: Iterable[ScrewId]) -> ValidationResult:
    """Replay a proposed solution and report the first violation, if any."""
    state = initial_state(level)
    steps = 0
    for screw_id in sequence:
        try:
            state = apply_move(level, state, screw_id)
        except (RuleViolation, InvalidState) as exc:
            return ValidationResult(
                legal=False,
                won=False,
                steps_applied=steps,
                final_state=state,
                message=f"step {steps + 1}: {exc}",
            )
        steps += 1

    won = is_goal(level, state)
    return ValidationResult(
        legal=True,
        won=won,
        steps_applied=steps,
        final_state=state,
        message="valid solution" if won else "legal prefix, but the goal was not reached",
    )

