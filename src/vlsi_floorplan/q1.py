"""问题 1 的强构造上界、CP-SAT 精确改进和独立可行性检查。"""

from __future__ import annotations

from dataclasses import dataclass
from math import isqrt
from time import perf_counter

from ortools.sat.python import cp_model

from .construct import ConstructionStats, ConstructiveLayout, construct_upper_bound
from .data import FloorplanProblem


@dataclass(frozen=True, slots=True)
class Placement:
    name: str
    x: int
    y: int
    width: int
    height: int
    rotated: bool


@dataclass(frozen=True, slots=True)
class PhaseStats:
    status: str
    objective: int | None
    best_bound: float | None
    wall_time_seconds: float
    conflicts: int
    branches: int


@dataclass(frozen=True, slots=True)
class Q1Solution:
    method: str
    width: int
    height: int
    area: int
    total_block_area: int
    placements: tuple[Placement, ...]
    construction: ConstructionStats
    area_phase: PhaseStats
    shape_phase: PhaseStats | None
    factor_search: "FactorSearchStats | None"
    seed: int
    workers: int

    @property
    def aspect_ratio(self) -> float:
        return max(self.width / self.height, self.height / self.width)

    @property
    def dead_space_ratio(self) -> float:
        return self.area / self.total_block_area - 1.0

    @property
    def area_proven_optimal(self) -> bool:
        return self.area_phase.status == "OPTIMAL"

    @property
    def lexicographic_proven_optimal(self) -> bool:
        return self.area_proven_optimal and bool(
            self.shape_phase and self.shape_phase.status == "OPTIMAL"
        )


@dataclass(frozen=True, slots=True)
class FactorSearchStats:
    factor_pairs: int
    closer_pairs: int
    checked_pairs: int
    proven_infeasible_pairs: int
    unresolved_pairs: int
    selected_width: int
    selected_height: int


@dataclass(slots=True)
class _ModelContext:
    model: cp_model.CpModel
    rotations: list[cp_model.IntVar]
    widths: list[cp_model.IntVar]
    heights: list[cp_model.IntVar]
    xs: list[cp_model.IntVar]
    ys: list[cp_model.IntVar]
    width: cp_model.IntVar
    height: cp_model.IntVar
    area: cp_model.IntVar


def _build_model(problem: FloorplanProblem, hint: ConstructiveLayout) -> _ModelContext:
    model = cp_model.CpModel()
    total_area = problem.total_block_area
    upper_area = hint.area
    minimum_side = max(min(block.width, block.height) for block in problem.blocks)

    width_lower = max(minimum_side, isqrt(total_area - 1) + 1)
    width_upper = upper_area // minimum_side
    height_lower = minimum_side
    height_upper = isqrt(upper_area)

    rotations: list[cp_model.IntVar] = []
    widths: list[cp_model.IntVar] = []
    heights: list[cp_model.IntVar] = []
    xs: list[cp_model.IntVar] = []
    ys: list[cp_model.IntVar] = []
    x_ends: list[cp_model.IntVar] = []
    y_ends: list[cp_model.IntVar] = []
    x_intervals: list[cp_model.IntervalVar] = []
    y_intervals: list[cp_model.IntervalVar] = []

    for index, block in enumerate(problem.blocks):
        rotation = model.new_bool_var(f"r_{index}")
        block_width = model.new_int_var(min(block.width, block.height), max(block.width, block.height), f"w_{index}")
        block_height = model.new_int_var(min(block.width, block.height), max(block.width, block.height), f"h_{index}")
        model.add(block_width == block.width + (block.height - block.width) * rotation)
        model.add(block_height == block.height + (block.width - block.height) * rotation)

        x = model.new_int_var(0, width_upper, f"x_{index}")
        y = model.new_int_var(0, height_upper, f"y_{index}")
        x_end = model.new_int_var(0, width_upper, f"xe_{index}")
        y_end = model.new_int_var(0, height_upper, f"ye_{index}")
        model.add(x_end == x + block_width)
        model.add(y_end == y + block_height)

        rotations.append(rotation)
        widths.append(block_width)
        heights.append(block_height)
        xs.append(x)
        ys.append(y)
        x_ends.append(x_end)
        y_ends.append(y_end)
        x_intervals.append(model.new_interval_var(x, block_width, x_end, f"xi_{index}"))
        y_intervals.append(model.new_interval_var(y, block_height, y_end, f"yi_{index}"))

    model.add_no_overlap_2d(x_intervals, y_intervals)

    outline_width = model.new_int_var(width_lower, width_upper, "W")
    outline_height = model.new_int_var(height_lower, height_upper, "H")
    model.add_max_equality(outline_width, x_ends)
    model.add_max_equality(outline_height, y_ends)
    model.add(outline_width >= outline_height)

    min_x = model.new_int_var(0, 0, "min_x")
    min_y = model.new_int_var(0, 0, "min_y")
    model.add_min_equality(min_x, xs)
    model.add_min_equality(min_y, ys)

    outline_area = model.new_int_var(total_area, upper_area, "A")
    model.add_multiplication_equality(outline_area, (outline_width, outline_height))
    model.minimize(outline_area)

    hint_by_name = {placement.name: placement for placement in hint.placements}
    for index, block in enumerate(problem.blocks):
        placement = hint_by_name[block.name]
        model.add_hint(rotations[index], int(placement.rotated))
        model.add_hint(widths[index], placement.width)
        model.add_hint(heights[index], placement.height)
        model.add_hint(xs[index], placement.x)
        model.add_hint(ys[index], placement.y)
    model.add_hint(outline_width, hint.width)
    model.add_hint(outline_height, hint.height)
    model.add_hint(outline_area, hint.area)

    return _ModelContext(
        model=model,
        rotations=rotations,
        widths=widths,
        heights=heights,
        xs=xs,
        ys=ys,
        width=outline_width,
        height=outline_height,
        area=outline_area,
    )


