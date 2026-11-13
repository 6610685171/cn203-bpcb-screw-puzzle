from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from osrp import (
    SearchStatus,
    MutationRecipe,
    brute_force_dfs,
    bpcb1_memoized_dfs,
    bpcb12_memoized_dfs,
    bpcb2_memoized_dfs,
    box_prefix_bound,
    box_prefix_one_bound,
    initial_state,
    level_from_source_snapshot,
    load_discrete_level,
    memoized_dfs,
    reconstruct_source_level_1,
    profile_capacities,
    save_discrete_level,
    validate_solution,
)
from osrp.examples import (
    repeated_state_trap,
    t2_one_forced_wait,
    t4_forced_overflow,
    t9_cross_box_forced_overflow,
)


ROOT = Path(__file__).resolve().parents[1]


class ExactSearchTests(unittest.TestCase):
    def test_combined_bpcb_uses_either_safe_bound(self) -> None:
        one_box_case = bpcb12_memoized_dfs(t4_forced_overflow())
        two_box_case = bpcb12_memoized_dfs(
            t9_cross_box_forced_overflow(waiting_capacity=1)
        )
        self.assertEqual(one_box_case.status, SearchStatus.UNSOLVABLE)
        self.assertEqual(two_box_case.status, SearchStatus.UNSOLVABLE)
        self.assertEqual(one_box_case.stats.nodes_expanded, 0)
        self.assertEqual(two_box_case.stats.nodes_expanded, 0)

    def test_bpcb2_sees_forced_overflow_across_the_next_box(self) -> None:
        level = t9_cross_box_forced_overflow(waiting_capacity=1)
        state = initial_state(level)
        one_box = box_prefix_one_bound(level, state)
        two_boxes = box_prefix_bound(level, state, prefix_length=2)
        self.assertFalse(one_box.prunable)
        self.assertEqual(two_boxes.forced_off_prefix_lower_bound, 2)
        self.assertTrue(two_boxes.prunable)

        one_result = bpcb1_memoized_dfs(level)
        two_result = bpcb2_memoized_dfs(level)
        self.assertEqual(one_result.status, SearchStatus.UNSOLVABLE)
        self.assertEqual(two_result.status, SearchStatus.UNSOLVABLE)
        self.assertGreater(one_result.stats.nodes_expanded, 0)
        self.assertEqual(two_result.stats.nodes_expanded, 0)

    def test_bpcb2_keeps_cross_box_tight_solvable_case(self) -> None:
        level = t9_cross_box_forced_overflow(waiting_capacity=2)
        bound = box_prefix_bound(level, initial_state(level), prefix_length=2)
        self.assertEqual(bound.required_waiting_capacity_lower_bound, 2)
        self.assertFalse(bound.prunable)
        result = bpcb2_memoized_dfs(level)
        self.assertEqual(result.status, SearchStatus.SOLVED)
        self.assertTrue(validate_solution(level, result.solution or ()).valid_solution)

    def test_bpcb1_bound_prunes_forced_overflow_at_root(self) -> None:
        level = t4_forced_overflow()
        bound = box_prefix_one_bound(level, initial_state(level))
        self.assertEqual(bound.forced_off_color_lower_bound, 2)
        self.assertEqual(bound.required_waiting_capacity_lower_bound, 2)
        self.assertTrue(bound.prunable)

        result = bpcb1_memoized_dfs(level)
        self.assertEqual(result.status, SearchStatus.UNSOLVABLE)
        self.assertEqual(result.stats.nodes_expanded, 0)
        self.assertEqual(result.stats.bound_prunes, 1)

    def test_bpcb1_does_not_prune_the_tight_solvable_case(self) -> None:
        level = t2_one_forced_wait()
        bound = box_prefix_one_bound(level, initial_state(level))
        self.assertEqual(bound.required_waiting_capacity_lower_bound, 1)
        self.assertFalse(bound.prunable)
        result = bpcb1_memoized_dfs(level)
        self.assertEqual(result.status, SearchStatus.SOLVED)
        self.assertTrue(validate_solution(level, result.solution or ()).valid_solution)

    def test_capacity_profile_finds_exact_minimum_waiting_space(self) -> None:
        profile = profile_capacities(
            t2_one_forced_wait(),
            MutationRecipe(seed=1, box_swaps=0, screw_color_swaps=0),
            capacities=(0, 1, 2),
        )
        self.assertTrue(profile.boundary_confirmed)
        self.assertEqual(profile.minimum_feasible_capacity, 1)
        self.assertEqual(profile.run_at(0).status, SearchStatus.UNSOLVABLE)
        self.assertEqual(profile.run_at(1).status, SearchStatus.SOLVED)
        self.assertEqual(profile.run_at(1).max_tray_occupancy, 1)

    def test_both_baselines_find_and_validate_a_solution(self) -> None:
        level = t2_one_forced_wait()
        for solver in (brute_force_dfs, memoized_dfs):
            result = solver(level)
            self.assertEqual(result.status, SearchStatus.SOLVED)
            self.assertIsNotNone(result.solution)
            self.assertTrue(validate_solution(level, result.solution or ()).valid_solution)

    def test_both_baselines_prove_forced_overflow_unsolvable(self) -> None:
        level = t4_forced_overflow()
        for solver in (brute_force_dfs, memoized_dfs):
            result = solver(level)
            self.assertEqual(result.status, SearchStatus.UNSOLVABLE)
            self.assertIsNone(result.solution)
            self.assertGreater(result.stats.terminal_dead_ends, 0)

    def test_memoization_prunes_merged_independent_orders(self) -> None:
        level = repeated_state_trap()
        brute = brute_force_dfs(level)
        memo = memoized_dfs(level)

        self.assertEqual(brute.status, SearchStatus.UNSOLVABLE)
        self.assertEqual(memo.status, SearchStatus.UNSOLVABLE)
        self.assertGreater(brute.stats.repeated_state_visits, 0)
        self.assertGreater(memo.stats.memo_prunes, 0)
        self.assertLess(memo.stats.nodes_expanded, brute.stats.nodes_expanded)
        # The edge leading to a cached child still has to be generated, but the
        # cached child is not expanded or counted as another terminal dead end.
        self.assertLess(
            memo.stats.terminal_dead_ends, brute.stats.terminal_dead_ends
        )

    def test_limit_is_not_mislabeled_as_unsolvable(self) -> None:
        result = brute_force_dfs(repeated_state_trap(), max_nodes=0)
        self.assertEqual(result.status, SearchStatus.LIMIT_REACHED)
        self.assertIsNone(result.solution)


