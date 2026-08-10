"""问题 2 的固定正方形 B*-Tree + Fast-SA 模型与独立校验。"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from math import isclose, isqrt, sqrt
from time import perf_counter

from .bstar import (
    FastSAStats,
    bstar_tree_from_placements,
    complete_bstar_tree,
    fast_simulated_annealing,
)
from .construct import pack_maxrects
from .data import FloorplanDataset
from .q1 import Placement


@dataclass(frozen=True, slots=True)
class Q2ConstructionStats:
    """固定轮廓 MaxRects 初始可行上界及 B*-Tree 转换统计。"""

    attempts: int
    feasible_attempts: int
    initial_hpwl2: int
    bstar_seed_available: bool
    bstar_seed_feasible: bool
    wall_time_seconds: float


@dataclass(frozen=True, slots=True)
class Q2Solution:
    """问题 2 的固定轮廓布局及可复算线网指标。"""

    method: str
    dead_space_ratio: float
    chip_side: float
    coordinate_limit: int
    total_block_area: int
    placements: tuple[Placement, ...]
    net_hpwl2: tuple[int, ...]
    total_hpwl2: int
    construction: Q2ConstructionStats
    feasibility_annealing: FastSAStats | None
    annealing: FastSAStats
    seed: int

    @property
    def total_hpwl(self) -> float:
        return self.total_hpwl2 / 2

    @property
    def hpwl_proven_optimal(self) -> bool:
        """Fast-SA 构造的是可行上界，不提供 HPWL 全局最优证明。"""

        return False

    @property
    def effective_integer_dead_space_ratio(self) -> float:
        return self.coordinate_limit**2 / self.total_block_area - 1.0


def outline_dimensions(total_block_area: int, dead_space_ratio: float) -> tuple[float, int]:
    """返回题目真实边长与整数坐标模型使用的 ``floor(L)``。"""

    if dead_space_ratio < 0:
        raise ValueError("死区比例不能为负")
    ratio = Fraction(str(dead_space_ratio))
    area_factor = ratio + 1
    scaled_numerator = total_block_area * area_factor.numerator
    coordinate_limit = isqrt(scaled_numerator // area_factor.denominator)
    chip_side = sqrt(total_block_area * float(area_factor))
    return chip_side, coordinate_limit


def _terminal_coordinate2(value: float, name: str, axis: str) -> int:
    doubled = value * 2
    rounded = round(doubled)
    if not isclose(doubled, rounded, rel_tol=0.0, abs_tol=1e-9):
        raise ValueError(f"{name}: Terminal {axis} 坐标必须是 0.5 的整数倍")
    return int(rounded)


def compute_net_hpwl2(
    dataset: FloorplanDataset,
    placements: tuple[Placement, ...],
) -> tuple[int, ...]:
    """不依赖搜索器，按题目中心引脚口径计算每条线网的两倍 HPWL。"""

    centers2 = {
        placement.name: (
            2 * placement.x + placement.width,
            2 * placement.y + placement.height,
        )
        for placement in placements
    }
    centers2.update(
        {
            terminal.name: (
                _terminal_coordinate2(terminal.x, terminal.name, "X"),
                _terminal_coordinate2(terminal.y, terminal.name, "Y"),
            )
            for terminal in dataset.terminals
        }
    )

    hpwl2_values: list[int] = []
    for net in dataset.nets:
        try:
            points = [centers2[pin] for pin in net.pins]
        except KeyError as error:
            raise ValueError(f"线网引用未知节点：{error.args[0]}") from error
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        hpwl2_values.append(max(xs) - min(xs) + max(ys) - min(ys))
    return tuple(hpwl2_values)


def construct_fixed_outline_seed(
    dataset: FloorplanDataset,
    coordinate_limit: int,
) -> tuple[tuple[Placement, ...], Q2ConstructionStats]:
    """用多排序、多规则 MaxRects 构造初始可行解，不承担最终优化。"""

    started = perf_counter()
    order_keys = (
        lambda block: (-block.area, -max(block.width, block.height), block.name),
        lambda block: (-max(block.width, block.height), -block.area, block.name),
        lambda block: (-abs(block.width - block.height), -block.area, block.name),
        lambda block: (-(block.width + block.height), -block.area, block.name),
    )
    rules = ("best_short_side_fit", "min_area", "bottom_left", "best_area_fit")
    attempts = 0
    candidates: list[tuple[int, tuple[Placement, ...]]] = []
    block_order = {block.name: index for index, block in enumerate(dataset.problem.blocks)}

    for rule in rules:
        for order_key in order_keys:
            attempts += 1
            layout = pack_maxrects(
                sorted(dataset.problem.blocks, key=order_key),
                coordinate_limit,
                rule=rule,
                height_cap=coordinate_limit,
            )
            if layout is None:
                continue
            placements = tuple(
                Placement(
                    name=placement.name,
                    x=placement.x,
                    y=placement.y,
                    width=placement.width,
                    height=placement.height,
                    rotated=placement.rotated,
                )
                for placement in sorted(
                    layout.placements, key=lambda placement: block_order[placement.name]
                )
            )
            candidates.append((sum(compute_net_hpwl2(dataset, placements)), placements))

    if not candidates:
        raise RuntimeError("MaxRects 未能在固定正方形轮廓内构造可行布局")
    initial_hpwl2, placements = min(candidates, key=lambda candidate: candidate[0])
    seed_tree = bstar_tree_from_placements(dataset.problem, placements)
    seed_feasible = False
    if seed_tree is not None:
        from .bstar import decode_bstar_tree

        decoded = decode_bstar_tree(dataset.problem, seed_tree)
        seed_feasible = (
            decoded.width <= coordinate_limit and decoded.height <= coordinate_limit
        )
    return placements, Q2ConstructionStats(
        attempts=attempts,
        feasible_attempts=len(candidates),
        initial_hpwl2=initial_hpwl2,
        bstar_seed_available=seed_tree is not None,
        bstar_seed_feasible=seed_feasible,
        wall_time_seconds=perf_counter() - started,
    )


def solve_q2(
    dataset: FloorplanDataset,
    *,
    dead_space_ratio: float = 0.15,
    iterations_per_restart: int = 30_000,
    restarts: int = 2,
    optimization_time_limit: float = 60.0,
    seed: int = 20260810,
) -> Q2Solution:
    """以 MaxRects 为可行上界，使用 B*-Tree + 三阶段 Fast-SA 优化 HPWL。"""

    if optimization_time_limit <= 0:
        raise ValueError("optimization_time_limit 必须为正")
    chip_side, coordinate_limit = outline_dimensions(
        dataset.problem.total_block_area, dead_space_ratio
    )
    incumbent, construction = construct_fixed_outline_seed(dataset, coordinate_limit)
    initial_tree = bstar_tree_from_placements(dataset.problem, incumbent)
    if initial_tree is None:
        initial_tree = complete_bstar_tree(dataset.problem, outline_limit=coordinate_limit)

    feasibility_stats: FastSAStats | None = None
    search_tree = initial_tree
    remaining_time = optimization_time_limit
    if not construction.bstar_seed_feasible:
        feasibility = fast_simulated_annealing(
            dataset.problem,
            outline_limit=coordinate_limit,
            objective="feasibility",
            initial_tree=initial_tree,
            iterations_per_restart=iterations_per_restart,
            restarts=restarts,
            seed=seed,
            time_limit=max(0.1, 0.6 * optimization_time_limit),
            stop_on_first_feasible=True,
        )
        feasibility_stats = feasibility.stats
        search_tree = feasibility.tree
        remaining_time = max(0.1, optimization_time_limit - feasibility.stats.wall_time_seconds)

    annealed = fast_simulated_annealing(
        dataset.problem,
        outline_limit=coordinate_limit,
        objective="hpwl",
        dataset=dataset,
        initial_tree=search_tree,
        iterations_per_restart=iterations_per_restart,
        restarts=restarts,
        seed=seed,
        time_limit=remaining_time,
    )
    incumbent_hpwl2 = construction.initial_hpwl2
    if annealed.feasible and annealed.total_hpwl2 is not None and annealed.total_hpwl2 <= incumbent_hpwl2:
        placements = annealed.placements
        method = "bstar-fast-sa"
    else:
        placements = incumbent
        method = "bstar-fast-sa-maxrects-incumbent"

    net_hpwl2 = compute_net_hpwl2(dataset, placements)
    solution = Q2Solution(
        method=method,
        dead_space_ratio=dead_space_ratio,
        chip_side=chip_side,
        coordinate_limit=coordinate_limit,
        total_block_area=dataset.problem.total_block_area,
        placements=placements,
        net_hpwl2=net_hpwl2,
        total_hpwl2=sum(net_hpwl2),
        construction=construction,
        feasibility_annealing=feasibility_stats,
        annealing=annealed.stats,
        seed=seed,
    )
    validate_q2_solution(dataset, solution)
    return solution


def validate_fixed_outline_placements(
    dataset: FloorplanDataset,
    placements: tuple[Placement, ...],
    coordinate_limit: int,
) -> None:
    """统一检查模块集合、旋转、非负坐标、边界与两两不重叠。"""

    placement_by_name = {placement.name: placement for placement in placements}
    if len(placement_by_name) != len(placements):
        raise ValueError("布局中存在重复模块")
    expected_names = {block.name for block in dataset.problem.blocks}
    if set(placement_by_name) != expected_names:
        raise ValueError("布局模块集合与输入不一致")

    for block in dataset.problem.blocks:
        placement = placement_by_name[block.name]
        expected_dimensions = (
            (block.height, block.width) if placement.rotated else (block.width, block.height)
        )
        if (placement.width, placement.height) != expected_dimensions:
            raise ValueError(f"{block.name}: 旋转状态与宽高不一致")
        if placement.x < 0 or placement.y < 0:
            raise ValueError(f"{block.name}: 坐标不能为负")
        if placement.x + placement.width > coordinate_limit:
            raise ValueError(f"{block.name}: 超出芯片右边界")
        if placement.y + placement.height > coordinate_limit:
            raise ValueError(f"{block.name}: 超出芯片上边界")

    for index, first in enumerate(placements):
        for second in placements[index + 1 :]:
            separated = (
                first.x + first.width <= second.x
                or second.x + second.width <= first.x
                or first.y + first.height <= second.y
                or second.y + second.height <= first.y
            )
            if not separated:
                raise ValueError(f"{first.name} 与 {second.name} 重叠")


def validate_q2_solution(dataset: FloorplanDataset, solution: Q2Solution) -> None:
    """独立检查固定边界、旋转、不重叠以及逐网 HPWL。"""

    expected_side, expected_limit = outline_dimensions(
        dataset.problem.total_block_area, solution.dead_space_ratio
    )
    if not isclose(solution.chip_side, expected_side, rel_tol=0.0, abs_tol=1e-9):
        raise ValueError("记录的芯片边长与模块总面积、死区比例不一致")
    if solution.coordinate_limit != expected_limit:
        raise ValueError("记录的整数坐标边界与真实芯片边长不一致")
    validate_fixed_outline_placements(dataset, solution.placements, solution.coordinate_limit)

    net_hpwl2 = compute_net_hpwl2(dataset, solution.placements)
    if solution.net_hpwl2 != net_hpwl2:
        raise ValueError("记录的逐网 HPWL 与独立复算结果不一致")
    if solution.total_hpwl2 != sum(net_hpwl2):
        raise ValueError("记录的总 HPWL 与逐网求和不一致")
    if solution.total_hpwl2 > solution.construction.initial_hpwl2:
        raise ValueError("最终 HPWL 超过 MaxRects 已知可行上界")
