"""问题 2 的固定正方形轮廓 CP-SAT 模型与独立结果校验。"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from math import isclose, isqrt, sqrt
from time import perf_counter

from ortools.sat.python import cp_model

from .construct import pack_maxrects
from .data import FloorplanDataset
from .q1 import Placement


@dataclass(frozen=True, slots=True)
class Q2PhaseStats:
    """一次 CP-SAT 阶段的求解统计；HPWL 字段均为真实值的两倍。"""

    status: str
    objective_hpwl2: int | None
    best_bound_hpwl2: float | None
    wall_time_seconds: float
    conflicts: int
    branches: int


@dataclass(frozen=True, slots=True)
class Q2ConstructionStats:
    """固定正方形 MaxRects 初始布局的构造统计。"""

    attempts: int
    feasible_attempts: int
    initial_hpwl2: int
    wall_time_seconds: float


@dataclass(frozen=True, slots=True)
class Q2Solution:
    """问题 2 的固定轮廓布局及可复算的线网指标。"""

    method: str
    dead_space_ratio: float
    chip_side: float
    coordinate_limit: int
    total_block_area: int
    placements: tuple[Placement, ...]
    net_hpwl2: tuple[int, ...]
    total_hpwl2: int
    construction: Q2ConstructionStats
    feasibility_phase: Q2PhaseStats | None
    optimization_phase: Q2PhaseStats
    seed: int
    workers: int

    @property
    def total_hpwl(self) -> float:
        return self.total_hpwl2 / 2

    @property
    def hpwl_proven_optimal(self) -> bool:
        return self.optimization_phase.status == "OPTIMAL"

    @property
    def effective_integer_dead_space_ratio(self) -> float:
        """整数坐标基线实际使用的 `floor(L) × floor(L)` 面积比例。"""

        return self.coordinate_limit**2 / self.total_block_area - 1.0


@dataclass(slots=True)
class _ModelContext:
    model: cp_model.CpModel
    rotations: list[cp_model.IntVar]
    widths: list[cp_model.IntVar]
    heights: list[cp_model.IntVar]
    xs: list[cp_model.IntVar]
    ys: list[cp_model.IntVar]
    total_hpwl2: cp_model.IntVar


def _outline_dimensions(total_block_area: int, dead_space_ratio: float) -> tuple[float, int]:
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


def _build_model(
    dataset: FloorplanDataset,
    coordinate_limit: int,
) -> _ModelContext:
    model = cp_model.CpModel()
    rotations: list[cp_model.IntVar] = []
    widths: list[cp_model.IntVar] = []
    heights: list[cp_model.IntVar] = []
    xs: list[cp_model.IntVar] = []
    ys: list[cp_model.IntVar] = []
    x_intervals: list[cp_model.IntervalVar] = []
    y_intervals: list[cp_model.IntervalVar] = []

    block_centers2: dict[str, tuple[cp_model.IntVar, cp_model.IntVar]] = {}
    for index, block in enumerate(dataset.problem.blocks):
        if min(block.width, block.height) > coordinate_limit:
            raise ValueError(f"{block.name}: 两种朝向都无法放入固定轮廓")

        rotation = model.new_bool_var(f"r_{index}")
        width = model.new_int_var(
            min(block.width, block.height), max(block.width, block.height), f"w_{index}"
        )
        height = model.new_int_var(
            min(block.width, block.height), max(block.width, block.height), f"h_{index}"
        )
        model.add(width == block.width + (block.height - block.width) * rotation)
        model.add(height == block.height + (block.width - block.height) * rotation)

        x = model.new_int_var(0, coordinate_limit, f"x_{index}")
        y = model.new_int_var(0, coordinate_limit, f"y_{index}")
        x_end = model.new_int_var(0, coordinate_limit, f"xe_{index}")
        y_end = model.new_int_var(0, coordinate_limit, f"ye_{index}")
        model.add(x_end == x + width)
        model.add(y_end == y + height)

        center_x2 = model.new_int_var(0, 2 * coordinate_limit, f"cx2_{index}")
        center_y2 = model.new_int_var(0, 2 * coordinate_limit, f"cy2_{index}")
        model.add(center_x2 == 2 * x + width)
        model.add(center_y2 == 2 * y + height)

        rotations.append(rotation)
        widths.append(width)
        heights.append(height)
        xs.append(x)
        ys.append(y)
        x_intervals.append(model.new_interval_var(x, width, x_end, f"xi_{index}"))
        y_intervals.append(model.new_interval_var(y, height, y_end, f"yi_{index}"))
        block_centers2[block.name] = (center_x2, center_y2)

    model.add_no_overlap_2d(x_intervals, y_intervals)

    terminal_centers2 = {
        terminal.name: (
            _terminal_coordinate2(terminal.x, terminal.name, "X"),
            _terminal_coordinate2(terminal.y, terminal.name, "Y"),
        )
        for terminal in dataset.terminals
    }
    terminal_values = [value for point in terminal_centers2.values() for value in point]
    coordinate_low = min([0, *terminal_values])
    coordinate_high = max([2 * coordinate_limit, *terminal_values])
    coordinate_span = coordinate_high - coordinate_low

    net_hpwl2: list[cp_model.IntVar | int] = []
    for net_index, net in enumerate(dataset.nets):
        x_values: list[cp_model.IntVar | int] = []
        y_values: list[cp_model.IntVar | int] = []
        for pin in net.pins:
            center = block_centers2.get(pin, terminal_centers2.get(pin))
            if center is None:  # parse_dataset 已校验，此分支保护直接构造的数据对象。
                raise ValueError(f"线网引用未知节点：{pin}")
            x_values.append(center[0])
            y_values.append(center[1])

        if all(isinstance(value, int) for value in (*x_values, *y_values)):
            hpwl2 = max(x_values) - min(x_values) + max(y_values) - min(y_values)
            net_hpwl2.append(int(hpwl2))
            continue

        x_min = model.new_int_var(coordinate_low, coordinate_high, f"net_xmin_{net_index}")
        x_max = model.new_int_var(coordinate_low, coordinate_high, f"net_xmax_{net_index}")
        y_min = model.new_int_var(coordinate_low, coordinate_high, f"net_ymin_{net_index}")
        y_max = model.new_int_var(coordinate_low, coordinate_high, f"net_ymax_{net_index}")
        model.add_min_equality(x_min, x_values)
        model.add_max_equality(x_max, x_values)
        model.add_min_equality(y_min, y_values)
        model.add_max_equality(y_max, y_values)
        hpwl2 = model.new_int_var(0, 2 * coordinate_span, f"net_hpwl2_{net_index}")
        model.add(hpwl2 == x_max - x_min + y_max - y_min)
        net_hpwl2.append(hpwl2)

    total_upper = 2 * coordinate_span * len(dataset.nets)
    total_hpwl2 = model.new_int_var(0, total_upper, "total_hpwl2")
    model.add(total_hpwl2 == sum(net_hpwl2))
    return _ModelContext(
        model=model,
        rotations=rotations,
        widths=widths,
        heights=heights,
        xs=xs,
        ys=ys,
        total_hpwl2=total_hpwl2,
    )


def _construct_fixed_outline_hint(
    dataset: FloorplanDataset,
    coordinate_limit: int,
) -> tuple[tuple[Placement, ...], Q2ConstructionStats]:
    """用多排序、多规则 MaxRects 构造固定正方形内的低 HPWL 初始布局。"""

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
    return placements, Q2ConstructionStats(
        attempts=attempts,
        feasible_attempts=len(candidates),
        initial_hpwl2=initial_hpwl2,
        wall_time_seconds=perf_counter() - started,
    )


def _configure_solver(
    time_limit: float,
    workers: int,
    seed: int,
    log_search: bool,
) -> cp_model.CpSolver:
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_search_workers = workers
    solver.parameters.random_seed = seed
    solver.parameters.log_search_progress = log_search
    return solver


def _phase_stats(
    solver: cp_model.CpSolver,
    status: cp_model.CpSolverStatus,
    *,
    has_objective: bool,
) -> Q2PhaseStats:
    has_solution = status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    return Q2PhaseStats(
        status=solver.status_name(status),
        objective_hpwl2=(
            int(round(solver.objective_value)) if has_objective and has_solution else None
        ),
        best_bound_hpwl2=(
            solver.best_objective_bound if has_objective and has_solution else None
        ),
        wall_time_seconds=solver.wall_time,
        conflicts=solver.num_conflicts,
        branches=solver.num_branches,
    )


def _extract_placements(
    dataset: FloorplanDataset,
    context: _ModelContext,
    solver: cp_model.CpSolver,
) -> tuple[Placement, ...]:
    return tuple(
        Placement(
            name=block.name,
            x=solver.value(context.xs[index]),
            y=solver.value(context.ys[index]),
            width=solver.value(context.widths[index]),
            height=solver.value(context.heights[index]),
            rotated=bool(solver.value(context.rotations[index])),
        )
        for index, block in enumerate(dataset.problem.blocks)
    )


def _replace_geometry_hints(context: _ModelContext, placements: tuple[Placement, ...]) -> None:
    if hasattr(context.model, "clear_hints"):
        context.model.clear_hints()
    for index, placement in enumerate(placements):
        context.model.add_hint(context.rotations[index], int(placement.rotated))
        context.model.add_hint(context.widths[index], placement.width)
        context.model.add_hint(context.heights[index], placement.height)
        context.model.add_hint(context.xs[index], placement.x)
        context.model.add_hint(context.ys[index], placement.y)


def compute_net_hpwl2(
    dataset: FloorplanDataset,
    placements: tuple[Placement, ...],
) -> tuple[int, ...]:
    """不依赖求解器，按题目中心引脚口径计算每条线网的两倍 HPWL。"""

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


def solve_q2(
    dataset: FloorplanDataset,
    *,
    dead_space_ratio: float = 0.15,
    feasibility_time_limit: float = 30.0,
    optimization_time_limit: float = 60.0,
    workers: int = 8,
    seed: int = 20260810,
    log_search: bool = False,
) -> Q2Solution:
    """先寻找固定轮廓可行布局，再以该布局为提示最小化总 HPWL。"""

    if feasibility_time_limit < 0 or optimization_time_limit <= 0:
        raise ValueError("可行性阶段可设为 0，优化阶段时间限制必须为正")
    if workers <= 0:
        raise ValueError("workers 必须为正整数")

    chip_side, coordinate_limit = _outline_dimensions(
        dataset.problem.total_block_area, dead_space_ratio
    )
    incumbent_placements, construction_stats = _construct_fixed_outline_hint(
        dataset, coordinate_limit
    )
    context = _build_model(dataset, coordinate_limit)
    _replace_geometry_hints(context, incumbent_placements)
    feasibility_stats: Q2PhaseStats | None = None

    if feasibility_time_limit > 0:
        feasibility_solver = _configure_solver(
            feasibility_time_limit, workers, seed, log_search
        )
        feasibility_status = feasibility_solver.solve(context.model)
        feasibility_stats = _phase_stats(
            feasibility_solver, feasibility_status, has_objective=False
        )
        if feasibility_status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            incumbent_placements = _extract_placements(dataset, context, feasibility_solver)
            _replace_geometry_hints(context, incumbent_placements)
        elif feasibility_status == cp_model.INFEASIBLE:
            raise RuntimeError("求解器证明整数坐标固定轮廓下无可行布局")

    context.model.minimize(context.total_hpwl2)
    optimization_solver = _configure_solver(
        optimization_time_limit, workers, seed, log_search
    )
    optimization_status = optimization_solver.solve(context.model)
    optimization_stats = _phase_stats(
        optimization_solver, optimization_status, has_objective=True
    )

    if optimization_status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        placements = _extract_placements(dataset, context, optimization_solver)
        method = "cp-sat-fixed-outline-hpwl"
    else:
        placements = incumbent_placements
        method = "cp-sat-feasible-fallback"

    net_hpwl2 = compute_net_hpwl2(dataset, placements)
    if optimization_status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        modeled_hpwl2 = optimization_solver.value(context.total_hpwl2)
        if modeled_hpwl2 != sum(net_hpwl2):
            raise RuntimeError("CP-SAT 目标值与独立逐网 HPWL 复算不一致")
    solution = Q2Solution(
        method=method,
        dead_space_ratio=dead_space_ratio,
        chip_side=chip_side,
        coordinate_limit=coordinate_limit,
        total_block_area=dataset.problem.total_block_area,
        placements=placements,
        net_hpwl2=net_hpwl2,
        total_hpwl2=sum(net_hpwl2),
        construction=construction_stats,
        feasibility_phase=feasibility_stats,
        optimization_phase=optimization_stats,
        seed=seed,
        workers=workers,
    )
    validate_q2_solution(dataset, solution)
    return solution


def validate_q2_solution(dataset: FloorplanDataset, solution: Q2Solution) -> None:
    """独立检查固定边界、旋转、不重叠以及逐网 HPWL。"""

    expected_side, expected_limit = _outline_dimensions(
        dataset.problem.total_block_area, solution.dead_space_ratio
    )
    if not isclose(solution.chip_side, expected_side, rel_tol=0.0, abs_tol=1e-9):
        raise ValueError("记录的芯片边长与模块总面积、死区比例不一致")
    if solution.coordinate_limit != expected_limit:
        raise ValueError("记录的整数坐标边界与真实芯片边长不一致")

    placement_by_name = {placement.name: placement for placement in solution.placements}
    if len(placement_by_name) != len(solution.placements):
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
        if placement.x + placement.width > solution.coordinate_limit:
            raise ValueError(f"{block.name}: 超出芯片右边界")
        if placement.y + placement.height > solution.coordinate_limit:
            raise ValueError(f"{block.name}: 超出芯片上边界")

    for index, first in enumerate(solution.placements):
        for second in solution.placements[index + 1 :]:
            separated = (
                first.x + first.width <= second.x
                or second.x + second.width <= first.x
                or first.y + first.height <= second.y
                or second.y + second.height <= first.y
            )
            if not separated:
                raise ValueError(f"{first.name} 与 {second.name} 重叠")

    net_hpwl2 = compute_net_hpwl2(dataset, solution.placements)
    if solution.net_hpwl2 != net_hpwl2:
        raise ValueError("记录的逐网 HPWL 与独立复算结果不一致")
    if solution.total_hpwl2 != sum(net_hpwl2):
        raise ValueError("记录的总 HPWL 与逐网求和不一致")
