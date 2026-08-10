"""问题 3：单调边界搜索、B*-Tree 启发式与 CP-SAT 临界认证。"""

from __future__ import annotations

from dataclasses import dataclass
from math import isclose, isqrt

from ortools.sat.python import cp_model

from .bstar import (
    FastSAStats,
    bstar_tree_from_placements,
    complete_bstar_tree,
    fast_simulated_annealing,
)
from .data import FloorplanDataset, FloorplanProblem
from .q1 import Placement
from .q2 import (
    Q2ConstructionStats,
    compute_net_hpwl2,
    construct_fixed_outline_seed,
    outline_dimensions,
    validate_fixed_outline_placements,
)


@dataclass(frozen=True, slots=True)
class ExactFeasibilityStats:
    """固定整数边长下纯几何 CP-SAT 判定的证据。"""

    side: int
    time_limit_seconds: float
    workers: int
    seed: int
    status: str
    has_solution: bool
    proven_infeasible: bool
    wall_time_seconds: float
    conflicts: int
    branches: int


@dataclass(frozen=True, slots=True)
class BoundarySearchStep:
    """一次二分候选的启发式与可选精确判定结果。"""

    side: int
    lower_before: int
    upper_before: int
    constructive_feasible: bool
    constructive_feasible_attempts: int
    heuristic_violation: int
    heuristic_feasible: bool
    heuristic_iterations: int
    heuristic_stats: FastSAStats | None
    exact_status: str | None
    exact_stats: ExactFeasibilityStats | None
    decision: str


@dataclass(frozen=True, slots=True)
class BoundarySearchStats:
    """临界边长搜索的最终区间与逐步证据。"""

    theoretical_lower_bound: int
    initial_feasible_upper_bound: int
    final_lower_bound: int
    final_feasible_upper_bound: int
    certified_infeasible_through: int
    max_steps: int
    unknown_sides: tuple[int, ...]
    status: str
    steps: tuple[BoundarySearchStep, ...]

    @property
    def minimum_proven(self) -> bool:
        return self.status == "CERTIFIED_INTEGER_MINIMUM"


@dataclass(frozen=True, slots=True)
class Q3Solution:
    """先压缩边长、后固定边长优化 HPWL 的字典序结果。"""

    method: str
    total_block_area: int
    chip_side: int
    dead_space_ratio: float
    placements: tuple[Placement, ...]
    net_hpwl2: tuple[int, ...]
    total_hpwl2: int
    initial_construction: Q2ConstructionStats
    boundary_search: BoundarySearchStats
    hpwl_annealing: FastSAStats
    seed: int

    @property
    def total_hpwl(self) -> float:
        return self.total_hpwl2 / 2

    @property
    def coordinate_limit(self) -> int:
        """第三问直接搜索的整数边长也是最终坐标边界。"""

        return self.chip_side

    @property
    def minimum_dead_space_proven(self) -> bool:
        return self.boundary_search.minimum_proven


@dataclass(slots=True)
class _FeasibilityModel:
    model: cp_model.CpModel
    rotations: list[cp_model.IntVar]
    widths: list[cp_model.IntVar]
    heights: list[cp_model.IntVar]
    xs: list[cp_model.IntVar]
    ys: list[cp_model.IntVar]


def theoretical_side_lower_bound(problem: FloorplanProblem) -> int:
    """面积与单模块最大边共同给出的严格整数边长下界。"""

    area_bound = isqrt(problem.total_block_area - 1) + 1
    block_bound = max(max(block.width, block.height) for block in problem.blocks)
    return max(area_bound, block_bound)


def _next_boundary_candidate(
    lower: int,
    upper: int,
    unknown_sides: set[int],
) -> int | None:
    """优先从靠近可行上界的未测试连续区间中选择中点。

    ``UNKNOWN`` 点既不能提高已认证下界，也不能作为可行上界。将其从候选集合
    中剔除后，继续搜索其上方区间以优先压缩可行上界；上方耗尽后再处理下方
    区间。这样可以保留严格的 ``lower <= L* <= upper`` 语义，同时避免在同一
    未决点重复求解。
    """

    if lower >= upper:
        return None
    relevant_unknown = sorted(side for side in unknown_sides if lower <= side < upper)
    intervals: list[tuple[int, int]] = []
    start = lower
    for side in relevant_unknown:
        if start <= side - 1:
            intervals.append((start, side - 1))
        start = side + 1
    if start <= upper - 1:
        intervals.append((start, upper - 1))
    if not intervals:
        return None
    interval_lower, interval_upper = max(intervals, key=lambda interval: interval[1])
    return (interval_lower + interval_upper + 1) // 2


