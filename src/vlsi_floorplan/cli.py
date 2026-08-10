"""问题 1 直接求解命令入口。"""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path

from .data import parse_blocks
from .output import write_solution_json, write_solution_svg
from .q1 import solve_q1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MaxRects + CP-SAT 混合求解华数杯 B 题问题 1")
    parser.add_argument("blocks", type=Path, help="输入 .blocks 文件")
    parser.add_argument("--output-dir", type=Path, default=None, help="结果目录，默认 outputs/q1/<数据集>")
    parser.add_argument("--area-time-limit", type=float, default=30.0, help="面积阶段秒数")
    parser.add_argument("--shape-time-limit", type=float, default=10.0, help="同面积长宽差阶段秒数")
    parser.add_argument("--workers", type=int, default=8, help="CP-SAT 并行 worker 数")
    parser.add_argument("--seed", type=int, default=20260810, help="随机种子")
    parser.add_argument("--width-multiplier", type=float, default=1.8, help="构造宽度扫描上界相对 sqrt(S) 的倍数")
    parser.add_argument("--width-samples", type=int, default=64, help="构造阶段采样的候选宽度数")
    parser.add_argument("--random-starts", type=int, default=24, help="随机扰动排序的构造次数")
    parser.add_argument("--local-iterations", type=int, default=120, help="严格改进型局部搜索迭代数")
    parser.add_argument("--construction-time-limit", type=float, default=75.0, help="MaxRects 构造与局部改进总秒数")
    parser.add_argument("--factor-pair-time-limit", type=float, default=2.0, help="单个面积因子对的可行性检查秒数")
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
        width_multiplier=args.width_multiplier,
        width_samples=args.width_samples,
        random_starts=args.random_starts,
        local_iterations=args.local_iterations,
        factor_pair_time_limit=args.factor_pair_time_limit,
        construction_time_limit=args.construction_time_limit,
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
        "construction_area": solution.construction.area_after_local_search,
        "construction_seconds": solution.construction.wall_time_seconds,
        "area_status": solution.area_phase.status,
        "area_best_bound": solution.area_phase.best_bound,
        "shape_status": solution.shape_phase.status if solution.shape_phase else None,
        "factor_search": asdict(solution.factor_search) if solution.factor_search else None,
        "json": str(json_path.resolve()),
        "svg": str(svg_path.resolve()),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
