from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from vlsi_floorplan.q4 import (
    ComponentRect,
    OrthogonalModule,
    figure3_modules,
    generate_orientations,
    solve_q4,
    validate_q4_solution,
)
from vlsi_floorplan.q4_output import write_q4_solution_json, write_q4_solution_svg


class OrthogonalGeometryTests(unittest.TestCase):
    def test_non_integer_component_geometry_fails_closed(self) -> None:
        with self.assertRaisesRegex(TypeError, "必须为整数"):
            ComponentRect(0, 0, 1.5, 2)  # type: ignore[arg-type]

    def test_overlapping_component_rectangles_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "组成矩形.*重叠"):
            OrthogonalModule(
                "bad",
                (
                    ComponentRect(0, 0, 2, 2),
                    ComponentRect(1, 1, 2, 2),
                ),
            )

    def test_figure3_areas_and_unique_orientations(self) -> None:
        modules = figure3_modules()
        self.assertEqual([module.area for module in modules], [12, 6, 2, 4])
        self.assertEqual(
            [len(generate_orientations(module)) for module in modules],
            [4, 4, 2, 2],
        )
        for module in modules:
            with self.subTest(module=module.name):
                for orientation in generate_orientations(module):
                    self.assertEqual(
                        sum(rect.area for rect in orientation.components),
                        module.area,
                    )
                    self.assertEqual(
                        max(rect.right for rect in orientation.components),
                        orientation.width,
                    )
                    self.assertEqual(
                        max(rect.top for rect in orientation.components),
                        orientation.height,
                    )


class Q4ExactSolveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.modules = figure3_modules()
        cls.solution = solve_q4(
            cls.modules,
            time_limit_per_outline=5,
            workers=1,
            seed=7,
        )

    def test_figure3_reaches_and_proves_zero_dead_space(self) -> None:
        validate_q4_solution(self.modules, self.solution)
        self.assertEqual((self.solution.width, self.solution.height), (6, 4))
        self.assertEqual(self.solution.total_module_area, 24)
        self.assertEqual(self.solution.area, 24)
        self.assertEqual(self.solution.dead_space_ratio, 0.0)
        self.assertTrue(self.solution.area_proven_optimal)
        self.assertTrue(self.solution.lexicographic_proven_optimal)
        self.assertEqual(self.solution.search.area_lower_bound, 24)

    def test_validator_rejects_overlap(self) -> None:
        placements = list(self.solution.placements)
        placements[1] = replace(placements[1], x=placements[0].x, y=placements[0].y)
        invalid = replace(self.solution, placements=tuple(placements))
        with self.assertRaisesRegex(ValueError, "重叠|边界"):
            validate_q4_solution(self.modules, invalid)

    def test_json_and_svg_preserve_real_component_geometry(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            json_path = write_q4_solution_json(
                self.modules,
                self.solution,
                root / "solution.json",
            )
            svg_path = write_q4_solution_svg(self.solution, root / "layout.svg")
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["area"], 24)
            self.assertTrue(payload["area_proven_optimal"])
            self.assertEqual(len(payload["placements"]), 4)
            svg = svg_path.read_text(encoding="utf-8")
            self.assertIn("area=24", svg)
            self.assertIn(">b1</text>", svg)


if __name__ == "__main__":
    unittest.main()
