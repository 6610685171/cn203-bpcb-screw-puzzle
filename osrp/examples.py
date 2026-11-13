"""Small hand-checkable levels corresponding to specification tests T1-T8."""

from __future__ import annotations

from .model import Box, Level, Plate, Screw


def t1_direct_only() -> Level:
    return Level(
        name="T1 direct-only",
        screws=(Screw("a1", "pA", "A"), Screw("a2", "pA", "A")),
        plates=(Plate("pA", layer=0, order=0),),
        boxes=(Box("A", 2),),
        waiting_capacity=1,
    )


def t2_one_forced_wait() -> Level:
    return Level(
        name="T2 one forced wait",
        screws=(Screw("a1", "pA", "A"), Screw("b1", "pB", "B")),
        plates=(Plate("pA", 0, 0), Plate("pB", 1, 0)),
        boxes=(Box("A", 1), Box("B", 1)),
        waiting_capacity=1,
        covers=frozenset({("pB", "a1")}),
    )


def t3_full_tray_recoverable() -> Level:
    return Level(
        name="T3 full tray but recoverable",
        screws=(Screw("a1", "pA", "A"), Screw("b1", "pB", "B")),
        plates=(Plate("pA", 0, 0), Plate("pB", 0, 1)),
        boxes=(Box("A", 1), Box("B", 1)),
        waiting_capacity=1,
    )


def t4_forced_overflow() -> Level:
    return Level(
        name="T4 forced overflow",
        screws=(
            Screw("a1", "pA", "A"),
            Screw("b1", "pB1", "B"),
            Screw("b2", "pB2", "B"),
        ),
        plates=(
            Plate("pA", 0, 0),
            Plate("pB1", 1, 0),
            Plate("pB2", 2, 0),
        ),
        boxes=(Box("A", 1), Box("B", 2)),
        waiting_capacity=1,
        covers=frozenset({("pB1", "a1"), ("pB2", "a1")}),
    )


def t5_auto_drain_chain() -> Level:
    return Level(
        name="T5 auto-drain chain",
        screws=(
            Screw("a1", "pA", "A"),
            Screw("b1", "pB", "B"),
            Screw("c1", "pC", "C"),
        ),
        plates=(Plate("pA", 0, 0), Plate("pB", 0, 1), Plate("pC", 0, 2)),
        boxes=(Box("A", 1), Box("B", 1), Box("C", 1)),
        waiting_capacity=2,
    )


def t6_same_layer_tie() -> Level:
    return Level(
        name="T6 same-layer order tie",
        screws=(Screw("a1", "pLow", "A"), Screw("b1", "pHigh", "B")),
        plates=(Plate("pLow", 1, 0), Plate("pHigh", 1, 1)),
        boxes=(Box("A", 1), Box("B", 1)),
        waiting_capacity=1,
        covers=frozenset({("pHigh", "a1")}),
    )


def t7_multiple_blockers() -> Level:
    return Level(
        name="T7 multiple blockers",
        screws=(
            Screw("a1", "pA", "A"),
            Screw("b1", "pB", "B"),
            Screw("c1", "pC", "C"),
        ),
        plates=(Plate("pA", 0, 0), Plate("pB", 1, 0), Plate("pC", 2, 0)),
        boxes=(Box("A", 1), Box("B", 1), Box("C", 1)),
        waiting_capacity=2,
        covers=frozenset({("pB", "a1"), ("pC", "a1")}),
    )


def t8_equivalent_tray_layouts() -> Level:
    return Level(
        name="T8 equivalent tray layouts",
        screws=(
            Screw("a1", "pA", "A"),
            Screw("b1", "pB", "B"),
            Screw("c1", "pC", "C"),
        ),
        plates=(Plate("pA", 0, 0), Plate("pB", 0, 1), Plate("pC", 0, 2)),
        boxes=(Box("A", 1), Box("B", 1), Box("C", 1)),
        waiting_capacity=2,
    )


def repeated_state_trap() -> Level:
    """Unsolvable instance where independent removal orders merge.

    Three off-color one-screw plates all block A, but the tray holds only two.
    Removing B then C reaches the same state as C then B, which exposes the
    difference between plain DFS and canonical dead-state memoization.
    """
    return Level(
        name="Repeated-state forced-overflow trap",
        screws=(
            Screw("a1", "pA", "A"),
            Screw("b1", "pB", "B"),
            Screw("c1", "pC", "C"),
            Screw("d1", "pD", "D"),
        ),
        plates=(
            Plate("pA", 0, 0),
            Plate("pB", 1, 0),
            Plate("pC", 2, 0),
            Plate("pD", 3, 0),
        ),
        boxes=(Box("A", 1), Box("B", 1), Box("C", 1), Box("D", 1)),
        waiting_capacity=2,
        covers=frozenset(
            {("pB", "a1"), ("pC", "a1"), ("pD", "a1")}
        ),
    )


def t9_cross_box_forced_overflow(waiting_capacity: int = 1) -> Level:
    """A is free, but finishing the next B box forces two C screws."""
    return Level(
        name=f"T9 cross-box forced overflow W={waiting_capacity}",
        screws=(
            Screw("a1", "pA", "A"),
            Screw("b1", "pB", "B"),
            Screw("c1", "pC1", "C"),
            Screw("c2", "pC2", "C"),
        ),
        plates=(
            Plate("pA", 0, 0),
            Plate("pB", 0, 1),
            Plate("pC1", 1, 0),
            Plate("pC2", 2, 0),
        ),
        boxes=(Box("A", 1), Box("B", 1), Box("C", 2)),
        waiting_capacity=waiting_capacity,
        covers=frozenset({("pC1", "b1"), ("pC2", "b1")}),
    )


TOY_LEVELS = {
    "T1": t1_direct_only,
    "T2": t2_one_forced_wait,
    "T3": t3_full_tray_recoverable,
    "T4": t4_forced_overflow,
    "T5": t5_auto_drain_chain,
    "T6": t6_same_layer_tie,
    "T7": t7_multiple_blockers,
    "T8": t8_equivalent_tray_layouts,
    "RepeatedTrap": repeated_state_trap,
    "T9": t9_cross_box_forced_overflow,
}

