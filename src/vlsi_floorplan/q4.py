"""问题 4：正交异形模块的四向旋转、精确布局和独立校验。"""

from __future__ import annotations

from dataclasses import dataclass
from math import isqrt
from time import perf_counter
from typing import Iterable

from ortools.sat.python import cp_model


@dataclass(frozen=True, order=True, slots=True)
class ComponentRect:
    """模块局部坐标系中的半开矩形 ``[x,x+w) × [y,y+h)``。"""

    x: int
    y: int
    width: int
    height: int

    def __post_init__(self) -> None:
        if any(type(value) is not int for value in (self.x, self.y, self.width, self.height)):
            raise TypeError("组成矩形的坐标和宽高必须为整数")
        if self.x < 0 or self.y < 0:
            raise ValueError("组成矩形的局部坐标不能为负")
        if self.width <= 0 or self.height <= 0:
            raise ValueError("组成矩形的宽高必须为正整数")

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def top(self) -> int:
        return self.y + self.height

    @property
    def area(self) -> int:
        return self.width * self.height


@dataclass(frozen=True, slots=True)
class OrthogonalModule:
    """由互不重叠的轴对齐矩形组成的正交模块。"""

    name: str
    components: tuple[ComponentRect, ...]

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("模块名称不能为空")
        if not self.components:
            raise ValueError(f"{self.name}: 至少需要一个组成矩形")
        if min(rect.x for rect in self.components) != 0:
            raise ValueError(f"{self.name}: 局部几何必须贴齐 x=0")
        if min(rect.y for rect in self.components) != 0:
            raise ValueError(f"{self.name}: 局部几何必须贴齐 y=0")
        _validate_disjoint_rectangles(self.components, f"{self.name} 的组成矩形")

    @property
    def width(self) -> int:
        return max(rect.right for rect in self.components)

    @property
    def height(self) -> int:
        return max(rect.top for rect in self.components)

    @property
    def area(self) -> int:
        return sum(rect.area for rect in self.components)


@dataclass(frozen=True, slots=True)
class ModuleOrientation:
    """模块某个不重复旋转方向下的规范化局部几何。"""

    degrees: int
    width: int
    height: int
    components: tuple[ComponentRect, ...]


@dataclass(frozen=True, slots=True)
class Q4Placement:
    name: str
    x: int
    y: int
    orientation_degrees: int
    width: int
    height: int
    components: tuple[ComponentRect, ...]


@dataclass(frozen=True, slots=True)
class OutlineAttempt:
    width: int
    height: int
    area: int
    status: str
    wall_time_seconds: float
    conflicts: int
    branches: int


@dataclass(frozen=True, slots=True)
class Q4SearchStats:
    area_lower_bound: int
    initial_area_upper_bound: int
    checked_outlines: int
    proven_infeasible_outlines: int
    unresolved_outlines: int
    wall_time_seconds: float
    attempts: tuple[OutlineAttempt, ...]


@dataclass(frozen=True, slots=True)
class Q4Solution:
    method: str
    width: int
    height: int
    area: int
    total_module_area: int
    placements: tuple[Q4Placement, ...]
    search: Q4SearchStats
    area_proven_optimal: bool
    lexicographic_proven_optimal: bool
    seed: int
    workers: int

    @property
    def aspect_ratio(self) -> float:
        return max(self.width / self.height, self.height / self.width)

    @property
    def dead_space_ratio(self) -> float:
        return self.area / self.total_module_area - 1.0


@dataclass(slots=True)
class _FixedOutlineContext:
    model: cp_model.CpModel
    xs: list[cp_model.IntVar]
    ys: list[cp_model.IntVar]
    active_orientations: list[list[cp_model.BoolVarT]]


def _rectangles_overlap(first: ComponentRect, second: ComponentRect) -> bool:
    return not (
        first.right <= second.x
        or second.right <= first.x
        or first.top <= second.y
        or second.top <= first.y
    )


def _validate_disjoint_rectangles(
    rectangles: Iterable[ComponentRect],
    description: str,
) -> None:
    items = tuple(rectangles)
    for index, first in enumerate(items):
        for second in items[index + 1 :]:
            if _rectangles_overlap(first, second):
                raise ValueError(f"{description}发生重叠")