def _build_fixed_outline_model(
    problem: FloorplanProblem,
    width: int,
    height: int,
) -> _ModelContext:
    model = cp_model.CpModel()
    rotations: list[cp_model.IntVar] = []
    widths: list[cp_model.IntVar] = []
    heights: list[cp_model.IntVar] = []
    xs: list[cp_model.IntVar] = []
    ys: list[cp_model.IntVar] = []
    x_ends: list[cp_model.IntVar] = []
    y_ends: list[cp_model.IntVar] = []
    x_intervals: list[cp_model.IntervalVar] = []
    y_intervals: list[cp_model.IntervalVar] = []

    for index, block in enumerate(problem.blocks):
        rotation = model.new_bool_var(f"r_{index}")
        block_width = model.new_int_var(
            min(block.width, block.height), max(block.width, block.height), f"w_{index}"
        )
        block_height = model.new_int_var(
            min(block.width, block.height), max(block.width, block.height), f"h_{index}"
        )
        model.add(block_width == block.width + (block.height - block.width) * rotation)
        model.add(block_height == block.height + (block.width - block.height) * rotation)
        x = model.new_int_var(0, width, f"x_{index}")
        y = model.new_int_var(0, height, f"y_{index}")
        x_end = model.new_int_var(0, width, f"xe_{index}")
        y_end = model.new_int_var(0, height, f"ye_{index}")
        model.add(x_end == x + block_width)
        model.add(y_end == y + block_height)

        rotations.append(rotation)
        widths.append(block_width)
        heights.append(block_height)
        xs.append(x)
        ys.append(y)
        x_ends.append(x_end)
        y_ends.append(y_end)
        x_intervals.append(model.new_interval_var(x, block_width, x_end, f"xi_{index}"))
        y_intervals.append(model.new_interval_var(y, block_height, y_end, f"yi_{index}"))

    model.add_no_overlap_2d(x_intervals, y_intervals)
    outline_width = model.new_int_var(width, width, "W")
    outline_height = model.new_int_var(height, height, "H")
    model.add_max_equality(outline_width, x_ends)
    model.add_max_equality(outline_height, y_ends)
    min_x = model.new_int_var(0, 0, "min_x")
    min_y = model.new_int_var(0, 0, "min_y")
    model.add_min_equality(min_x, xs)
    model.add_min_equality(min_y, ys)
    outline_area = model.new_int_var(width * height, width * height, "A")

    return _ModelContext(
        model=model,
        rotations=rotations,
        widths=widths,
        heights=heights,
        xs=xs,
        ys=ys,
        width=outline_width,
        height=outline_height,
        area=outline_area,
    )


def _configure_solver(time_limit: float, workers: int, seed: int, log_search: bool) -> cp_model.CpSolver:
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_search_workers = workers
    solver.parameters.random_seed = seed
    solver.parameters.log_search_progress = log_search
    return solver


def _phase_stats(solver: cp_model.CpSolver, status: cp_model.CpSolverStatus) -> PhaseStats:
    status_name = solver.status_name(status)
    has_solution = status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    return PhaseStats(
        status=status_name,
        objective=int(round(solver.objective_value)) if has_solution else None,
        best_bound=solver.best_objective_bound if has_solution else None,
        wall_time_seconds=solver.wall_time,
        conflicts=solver.num_conflicts,
        branches=solver.num_branches,
    )