def _build_feasibility_model(problem: FloorplanProblem, side: int) -> _FeasibilityModel:
    model = cp_model.CpModel()
    rotations: list[cp_model.IntVar] = []
    widths: list[cp_model.IntVar] = []
    heights: list[cp_model.IntVar] = []
    xs: list[cp_model.IntVar] = []
    ys: list[cp_model.IntVar] = []
    x_intervals: list[cp_model.IntervalVar] = []
    y_intervals: list[cp_model.IntervalVar] = []

    for index, block in enumerate(problem.blocks):
        rotation = model.new_bool_var(f"r_{index}")
        width = model.new_int_var(
            min(block.width, block.height), max(block.width, block.height), f"w_{index}"
        )
        height = model.new_int_var(
            min(block.width, block.height), max(block.width, block.height), f"h_{index}"
        )
        model.add(width == block.width + (block.height - block.width) * rotation)
        model.add(height == block.height + (block.width - block.height) * rotation)
        x = model.new_int_var(0, side, f"x_{index}")
        y = model.new_int_var(0, side, f"y_{index}")
        x_end = model.new_int_var(0, side, f"xe_{index}")
        y_end = model.new_int_var(0, side, f"ye_{index}")
        model.add(x_end == x + width)
        model.add(y_end == y + height)
        x_intervals.append(model.new_interval_var(x, width, x_end, f"xi_{index}"))
        y_intervals.append(model.new_interval_var(y, height, y_end, f"yi_{index}"))
        rotations.append(rotation)
        widths.append(width)
        heights.append(height)
        xs.append(x)
        ys.append(y)
    model.add_no_overlap_2d(x_intervals, y_intervals)
    model.add_cumulative(x_intervals, heights, side)
    model.add_cumulative(y_intervals, widths, side)
    min_x = model.new_int_var(0, side, "min_x")
    min_y = model.new_int_var(0, side, "min_y")
    model.add_min_equality(min_x, xs)
    model.add_min_equality(min_y, ys)
    model.add(min_x == 0)
    model.add(min_y == 0)
    return _FeasibilityModel(model, rotations, widths, heights, xs, ys)


def check_exact_feasibility(
    problem: FloorplanProblem,
    side: int,
    *,
    time_limit: float = 30.0,
    workers: int = 8,
    seed: int = 20260810,
    hint_placements: tuple[Placement, ...] | None = None,
) -> tuple[ExactFeasibilityStats, tuple[Placement, ...] | None]:
    """只在 CP-SAT 明确返回 INFEASIBLE 时给出不可行认证。"""

    if side <= 0 or time_limit <= 0 or workers <= 0:
        raise ValueError("边长、时间限制和 workers 必须为正")
    if side < theoretical_side_lower_bound(problem):
        return (
            ExactFeasibilityStats(
                side=side,
                time_limit_seconds=time_limit,
                workers=workers,
                seed=seed,
                status="INFEASIBLE_BY_LOWER_BOUND",
                has_solution=False,
                proven_infeasible=True,
                wall_time_seconds=0.0,
                conflicts=0,
                branches=0,
            ),
            None,
        )

    context = _build_feasibility_model(problem, side)
    if hint_placements is not None:
        hints_by_name = {placement.name: placement for placement in hint_placements}
        for index, block in enumerate(problem.blocks):
            hint = hints_by_name.get(block.name)
            if hint is None:
                continue
            hinted_width = block.height if hint.rotated else block.width
            hinted_height = block.width if hint.rotated else block.height
            context.model.add_hint(context.rotations[index], int(hint.rotated))
            context.model.add_hint(
                context.xs[index], max(0, min(hint.x, side - hinted_width))
            )
            context.model.add_hint(
                context.ys[index], max(0, min(hint.y, side - hinted_height))
            )
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_search_workers = workers
    solver.parameters.random_seed = seed
    solver.parameters.use_energetic_reasoning_in_no_overlap_2d = True
    solver.parameters.use_area_energetic_reasoning_in_no_overlap_2d = True
    solver.parameters.use_timetabling_in_no_overlap_2d = True
    solver.parameters.use_try_edge_reasoning_in_no_overlap_2d = True
    solver.parameters.use_combined_no_overlap = True
    status = solver.solve(context.model)
    has_solution = status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    placements = None
    if has_solution:
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
    stats = ExactFeasibilityStats(
        side=side,
        time_limit_seconds=time_limit,
        workers=workers,
        seed=seed,
        status=solver.status_name(status),
        has_solution=has_solution,
        proven_infeasible=status == cp_model.INFEASIBLE,
        wall_time_seconds=solver.wall_time,
        conflicts=solver.num_conflicts,
        branches=solver.num_branches,
    )
    return stats, placements


