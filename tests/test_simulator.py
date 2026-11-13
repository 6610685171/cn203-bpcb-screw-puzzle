from __future__ import annotations

import unittest

from osrp import (
    Box,
    CoveredScrew,
    InvalidLevel,
    Level,
    Plate,
    Screw,
    State,
    TrayOverflow,
    accessible_screws,
    apply_move,
    canonical_tray,
    initial_state,
    is_accessible,
    is_goal,
    legal_moves,
    validate_solution,
)
from osrp.examples import (
    t1_direct_only,
    t2_one_forced_wait,
    t3_full_tray_recoverable,
    t4_forced_overflow,
    t5_auto_drain_chain,
    t6_same_layer_tie,
    t7_multiple_blockers,
    t8_equivalent_tray_layouts,
)


class SimulatorToyTests(unittest.TestCase):
    def test_t1_direct_only(self) -> None:
        level = t1_direct_only()
        result = validate_solution(level, ["a1", "a2"])
        self.assertTrue(result.valid_solution, result.message)
        self.assertEqual(result.final_state.box_fill, 2)

    def test_t2_one_forced_wait(self) -> None:
        level = t2_one_forced_wait()
        state = initial_state(level)
        self.assertEqual(accessible_screws(level, state), ("b1",))
        with self.assertRaises(CoveredScrew):
            apply_move(level, state, "a1")

        state = apply_move(level, state, "b1")
        self.assertEqual(state.tray, (("B", 1),))
        self.assertEqual(accessible_screws(level, state), ("a1",))
        state = apply_move(level, state, "a1")
        self.assertTrue(is_goal(level, state))

    def test_t3_full_tray_is_recoverable(self) -> None:
        level = t3_full_tray_recoverable()
        state = apply_move(level, initial_state(level), "b1")
        self.assertEqual(state.tray_size, level.waiting_capacity)
        self.assertEqual(legal_moves(level, state), ("a1",))
        state = apply_move(level, state, "a1")
        self.assertTrue(is_goal(level, state))

    def test_t4_forced_overflow_is_dead(self) -> None:
        level = t4_forced_overflow()
        root = initial_state(level)
        self.assertEqual(set(legal_moves(level, root)), {"b1", "b2"})

        for first, second in (("b1", "b2"), ("b2", "b1")):
            state = apply_move(level, root, first)
            self.assertFalse(is_accessible(level, state, "a1"))
            self.assertEqual(legal_moves(level, state), ())
            with self.assertRaises(TrayOverflow):
                apply_move(level, state, second)

    def test_t5_auto_drain_can_finish_multiple_boxes(self) -> None:
        level = t5_auto_drain_chain()
        state = initial_state(level)
        state = apply_move(level, state, "b1")
        state = apply_move(level, state, "c1")
        self.assertEqual(state.tray, (("B", 1), ("C", 1)))
        state = apply_move(level, state, "a1")
        self.assertTrue(is_goal(level, state))
        self.assertEqual(state.box_index, 2)
        self.assertEqual(state.box_fill, 1)
        self.assertEqual(state.tray, ())

    def test_t6_same_layer_order_breaks_tie(self) -> None:
        level = t6_same_layer_tie()
        state = initial_state(level)
        self.assertEqual(accessible_screws(level, state), ("b1",))
        self.assertTrue(validate_solution(level, ["b1", "a1"]).valid_solution)

    def test_t7_all_blocking_plates_must_fall(self) -> None:
        level = t7_multiple_blockers()
        state = initial_state(level)
        self.assertFalse(is_accessible(level, state, "a1"))
        state = apply_move(level, state, "b1")
        self.assertFalse(is_accessible(level, state, "a1"))
        state = apply_move(level, state, "c1")
        self.assertTrue(is_accessible(level, state, "a1"))
        state = apply_move(level, state, "a1")
        self.assertTrue(is_goal(level, state))

    def test_t8_tray_layouts_have_one_canonical_state(self) -> None:
        level = t8_equivalent_tray_layouts()
        remaining = frozenset({"a1"})
        state_left = State(
            remaining=remaining,
            box_index=0,
            box_fill=0,
            tray=canonical_tray({"B": 1, "C": 1}),
        )
        state_right = State(
            remaining=remaining,
            box_index=0,
            box_fill=0,
            tray=canonical_tray({"C": 1, "B": 1}),
        )
        self.assertEqual(state_left, state_right)
        self.assertEqual(hash(state_left), hash(state_right))
        self.assertEqual(legal_moves(level, state_left), ("a1",))


class ValidationAndInvariantTests(unittest.TestCase):
    def test_validator_rejects_a_covered_move_at_the_correct_step(self) -> None:
        result = validate_solution(t2_one_forced_wait(), ["a1", "b1"])
        self.assertFalse(result.legal)
        self.assertFalse(result.won)
        self.assertEqual(result.steps_applied, 0)
        self.assertIn("covered", result.message)

    def test_validator_distinguishes_legal_prefix_from_solution(self) -> None:
        result = validate_solution(t1_direct_only(), ["a1"])
        self.assertTrue(result.legal)
        self.assertFalse(result.won)
        self.assertFalse(result.valid_solution)

    def test_color_conservation_is_required(self) -> None:
        with self.assertRaises(InvalidLevel):
            Level(
                name="bad colors",
                screws=(Screw("a1", "pA", "A"),),
                plates=(Plate("pA", 0, 0),),
                boxes=(Box("B", 1),),
                waiting_capacity=1,
            )

    def test_a_lower_plate_cannot_be_declared_as_a_blocker(self) -> None:
        with self.assertRaises(InvalidLevel):
            Level(
                name="bad blocker",
                screws=(Screw("a1", "pHigh", "A"), Screw("b1", "pLow", "B")),
                plates=(Plate("pLow", 0, 0), Plate("pHigh", 1, 0)),
                boxes=(Box("A", 1), Box("B", 1)),
                waiting_capacity=1,
                covers=frozenset({("pLow", "a1")}),
            )


if __name__ == "__main__":
    unittest.main()

