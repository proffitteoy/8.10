"""问题 1 在安全静态剪枝后的离散搜索空间计数。"""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass
import json
from math import isqrt, log10
from pathlib import Path

from .data import Block, FloorplanProblem, parse_blocks
from .q1 import factor_pairs


@dataclass(frozen=True, slots=True)
class OutlineBounds:
    """与问题 1 CP-SAT 面积阶段一致的安全整数轮廓边界。"""

    width_lower: int
    width_upper: int
    height_lower: int
    height_upper: int


@dataclass(frozen=True, slots=True)
class SearchSpaceAnalysis:
    """一组数据的精确静态计数及忽略重叠后的组合上界。"""

    dataset: str
    block_count: int
    non_square_blocks: int
    total_block_area: int
    best_width: int
    best_height: int
    area_upper_bound: int
    bounds: OutlineBounds
    finite_domain_outline_pairs: int
    ordered_outline_pairs: int
    area_bounded_outline_pairs: int
    module_fit_outline_pairs: int
    distinct_rotation_assignments: int
    factor_pairs_at_best_area: int
    factor_pairs_passing_module_fit: int
    closer_factor_pairs: int
    closer_factor_pairs_passing_module_fit: int
    fixed_outline_relaxed_assignments: int
    explicit_cp_scalar_variables: int

    @property
    def fixed_outline_log10(self) -> float:
        return _integer_log10(self.fixed_outline_relaxed_assignments)

def _integer_log10(value: int) -> float:
    if value <= 0:
        raise ValueError("组合数必须为正整数")
    text = str(value)
    leading = int(text[:16])
    return len(text) - 16 + log10(leading) if len(text) > 16 else log10(value)


def scientific_notation(value: int, significant_digits: int = 4) -> str:
    """不经浮点溢出地格式化任意大整数。"""

    if value < 0:
        raise ValueError("只支持非负整数")
    text = str(value)
    if len(text) <= significant_digits:
        return text
    return f"{text[0]}.{text[1:significant_digits]}e{len(text) - 1}"


def outline_bounds(problem: FloorplanProblem, area_upper_bound: int) -> OutlineBounds:
    """复现面积模型中由面积上界导出的安全边界。"""

    total_area = problem.total_block_area
    if area_upper_bound < total_area:
        raise ValueError("面积上界不能小于模块总面积")
    minimum_side = max(min(block.width, block.height) for block in problem.blocks)
    return OutlineBounds(
        width_lower=max(minimum_side, isqrt(total_area - 1) + 1),
        width_upper=area_upper_bound // minimum_side,
        height_lower=minimum_side,
        height_upper=isqrt(area_upper_bound),
    )


def _orientations(block: Block) -> tuple[tuple[int, int], ...]:
    if block.width == block.height:
        return ((block.width, block.height),)
    return ((block.width, block.height), (block.height, block.width))


def _all_modules_fit(problem: FloorplanProblem, width: int, height: int) -> bool:
    return all(
        any(block_width <= width and block_height <= height for block_width, block_height in _orientations(block))
        for block in problem.blocks
    )


def _relaxed_assignment_count(problem: FloorplanProblem, width: int, height: int) -> int:
    """精确计算忽略模块间重叠时，各模块方向与整数坐标状态数之积。"""

    result = 1
    for block in problem.blocks:
        states = sum(
            (width - block_width + 1) * (height - block_height + 1)
            for block_width, block_height in _orientations(block)
            if block_width <= width and block_height <= height
        )
        if states == 0:
            return 0
        result *= states
    return result


