"""问题 1 的直接 CP-SAT 模型、确定性初始解和独立可行性检查。"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, isqrt, sqrt
from time import perf_counter
from typing import Iterable

from ortools.sat.python import cp_model

from .data import Block, FloorplanProblem


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
    area_phase: PhaseStats
    shape_phase: PhaseStats | None
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


@dataclass(slots=True)
class _Shelf:
    y: int
    height: int
    used_width: int


@dataclass(frozen=True, slots=True)
class _HeuristicLayout:
    width: int
    height: int
    placements: tuple[Placement, ...]

    @property
    def area(self) -> int:
        return self.width * self.height


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


def _orientations(block: Block) -> tuple[tuple[int, int, bool], ...]:
    if block.width == block.height:
        return ((block.width, block.height, False),)
    return (
        (block.width, block.height, False),
        (block.height, block.width, True),
    )


def _shelf_layout(blocks: tuple[Block, ...], target_width: int) -> _HeuristicLayout | None:
    order = sorted(blocks, key=lambda block: (-max(block.width, block.height), -block.area, block.name))
    shelves: list[_Shelf] = []
    placed: dict[str, Placement] = {}

    for block in order:
        candidates: list[tuple[tuple[int, int, int], int, int, int, bool]] = []
        for shelf_index, shelf in enumerate(shelves):
            for width, height, rotated in _orientations(block):
                if height <= shelf.height and shelf.used_width + width <= target_width:
                    score = (target_width - shelf.used_width - width, shelf.height - height, shelf.y)
                    candidates.append((score, shelf_index, width, height, rotated))

        if candidates:
            _, shelf_index, width, height, rotated = min(candidates)
            shelf = shelves[shelf_index]
            placed[block.name] = Placement(
                name=block.name,
                x=shelf.used_width,
                y=shelf.y,
                width=width,
                height=height,
                rotated=rotated,
            )
            shelf.used_width += width
            continue

        new_shelf_options = [
            (height, -width, width, height, rotated)
            for width, height, rotated in _orientations(block)
            if width <= target_width
        ]
        if not new_shelf_options:
            return None
        _, _, width, height, rotated = min(new_shelf_options)
        y = sum(shelf.height for shelf in shelves)
        shelves.append(_Shelf(y=y, height=height, used_width=width))
        placed[block.name] = Placement(
            name=block.name,
            x=0,
            y=y,
            width=width,
            height=height,
            rotated=rotated,
        )

    width = max(shelf.used_width for shelf in shelves)
    height = sum(shelf.height for shelf in shelves)
    placements = tuple(placed[block.name] for block in blocks)
    layout = _HeuristicLayout(width=width, height=height, placements=placements)
    return _rotate_layout(layout) if layout.width < layout.height else layout


def _rotate_layout(layout: _HeuristicLayout) -> _HeuristicLayout:
    rotated = tuple(
        Placement(
            name=placement.name,
            x=placement.y,
            y=layout.width - placement.x - placement.width,
            width=placement.height,
            height=placement.width,
            rotated=not placement.rotated,
        )
        for placement in layout.placements
    )
    return _HeuristicLayout(width=layout.height, height=layout.width, placements=rotated)


def _initial_layout(problem: FloorplanProblem) -> _HeuristicLayout:
    root_area = sqrt(problem.total_block_area)
    minimum_width = max(min(block.width, block.height) for block in problem.blocks)
    targets = {minimum_width}
    for percent in range(70, 181, 5):
        targets.add(max(minimum_width, ceil(root_area * percent / 100)))

    layouts = [
        layout
        for target in sorted(targets)
        if (layout := _shelf_layout(problem.blocks, target)) is not None
    ]
    if not layouts:
        raise RuntimeError("无法构造确定性初始布局")
    return min(layouts, key=lambda layout: (layout.area, abs(layout.width - layout.height)))


def _build_model(problem: FloorplanProblem, hint: _HeuristicLayout) -> _ModelContext:
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


def _replace_hints(context: _ModelContext, placements: Iterable[Placement], width: int, height: int, area: int) -> None:
    if hasattr(context.model, "clear_hints"):
        context.model.clear_hints()
    for index, placement in enumerate(placements):
        context.model.add_hint(context.rotations[index], int(placement.rotated))
        context.model.add_hint(context.widths[index], placement.width)
        context.model.add_hint(context.heights[index], placement.height)
        context.model.add_hint(context.xs[index], placement.x)
        context.model.add_hint(context.ys[index], placement.y)
    context.model.add_hint(context.width, width)
    context.model.add_hint(context.height, height)
    context.model.add_hint(context.area, area)


def solve_q1(
    problem: FloorplanProblem,
    *,
    area_time_limit: float = 30.0,
    shape_time_limit: float = 10.0,
    workers: int = 8,
    seed: int = 20260810,
    log_search: bool = False,
) -> Q1Solution:
    """先最小化轮廓面积，再在当前面积上最小化 `W-H`。"""

    if area_time_limit <= 0 or shape_time_limit < 0:
        raise ValueError("求解时间限制必须为正，长宽比阶段可设为 0")
    if workers <= 0:
        raise ValueError("workers 必须为正整数")

    heuristic = _initial_layout(problem)
    context = _build_model(problem, heuristic)
    area_solver = _configure_solver(area_time_limit, workers, seed, log_search)
    area_status = area_solver.solve(context.model)
    area_stats = _phase_stats(area_solver, area_status)

    if area_status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        fallback_stats = PhaseStats(
            status="HEURISTIC",
            objective=heuristic.area,
            best_bound=area_stats.best_bound,
            wall_time_seconds=area_stats.wall_time_seconds,
            conflicts=area_stats.conflicts,
            branches=area_stats.branches,
        )
        solution = Q1Solution(
            method="deterministic-shelf-fallback",
            width=heuristic.width,
            height=heuristic.height,
            area=heuristic.area,
            total_block_area=problem.total_block_area,
            placements=heuristic.placements,
            area_phase=fallback_stats,
            shape_phase=None,
            seed=seed,
            workers=workers,
        )
        validate_solution(problem, solution)
        return solution

    width, height, area, placements = _extract_solution(problem, context, area_solver)
    shape_stats: PhaseStats | None = None

    if shape_time_limit > 0:
        context.model.add(context.area == area)
        gap = context.model.new_int_var(0, width - 1 if width > 0 else 0, "shape_gap")
        context.model.add(gap == context.width - context.height)
        context.model.minimize(gap)
        _replace_hints(context, placements, width, height, area)

        shape_solver = _configure_solver(shape_time_limit, workers, seed, log_search)
        shape_status = shape_solver.solve(context.model)
        shape_stats = _phase_stats(shape_solver, shape_status)
        if shape_status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            width, height, area, placements = _extract_solution(problem, context, shape_solver)

    solution = Q1Solution(
        method="cp-sat-direct-model",
        width=width,
        height=height,
        area=area,
        total_block_area=problem.total_block_area,
        placements=placements,
        area_phase=area_stats,
        shape_phase=shape_stats,
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