def _rotate_once(rectangles: tuple[ComponentRect, ...]) -> tuple[ComponentRect, ...]:
    """绕原点逆时针旋转 90°，再平移到非负局部坐标。"""

    rotated_raw: list[tuple[int, int, int, int]] = []
    for rect in rectangles:
        corners = (
            (-rect.y, rect.x),
            (-rect.y, rect.right),
            (-rect.top, rect.x),
            (-rect.top, rect.right),
        )
        min_x = min(point[0] for point in corners)
        max_x = max(point[0] for point in corners)
        min_y = min(point[1] for point in corners)
        max_y = max(point[1] for point in corners)
        rotated_raw.append((min_x, min_y, max_x - min_x, max_y - min_y))

    shift_x = -min(item[0] for item in rotated_raw)
    shift_y = -min(item[1] for item in rotated_raw)
    return tuple(
        sorted(
            ComponentRect(x + shift_x, y + shift_y, width, height)
            for x, y, width, height in rotated_raw
        )
    )


def generate_orientations(module: OrthogonalModule) -> tuple[ModuleOrientation, ...]:
    """预生成 0°、90°、180°、270°，并去除几何上重复的方向。"""

    rectangles = tuple(sorted(module.components))
    seen: set[tuple[ComponentRect, ...]] = set()
    orientations: list[ModuleOrientation] = []
    for quarter_turn in range(4):
        key = tuple(sorted(rectangles))
        if key not in seen:
            seen.add(key)
            orientations.append(
                ModuleOrientation(
                    degrees=quarter_turn * 90,
                    width=max(rect.right for rect in key),
                    height=max(rect.top for rect in key),
                    components=key,
                )
            )
        rectangles = _rotate_once(rectangles)
    return tuple(orientations)


def figure3_modules() -> tuple[OrthogonalModule, ...]:
    """返回赛题图 3 的 T 型、L 型和两个矩形模块。"""

    return (
        OrthogonalModule(
            "b1",
            (
                ComponentRect(0, 2, 4, 2),
                ComponentRect(1, 0, 2, 2),
            ),
        ),
        OrthogonalModule(
            "b2",
            (
                ComponentRect(0, 0, 1, 4),
                ComponentRect(1, 0, 1, 2),
            ),
        ),
        OrthogonalModule("b3", (ComponentRect(0, 0, 2, 1),)),
        OrthogonalModule("b4", (ComponentRect(0, 0, 1, 4),)),
    )


def _candidate_outlines(
    modules: tuple[OrthogonalModule, ...],
    orientations: tuple[tuple[ModuleOrientation, ...], ...],
    upper_area: int,
) -> tuple[tuple[int, int], ...]:
    total_area = sum(module.area for module in modules)
    candidates: list[tuple[int, int]] = []
    for area in range(total_area, upper_area + 1):
        same_area: list[tuple[int, int]] = []
        for height in range(1, isqrt(area) + 1):
            if area % height:
                continue
            width = area // height
            if all(
                any(shape.width <= width and shape.height <= height for shape in choices)
                for choices in orientations
            ):
                same_area.append((width, height))
        candidates.extend(sorted(same_area, key=lambda pair: (pair[0] - pair[1], pair[0])))
    return tuple(candidates)


