"""面向矩形 floorplanning 的 MaxRects 多起点构造与局部改进。"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, sqrt
from random import Random
from time import perf_counter

from .data import Block, FloorplanProblem


@dataclass(frozen=True, slots=True)
class ConstructivePlacement:
    name: str
    x: int
    y: int
    width: int
    height: int
    rotated: bool


@dataclass(frozen=True, slots=True)
class ConstructiveLayout:
    width: int
    height: int
    placements: tuple[ConstructivePlacement, ...]
    target_width: int
    strategy: str

    @property
    def area(self) -> int:
        return self.width * self.height

    @property
    def lex_score(self) -> tuple[int, int]:
        return self.area, abs(self.width - self.height)


@dataclass(frozen=True, slots=True)
class ConstructionStats:
    evaluations: int
    sampled_widths: int
    deterministic_orders: int
    random_starts: int
    local_iterations: int
    accepted_local_moves: int
    area_before_local_search: int
    area_after_local_search: int
    wall_time_seconds: float


@dataclass(frozen=True, slots=True)
class ConstructionResult:
    layout: ConstructiveLayout
    stats: ConstructionStats


@dataclass(frozen=True, slots=True)
class _FreeRectangle:
    x: int
    y: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def top(self) -> int:
        return self.y + self.height


@dataclass(slots=True)
class _SearchState:
    order: list[Block]
    target_width: int
    rule: str
    forced_orientations: dict[str, bool]
    layout: ConstructiveLayout


def _orientations(
    block: Block,
    forced_orientation: bool | None,
) -> tuple[tuple[int, int, bool], ...]:
    orientations = ((block.width, block.height, False),)
    if block.width != block.height:
        orientations += ((block.height, block.width, True),)
    if forced_orientation is None:
        return orientations
    return tuple(item for item in orientations if item[2] == forced_orientation)


def _intersects(free: _FreeRectangle, used: ConstructivePlacement) -> bool:
    return not (
        used.x >= free.right
        or used.x + used.width <= free.x
        or used.y >= free.top
        or used.y + used.height <= free.y
    )


def _split_free_rectangles(
    free_rectangles: list[_FreeRectangle],
    used: ConstructivePlacement,
) -> list[_FreeRectangle]:
    split: list[_FreeRectangle] = []
    used_right = used.x + used.width
    used_top = used.y + used.height

    for free in free_rectangles:
        if not _intersects(free, used):
            split.append(free)
            continue
        if used.x > free.x:
            split.append(_FreeRectangle(free.x, free.y, used.x - free.x, free.height))
        if used_right < free.right:
            split.append(_FreeRectangle(used_right, free.y, free.right - used_right, free.height))
        if used.y > free.y:
            split.append(_FreeRectangle(free.x, free.y, free.width, used.y - free.y))
        if used_top < free.top:
            split.append(_FreeRectangle(free.x, used_top, free.width, free.top - used_top))

    unique = list({rectangle for rectangle in split if rectangle.width > 0 and rectangle.height > 0})
    pruned: list[_FreeRectangle] = []
    for index, rectangle in enumerate(unique):
        contained = any(
            index != other_index
            and other.x <= rectangle.x
            and other.y <= rectangle.y
            and other.right >= rectangle.right
            and other.top >= rectangle.top
            for other_index, other in enumerate(unique)
        )
        if not contained:
            pruned.append(rectangle)
    return pruned


def _placement_score(
    rule: str,
    free: _FreeRectangle,
    width: int,
    height: int,
    used_width: int,
    used_height: int,
) -> tuple[int, ...]:
    leftover_width = free.width - width
    leftover_height = free.height - height
    short_side = min(leftover_width, leftover_height)
    long_side = max(leftover_width, leftover_height)
    top = free.y + height
    right = free.x + width
    new_width = max(used_width, right)
    new_height = max(used_height, top)
    if rule == "bottom_left":
        return top, free.x, short_side, long_side
    if rule == "min_area":
        return new_width * new_height, abs(new_width - new_height), top, free.x, short_side
    if rule == "best_area_fit":
        return free.width * free.height - width * height, short_side, long_side, top, free.x
    if rule == "best_short_side_fit":
        return short_side, long_side, top, free.x
    raise ValueError(f"未知 MaxRects 规则：{rule}")


def pack_maxrects(
    blocks: tuple[Block, ...] | list[Block],
    target_width: int,
    *,
    rule: str = "best_short_side_fit",
    forced_orientations: dict[str, bool] | None = None,
    height_cap: int | None = None,
) -> ConstructiveLayout | None:
    """在给定候选宽度内用 MaxRects 放置全部模块。"""

    ordered_blocks = tuple(blocks)
    if not ordered_blocks or target_width <= 0:
        return None
    forced_orientations = forced_orientations or {}
    if height_cap is None:
        height_cap = sum(max(block.width, block.height) for block in ordered_blocks)

    free_rectangles = [_FreeRectangle(0, 0, target_width, height_cap)]
    placements: list[ConstructivePlacement] = []
    used_width = 0
    used_height = 0

    for block in ordered_blocks:
        candidates: list[
            tuple[tuple[int, ...], int, int, int, int, bool, int, _FreeRectangle]
        ] = []
        forced = forced_orientations.get(block.name)
        for free_index, free in enumerate(free_rectangles):
            for width, height, rotated in _orientations(block, forced):
                if width > free.width or height > free.height:
                    continue
                score = _placement_score(
                    rule,
                    free,
                    width,
                    height,
                    used_width,
                    used_height,
                )
                candidates.append(
                    (score, free.y, free.x, width, height, rotated, free_index, free)
                )
        if not candidates:
            return None

        _, _, _, width, height, rotated, _, free = min(candidates)
        placement = ConstructivePlacement(
            name=block.name,
            x=free.x,
            y=free.y,
            width=width,
            height=height,
            rotated=rotated,
        )
        placements.append(placement)
        used_width = max(used_width, placement.x + placement.width)
        used_height = max(used_height, placement.y + placement.height)
        free_rectangles = _split_free_rectangles(free_rectangles, placement)

    return ConstructiveLayout(
        width=used_width,
        height=used_height,
        placements=tuple(placements),
        target_width=target_width,
        strategy=f"maxrects:{rule}",
    )


def _normalize_layout(layout: ConstructiveLayout, problem: FloorplanProblem) -> ConstructiveLayout:
    by_name = {placement.name: placement for placement in layout.placements}
    ordered = tuple(by_name[block.name] for block in problem.blocks)
    if layout.width >= layout.height:
        return ConstructiveLayout(
            width=layout.width,
            height=layout.height,
            placements=ordered,
            target_width=layout.target_width,
            strategy=layout.strategy,
        )

    rotated = tuple(
        ConstructivePlacement(
            name=placement.name,
            x=placement.y,
            y=layout.width - placement.x - placement.width,
            width=placement.height,
            height=placement.width,
            rotated=not placement.rotated,
        )
        for placement in ordered
    )
    return ConstructiveLayout(
        width=layout.height,
        height=layout.width,
        placements=rotated,
        target_width=layout.target_width,
        strategy=layout.strategy + "+global-rotate",
    )


def _deterministic_orders(blocks: tuple[Block, ...]) -> list[tuple[str, list[Block]]]:
    definitions = (
        ("area", lambda block: (-block.area, -max(block.width, block.height), block.name)),
        ("max-side", lambda block: (-max(block.width, block.height), -block.area, block.name)),
        ("aspect-difference", lambda block: (-abs(block.width - block.height), -block.area, block.name)),
        ("perimeter", lambda block: (-(block.width + block.height), -block.area, block.name)),
    )
    return [(name, sorted(blocks, key=key)) for name, key in definitions]


def _sample_widths(problem: FloorplanProblem, multiplier: float, samples: int) -> list[int]:
    if multiplier < 1.0:
        raise ValueError("width_multiplier 不能小于 1")
    if samples <= 0:
        raise ValueError("width_samples 必须为正整数")
    root_area = sqrt(problem.total_block_area)
    lower = max(ceil(root_area), max(min(block.width, block.height) for block in problem.blocks))
    upper = max(lower, ceil(multiplier * root_area))
    span = upper - lower
    if span + 1 <= samples:
        return list(range(lower, upper + 1))
    if samples == 1:
        return [lower]
    return sorted({round(lower + span * index / (samples - 1)) for index in range(samples)})


def _randomized_order(base: list[Block], rng: Random) -> list[Block]:
    order = list(base)
    swaps = max(2, len(order) // 5)
    for _ in range(swaps):
        first = rng.randrange(len(order))
        second = rng.randrange(len(order))
        order[first], order[second] = order[second], order[first]
    return order


def _local_search(
    initial_states: list[_SearchState],
    *,
    lower_width: int,
    upper_width: int,
    iterations: int,
    rng: Random,
    deadline: float | None = None,
) -> tuple[_SearchState, int, int]:
    if iterations <= 0:
        return min(initial_states, key=lambda state: state.layout.lex_score), 0, 0

    accepted = 0
    evaluations = 0
    per_start = max(1, iterations // len(initial_states))
    best_state = min(initial_states, key=lambda state: state.layout.lex_score)

    for initial in initial_states:
        current = _SearchState(
            order=list(initial.order),
            target_width=initial.target_width,
            rule=initial.rule,
            forced_orientations=dict(initial.forced_orientations),
            layout=initial.layout,
        )
        for _ in range(per_start):
            if deadline is not None and perf_counter() >= deadline:
                return best_state, evaluations, accepted
            trial_order = list(current.order)
            trial_width = current.target_width
            trial_forced = dict(current.forced_orientations)
            operation = rng.randrange(4)

            if operation == 0:
                first, second = rng.sample(range(len(trial_order)), 2)
                trial_order[first], trial_order[second] = trial_order[second], trial_order[first]
            elif operation == 1:
                source, destination = rng.sample(range(len(trial_order)), 2)
                block = trial_order.pop(source)
                trial_order.insert(destination, block)
            elif operation == 2:
                rotatable = [block for block in trial_order if block.width != block.height]
                if not rotatable:
                    continue
                block = rng.choice(rotatable)
                current_placement = next(
                    placement for placement in current.layout.placements if placement.name == block.name
                )
                trial_forced[block.name] = not current_placement.rotated
            else:
                radius = max(1, (upper_width - lower_width) // 30)
                trial_width = min(
                    upper_width,
                    max(lower_width, trial_width + rng.randint(-radius, radius)),
                )

            layout = pack_maxrects(
                trial_order,
                trial_width,
                rule=current.rule,
                forced_orientations=trial_forced,
                height_cap=max(
                    max(min(block.width, block.height) for block in trial_order),
                    (current.layout.area - 1) // trial_width,
                ),
            )
            evaluations += 1
            if layout is not None and layout.lex_score < current.layout.lex_score:
                current = _SearchState(
                    order=trial_order,
                    target_width=trial_width,
                    rule=current.rule,
                    forced_orientations=trial_forced,
                    layout=layout,
                )
                accepted += 1
                if current.layout.lex_score < best_state.layout.lex_score:
                    best_state = current

    return best_state, evaluations, accepted


def construct_upper_bound(
    problem: FloorplanProblem,
    *,
    width_multiplier: float = 1.8,
    width_samples: int = 64,
    random_starts: int = 24,
    local_iterations: int = 120,
    seed: int = 20260810,
    time_limit: float = 75.0,
) -> ConstructionResult:
    """多宽度、多排序、多规则构造，并以严格字典序做局部改进。"""

    started = perf_counter()
    if time_limit <= 0:
        raise ValueError("construction_time_limit 必须为正数")
    deadline = started + time_limit
    deterministic_deadline = started + 0.65 * time_limit
    refinement_deadline = started + 0.80 * time_limit
    random_deadline = started + 0.88 * time_limit
    rng = Random(seed)
    widths = _sample_widths(problem, width_multiplier, width_samples)
    orders = _deterministic_orders(problem.blocks)
    rules = ("best_short_side_fit", "min_area", "bottom_left", "best_area_fit")
    states: list[_SearchState] = []
    evaluations = 0
    best_layout: ConstructiveLayout | None = None
    minimum_height = max(min(block.width, block.height) for block in problem.blocks)

    deterministic_finished = True
    for rule in rules:
        for _, order in orders:
            for width in widths:
                if perf_counter() >= deterministic_deadline:
                    deterministic_finished = False
                    break
                height_cap = None
                if best_layout is not None:
                    height_cap = max(minimum_height, (best_layout.area - 1) // width)
                layout = pack_maxrects(order, width, rule=rule, height_cap=height_cap)
                evaluations += 1
                if layout is not None:
                    if best_layout is None or layout.lex_score < best_layout.lex_score:
                        best_layout = layout
                    states.append(
                        _SearchState(
                            order=list(order),
                            target_width=width,
                            rule=rule,
                            forced_orientations={},
                            layout=layout,
                        )
                    )
            if not deterministic_finished:
                break
        if not deterministic_finished:
            break

    if not states:
        raise RuntimeError("MaxRects 未能构造任何可行布局")

    states.sort(key=lambda state: state.layout.lex_score)
    coarse_step = max(1, (max(widths) - min(widths)) // max(1, len(widths) - 1))
    refined_states: list[_SearchState] = []
    seen_refinements: set[tuple[tuple[str, ...], str, int]] = set()
    for state in states[: min(8, len(states))]:
        order_key = tuple(block.name for block in state.order)
        for width in range(
            max(min(widths), state.target_width - coarse_step),
            min(max(widths), state.target_width + coarse_step) + 1,
        ):
            if perf_counter() >= refinement_deadline:
                break
            key = (order_key, state.rule, width)
            if key in seen_refinements:
                continue
            seen_refinements.add(key)
            height_cap = max(minimum_height, (best_layout.area - 1) // width)
            layout = pack_maxrects(state.order, width, rule=state.rule, height_cap=height_cap)
            evaluations += 1
            if layout is not None:
                if layout.lex_score < best_layout.lex_score:
                    best_layout = layout
                refined_states.append(
                    _SearchState(
                        order=list(state.order),
                        target_width=width,
                        rule=state.rule,
                        forced_orientations={},
                        layout=layout,
                    )
                )
        if perf_counter() >= refinement_deadline:
            break
    states.extend(refined_states)

    completed_random_starts = 0
    for _ in range(random_starts):
        if perf_counter() >= random_deadline:
            break
        _, base = rng.choice(orders)
        order = _randomized_order(base, rng)
        width = rng.choice(widths)
        rule = rng.choice(rules)
        height_cap = max(minimum_height, (best_layout.area - 1) // width)
        layout = pack_maxrects(order, width, rule=rule, height_cap=height_cap)
        evaluations += 1
        completed_random_starts += 1
        if layout is not None:
            if layout.lex_score < best_layout.lex_score:
                best_layout = layout
            states.append(
                _SearchState(
                    order=order,
                    target_width=width,
                    rule=rule,
                    forced_orientations={},
                    layout=layout,
                )
            )

    states.sort(key=lambda state: state.layout.lex_score)
    best_before_local = states[0].layout
    local_starts = states[: min(4, len(states))]
    best_state, local_evaluations, accepted = _local_search(
        local_starts,
        lower_width=min(widths),
        upper_width=max(widths),
        iterations=local_iterations,
        rng=rng,
        deadline=deadline,
    )
    evaluations += local_evaluations
    best_layout = _normalize_layout(best_state.layout, problem)

    return ConstructionResult(
        layout=best_layout,
        stats=ConstructionStats(
            evaluations=evaluations,
            sampled_widths=len(widths),
            deterministic_orders=len(orders),
            random_starts=completed_random_starts,
            local_iterations=local_evaluations,
            accepted_local_moves=accepted,
            area_before_local_search=best_before_local.area,
            area_after_local_search=best_layout.area,
            wall_time_seconds=perf_counter() - started,
        ),
    )
