from __future__ import annotations

from pathlib import Path
import json
import tempfile
import unittest

from vlsi_floorplan.data import Block, FloorplanDataset, FloorplanProblem, Net
from vlsi_floorplan.q3 import (
    check_exact_feasibility,
    solve_q3,
    theoretical_side_lower_bound,
)
from vlsi_floorplan.output import write_q2_solution_svg, write_q3_solution_json


def _dataset(blocks: tuple[Block, ...], nets: tuple[Net, ...]) -> FloorplanDataset:
    return FloorplanDataset(
        FloorplanProblem(Path("tiny.blocks"), blocks, ()),
        nets,
        (),
    )


class Q3BoundarySearchTests(unittest.TestCase):
    def test_lower_bound_uses_area_and_unrotated_max_dimension(self) -> None:
        problem = FloorplanProblem(Path("tiny.blocks"), (Block("long", 1, 10),), ())
        self.assertEqual(theoretical_side_lower_bound(problem), 10)

    def test_exact_checker_proves_small_outline_infeasible(self) -> None:
        problem = FloorplanProblem(
            Path("tiny.blocks"),
            (Block("a", 2, 2), Block("b", 2, 2), Block("c", 2, 2)),
            (),
        )
        stats, placements = check_exact_feasibility(
            problem,
            3,
            time_limit=2,
            workers=1,
            seed=5,
        )
        self.assertTrue(stats.proven_infeasible)
        self.assertIsNone(placements)

    def test_two_stage_solution_reports_zero_dead_space_small_case(self) -> None:
        dataset = _dataset(
            (Block("a", 1, 2), Block("b", 1, 2)),
            (Net(("a", "b")),),
        )
        solution = solve_q3(
            dataset,
            heuristic_iterations_per_restart=20,
            heuristic_restarts=1,
            heuristic_time_limit_per_side=1,
            exact_time_limit_per_side=1,
            exact_workers=1,
            hpwl_iterations_per_restart=50,
            hpwl_restarts=1,
            hpwl_time_limit=1,
            seed=3,
        )
        self.assertEqual(solution.chip_side, 2)
        self.assertEqual(solution.dead_space_ratio, 0)
        self.assertTrue(solution.minimum_dead_space_proven)
        self.assertEqual(solution.total_hpwl, 1)

        with tempfile.TemporaryDirectory() as directory:
            json_path = write_q3_solution_json(
                dataset, solution, Path(directory) / "solution.json"
            )
            svg_path = write_q2_solution_svg(solution, Path(directory) / "layout.svg")
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertTrue(payload["minimum_dead_space_proven"])
            self.assertEqual(payload["chip_side"], 2)
            self.assertTrue(svg_path.read_text(encoding="utf-8").startswith("<?xml"))


if __name__ == "__main__":
    unittest.main()
