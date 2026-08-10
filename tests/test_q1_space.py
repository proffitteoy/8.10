from __future__ import annotations

from pathlib import Path
import unittest

from vlsi_floorplan.data import Block, FloorplanProblem
from vlsi_floorplan.q1_space import analyze_search_space, scientific_notation


class SearchSpaceAnalysisTests(unittest.TestCase):
    def test_tiny_exact_counts(self) -> None:
        problem = FloorplanProblem(
            source=Path("tiny.blocks"),
            blocks=(Block("b0", 2, 3), Block("b1", 2, 2)),
            terminal_names=(),
        )
        analysis = analyze_search_space(
            problem,
            dataset="tiny",
            best_width=5,
            best_height=2,
            area_upper_bound=10,
        )

        self.assertEqual(analysis.finite_domain_outline_pairs, 4)
        self.assertEqual(analysis.ordered_outline_pairs, 4)
        self.assertEqual(analysis.area_bounded_outline_pairs, 1)
        self.assertEqual(analysis.module_fit_outline_pairs, 1)
        self.assertEqual(analysis.distinct_rotation_assignments, 2)
        self.assertEqual(analysis.factor_pairs_at_best_area, 2)
        self.assertEqual(analysis.factor_pairs_passing_module_fit, 1)
        self.assertEqual(analysis.fixed_outline_relaxed_assignments, 12)

    def test_scientific_notation_does_not_use_float_conversion(self) -> None:
        self.assertEqual(scientific_notation(12345678901234567890), "1.234e19")


if __name__ == "__main__":
    unittest.main()