def _extract_solution(
    problem: FloorplanProblem,
    context: _ModelContext,
    solver: cp_model.CpSolver,
) -> tuple[int, int, int, tuple[Placement, ...]]:
    placements = tuple(
        Placement(
            name=block.name,
            x=solver.value(context.xs[index]),
            y=solver.value(context.ys[index]),
            width=solver.value(context.widths[index]),
            height=solver.value(context.heights[index]),
            rotated=bool(solver.value(context.rotations[index])),
        )
        for index, block in enumerate(problem.blocks)
    )
    return (
        solver.value(context.width),
        solver.value(context.height),
        solver.value(context.area),
        placements,
    )


def factor_pairs(area: int) -> tuple[tuple[int, int], ...]:
    """返回 `W>=H` 的全部整数因子对，按 `W-H` 升序排列。"""

    if area <= 0:
        raise ValueError("面积必须为正整数")
    pairs = [(area // height, height) for height in range(1, isqrt(area) + 1) if area % height == 0]
    return tuple(sorted(pairs, key=lambda pair: (pair[0] - pair[1], pair[0])))


def _pair_orientation_possible(problem: FloorplanProblem, width: int, height: int) -> bool:
    return all(
        (block.width <= width and block.height <= height)
        or (block.height <= width and block.width <= height)
        for block in problem.blocks
    )


def _factor_shape_search(
    problem: FloorplanProblem,
    *,
    width: int,
    height: int,
    area: int,
    placements: tuple[Placement, ...],
    time_limit: float,
    pair_time_limit: float,
    workers: int,
    seed: int,
    log_search: bool,
) -> tuple[int, int, tuple[Placement, ...], PhaseStats, FactorSearchStats]:
    started = perf_counter()
    pairs = factor_pairs(area)
    current_gap = width - height
    closer_pairs = [pair for pair in pairs if pair[0] - pair[1] < current_gap]
    checked = 0
    proven_infeasible = 0
    unresolved_gaps: list[int] = []
    conflicts = 0
    branches = 0
    selected_width, selected_height = width, height
    selected_placements = placements

    for pair_index, (candidate_width, candidate_height) in enumerate(closer_pairs):
        remaining = time_limit - (perf_counter() - started)
        if remaining <= 0:
            unresolved_gaps.extend(
                pair[0] - pair[1] for pair in closer_pairs[pair_index:]
            )
            break
        checked += 1
        if not _pair_orientation_possible(problem, candidate_width, candidate_height):
            proven_infeasible += 1
            continue

        context = _build_fixed_outline_model(problem, candidate_width, candidate_height)
        solver = _configure_solver(min(pair_time_limit, remaining), workers, seed, log_search)
        status = solver.solve(context.model)
        conflicts += solver.num_conflicts
        branches += solver.num_branches
        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            selected_width, selected_height, _, selected_placements = _extract_solution(
                problem, context, solver
            )
            shape_status = "OPTIMAL" if not unresolved_gaps else "FEASIBLE"
            elapsed = perf_counter() - started
            stats = PhaseStats(
                status=shape_status,
                objective=selected_width - selected_height,
                best_bound=float(min(unresolved_gaps)) if unresolved_gaps else float(selected_width - selected_height),
                wall_time_seconds=elapsed,
                conflicts=conflicts,
                branches=branches,
            )
            factor_stats = FactorSearchStats(
                factor_pairs=len(pairs),
                closer_pairs=len(closer_pairs),
                checked_pairs=checked,
                proven_infeasible_pairs=proven_infeasible,
                unresolved_pairs=len(unresolved_gaps),
                selected_width=selected_width,
                selected_height=selected_height,
            )
            return selected_width, selected_height, selected_placements, stats, factor_stats
        if status == cp_model.INFEASIBLE:
            proven_infeasible += 1
        else:
            unresolved_gaps.append(candidate_width - candidate_height)
    elapsed = perf_counter() - started
    shape_status = "OPTIMAL" if not unresolved_gaps else "FEASIBLE"
    stats = PhaseStats(
        status=shape_status,
        objective=current_gap,
        best_bound=float(min(unresolved_gaps)) if unresolved_gaps else float(current_gap),
        wall_time_seconds=elapsed,
        conflicts=conflicts,
        branches=branches,
    )
    factor_stats = FactorSearchStats(
        factor_pairs=len(pairs),
        closer_pairs=len(closer_pairs),
        checked_pairs=checked,
        proven_infeasible_pairs=proven_infeasible,
        unresolved_pairs=len(unresolved_gaps),
        selected_width=selected_width,
        selected_height=selected_height,
    )
    return selected_width, selected_height, selected_placements, stats, factor_stats


def solve_q1(
    problem: FloorplanProblem,
    *,
    area_time_limit: float = 30.0,
    shape_time_limit: float = 10.0,
    workers: int = 8,
    seed: int = 20260810,
    log_search: bool = False,
    width_multiplier: float = 1.8,
    width_samples: int = 64,
    random_starts: int = 24,
    local_iterations: int = 120,
    factor_pair_time_limit: float = 2.0,
    construction_time_limit: float = 75.0,
) -> Q1Solution:
    """强构造得到上界，CP-SAT 改进面积，再按因子对优化同面积长宽比。"""

    if area_time_limit <= 0 or shape_time_limit < 0:
        raise ValueError("求解时间限制必须为正，长宽比阶段可设为 0")
    if shape_time_limit > 0 and factor_pair_time_limit <= 0:
        raise ValueError("启用长宽比阶段时，factor_pair_time_limit 必须为正数")
    if workers <= 0:
        raise ValueError("workers 必须为正整数")

    construction = construct_upper_bound(
        problem,
        width_multiplier=width_multiplier,
        width_samples=width_samples,
        random_starts=random_starts,
        local_iterations=local_iterations,
        seed=seed,
        time_limit=construction_time_limit,
    )
    hint = construction.layout
    context = _build_model(problem, hint)
    area_solver = _configure_solver(area_time_limit, workers, seed, log_search)
    area_status = area_solver.solve(context.model)
    area_stats = _phase_stats(area_solver, area_status)

    if area_status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        fallback_stats = PhaseStats(
            status="HEURISTIC",
            objective=hint.area,
            best_bound=area_stats.best_bound,
            wall_time_seconds=area_stats.wall_time_seconds,
            conflicts=area_stats.conflicts,
            branches=area_stats.branches,
        )
        solution = Q1Solution(
            method="maxrects-local-search-fallback",
            width=hint.width,
            height=hint.height,
            area=hint.area,
            total_block_area=problem.total_block_area,
            placements=tuple(
                Placement(
                    name=placement.name,
                    x=placement.x,
                    y=placement.y,
                    width=placement.width,
                    height=placement.height,
                    rotated=placement.rotated,
                )
                for placement in hint.placements
            ),
            construction=construction.stats,
            area_phase=fallback_stats,
            shape_phase=None,
            factor_search=None,
            seed=seed,
            workers=workers,
        )
        validate_solution(problem, solution)
        return solution

    width, height, area, placements = _extract_solution(problem, context, area_solver)
    shape_stats: PhaseStats | None = None
    factor_stats: FactorSearchStats | None = None

    if shape_time_limit > 0:
        width, height, placements, shape_stats, factor_stats = _factor_shape_search(
            problem,
            width=width,
            height=height,
            area=area,
            placements=placements,
            time_limit=shape_time_limit,
            pair_time_limit=factor_pair_time_limit,
            workers=workers,
            seed=seed,
            log_search=log_search,
        )

    solution = Q1Solution(
        method="maxrects-local-search+cp-sat+factor-feasibility",
        width=width,
        height=height,
        area=area,
        total_block_area=problem.total_block_area,
        placements=placements,
        construction=construction.stats,
        area_phase=area_stats,
        shape_phase=shape_stats,
        factor_search=factor_stats,
        seed=seed,
        workers=workers,
    )
    validate_solution(problem, solution)
    return solution


def validate_solution(problem: FloorplanProblem, solution: Q1Solution) -> None:
    """不依赖求解器，独立检查旋转、边界、轮廓和两两不重叠。"""

    if solution.width <= 0 or solution.height <= 0:
        raise ValueError("轮廓宽高必须为正")
    if solution.area != solution.width * solution.height:
        raise ValueError("记录面积与轮廓宽高不一致")

    placement_by_name = {placement.name: placement for placement in solution.placements}
    if len(placement_by_name) != len(solution.placements):
        raise ValueError("布局中存在重复模块")
    expected_names = {block.name for block in problem.blocks}
    if set(placement_by_name) != expected_names:
        raise ValueError("布局模块集合与输入不一致")

    for block in problem.blocks:
        placement = placement_by_name[block.name]
        expected_dimensions = (
            (block.height, block.width) if placement.rotated else (block.width, block.height)
        )
        if (placement.width, placement.height) != expected_dimensions:
            raise ValueError(f"{block.name}: 旋转状态与宽高不一致")
        if placement.x < 0 or placement.y < 0:
            raise ValueError(f"{block.name}: 坐标不能为负")
        if placement.x + placement.width > solution.width:
            raise ValueError(f"{block.name}: 超出轮廓右边界")
        if placement.y + placement.height > solution.height:
            raise ValueError(f"{block.name}: 超出轮廓上边界")

    placements = solution.placements
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

    max_x = max(placement.x + placement.width for placement in placements)
    max_y = max(placement.y + placement.height for placement in placements)
    if max_x != solution.width or max_y != solution.height:
        raise ValueError("轮廓宽高不是布局的最小外包矩形")