def solve_q3(
    dataset: FloorplanDataset,
    *,
    heuristic_iterations_per_restart: int = 2_000,
    heuristic_restarts: int = 3,
    heuristic_time_limit_per_side: float = 10.0,
    exact_time_limit_per_side: float = 30.0,
    exact_workers: int = 8,
    max_boundary_steps: int = 12,
    hpwl_iterations_per_restart: int = 10_000,
    hpwl_restarts: int = 4,
    hpwl_time_limit: float = 60.0,
    seed: int = 20260810,
) -> Q3Solution:
    """执行临界轮廓搜索，并在最小已知可行边长下重新优化 HPWL。"""

    positive_parameters = {
        "heuristic_iterations_per_restart": heuristic_iterations_per_restart,
        "heuristic_restarts": heuristic_restarts,
        "heuristic_time_limit_per_side": heuristic_time_limit_per_side,
        "exact_time_limit_per_side": exact_time_limit_per_side,
        "exact_workers": exact_workers,
        "max_boundary_steps": max_boundary_steps,
        "hpwl_iterations_per_restart": hpwl_iterations_per_restart,
        "hpwl_restarts": hpwl_restarts,
        "hpwl_time_limit": hpwl_time_limit,
    }
    invalid = [name for name, value in positive_parameters.items() if value <= 0]
    if invalid:
        raise ValueError(f"以下参数必须为正：{invalid}")

    _, initial_upper = outline_dimensions(dataset.problem.total_block_area, 0.15)
    upper_placements, construction = construct_fixed_outline_seed(dataset, initial_upper)
    theoretical_lower = theoretical_side_lower_bound(dataset.problem)
    if initial_upper < theoretical_lower:
        raise RuntimeError("15% 死区对应整数边长小于严格必要下界，无法作为可行上界")

    lower = theoretical_lower
    upper = initial_upper
    certified_infeasible_through = theoretical_lower - 1
    unknown_sides: set[int] = set()
    steps: list[BoundarySearchStep] = []
    search_status = "CERTIFIED_INTEGER_MINIMUM" if lower == upper else "SEARCHING"

    while lower < upper and len(steps) < max_boundary_steps:
        midpoint = _next_boundary_candidate(lower, upper, unknown_sides)
        if midpoint is None:
            search_status = "UNRESOLVED_EXACT_TIMEOUT"
            break
        lower_before, upper_before = lower, upper
        constructive_feasible = False
        constructive_feasible_attempts = 0
        constructive_placements: tuple[Placement, ...] | None = None
        try:
            constructive_placements, candidate_construction = construct_fixed_outline_seed(
                dataset, midpoint
            )
            constructive_feasible = True
            constructive_feasible_attempts = candidate_construction.feasible_attempts
        except RuntimeError:
            pass

        exact_status: str | None = None
        exact_stats: ExactFeasibilityStats | None = None
        heuristic_stats: FastSAStats | None = None
        heuristic_violation = 0
        heuristic_feasible = constructive_feasible
        heuristic_iterations = 0
        if constructive_placements is not None:
            upper = midpoint
            upper_placements = constructive_placements
            decision = "MAXRECTS_FEASIBLE_UPPER_REDUCED"
        else:
            initial_tree = bstar_tree_from_placements(dataset.problem, upper_placements)
            if initial_tree is None:
                initial_tree = complete_bstar_tree(
                    dataset.problem,
                    outline_limit=midpoint,
                )
            heuristic = fast_simulated_annealing(
                dataset.problem,
                outline_limit=midpoint,
                objective="feasibility",
                initial_tree=initial_tree,
                iterations_per_restart=heuristic_iterations_per_restart,
                restarts=heuristic_restarts,
                seed=seed + len(steps),
                time_limit=heuristic_time_limit_per_side,
                stop_on_first_feasible=True,
            )
            heuristic_stats = heuristic.stats
            heuristic_violation = heuristic.violation
            heuristic_feasible = heuristic.feasible
            heuristic_iterations = heuristic.stats.completed_iterations
            if heuristic.feasible:
                upper = midpoint
                upper_placements = heuristic.placements
                decision = "HEURISTIC_FEASIBLE_UPPER_REDUCED"
            else:
                exact, exact_placements = check_exact_feasibility(
                    dataset.problem,
                    midpoint,
                    time_limit=exact_time_limit_per_side,
                    workers=exact_workers,
                    seed=seed + len(steps),
                    hint_placements=upper_placements,
                )
                exact_status = exact.status
                exact_stats = exact
                if exact.has_solution and exact_placements is not None:
                    upper = midpoint
                    upper_placements = exact_placements
                    decision = "EXACT_FEASIBLE_UPPER_REDUCED"
                elif exact.proven_infeasible:
                    lower = midpoint + 1
                    certified_infeasible_through = max(certified_infeasible_through, midpoint)
                    decision = "EXACT_INFEASIBLE_LOWER_RAISED"
                else:
                    decision = "EXACT_UNKNOWN_INTERVAL_RETAINED"
                    unknown_sides.add(midpoint)
                    search_status = "UNRESOLVED_EXACT_TIMEOUT"

        steps.append(
            BoundarySearchStep(
                side=midpoint,
                lower_before=lower_before,
                upper_before=upper_before,
                constructive_feasible=constructive_feasible,
                constructive_feasible_attempts=constructive_feasible_attempts,
                heuristic_violation=heuristic_violation,
                heuristic_feasible=heuristic_feasible,
                heuristic_iterations=heuristic_iterations,
                heuristic_stats=heuristic_stats,
                exact_status=exact_status,
                exact_stats=exact_stats,
                decision=decision,
            )
        )
    if lower == upper:
        search_status = "CERTIFIED_INTEGER_MINIMUM"
    elif len(steps) >= max_boundary_steps:
        search_status = "UNRESOLVED_STEP_LIMIT"

    boundary_search = BoundarySearchStats(
        theoretical_lower_bound=theoretical_lower,
        initial_feasible_upper_bound=initial_upper,
        final_lower_bound=lower,
        final_feasible_upper_bound=upper,
        certified_infeasible_through=certified_infeasible_through,
        max_steps=max_boundary_steps,
        unknown_sides=tuple(sorted(side for side in unknown_sides if lower <= side < upper)),
        status=search_status,
        steps=tuple(steps),
    )

    hpwl_tree = bstar_tree_from_placements(dataset.problem, upper_placements)
    if hpwl_tree is None:
        hpwl_tree = complete_bstar_tree(dataset.problem, outline_limit=upper)
    hpwl_search = fast_simulated_annealing(
        dataset.problem,
        outline_limit=upper,
        objective="hpwl",
        dataset=dataset,
        initial_tree=hpwl_tree,
        iterations_per_restart=hpwl_iterations_per_restart,
        restarts=hpwl_restarts,
        seed=seed + 10_000,
        time_limit=hpwl_time_limit,
    )
    incumbent_hpwl2 = sum(compute_net_hpwl2(dataset, upper_placements))
    if (
        hpwl_search.feasible
        and hpwl_search.total_hpwl2 is not None
        and hpwl_search.total_hpwl2 <= incumbent_hpwl2
    ):
        placements = hpwl_search.placements
        method = "binary-bstar-exact-certification-bstar-hpwl"
    else:
        placements = upper_placements
        method = "binary-bstar-exact-certification-feasible-incumbent"

    net_hpwl2 = compute_net_hpwl2(dataset, placements)
    solution = Q3Solution(
        method=method,
        total_block_area=dataset.problem.total_block_area,
        chip_side=upper,
        dead_space_ratio=upper**2 / dataset.problem.total_block_area - 1.0,
        placements=placements,
        net_hpwl2=net_hpwl2,
        total_hpwl2=sum(net_hpwl2),
        initial_construction=construction,
        boundary_search=boundary_search,
        hpwl_annealing=hpwl_search.stats,
        seed=seed,
    )
    validate_q3_solution(dataset, solution)
    return solution


def validate_q3_solution(dataset: FloorplanDataset, solution: Q3Solution) -> None:
    """独立复算第三问最终可行性、死区率和 HPWL。"""

    validate_fixed_outline_placements(dataset, solution.placements, solution.chip_side)
    expected_ratio = solution.chip_side**2 / dataset.problem.total_block_area - 1.0
    if not isclose(solution.dead_space_ratio, expected_ratio, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError("第三问死区比例与边长、模块总面积不一致")
    if solution.boundary_search.final_feasible_upper_bound != solution.chip_side:
        raise ValueError("最终边长与边界搜索可行上界不一致")
    if solution.boundary_search.final_lower_bound > solution.chip_side:
        raise ValueError("边界搜索下界不能超过可行上界")
    net_hpwl2 = compute_net_hpwl2(dataset, solution.placements)
    if solution.net_hpwl2 != net_hpwl2 or solution.total_hpwl2 != sum(net_hpwl2):
        raise ValueError("第三问 HPWL 记录与独立复算不一致")
