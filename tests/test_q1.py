from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from vlsi_floorplan.data import Block, FloorplanProblem, parse_blocks, parse_dataset, parse_nets
from vlsi_floorplan.q1 import solve_q1, validate_solution


ROOT = Path(__file__).resolve().parents[1]


class BlocksParserTests(unittest.TestCase):
    def test_all_benchmark_datasets_are_consistent(self) -> None:
        expected = {
            100: (100, 334, 885, 1873, 179501),
            200: (200, 564, 1585, 3599, 175696),
            300: (300, 569, 1893, 4358, 273170),
        }
        for size, (blocks, terminals, nets, pins, area) in expected.items():
            with self.subTest(size=size):
                prefix = ROOT / "附件" / f"n{size}"
                dataset = parse_dataset(
                    prefix.with_suffix(".blocks"),
                    prefix.with_suffix(".nets"),
                    prefix.with_suffix(".pl"),
                )
                self.assertEqual(len(dataset.problem.blocks), blocks)
                self.assertEqual(len(dataset.terminals), terminals)
                self.assertEqual(len(dataset.nets), nets)
                self.assertEqual(dataset.pin_count, pins)
                self.assertEqual(dataset.problem.total_block_area, area)

    def test_declared_count_mismatch_fails_closed(self) -> None:
        content = """NumHardBlocks : 2
NumTerminals : 0

b0 block 4 (0, 0) (0, 2) (3, 2) (3, 0)
"""
        with TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "bad.blocks"
            path.write_text(content, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "声明 2 个，实际 1 个"):
                parse_blocks(path)

    def test_truncated_net_fails_closed(self) -> None:
        content = """NumNets : 1
NumPins : 2
NetDegree : 2
b0
"""
        with TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "bad.nets"
            path.write_text(content, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "文件已截断"):
                parse_nets(path)

    def test_unknown_net_reference_fails_closed(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            blocks_path = root / "tiny.blocks"
            nets_path = root / "tiny.nets"
            pl_path = root / "tiny.pl"
            blocks_path.write_text(
                "NumHardBlocks : 1\nNumTerminals : 0\n"
                "b0 block 4 (0, 0) (0, 2) (3, 2) (3, 0)\n",
                encoding="utf-8",
            )
            nets_path.write_text(
                "NumNets : 1\nNumPins : 2\nNetDegree : 2\nb0\nmissing\n",
                encoding="utf-8",
            )
            pl_path.write_text("", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "未知节点"):
                parse_dataset(blocks_path, nets_path, pl_path)


class DirectModelTests(unittest.TestCase):
    def test_two_rectangles_reach_exact_area(self) -> None:
        problem = FloorplanProblem(
            source=Path("tiny.blocks"),
            blocks=(Block("b0", 2, 3), Block("b1", 2, 2)),
            terminal_names=(),
        )
        solution = solve_q1(
            problem,
            area_time_limit=5,
            shape_time_limit=5,
            workers=1,
            seed=7,
        )
        validate_solution(problem, solution)
        self.assertEqual(solution.area, 10)
        self.assertTrue(solution.area_proven_optimal)
        self.assertTrue(solution.lexicographic_proven_optimal)


if __name__ == "__main__":
    unittest.main()
