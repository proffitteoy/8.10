"""问题 1 直接求解命令入口。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .data import parse_blocks
from .output import write_solution_json, write_solution_svg
from .q1 import solve_q1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="直接 CP-SAT 求解华数杯 B 题问题 1")
    parser.add_argument("blocks", type=Path, help="输入 .blocks 文件")
    parser.add_argument("--output-dir", type=Path, default=None, help="结果目录，默认 outputs/q1/<数据集>")
    parser.add_argument("--area-time-limit", type=float, default=30.0, help="面积阶段秒数")
    parser.add_argument("--shape-time-limit", type=float, default=10.0, help="同面积长宽差阶段秒数")
    parser.add_argument("--workers", type=int, default=8, help="CP-SAT 并行 worker 数")
    parser.add_argument("--seed", type=int, default=20260810, help="随机种子")
    parser.add_argument("--log-search", action="store_true", help="打印 CP-SAT 搜索日志")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    problem = parse_blocks(args.blocks)
    solution = solve_q1(
        problem,
        area_time_limit=args.area_time_limit,
        shape_time_limit=args.shape_time_limit,
        workers=args.workers,
        seed=args.seed,
        log_search=args.log_search,
    )

    output_dir = args.output_dir or Path("outputs") / "q1" / problem.source.stem
    json_path = write_solution_json(problem, solution, output_dir / "solution.json")
    svg_path = write_solution_svg(solution, output_dir / "layout.svg")
    summary = {
        "dataset": problem.source.stem,
        "method": solution.method,
        "outline": [solution.width, solution.height],
        "area": solution.area,
        "block_area": solution.total_block_area,
        "dead_space_ratio": solution.dead_space_ratio,
        "aspect_ratio": solution.aspect_ratio,
        "area_status": solution.area_phase.status,
        "area_best_bound": solution.area_phase.best_bound,
        "shape_status": solution.shape_phase.status if solution.shape_phase else None,
        "json": str(json_path.resolve()),
        "svg": str(svg_path.resolve()),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

