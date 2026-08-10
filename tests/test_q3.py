from __future__ import annotations

from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

from vlsi_floorplan.bstar import FastSAResult, FastSAStats, complete_bstar_tree
from vlsi_floorplan.data import Block, FloorplanDataset, FloorplanProblem, Net
from vlsi_floorplan.q1 import Placement
from vlsi_floorplan.q3 import (
    ExactFeasibilityStats,
    check_exact_feasibility,
    solve_q3,
    theoretical_side_lower_bound,
)
from vlsi_floorplan.q2 import construct_fixed_outline_seed
from vlsi_floorplan.output import write_q2_solution_svg, write_q3_solution_json


def _dataset(blocks: tuple[Block, ...], nets: tuple[Net, ...]) -> FloorplanDataset:
    return FloorplanDataset(
        FloorplanProblem(Path("tiny.blocks"), blocks, ()),
        nets,
        (),
    )


class Q3BoundarySearchTests(unittest.TestCase):
    @staticmethod
    def _fake_sa_result(
        problem: FloorplanProblem,
        *,
        outline_limit: int,
        objective: str,
        seed: int,
    ) -> FastSAResult:
        placement = Placement("a", 0, 0, 100, 100, False)
        stats = FastSAStats(
            objective=objective,
            outline_limit=outline_limit,
            seed=seed,
            restarts=1,
            completed_restarts=1,
            requested_iterations_per_restart=1,
            time_limit_seconds=1.0,
            initial_acceptance_probability=0.9,
            pseudo_greedy_c=100.0,
            pseudo_greedy_epochs=1,
            completed_iterations=1,
            accepted_moves=0,
            uphill_accepted_moves=0,
            feasible_evaluations=0,
            rotate_attempts=0,
            move_attempts=0,
            swap_attempts=0,
            initial_temperature=1.0,
            final_temperature=0.0,
            best_violation=1,
            best_width=100,
            best_height=100,
            wall_time_seconds=0.0,
        )
        return FastSAResult(
            tree=complete_bstar_tree(problem, outline_limit=outline_limit),
            placements=(placement,),
            width=100,
            height=100,
            violation=1,
            total_hpwl2=0,
            stats=stats,
        )

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

    def test_unknown_midpoint_continues_searching_upper_interval(self) -> None:
        dataset = _dataset((Block("a", 100, 100),), ())
        placement = Placement("a", 0, 0, 100, 100, False)

        def fake_annealing(problem: FloorplanProblem, **kwargs: object) -> FastSAResult:
            return self._fake_sa_result(
                problem,
                outline_limit=int(kwargs["outline_limit"]),
                objective=str(kwargs["objective"]),
                seed=int(kwargs["seed"]),
            )

        def fake_exact(
            problem: FloorplanProblem,
            side: int,
            *,
            time_limit: float,
            workers: int,
            seed: int,
            hint_placements: tuple[Placement, ...] | None = None,
        ) -> tuple[ExactFeasibilityStats, tuple[Placement, ...] | None]:
            unknown = side == 103
            return (
                ExactFeasibilityStats(
                    side=side,
                    time_limit_seconds=time_limit,
                    workers=workers,
                    seed=seed,
                    status="UNKNOWN" if unknown else "OPTIMAL",
                    has_solution=not unknown,
                    proven_infeasible=False,
                    wall_time_seconds=0.0,
                    conflicts=0,
                    branches=0,
                ),
                None if unknown else (placement,),
            )

        def fake_construction(
            candidate_dataset: FloorplanDataset,
            side: int,
        ) -> object:
            if side == 107:
                return construct_fixed_outline_seed(candidate_dataset, side)
            raise RuntimeError("force boundary candidates through mocked annealing and exact checks")

        with (
            patch("vlsi_floorplan.q3.construct_fixed_outline_seed", side_effect=fake_construction),
            patch("vlsi_floorplan.q3.fast_simulated_annealing", side_effect=fake_annealing),
            patch("vlsi_floorplan.q3.check_exact_feasibility", side_effect=fake_exact),
        ):
            solution = solve_q3(
                dataset,
                heuristic_iterations_per_restart=1,
                heuristic_restarts=1,
                heuristic_time_limit_per_side=1,
                exact_time_limit_per_side=1,
                exact_workers=1,
                max_boundary_steps=10,
                hpwl_iterations_per_restart=1,
                hpwl_restarts=1,
                hpwl_time_limit=1,
                seed=7,
            )

        self.assertEqual([step.side for step in solution.boundary_search.steps[:2]], [103, 105])
        self.assertGreater(len(solution.boundary_search.steps), 1)
        self.assertEqual(solution.chip_side, 100)
        self.assertTrue(solution.minimum_dead_space_proven)


if __name__ == "__main__":
    unittest.main()
