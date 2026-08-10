"""问题 2 固定轮廓 B*-Tree + Fast-SA 命令入口。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .data import parse_dataset
from .output import write_q2_solution_json, write_q2_solution_svg
from .q2 import solve_q2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="B*-Tree + Fast-SA 求解华数杯 B 题问题 2")
    parser.add_argument("blocks", type=Path, help="输入 .blocks 文件")
    parser.add_argument("nets", type=Path, help="输入 .nets 文件")
    parser.add_argument("pl", type=Path, help="输入 .pl 文件")
    parser.add_argument(
        "--output-dir", type=Path, default=None, help="结果目录，默认 outputs/q2/<数据集>"
    )
    parser.add_argument("--dead-space-ratio", type=float, default=0.15, help="死区比例")
    parser.add_argument("--iterations-per-restart", type=int, default=30_000, help="每次重启迭代数")
    parser.add_argument("--restarts", type=int, default=2, help="Fast-SA 重启次数")
    parser.add_argument("--optimization-time-limit", type=float, default=60.0, help="HPWL 优化阶段秒数")
    parser.add_argument("--seed", type=int, default=20260810, help="随机种子")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    dataset = parse_dataset(args.blocks, args.nets, args.pl)
    solution = solve_q2(
        dataset,
        dead_space_ratio=args.dead_space_ratio,
        iterations_per_restart=args.iterations_per_restart,
        restarts=args.restarts,
        optimization_time_limit=args.optimization_time_limit,
        seed=args.seed,
    )

    output_dir = args.output_dir or Path("outputs") / "q2" / dataset.problem.source.stem
    json_path = write_q2_solution_json(dataset, solution, output_dir / "solution.json")
    svg_path = write_q2_solution_svg(solution, output_dir / "layout.svg")
    summary = {
        "dataset": dataset.problem.source.stem,
        "method": solution.method,
        "dead_space_ratio": solution.dead_space_ratio,
        "chip_side": solution.chip_side,
        "integer_coordinate_limit": solution.coordinate_limit,
        "total_hpwl": solution.total_hpwl,
        "annealing_iterations": solution.annealing.completed_iterations,
        "feasible_evaluations": solution.annealing.feasible_evaluations,
        "hpwl_proven_optimal": solution.hpwl_proven_optimal,
        "json": str(json_path.resolve()),
        "svg": str(svg_path.resolve()),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