class SourceImportTests(unittest.TestCase):
    def test_runtime_exports_levels_1_through_5_import_and_solve(self) -> None:
        for runtime_level in range(1, 6):
            level = level_from_source_snapshot(
                ROOT / "fixtures" / f"flutter_source_level_{runtime_level}.json"
            )
            result = memoized_dfs(level, max_nodes=10_000, time_limit_seconds=1)
            self.assertEqual(result.status, SearchStatus.SOLVED)
            self.assertTrue(validate_solution(level, result.solution or ()).valid_solution)

    def test_runtime_export_matches_level_1_reconstruction(self) -> None:
        runtime = level_from_source_snapshot(
            ROOT / "fixtures" / "flutter_source_level_1.json"
        )
        reconstructed, witness = reconstruct_source_level_1()
        self.assertEqual(runtime.plates, reconstructed.plates)
        self.assertEqual(runtime.screws, reconstructed.screws)
        self.assertEqual(runtime.boxes, reconstructed.boxes)
        self.assertEqual(runtime.covers, reconstructed.covers)
        self.assertTrue(validate_solution(runtime, witness).valid_solution)

    def test_reconstructed_public_source_level_1_witness_is_valid(self) -> None:
        level, witness = reconstruct_source_level_1()
        self.assertEqual(len(level.plates), 6)
        self.assertEqual(len(level.screws), 24)
        self.assertEqual(len(level.boxes), 8)
        self.assertGreater(len(level.covers), 0)
        self.assertTrue(validate_solution(level, witness).valid_solution)

        result = memoized_dfs(level, max_nodes=10_000, time_limit_seconds=2)
        self.assertEqual(result.status, SearchStatus.SOLVED)
        self.assertTrue(validate_solution(level, result.solution or ()).valid_solution)

    def test_source_snapshot_preprocesses_overlap_and_solves(self) -> None:
        snapshot = ROOT / "fixtures" / "source_snapshot_toy.json"
        level = level_from_source_snapshot(snapshot)
        self.assertIn(("pB", "a1"), level.covers)

        result = memoized_dfs(level)
        self.assertEqual(result.status, SearchStatus.SOLVED)
        self.assertEqual(result.solution, ("b1", "a1"))
        self.assertTrue(validate_solution(level, result.solution or ()).valid_solution)

    def test_discrete_json_round_trip_is_lossless(self) -> None:
        original = t2_one_forced_wait()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "level.json"
            save_discrete_level(original, path)
            restored = load_discrete_level(path)
        self.assertEqual(restored, original)


if __name__ == "__main__":
    unittest.main()

