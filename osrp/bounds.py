"""Provably safe box-prefix blocker-closure bounds."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from itertools import combinations, product
from types import MappingProxyType
from typing import Mapping

from .model import Level, ScrewId, State
from .simulator import normalize


@dataclass(frozen=True, slots=True)
class BPCB1Result:
    active_color: str
    screws_needed: int
    candidate_screws: int
    combinations_evaluated: int
    forced_off_color_lower_bound: int
    existing_tray_occupancy: int
    required_waiting_capacity_lower_bound: int
    shortage: bool
    prunable: bool


@dataclass(frozen=True, slots=True)
class BPCBPrefixResult:
    requested_prefix_length: int
    actual_prefix_length: int
    prefix_colors: tuple[str, ...]
    board_requirements: tuple[tuple[str, int], ...]
    candidate_combinations: int
    combinations_evaluated: int
    skipped_for_combination_limit: bool
    forced_off_prefix_lower_bound: int
    persistent_tray_occupancy: int
    required_waiting_capacity_lower_bound: int
    shortage: bool
    prunable: bool


@dataclass(frozen=True, slots=True)
class _BoundIndex:
    screw_ids: tuple[ScrewId, ...]
    screw_to_index: Mapping[ScrewId, int]
    color_masks: Mapping[str, int]
    blocker_plate_masks: tuple[tuple[int, ...], ...]


@lru_cache(maxsize=None)
def _bound_index(level: Level) -> _BoundIndex:
    screw_ids = tuple(screw.id for screw in level.screws)
    screw_to_index = {screw_id: i for i, screw_id in enumerate(screw_ids)}
    plate_masks: dict[str, int] = {plate.id: 0 for plate in level.plates}
    color_masks: dict[str, int] = {}
    for index, screw in enumerate(level.screws):
        bit = 1 << index
        plate_masks[screw.plate_id] |= bit
        color_masks[screw.color] = color_masks.get(screw.color, 0) | bit

    blockers = level.blockers_by_screw()
    blocker_plate_masks = tuple(
        tuple(plate_masks[plate_id] for plate_id in blockers[screw_id])
        for screw_id in screw_ids
    )
    return _BoundIndex(
        screw_ids=screw_ids,
        screw_to_index=MappingProxyType(screw_to_index),
        color_masks=MappingProxyType(color_masks),
        blocker_plate_masks=blocker_plate_masks,
    )


def _remaining_mask(index: _BoundIndex, state: State) -> int:
    mask = 0
    for screw_id in state.remaining:
        mask |= 1 << index.screw_to_index[screw_id]
    return mask


def _closure_mask(index: _BoundIndex, remaining_mask: int, target_index: int) -> int:
    required = 0
    expanded = 0
    stack = [target_index]
    while stack:
        screw_index = stack.pop()
        screw_bit = 1 << screw_index
        if expanded & screw_bit:
            continue
        expanded |= screw_bit
        for plate_mask in index.blocker_plate_masks[screw_index]:
            active_screws = plate_mask & remaining_mask
            if not active_screws:
                continue
            required |= active_screws
            pending = active_screws
            while pending:
                least_bit = pending & -pending
                stack.append(least_bit.bit_length() - 1)
                pending ^= least_bit
    return required


def recursive_blocker_closure(
    level: Level, state: State, targets: tuple[ScrewId, ...]
) -> frozenset[ScrewId]:
    """Remaining screws that must be removed before all targets can be removed.

    If an active plate blocks a target, every remaining screw on that plate has
    to be removed. Accessing those screws may recursively require higher plates
    to be emptied. Targets themselves are removed from the returned set; if one
    target is a blocker required by another, it is still represented by the
    caller's target set and does not affect the off-color count.
    """
    state = normalize(level, state)
    screws_by_plate = level.screws_by_plate()
    blockers_by_screw = level.blockers_by_screw()
    screw_map = level.screw_map()
    active_plates = {
        screw_map[screw_id].plate_id for screw_id in state.remaining
    }
    target_set = set(targets)
    required: set[ScrewId] = set()
    expanded_screws: set[ScrewId] = set()

    def expand_access(screw_id: ScrewId) -> None:
        if screw_id in expanded_screws:
            return
        expanded_screws.add(screw_id)
        for blocker_plate in blockers_by_screw[screw_id]:
            if blocker_plate not in active_plates:
                continue
            for blocker_screw in screws_by_plate[blocker_plate] & state.remaining:
                if blocker_screw not in target_set:
                    required.add(blocker_screw)
                expand_access(blocker_screw)

    for target in targets:
        if target not in state.remaining:
            raise ValueError(f"target screw {target!r} is not remaining")
        expand_access(target)
    return frozenset(required)


def box_prefix_one_bound(level: Level, state: State) -> BPCB1Result:
    """Lower-bound tray space forced before the current box can complete.

    For every possible set of current-color screws that could finish the active
    box, compute its recursive blocker closure. Off-color closure screws cannot
    enter the active box and therefore remain simultaneously in the tray until
    that box completes. The minimum over all candidate sets is a safe lower
    bound for every continuation.
    """
    state = normalize(level, state)
    active_box = level.boxes[state.box_index]
    needed = active_box.capacity - state.box_fill
    index = _bound_index(level)
    remaining_mask = _remaining_mask(index, state)
    active_color_mask = index.color_masks.get(active_box.color, 0)
    candidate_mask = remaining_mask & active_color_mask
    candidate_indices: list[int] = []
    pending_candidates = candidate_mask
    while pending_candidates:
        least_bit = pending_candidates & -pending_candidates
        candidate_indices.append(least_bit.bit_length() - 1)
        pending_candidates ^= least_bit
    candidates = tuple(index.screw_ids[i] for i in candidate_indices)

    if needed <= 0:
        required = state.tray_size
        return BPCB1Result(
            active_color=active_box.color,
            screws_needed=0,
            candidate_screws=len(candidates),
            combinations_evaluated=0,
            forced_off_color_lower_bound=0,
            existing_tray_occupancy=state.tray_size,
            required_waiting_capacity_lower_bound=required,
            shortage=False,
            prunable=required > level.waiting_capacity,
        )

    if len(candidates) < needed:
        return BPCB1Result(
            active_color=active_box.color,
            screws_needed=needed,
            candidate_screws=len(candidates),
            combinations_evaluated=0,
            forced_off_color_lower_bound=0,
            existing_tray_occupancy=state.tray_size,
            required_waiting_capacity_lower_bound=state.tray_size,
            shortage=True,
            prunable=True,
        )

    # Closure is distributive over a target set under the static blocker model.
    # Compute each candidate's off-color closure once, then union those cached
    # sets for each small target combination (box capacity is usually three).
    off_color_closure_masks: dict[int, int] = {}
    for candidate_index in candidate_indices:
        closure = _closure_mask(index, remaining_mask, candidate_index)
        off_color_closure_masks[candidate_index] = closure & ~active_color_mask

    best: int | None = None
    evaluated = 0
    for targets in combinations(candidate_indices, needed):
        evaluated += 1
        forced_mask = 0
        for target in targets:
            forced_mask |= off_color_closure_masks[target]
        off_color = forced_mask.bit_count()
        if best is None or off_color < best:
            best = off_color
            if best == 0:
                break

    lower_bound = 0 if best is None else best
    required = state.tray_size + lower_bound
    return BPCB1Result(
        active_color=active_box.color,
        screws_needed=needed,
        candidate_screws=len(candidates),
        combinations_evaluated=evaluated,
        forced_off_color_lower_bound=lower_bound,
        existing_tray_occupancy=state.tray_size,
        required_waiting_capacity_lower_bound=required,
        shortage=False,
        prunable=required > level.waiting_capacity,
    )


def box_prefix_bound(
    level: Level,
    state: State,
    *,
    prefix_length: int,
    max_combinations: int = 50_000,
) -> BPCBPrefixResult:
    """Safe persistent-storage bound across a prefix of ordered boxes.

    Only screws whose colors are absent from the whole prefix are counted in
    the closure lower bound. Such screws cannot drain before the prefix ends.
    If exact target-set enumeration would exceed ``max_combinations``, the
    function returns the weaker tray-only bound instead of risking an unsafe
    approximation.
    """
    if prefix_length <= 0:
        raise ValueError("prefix_length must be positive")
    if max_combinations <= 0:
        raise ValueError("max_combinations must be positive")

    state = normalize(level, state)
    stop = min(len(level.boxes), state.box_index + prefix_length)
    prefix = level.boxes[state.box_index : stop]
    demands: dict[str, int] = {}
    for offset, box in enumerate(prefix):
        capacity = box.capacity
        if offset == 0:
            capacity -= state.box_fill
        demands[box.color] = demands.get(box.color, 0) + capacity

    tray = dict(state.tray)
    persistent_tray = 0
    board_requirements: dict[str, int] = {}
    for color, count in tray.items():
        demand = demands.get(color, 0)
        persistent_tray += max(0, count - demand)
    for color, demand in demands.items():
        board_requirements[color] = max(0, demand - tray.get(color, 0))

    index = _bound_index(level)
    remaining_mask = _remaining_mask(index, state)
    candidate_indices_by_color: dict[str, tuple[int, ...]] = {}
    shortage = False
    combination_count = 1
    choice_groups: list[tuple[tuple[int, ...], ...]] = []

    for color in sorted(board_requirements):
        required = board_requirements[color]
        color_mask = index.color_masks.get(color, 0) & remaining_mask
        indices: list[int] = []
        pending = color_mask
        while pending:
            least_bit = pending & -pending
            indices.append(least_bit.bit_length() - 1)
            pending ^= least_bit
        candidate_indices_by_color[color] = tuple(indices)
        if len(indices) < required:
            shortage = True
            break
        choices = tuple(combinations(indices, required)) if required else ((),)
        choice_groups.append(choices)
        combination_count *= len(choices)

    prefix_color_mask = 0
    for color in demands:
        prefix_color_mask |= index.color_masks.get(color, 0)

    if shortage:
        return BPCBPrefixResult(
            requested_prefix_length=prefix_length,
            actual_prefix_length=len(prefix),
            prefix_colors=tuple(box.color for box in prefix),
            board_requirements=tuple(sorted(board_requirements.items())),
            candidate_combinations=0,
            combinations_evaluated=0,
            skipped_for_combination_limit=False,
            forced_off_prefix_lower_bound=0,
            persistent_tray_occupancy=persistent_tray,
            required_waiting_capacity_lower_bound=persistent_tray,
            shortage=True,
            prunable=True,
        )

    if combination_count > max_combinations:
        return BPCBPrefixResult(
            requested_prefix_length=prefix_length,
            actual_prefix_length=len(prefix),
            prefix_colors=tuple(box.color for box in prefix),
            board_requirements=tuple(sorted(board_requirements.items())),
            candidate_combinations=combination_count,
            combinations_evaluated=0,
            skipped_for_combination_limit=True,
            forced_off_prefix_lower_bound=0,
            persistent_tray_occupancy=persistent_tray,
            required_waiting_capacity_lower_bound=persistent_tray,
            shortage=False,
            prunable=persistent_tray > level.waiting_capacity,
        )

    all_candidates = {
        candidate
        for candidates in candidate_indices_by_color.values()
        for candidate in candidates
    }
    off_prefix_closure_masks = {
        candidate: _closure_mask(index, remaining_mask, candidate)
        & ~prefix_color_mask
        for candidate in all_candidates
    }

    best: int | None = None
    evaluated = 0
    for grouped_targets in product(*choice_groups):
        evaluated += 1
        forced_mask = 0
        for targets in grouped_targets:
            for target in targets:
                forced_mask |= off_prefix_closure_masks[target]
        count = forced_mask.bit_count()
        if best is None or count < best:
            best = count
            if best == 0:
                break

    lower_bound = 0 if best is None else best
    required_capacity = persistent_tray + lower_bound
    return BPCBPrefixResult(
        requested_prefix_length=prefix_length,
        actual_prefix_length=len(prefix),
        prefix_colors=tuple(box.color for box in prefix),
        board_requirements=tuple(sorted(board_requirements.items())),
        candidate_combinations=combination_count,
        combinations_evaluated=evaluated,
        skipped_for_combination_limit=False,
        forced_off_prefix_lower_bound=lower_bound,
        persistent_tray_occupancy=persistent_tray,
        required_waiting_capacity_lower_bound=required_capacity,
        shortage=False,
        prunable=required_capacity > level.waiting_capacity,
    )