def analyze_search_space(
    problem: FloorplanProblem,
    *,
    dataset: str,
    best_width: int,
    best_height: int,
    area_upper_bound: int,
) -> SearchSpaceAnalysis:
    """按当前 CP-SAT 边界逐层计数，并计算两个放松搜索空间上界。"""

    if best_width < best_height:
        raise ValueError("计数口径要求 best_width >= best_height")
    if best_width * best_height != area_upper_bound:
        raise ValueError("最好轮廓宽高与面积上界不一致")

    bounds = outline_bounds(problem, area_upper_bound)
    finite_domain_pairs = (
        (bounds.width_upper - bounds.width_lower + 1)
        * (bounds.height_upper - bounds.height_lower + 1)
    )
    ordered_pairs = 0
    area_bounded_pairs = 0
    module_fit_pairs = 0
    required_width = max(max(block.width, block.height) for block in problem.blocks)
    required_height = max(min(block.width, block.height) for block in problem.blocks)

    for width in range(bounds.width_lower, bounds.width_upper + 1):
        ordered_height_upper = min(bounds.height_upper, width)
        ordered_pairs += max(0, ordered_height_upper - bounds.height_lower + 1)

        area_height_lower = max(
            bounds.height_lower,
            (problem.total_block_area + width - 1) // width,
        )
        area_height_upper = min(ordered_height_upper, area_upper_bound // width)
        area_bounded_pairs += max(0, area_height_upper - area_height_lower + 1)

        # 在 W>=H 时，任一矩形总可把长边沿 W 放置；因此全体模块至少
        # 各有一个可用方向，当且仅当这两个全局边长条件成立。
        if width >= required_width:
            fit_height_lower = max(area_height_lower, required_height)
            module_fit_pairs += max(0, area_height_upper - fit_height_lower + 1)

    current_gap = best_width - best_height
    best_area_pairs = factor_pairs(area_upper_bound)
    passing_factor_pairs = [
        pair for pair in best_area_pairs if _all_modules_fit(problem, pair[0], pair[1])
    ]
    closer_pairs = [pair for pair in best_area_pairs if pair[0] - pair[1] < current_gap]
    closer_passing_pairs = [
        pair for pair in closer_pairs if _all_modules_fit(problem, pair[0], pair[1])
    ]
    non_square_blocks = sum(block.width != block.height for block in problem.blocks)

    return SearchSpaceAnalysis(
        dataset=dataset,
        block_count=len(problem.blocks),
        non_square_blocks=non_square_blocks,
        total_block_area=problem.total_block_area,
        best_width=best_width,
        best_height=best_height,
        area_upper_bound=area_upper_bound,
        bounds=bounds,
        finite_domain_outline_pairs=finite_domain_pairs,
        ordered_outline_pairs=ordered_pairs,
        area_bounded_outline_pairs=area_bounded_pairs,
        module_fit_outline_pairs=module_fit_pairs,
        distinct_rotation_assignments=1 << non_square_blocks,
        factor_pairs_at_best_area=len(best_area_pairs),
        factor_pairs_passing_module_fit=len(passing_factor_pairs),
        closer_factor_pairs=len(closer_pairs),
        closer_factor_pairs_passing_module_fit=len(closer_passing_pairs),
        fixed_outline_relaxed_assignments=_relaxed_assignment_count(
            problem, best_width, best_height
        ),
        explicit_cp_scalar_variables=7 * len(problem.blocks) + 5,
    )


def _json_record(analysis: SearchSpaceAnalysis) -> dict[str, object]:
    record = asdict(analysis)
    record["fixed_outline_log10"] = analysis.fixed_outline_log10
    record["fixed_outline_scientific"] = scientific_notation(
        analysis.fixed_outline_relaxed_assignments
    )
    return record


def _write_outputs(analyses: list[SearchSpaceAnalysis], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    records = [_json_record(analysis) for analysis in analyses]
    (output_dir / "analysis.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    fieldnames = [
        "dataset",
        "block_count",
        "non_square_blocks",
        "total_block_area",
        "area_upper_bound",
        "best_outline",
        "finite_domain_outline_pairs",
        "ordered_outline_pairs",
        "area_bounded_outline_pairs",
        "module_fit_outline_pairs",
        "distinct_rotation_assignments",
        "factor_pairs_at_best_area",
        "factor_pairs_passing_module_fit",
        "closer_factor_pairs",
        "closer_factor_pairs_passing_module_fit",
        "fixed_outline_scientific",
        "fixed_outline_log10",
        "explicit_cp_scalar_variables",
    ]
    with (output_dir / "summary.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for analysis, record in zip(analyses, records, strict=True):
            writer.writerow(
                {
                    "dataset": analysis.dataset,
                    "block_count": analysis.block_count,
                    "non_square_blocks": analysis.non_square_blocks,
                    "total_block_area": analysis.total_block_area,
                    "area_upper_bound": analysis.area_upper_bound,
                    "best_outline": f"{analysis.best_width}x{analysis.best_height}",
                    "finite_domain_outline_pairs": analysis.finite_domain_outline_pairs,
                    "ordered_outline_pairs": analysis.ordered_outline_pairs,
                    "area_bounded_outline_pairs": analysis.area_bounded_outline_pairs,
                    "module_fit_outline_pairs": analysis.module_fit_outline_pairs,
                    "distinct_rotation_assignments": analysis.distinct_rotation_assignments,
                    "factor_pairs_at_best_area": analysis.factor_pairs_at_best_area,
                    "factor_pairs_passing_module_fit": analysis.factor_pairs_passing_module_fit,
                    "closer_factor_pairs": analysis.closer_factor_pairs,
                    "closer_factor_pairs_passing_module_fit": analysis.closer_factor_pairs_passing_module_fit,
                    "fixed_outline_scientific": record["fixed_outline_scientific"],
                    "fixed_outline_log10": f"{analysis.fixed_outline_log10:.6f}",
                    "explicit_cp_scalar_variables": analysis.explicit_cp_scalar_variables,
                }
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="统计问题 1 静态剪枝后的离散搜索空间")
    parser.add_argument(
        "--summary",
        type=Path,
        default=Path("outputs/q1_hybrid/summary.csv"),
        help="包含 dataset、width、height、area 的 Q1 汇总 CSV",
    )
    parser.add_argument("--attachments-dir", type=Path, default=Path("附件"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/q1_space"))
    args = parser.parse_args()

    analyses: list[SearchSpaceAnalysis] = []
    with args.summary.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            dataset = row["dataset"]
            problem = parse_blocks(args.attachments_dir / f"{dataset}.blocks")
            analyses.append(
                analyze_search_space(
                    problem,
                    dataset=dataset,
                    best_width=int(row["width"]),
                    best_height=int(row["height"]),
                    area_upper_bound=int(row["area"]),
                )
            )

    _write_outputs(analyses, args.output_dir)
    print(json.dumps([_json_record(item) for item in analyses], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
