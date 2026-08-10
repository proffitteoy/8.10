"""赛题图 3 的问题 4 精确求解命令入口。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .q4 import figure3_modules, solve_q4
from .q4_output import write_q4_solution_json, write_q4_solution_svg


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="精确求解华数杯 B 题问题 4 的图 3 实例")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs") / "q4" / "figure3",
        help="结果目录",
    )
    parser.add_argument(
        "--time-limit-per-outline",
        type=float,
        default=10.0,
        help="每个候选轮廓的 CP-SAT 求解秒数",
    )
    parser.add_argument("--workers", type=int, default=1, help="CP-SAT worker 数")
    parser.add_argument("--seed", type=int, default=20260810, help="随机种子")
    parser.add_argument("--log-search", action="store_true", help="打印 CP-SAT 搜索日志")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    modules = figure3_modules()
    solution = solve_q4(
        modules,
        time_limit_per_outline=args.time_limit_per_outline,
        workers=args.workers,
        seed=args.seed,
        log_search=args.log_search,
    )
    json_path = write_q4_solution_json(modules, solution, args.output_dir / "solution.json")
    svg_path = write_q4_solution_svg(solution, args.output_dir / "layout.svg")
    summary = {
        "case": "figure3",
        "outline": [solution.width, solution.height],
        "area": solution.area,
        "module_area": solution.total_module_area,
        "dead_space_ratio": solution.dead_space_ratio,
        "aspect_ratio": solution.aspect_ratio,
        "area_proven_optimal": solution.area_proven_optimal,
        "lexicographic_proven_optimal": solution.lexicographic_proven_optimal,
        "checked_outlines": solution.search.checked_outlines,
        "json": str(json_path.resolve()),
        "svg": str(svg_path.resolve()),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

