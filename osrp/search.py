"""Exact baseline search algorithms with reproducible instrumentation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from time import perf_counter
from typing import Callable

from .model import Level, ScrewId, State
from .simulator import apply_move, initial_state, is_goal, legal_moves, normalize


class SearchStatus(str, Enum):
    SOLVED = "solved"
    UNSOLVABLE = "unsolvable"
    LIMIT_REACHED = "limit_reached"


@dataclass(slots=True)
class SearchStats:
    nodes_expanded: int = 0
    transitions_generated: int = 0
    unique_states_seen: int = 0
    repeated_state_visits: int = 0
    memo_prunes: int = 0
    terminal_dead_ends: int = 0
    proven_dead_states: int = 0
    max_depth: int = 0
    dead_depth_sum: int = 0
    deepest_terminal_dead_end: int = 0
    bound_checks: int = 0
    bound_prunes: int = 0
    bound_combinations_evaluated: int = 0
    bound_fallbacks: int = 0
    elapsed_seconds: float = 0.0

    @property
    def average_terminal_dead_depth(self) -> float:
        if self.terminal_dead_ends == 0:
            return 0.0
        return self.dead_depth_sum / self.terminal_dead_ends


@dataclass(frozen=True, slots=True)
class SearchResult:
    status: SearchStatus
    solution: tuple[ScrewId, ...] | None
    stats: SearchStats
    memoized: bool
    message: str

    @property
    def solved(self) -> bool:
        return self.status is SearchStatus.SOLVED


@dataclass(frozen=True, slots=True)
class PruneDecision:
    """Instrumented result of one provably safe pruning check."""

    prunable: bool
    combinations_evaluated: int = 0
    fallback_count: int = 0


class _SearchLimitReached(RuntimeError):
    pass


def _exact_dfs(
    level: Level,
    *,
    memoize: bool,
    max_nodes: int | None,
    time_limit_seconds: float | None,
    prune_test: Callable[[Level, State], bool | PruneDecision] | None,
) -> SearchResult:
    if max_nodes is not None and max_nodes < 0:
        raise ValueError("max_nodes must be non-negative or None")
    if time_limit_seconds is not None and time_limit_seconds < 0:
        raise ValueError("time_limit_seconds must be non-negative or None")

    stats = SearchStats()
    seen_for_measurement: set[State] = set()
    dead_cache: set[State] = set()
    started = perf_counter()

    def check_limits() -> None:
        if max_nodes is not None and stats.nodes_expanded >= max_nodes:
            raise _SearchLimitReached(f"node limit {max_nodes} reached")
        if (
            time_limit_seconds is not None
            and perf_counter() - started >= time_limit_seconds
        ):
            raise _SearchLimitReached(
                f"time limit {time_limit_seconds:.6g} seconds reached"
            )

    def dfs(state: State, depth: int) -> tuple[ScrewId, ...] | None:
        state = normalize(level, state)
        stats.max_depth = max(stats.max_depth, depth)

        if is_goal(level, state):
            return ()

        if state in seen_for_measurement:
            stats.repeated_state_visits += 1
        else:
            seen_for_measurement.add(state)
            stats.unique_states_seen = len(seen_for_measurement)

        if memoize and state in dead_cache:
            stats.memo_prunes += 1
            return None

        if prune_test is not None:
            stats.bound_checks += 1
            decision = prune_test(level, state)
            if isinstance(decision, PruneDecision):
                stats.bound_combinations_evaluated += decision.combinations_evaluated
                stats.bound_fallbacks += decision.fallback_count
                should_prune = decision.prunable
            else:
                should_prune = decision
            if should_prune:
                stats.bound_prunes += 1
                stats.proven_dead_states += 1
                if memoize:
                    dead_cache.add(state)
                return None

        check_limits()
        stats.nodes_expanded += 1
        moves = legal_moves(level, state)
        if not moves:
            stats.terminal_dead_ends += 1
            stats.dead_depth_sum += depth
            stats.deepest_terminal_dead_end = max(
                stats.deepest_terminal_dead_end, depth
            )
            if memoize:
                dead_cache.add(state)
            stats.proven_dead_states += 1
            return None

        for screw_id in moves:
            stats.transitions_generated += 1
            child = apply_move(level, state, screw_id)
            suffix = dfs(child, depth + 1)
            if suffix is not None:
                return (screw_id,) + suffix

        if memoize:
            dead_cache.add(state)
        stats.proven_dead_states += 1
        return None

    try:
        solution = dfs(initial_state(level), 0)
    except _SearchLimitReached as exc:
        stats.elapsed_seconds = perf_counter() - started
        return SearchResult(
            status=SearchStatus.LIMIT_REACHED,
            solution=None,
            stats=stats,
            memoized=memoize,
            message=str(exc),
        )

    stats.elapsed_seconds = perf_counter() - started
    if solution is not None:
        return SearchResult(
            status=SearchStatus.SOLVED,
            solution=solution,
            stats=stats,
            memoized=memoize,
            message="exact solution found",
        )
    return SearchResult(
        status=SearchStatus.UNSOLVABLE,
        solution=None,
        stats=stats,
        memoized=memoize,
        message="the complete search space was exhausted",
    )


def brute_force_dfs(
    level: Level,
    *,
    max_nodes: int | None = None,
    time_limit_seconds: float | None = None,
) -> SearchResult:
    """Exact DFS that deliberately does not prune repeated states."""
    return _exact_dfs(
        level,
        memoize=False,
        max_nodes=max_nodes,
        time_limit_seconds=time_limit_seconds,
        prune_test=None,
    )


def memoized_dfs(
    level: Level,
    *,
    max_nodes: int | None = None,
    time_limit_seconds: float | None = None,
) -> SearchResult:
    """Exact DFS with a canonical cache of states proven unsolvable."""
    return _exact_dfs(
        level,
        memoize=True,
        max_nodes=max_nodes,
        time_limit_seconds=time_limit_seconds,
        prune_test=None,
    )


def bpcb1_memoized_dfs(
    level: Level,
    *,
    max_nodes: int | None = None,
    time_limit_seconds: float | None = None,
) -> SearchResult:
    """Memoized exact DFS with the safe one-box BPCB pruning rule."""
    from .bounds import box_prefix_one_bound

    def prune(current_level: Level, state: State) -> PruneDecision:
        result = box_prefix_one_bound(current_level, state)
        return PruneDecision(
            prunable=result.prunable,
            combinations_evaluated=result.combinations_evaluated,
        )

    return _exact_dfs(
        level,
        memoize=True,
        max_nodes=max_nodes,
        time_limit_seconds=time_limit_seconds,
        prune_test=prune,
    )


def bpcb2_memoized_dfs(
    level: Level,
    *,
    max_nodes: int | None = None,
    time_limit_seconds: float | None = None,
    max_bound_combinations: int = 50_000,
) -> SearchResult:
    """Memoized exact DFS with the safe two-box prefix bound."""
    from .bounds import box_prefix_bound

    def prune(current_level: Level, state: State) -> PruneDecision:
        result = box_prefix_bound(
            current_level,
            state,
            prefix_length=2,
            max_combinations=max_bound_combinations,
        )
        return PruneDecision(
            prunable=result.prunable,
            combinations_evaluated=result.combinations_evaluated,
            fallback_count=int(result.skipped_for_combination_limit),
        )

    return _exact_dfs(
        level,
        memoize=True,
        max_nodes=max_nodes,
        time_limit_seconds=time_limit_seconds,
        prune_test=prune,
    )


def bpcb12_memoized_dfs(
    level: Level,
    *,
    max_nodes: int | None = None,
    time_limit_seconds: float | None = None,
    max_bound_combinations: int = 50_000,
) -> SearchResult:
    """Memoized DFS that applies both one-box and two-box safe bounds."""
    from .bounds import box_prefix_bound, box_prefix_one_bound

    def combined_prune(current_level: Level, state: State) -> PruneDecision:
        one = box_prefix_one_bound(current_level, state)
        if one.prunable:
            return PruneDecision(
                prunable=True,
                combinations_evaluated=one.combinations_evaluated,
            )
        two = box_prefix_bound(
            current_level,
            state,
            prefix_length=2,
            max_combinations=max_bound_combinations,
        )
        return PruneDecision(
            prunable=two.prunable,
            combinations_evaluated=(
                one.combinations_evaluated + two.combinations_evaluated
            ),
            fallback_count=int(two.skipped_for_combination_limit),
        )

    return _exact_dfs(
        level,
        memoize=True,
        max_nodes=max_nodes,
        time_limit_seconds=time_limit_seconds,
        prune_test=combined_prune,
    )

