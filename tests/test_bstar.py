from __future__ import annotations

from pathlib import Path
from random import Random
import unittest

from vlsi_floorplan.bstar import (
    BStarTree,
    complete_bstar_tree,
    decode_bstar_tree,
    fast_simulated_annealing,
    validate_bstar_tree,
)
from vlsi_floorplan.data import Block, FloorplanProblem


def _problem(*blocks: Block) -> FloorplanProblem:
    return FloorplanProblem(Path("tiny.blocks"), tuple(blocks), ())


class BStarTreeTests(unittest.TestCase):
    def test_left_child_is_right_and_right_child_is_above(self) -> None:
        problem = _problem(Block("root", 2, 2), Block("right", 3, 1), Block("above", 1, 3))
        tree = BStarTree(
            block_at=(0, 1, 2),
            left=(1, -1, -1),
            right=(2, -1, -1),
            rotated=(False, False, False),
        )
        decoded = decode_bstar_tree(problem, tree)
        placements = {placement.name: placement for placement in decoded.placements}
        self.assertEqual((placements["root"].x, placements["root"].y), (0, 0))
        self.assertEqual(placements["right"].x, 2)
        self.assertEqual(placements["above"].x, 0)
        self.assertGreaterEqual(placements["above"].y, 2)

    def test_complete_tree_and_all_perturbations_remain_decodable(self) -> None:
        problem = _problem(*(Block(f"b{i}", i % 3 + 1, i % 4 + 1) for i in range(12)))
        tree = complete_bstar_tree(problem, rng=Random(9), outline_limit=20)
        validate_bstar_tree(tree, len(problem.blocks))
        result = fast_simulated_annealing(
            problem,
            outline_limit=20,
            objective="feasibility",
            initial_tree=tree,
            iterations_per_restart=200,
            restarts=1,
            seed=11,
            time_limit=2,
        )
        validate_bstar_tree(result.tree, len(problem.blocks))
        self.assertEqual(len(result.placements), len(problem.blocks))
        self.assertEqual(
            result.stats.rotate_attempts
            + result.stats.move_attempts
            + result.stats.swap_attempts,
            result.stats.completed_iterations,
        )

    def test_invalid_disconnected_tree_fails(self) -> None:
        tree = BStarTree(
            block_at=(0, 1),
            left=(-1, -1),
            right=(-1, -1),
            rotated=(False, False),
        )
        with self.assertRaisesRegex(ValueError, "唯一根"):
            validate_bstar_tree(tree, 2)


if __name__ == "__main__":
    unittest.main()
