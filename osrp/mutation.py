"""Reproducible, conservation-preserving benchmark mutations."""

from __future__ import annotations

import random
from dataclasses import dataclass, replace
from typing import Iterable

from .model import Box, Level, Screw, ScrewId
from .search import SearchResult, SearchStatus, memoized_dfs
from .simulator import apply_move, initial_state, validate_solution


@dataclass(frozen=True, slots=True)
class MutationRecipe:
    seed: int
    box_swaps: int
    screw_color_swaps: int


@dataclass(frozen=True, slots=True)
class CapacityRun:
    waiting_capacity: int
    status: SearchStatus
    nodes_expanded: int
    memo_prunes: int
    max_depth: int
    max_tray_occupancy: int | None
    solution: tuple[ScrewId, ...] | None


@dataclass(frozen=True, slots=True)
class CapacityProfile:
    recipe: MutationRecipe
    runs: tuple[CapacityRun, ...]
    minimum_feasible_capacity: int | None
    boundary_confirmed: bool

    def run_at(self, capacity: int) -> CapacityRun:
        for run in self.runs:
            if run.waiting_capacity == capacity:
                return run
        raise KeyError(capacity)


def with_waiting_capacity(level: Level, capacity: int, *, name: str | None = None) -> Level:
    if capacity < 0:
        raise ValueError("waiting capacity must be non-negative")
    return replace(
        level,
        name=name or f"{level.name} [W={capacity}]",
        waiting_capacity=capacity,
    )


def _swap_different_colors_screws(
    screws: list[Screw], rng: random.Random, count: int
) -> None:
    for _ in range(count):
        pairs = [
            (i, j)
            for i in range(len(screws))
            for j in range(i + 1, len(screws))
            if screws[i].color != screws[j].color
        ]
        if not pairs:
            return
        i, j = rng.choice(pairs)
        left = screws[i]
        right = screws[j]
        screws[i] = Screw(left.id, left.plate_id, right.color)
        screws[j] = Screw(right.id, right.plate_id, left.color)


def _swap_different_color_boxes(
    boxes: list[Box], rng: random.Random, count: int
) -> None:
    for _ in range(count):
        pairs = [
            (i, j)
            for i in range(len(boxes))
            for j in range(i + 1, len(boxes))
            if boxes[i].color != boxes[j].color
        ]
        if not pairs:
            return
        i, j = rng.choice(pairs)
        boxes[i], boxes[j] = boxes[j], boxes[i]


def mutate_level(
    base: Level,
    recipe: MutationRecipe,
    *,
    waiting_capacity: int | None = None,
) -> Level:
    """Swap colors and box positions without changing any color totals."""
    if recipe.box_swaps < 0 or recipe.screw_color_swaps < 0:
        raise ValueError("mutation counts must be non-negative")
    rng = random.Random(recipe.seed)
    screws = list(base.screws)
    boxes = list(base.boxes)
    _swap_different_colors_screws(screws, rng, recipe.screw_color_swaps)
    _swap_different_color_boxes(boxes, rng, recipe.box_swaps)
    capacity = base.waiting_capacity if waiting_capacity is None else waiting_capacity
    return Level(
        name=(
            f"{base.name} [seed={recipe.seed}, box_swaps={recipe.box_swaps}, "
            f"color_swaps={recipe.screw_color_swaps}, W={capacity}]"
        ),
        screws=tuple(screws),
        plates=base.plates,
        boxes=tuple(boxes),
        waiting_capacity=capacity,
        covers=base.covers,
    )


def maximum_tray_occupancy(level: Level, solution: Iterable[ScrewId]) -> int:
    state = initial_state(level)
    maximum = state.tray_size
    for screw_id in solution:
        state = apply_move(level, state, screw_id)
        maximum = max(maximum, state.tray_size)
    return maximum


def profile_capacities(
    base: Level,
    recipe: MutationRecipe,
    capacities: Iterable[int],
    *,
    max_nodes: int | None = 500_000,
    time_limit_seconds: float | None = 5.0,
) -> CapacityProfile:
    runs: list[CapacityRun] = []
    for capacity in sorted(set(capacities)):
        level = mutate_level(base, recipe, waiting_capacity=capacity)
        result: SearchResult = memoized_dfs(
            level,
            max_nodes=max_nodes,
            time_limit_seconds=time_limit_seconds,
        )
        occupancy: int | None = None
        if result.solution is not None:
            validation = validate_solution(level, result.solution)
            if not validation.valid_solution:
                raise AssertionError(
                    f"search returned invalid mutation solution: {validation.message}"
                )
            occupancy = maximum_tray_occupancy(level, result.solution)
        runs.append(
            CapacityRun(
                waiting_capacity=capacity,
                status=result.status,
                nodes_expanded=result.stats.nodes_expanded,
                memo_prunes=result.stats.memo_prunes,
                max_depth=result.stats.max_depth,
                max_tray_occupancy=occupancy,
                solution=result.solution,
            )
        )

    minimum: int | None = None
    boundary_confirmed = False
    for index, run in enumerate(runs):
        if run.status is not SearchStatus.SOLVED:
            continue
        lower = runs[:index]
        if all(item.status is SearchStatus.UNSOLVABLE for item in lower):
            minimum = run.waiting_capacity
            boundary_confirmed = True
        break

    return CapacityProfile(
        recipe=recipe,
        runs=tuple(runs),
        minimum_feasible_capacity=minimum,
        boundary_confirmed=boundary_confirmed,
    )

