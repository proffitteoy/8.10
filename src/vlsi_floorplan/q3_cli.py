"""问题 3 临界可行边界搜索命令入口。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .data import parse_dataset
from .output import write_q2_solution_svg, write_q3_solution_json
from .q3 import solve_q3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="求解华数杯 B 题问题 3")
    parser.add_argument("blocks", type=Path, help="输入 .blocks 文件")
    parser.add_argument("nets", type=Path, help="输入 .nets 文件")
    parser.add_argument("pl", type=Path, help="输入 .pl 文件")
    parser.add_argument(
        "--output-dir", type=Path, default=None, help="结果目录，默认 outputs/q3/<数据集>"
    )
    parser.add_argument("--heuristic-iterations", type=int, default=2_000)
    parser.add_argument("--heuristic-restarts", type=int, default=3)
    parser.add_argument("--heuristic-time-limit", type=float, default=10.0)
    parser.add_argument("--exact-time-limit", type=float, default=30.0)
    parser.add_argument("--exact-workers", type=int, default=8)
    parser.add_argument("--hpwl-iterations", type=int, default=10_000)
    parser.add_argument("--hpwl-restarts", type=int, default=4)
    parser.add_argument("--hpwl-time-limit", type=float, default=60.0)
    parser.add_argument("--seed", type=int, default=20260810)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    dataset = parse_dataset(args.blocks, args.nets, args.pl)
    solution = solve_q3(
        dataset,
        heuristic_iterations_per_restart=args.heuristic_iterations,
        heuristic_restarts=args.heuristic_restarts,
        heuristic_time_limit_per_side=args.heuristic_time_limit,
        exact_time_limit_per_side=args.exact_time_limit,
        exact_workers=args.exact_workers,
        hpwl_iterations_per_restart=args.hpwl_iterations,
        hpwl_restarts=args.hpwl_restarts,
        hpwl_time_limit=args.hpwl_time_limit,
        seed=args.seed,
    )
    output_dir = args.output_dir or Path("outputs") / "q3" / dataset.problem.source.stem
    json_path = write_q3_solution_json(dataset, solution, output_dir / "solution.json")
    svg_path = write_q2_solution_svg(solution, output_dir / "layout.svg")
    summary = {
        "dataset": dataset.problem.source.stem,
        "method": solution.method,
        "chip_side": solution.chip_side,
        "dead_space_ratio": solution.dead_space_ratio,
        "minimum_dead_space_proven": solution.minimum_dead_space_proven,
        "search_status": solution.boundary_search.status,
        "side_interval": [
            solution.boundary_search.final_lower_bound,
            solution.boundary_search.final_feasible_upper_bound,
        ],
        "total_hpwl": solution.total_hpwl,
        "json": str(json_path.resolve()),
        "svg": str(svg_path.resolve()),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