def _build_fixed_outline_model(
    orientations: tuple[tuple[ModuleOrientation, ...], ...],
    width: int,
    height: int,
) -> _FixedOutlineContext:
    model = cp_model.CpModel()
    xs: list[cp_model.IntVar] = []
    ys: list[cp_model.IntVar] = []
    all_active: list[list[cp_model.BoolVarT]] = []
    x_intervals: list[cp_model.IntervalVar] = []
    y_intervals: list[cp_model.IntervalVar] = []
    right_touches: list[cp_model.BoolVarT] = []
    top_touches: list[cp_model.BoolVarT] = []

    for module_index, choices in enumerate(orientations):
        x = model.new_int_var(0, width, f"x_{module_index}")
        y = model.new_int_var(0, height, f"y_{module_index}")
        active_choices: list[cp_model.BoolVarT] = []
        for orientation_index, shape in enumerate(choices):
            active = model.new_bool_var(f"active_{module_index}_{orientation_index}")
            active_choices.append(active)
            model.add(x + shape.width <= width).only_enforce_if(active)
            model.add(y + shape.height <= height).only_enforce_if(active)

            right_touch = model.new_bool_var(f"right_{module_index}_{orientation_index}")
            top_touch = model.new_bool_var(f"top_{module_index}_{orientation_index}")
            model.add_implication(right_touch, active)
            model.add_implication(top_touch, active)
            model.add(x + shape.width == width).only_enforce_if(right_touch)
            model.add(y + shape.height == height).only_enforce_if(top_touch)
            right_touches.append(right_touch)
            top_touches.append(top_touch)

            for component_index, rect in enumerate(shape.components):
                suffix = f"{module_index}_{orientation_index}_{component_index}"
                x_intervals.append(
                    model.new_optional_fixed_size_interval_var(
                        x + rect.x,
                        rect.width,
                        active,
                        f"xi_{suffix}",
                    )
                )
                y_intervals.append(
                    model.new_optional_fixed_size_interval_var(
                        y + rect.y,
                        rect.height,
                        active,
                        f"yi_{suffix}",
                    )
                )
        model.add_exactly_one(active_choices)
        xs.append(x)
        ys.append(y)
        all_active.append(active_choices)

    model.add_no_overlap_2d(x_intervals, y_intervals)
    min_x = model.new_int_var(0, 0, "min_x")
    min_y = model.new_int_var(0, 0, "min_y")
    model.add_min_equality(min_x, xs)
    model.add_min_equality(min_y, ys)
    model.add(sum(right_touches) >= 1)
    model.add(sum(top_touches) >= 1)
    return _FixedOutlineContext(model, xs, ys, all_active)


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


def solve_q4(
    modules: Iterable[OrthogonalModule] | None = None,
    *,
    time_limit_per_outline: float = 10.0,
    workers: int = 1,
    seed: int = 20260810,
    log_search: bool = False,
) -> Q4Solution:
    """按面积升序、同面积长宽差升序精确检查整数轮廓。"""

    if time_limit_per_outline <= 0:
        raise ValueError("单轮廓求解时间必须为正数")
    if workers <= 0:
        raise ValueError("workers 必须为正整数")
    module_tuple = tuple(modules) if modules is not None else figure3_modules()
    if not module_tuple:
        raise ValueError("至少需要一个模块")
    names = [module.name for module in module_tuple]
    if len(names) != len(set(names)):
        raise ValueError("模块名称不能重复")

    orientation_sets = tuple(generate_orientations(module) for module in module_tuple)
    base_width = sum(choices[0].width for choices in orientation_sets)
    base_height = max(choices[0].height for choices in orientation_sets)
    upper_width, upper_height = max(base_width, base_height), min(base_width, base_height)
    upper_area = upper_width * upper_height
    total_area = sum(module.area for module in module_tuple)
    candidates = _candidate_outlines(module_tuple, orientation_sets, upper_area)

    started = perf_counter()
    attempts: list[OutlineAttempt] = []
    unresolved_before_solution = 0
    infeasible_before_solution = 0
    selected: tuple[int, int, _FixedOutlineContext, cp_model.CpSolver] | None = None

    for width, height in candidates:
        context = _build_fixed_outline_model(orientation_sets, width, height)
        solver = _configure_solver(
            time_limit_per_outline,
            workers,
            seed,
            log_search,
        )
        status = solver.solve(context.model)
        status_name = solver.status_name(status)
        attempts.append(
            OutlineAttempt(
                width=width,
                height=height,
                area=width * height,
                status=status_name,
                wall_time_seconds=solver.wall_time,
                conflicts=solver.num_conflicts,
                branches=solver.num_branches,
            )
        )
        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            selected = (width, height, context, solver)
            break
        if status == cp_model.INFEASIBLE:
            infeasible_before_solution += 1
        else:
            unresolved_before_solution += 1

    if selected is None:
        raise RuntimeError("未在构造上界内找到可行布局；请提高单轮廓求解时间")

    width, height, context, solver = selected
    placements: list[Q4Placement] = []
    for module_index, module in enumerate(module_tuple):
        active_index = next(
            index
            for index, active in enumerate(context.active_orientations[module_index])
            if solver.value(active)
        )
        shape = orientation_sets[module_index][active_index]
        x = solver.value(context.xs[module_index])
        y = solver.value(context.ys[module_index])
        placements.append(
            Q4Placement(
                name=module.name,
                x=x,
                y=y,
                orientation_degrees=shape.degrees,
                width=shape.width,
                height=shape.height,
                components=shape.components,
            )
        )

    area = width * height
    earlier_attempts = attempts[:-1]
    lower_areas_resolved = all(
        attempt.status == "INFEASIBLE"
        for attempt in earlier_attempts
        if attempt.area < area
    )
    closer_shapes_resolved = all(
        attempt.status == "INFEASIBLE"
        for attempt in earlier_attempts
        if attempt.area == area
    )
    area_proven = area == total_area or lower_areas_resolved
    lexicographic_proven = area_proven and closer_shapes_resolved
    search = Q4SearchStats(
        area_lower_bound=total_area,
        initial_area_upper_bound=upper_area,
        checked_outlines=len(attempts),
        proven_infeasible_outlines=infeasible_before_solution,
        unresolved_outlines=unresolved_before_solution,
        wall_time_seconds=perf_counter() - started,
        attempts=tuple(attempts),
    )
    solution = Q4Solution(
        method="component-rectangles+four-orientation+cp-sat-outline-enumeration",
        width=width,
        height=height,
        area=area,
        total_module_area=total_area,
        placements=tuple(placements),
        search=search,
        area_proven_optimal=area_proven,
        lexicographic_proven_optimal=lexicographic_proven,
        seed=seed,
        workers=workers,
    )
    validate_q4_solution(module_tuple, solution)
    return solution


