from __future__ import annotations

from pathlib import Path
import unittest

from vlsi_floorplan.data import Block, FloorplanDataset, FloorplanProblem, Net, Terminal
from vlsi_floorplan.q1 import Placement
from vlsi_floorplan.q2 import compute_net_hpwl2, solve_q2, validate_q2_solution


def _dataset(
    blocks: tuple[Block, ...],
    nets: tuple[Net, ...],
    terminals: tuple[Terminal, ...] = (),
) -> FloorplanDataset:
    return FloorplanDataset(
        problem=FloorplanProblem(
            source=Path("tiny.blocks"),
            blocks=blocks,
            terminal_names=tuple(terminal.name for terminal in terminals),
        ),
        nets=nets,
        terminals=terminals,
    )


class HpwlTests(unittest.TestCase):
    def test_mixed_net_and_rotated_module_match_hand_calculation(self) -> None:
        dataset = _dataset(
            blocks=(Block("b0", 2, 4),),
            terminals=(Terminal("p0", 7.0, 1.0),),
            nets=(Net(("b0", "p0")),),
        )
        placements = (
            Placement("b0", x=1, y=2, width=4, height=2, rotated=True),
        )

        # b0 中心为 (3, 3)，p0 为 (7, 1)，所以 HPWL = 4 + 2 = 6。
        self.assertEqual(compute_net_hpwl2(dataset, placements), (12,))

    def test_half_integer_terminal_coordinate_is_exact(self) -> None:
        dataset = _dataset(
            blocks=(Block("b0", 2, 2),),
            terminals=(Terminal("p0", 2.5, 1.5),),
            nets=(Net(("b0", "p0")),),
        )
        placements = (
            Placement("b0", x=0, y=0, width=2, height=2, rotated=False),
        )
        self.assertEqual(compute_net_hpwl2(dataset, placements), (4,))

    def test_unsupported_terminal_precision_fails_explicitly(self) -> None:
        dataset = _dataset(
            blocks=(Block("b0", 1, 1),),
            terminals=(Terminal("p0", 0.25, 0.0),),
            nets=(Net(("b0", "p0")),),
        )
        placements = (
            Placement("b0", x=0, y=0, width=1, height=1, rotated=False),
        )
        with self.assertRaisesRegex(ValueError, "0.5 的整数倍"):
            compute_net_hpwl2(dataset, placements)


class Q2DirectModelTests(unittest.TestCase):
    def test_solver_objective_matches_mixed_terminal_net(self) -> None:
        dataset = _dataset(
            blocks=(Block("b0", 2, 2),),
            terminals=(Terminal("p0", 4.0, 1.0),),
            nets=(Net(("b0", "p0")),),
        )
        solution = solve_q2(
            dataset,
            feasibility_time_limit=1,
            optimization_time_limit=2,
            workers=1,
            seed=7,
        )
        self.assertEqual(solution.total_hpwl, 3)
        self.assertTrue(solution.hpwl_proven_optimal)

    def test_two_blocks_reach_hand_calculated_optimum(self) -> None:
        dataset = _dataset(
            blocks=(Block("b0", 1, 2), Block("b1", 1, 2)),
            nets=(Net(("b0", "b1")),),
        )
        solution = solve_q2(
            dataset,
            feasibility_time_limit=2,
            optimization_time_limit=5,
            workers=1,
            seed=7,
        )

        validate_q2_solution(dataset, solution)
        self.assertEqual(solution.coordinate_limit, 2)
        self.assertEqual(solution.total_hpwl, 1)
        self.assertTrue(solution.hpwl_proven_optimal)

    def test_validation_rejects_overlap(self) -> None:
        dataset = _dataset(
            blocks=(Block("b0", 1, 2), Block("b1", 1, 2)),
            nets=(Net(("b0", "b1")),),
        )
        solution = solve_q2(
            dataset,
            feasibility_time_limit=2,
            optimization_time_limit=2,
            workers=1,
            seed=7,
        )
        first, second = solution.placements
        bad_second = Placement(
            second.name,
            x=first.x,
            y=first.y,
            width=second.width,
            height=second.height,
            rotated=second.rotated,
        )
        bad_solution = type(solution)(
            method=solution.method,
            dead_space_ratio=solution.dead_space_ratio,
            chip_side=solution.chip_side,
            coordinate_limit=solution.coordinate_limit,
            total_block_area=solution.total_block_area,
            placements=(first, bad_second),
            net_hpwl2=solution.net_hpwl2,
            total_hpwl2=solution.total_hpwl2,
            construction=solution.construction,
            feasibility_phase=solution.feasibility_phase,
            optimization_phase=solution.optimization_phase,
            seed=solution.seed,
            workers=solution.workers,
        )
        with self.assertRaisesRegex(ValueError, "重叠"):
            validate_q2_solution(dataset, bad_solution)


if __name__ == "__main__":
    unittest.main()