def validate_q4_solution(
    modules: Iterable[OrthogonalModule],
    solution: Q4Solution,
) -> None:
    """独立检查方向、真实分块几何、边界、轮廓与模块间不重叠。"""

    module_tuple = tuple(modules)
    if solution.width <= 0 or solution.height <= 0:
        raise ValueError("轮廓宽高必须为正")
    if solution.width < solution.height:
        raise ValueError("轮廓应按 width >= height 规范化")
    if solution.area != solution.width * solution.height:
        raise ValueError("记录面积与轮廓宽高不一致")
    if solution.total_module_area != sum(module.area for module in module_tuple):
        raise ValueError("记录的模块总面积不一致")
    if solution.area < solution.total_module_area:
        raise ValueError("轮廓面积小于模块总面积下界")

    module_by_name = {module.name: module for module in module_tuple}
    placement_by_name = {placement.name: placement for placement in solution.placements}
    if len(placement_by_name) != len(solution.placements):
        raise ValueError("布局中存在重复模块")
    if set(placement_by_name) != set(module_by_name):
        raise ValueError("布局模块集合与输入不一致")

    global_components: list[tuple[str, ComponentRect]] = []
    for name, module in module_by_name.items():
        placement = placement_by_name[name]
        orientation_by_degrees = {
            orientation.degrees: orientation for orientation in generate_orientations(module)
        }
        if placement.orientation_degrees not in orientation_by_degrees:
            raise ValueError(f"{name}: 非法或重复的旋转方向")
        expected = orientation_by_degrees[placement.orientation_degrees]
        if (placement.width, placement.height) != (expected.width, expected.height):
            raise ValueError(f"{name}: 旋转方向与包围盒尺寸不一致")
        if tuple(sorted(placement.components)) != expected.components:
            raise ValueError(f"{name}: 旋转方向与组成矩形不一致")
        if placement.x < 0 or placement.y < 0:
            raise ValueError(f"{name}: 坐标不能为负")
        for rect in placement.components:
            global_rect = ComponentRect(
                placement.x + rect.x,
                placement.y + rect.y,
                rect.width,
                rect.height,
            )
            if global_rect.right > solution.width or global_rect.top > solution.height:
                raise ValueError(f"{name}: 超出轮廓边界")
            global_components.append((name, global_rect))

    for index, (first_name, first) in enumerate(global_components):
        for second_name, second in global_components[index + 1 :]:
            if first_name != second_name and _rectangles_overlap(first, second):
                raise ValueError(f"{first_name} 与 {second_name} 重叠")

    min_x = min(rect.x for _, rect in global_components)
    min_y = min(rect.y for _, rect in global_components)
    max_x = max(rect.right for _, rect in global_components)
    max_y = max(rect.top for _, rect in global_components)
    if (min_x, min_y, max_x, max_y) != (0, 0, solution.width, solution.height):
        raise ValueError("轮廓不是布局的最小外包矩形")
