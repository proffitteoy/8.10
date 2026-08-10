"""B*-Tree 编码、轮廓压紧解码与三阶段 Fast-SA 搜索。"""

from __future__ import annotations

from dataclasses import dataclass
from math import exp, log
from random import Random
from time import perf_counter

from .data import FloorplanDataset, FloorplanProblem
from .q1 import Placement


@dataclass(frozen=True, slots=True)
class BStarTree:
    """有序二叉树；节点槽位与模块编号通过 ``block_at`` 分离。"""

    block_at: tuple[int, ...]
    left: tuple[int, ...]
    right: tuple[int, ...]
    rotated: tuple[bool, ...]


@dataclass(frozen=True, slots=True)
class DecodedBStarTree:
    """轮廓压紧后自动无重叠的矩形布局。"""

    width: int
    height: int
    placements: tuple[Placement, ...]


@dataclass(frozen=True, slots=True)
class FastSAStats:
    """一次或多次 Fast-SA 重启的可复现实验统计。"""

    objective: str
    outline_limit: int
    seed: int
    restarts: int
    completed_restarts: int
    requested_iterations_per_restart: int
    time_limit_seconds: float
    initial_acceptance_probability: float
    pseudo_greedy_c: float
    pseudo_greedy_epochs: int
    completed_iterations: int
    accepted_moves: int
    uphill_accepted_moves: int
    feasible_evaluations: int
    rotate_attempts: int
    move_attempts: int
    swap_attempts: int
    initial_temperature: float
    final_temperature: float
    best_violation: int
    best_width: int
    best_height: int
    wall_time_seconds: float


@dataclass(frozen=True, slots=True)
class FastSAResult:
    """Fast-SA 找到的最佳树；``placements`` 总是与 ``tree`` 同源。"""

    tree: BStarTree
    placements: tuple[Placement, ...]
    width: int
    height: int
    violation: int
    total_hpwl2: int | None
    stats: FastSAStats

    @property
    def feasible(self) -> bool:
        return self.violation == 0


@dataclass(frozen=True, slots=True)
class _Evaluation:
    decoded: DecodedBStarTree
    violation: int
    total_hpwl2: int
    energy: float


def validate_bstar_tree(tree: BStarTree, block_count: int) -> None:
    """检查树的排列、索引、连通性与单亲约束。"""

    if block_count <= 0:
        raise ValueError("B*-Tree 至少需要一个模块")
    fields = (tree.block_at, tree.left, tree.right, tree.rotated)
    if any(len(field) != block_count for field in fields):
        raise ValueError("B*-Tree 字段长度与模块数不一致")
    if sorted(tree.block_at) != list(range(block_count)):
        raise ValueError("B*-Tree 的 block_at 必须是模块编号的排列")

    parent_count = [0] * block_count
    for node, children in enumerate(zip(tree.left, tree.right, strict=True)):
        left, right = children
        if left == right and left != -1:
            raise ValueError(f"节点 {node} 的左右孩子不能相同")
        for child in children:
            if child == -1:
                continue
            if child < 0 or child >= block_count:
                raise ValueError(f"节点 {node} 包含越界孩子索引 {child}")
            parent_count[child] += 1
    if parent_count[0] != 0 or any(count != 1 for count in parent_count[1:]):
        raise ValueError("B*-Tree 必须以节点 0 为唯一根，且每个非根节点只有一个父节点")

    visited: set[int] = set()
    stack = [0]
    while stack:
        node = stack.pop()
        if node in visited:
            raise ValueError("B*-Tree 中存在环")
        visited.add(node)
        if tree.right[node] != -1:
            stack.append(tree.right[node])
        if tree.left[node] != -1:
            stack.append(tree.left[node])
    if len(visited) != block_count:
        raise ValueError("B*-Tree 存在与根断开的节点")


def _decode_bstar_tree(
    problem: FloorplanProblem,
    tree: BStarTree,
    *,
    validate: bool,
) -> DecodedBStarTree:
    block_count = len(problem.blocks)
    if validate:
        validate_bstar_tree(tree, block_count)

    node_x = [0] * block_count
    node_width = [0] * block_count
    skyline = [0] * sum(max(block.width, block.height) for block in problem.blocks)
    placements_by_block: list[Placement | None] = [None] * block_count
    outline_width = 0
    outline_height = 0

    stack = [0]
    while stack:
        node = stack.pop()
        block_index = tree.block_at[node]
        block = problem.blocks[block_index]
        rotated = tree.rotated[node]
        width, height = (
            (block.height, block.width) if rotated else (block.width, block.height)
        )
        x = node_x[node]
        y = max(skyline[x : x + width], default=0)
        skyline[x : x + width] = [y + height] * width
        node_width[node] = width
        placements_by_block[block_index] = Placement(
            name=block.name,
            x=x,
            y=y,
            width=width,
            height=height,
            rotated=rotated,
        )
        outline_width = max(outline_width, x + width)
        outline_height = max(outline_height, y + height)

        right = tree.right[node]
        if right != -1:
            node_x[right] = x
            stack.append(right)
        left = tree.left[node]
        if left != -1:
            node_x[left] = x + width
            stack.append(left)

    if any(placement is None for placement in placements_by_block):
        raise ValueError("B*-Tree 解码后缺少模块")
    return DecodedBStarTree(
        width=outline_width,
        height=outline_height,
        placements=tuple(placement for placement in placements_by_block if placement is not None),
    )


def decode_bstar_tree(problem: FloorplanProblem, tree: BStarTree) -> DecodedBStarTree:
    """按左孩子向右、右孩子向上的规则用整数轮廓结构压紧布局。"""

    return _decode_bstar_tree(problem, tree, validate=True)


def complete_bstar_tree(
    problem: FloorplanProblem,
    *,
    rng: Random | None = None,
    outline_limit: int | None = None,
) -> BStarTree:
    """按原论文建议构造完全二叉树初态，并可随机化模块排列。"""

    block_at = list(range(len(problem.blocks)))
    block_at.sort(
        key=lambda index: (
            -problem.blocks[index].area,
            -max(problem.blocks[index].width, problem.blocks[index].height),
            problem.blocks[index].name,
        )
    )
    if rng is not None:
        rng.shuffle(block_at)
    count = len(block_at)
    left = [2 * node + 1 if 2 * node + 1 < count else -1 for node in range(count)]
    right = [2 * node + 2 if 2 * node + 2 < count else -1 for node in range(count)]
    rotated: list[bool] = []
    for block_index in block_at:
        block = problem.blocks[block_index]
        if outline_limit is not None:
            normal_fits = block.width <= outline_limit and block.height <= outline_limit
            rotated_fits = block.height <= outline_limit and block.width <= outline_limit
            if normal_fits != rotated_fits:
                rotated.append(rotated_fits)
                continue
        rotated.append(bool(rng and rng.randrange(2)) if block.width != block.height else False)
    return BStarTree(tuple(block_at), tuple(left), tuple(right), tuple(rotated))


def bstar_tree_from_placements(
    problem: FloorplanProblem,
    placements: tuple[Placement, ...],
) -> BStarTree | None:
    """把已知紧凑布局按原论文的右侧邻接/同 x 上方关系转成搜索初态。"""

    if {placement.name for placement in placements} != {
        block.name for block in problem.blocks
    }:
        raise ValueError("初始布局的模块集合与问题不一致")
    block_index = {block.name: index for index, block in enumerate(problem.blocks)}

    # B*-Tree 的唯一线性构造要求输入为 admissible placement：任何模块都不能
    # 在不引起重叠的前提下继续向左或向下移动。MaxRects 的可行解先做交替压紧。
    compacted = {
        placement.name: Placement(
            placement.name,
            placement.x,
            placement.y,
            placement.width,
            placement.height,
            placement.rotated,
        )
        for placement in placements
    }
    for _ in range(2 * len(placements) + 1):
        changed = False
        for placement in sorted(compacted.values(), key=lambda item: (item.x, item.y, item.name)):
            blockers = [
                other
                for other in compacted.values()
                if other.name != placement.name
                and other.x + other.width <= placement.x
                and not (
                    other.y + other.height <= placement.y
                    or placement.y + placement.height <= other.y
                )
            ]
            new_x = max((other.x + other.width for other in blockers), default=0)
            if new_x < placement.x:
                compacted[placement.name] = Placement(
                    placement.name,
                    new_x,
                    placement.y,
                    placement.width,
                    placement.height,
                    placement.rotated,
                )
                changed = True
        for placement in sorted(compacted.values(), key=lambda item: (item.y, item.x, item.name)):
            blockers = [
                other
                for other in compacted.values()
                if other.name != placement.name
                and other.y + other.height <= placement.y
                and not (
                    other.x + other.width <= placement.x
                    or placement.x + placement.width <= other.x
                )
            ]
            new_y = max((other.y + other.height for other in blockers), default=0)
            if new_y < placement.y:
                compacted[placement.name] = Placement(
                    placement.name,
                    placement.x,
                    new_y,
                    placement.width,
                    placement.height,
                    placement.rotated,
                )
                changed = True
        if not changed:
            break

    compacted_values = tuple(compacted.values())
    root_candidates = [
        placement for placement in compacted_values if placement.x == 0 and placement.y == 0
    ]
    if root_candidates:
        left_by_block = [-1] * len(problem.blocks)
        right_by_block = [-1] * len(problem.blocks)
        root = min(root_candidates, key=lambda item: item.name)
        visited: set[int] = set()

        def build(block_id: int) -> None:
            visited.add(block_id)
            placement = compacted[problem.blocks[block_id].name]
            right_adjacent = [
                other
                for other in compacted_values
                if block_index[other.name] not in visited
                and other.x == placement.x + placement.width
                and not (
                    other.y + other.height <= placement.y
                    or placement.y + placement.height <= other.y
                )
            ]
            if right_adjacent:
                child = min(right_adjacent, key=lambda item: (item.y, item.name))
                child_id = block_index[child.name]
                left_by_block[block_id] = child_id
                build(child_id)

            above = [
                other
                for other in compacted_values
                if block_index[other.name] not in visited
                and other.x == placement.x
                and other.y >= placement.y + placement.height
            ]
            if above:
                child = min(above, key=lambda item: (item.y, item.name))
                child_id = block_index[child.name]
                right_by_block[block_id] = child_id
                build(child_id)

        root_block = block_index[root.name]
        build(root_block)
        if len(visited) == len(problem.blocks):
            traversal: list[int] = []
            stack = [root_block]
            while stack:
                node = stack.pop()
                traversal.append(node)
                if right_by_block[node] != -1:
                    stack.append(right_by_block[node])
                if left_by_block[node] != -1:
                    stack.append(left_by_block[node])
            slot_of = {block: slot for slot, block in enumerate(traversal)}
            return BStarTree(
                block_at=tuple(traversal),
                left=tuple(
                    slot_of[left_by_block[block]] if left_by_block[block] != -1 else -1
                    for block in traversal
                ),
                right=tuple(
                    slot_of[right_by_block[block]] if right_by_block[block] != -1 else -1
                    for block in traversal
                ),
                rotated=tuple(
                    compacted[problem.blocks[block].name].rotated for block in traversal
                ),
            )

    # 若一次递归未覆盖全部模块，按从低到高的轮廓事件补建：每个模块优先成为
    # 某个左侧相邻模块的左孩子；该槽位已占用时，才接到同 x 低层模块的右链。
    # 与“整列只选一个锚点”相比，这能保留不同高度处的右侧邻接关系。
    event_left = [-1] * len(problem.blocks)
    event_right = [-1] * len(problem.blocks)
    event_root = min(
        (placement for placement in compacted_values if placement.x == 0),
        key=lambda item: (item.y, item.name),
    )
    attached = {block_index[event_root.name]}
    event_failed = event_root.y != 0
    for x in sorted({placement.x for placement in compacted_values}):
        group = sorted(
            (placement for placement in compacted_values if placement.x == x),
            key=lambda item: (item.y, item.name),
        )
        for placement in group:
            placement_id = block_index[placement.name]
            if placement_id in attached:
                continue
            adjacent = [
                other
                for other in compacted_values
                if other.x + other.width == x
                and block_index[other.name] in attached
                and event_left[block_index[other.name]] == -1
                and not (
                    other.y + other.height <= placement.y
                    or placement.y + placement.height <= other.y
                )
            ]
            if adjacent:
                parent = min(
                    adjacent,
                    key=lambda item: (
                        abs(item.y + item.height - placement.y),
                        -item.y,
                        item.name,
                    ),
                )
                event_left[block_index[parent.name]] = placement_id
                attached.add(placement_id)
                continue
            below = [
                other
                for other in group
                if other.y < placement.y
                and block_index[other.name] in attached
                and event_right[block_index[other.name]] == -1
            ]
            if below:
                parent = max(below, key=lambda item: (item.y, item.name))
                event_right[block_index[parent.name]] = placement_id
                attached.add(placement_id)
            else:
                event_failed = True
                break
        if event_failed:
            break

    if not event_failed and len(attached) == len(problem.blocks):
        root_block = block_index[event_root.name]
        traversal = []
        stack = [root_block]
        seen: set[int] = set()
        while stack:
            node = stack.pop()
            if node in seen:
                event_failed = True
                break
            seen.add(node)
            traversal.append(node)
            if event_right[node] != -1:
                stack.append(event_right[node])
            if event_left[node] != -1:
                stack.append(event_left[node])
        if not event_failed and len(traversal) == len(problem.blocks):
            slot_of = {block: slot for slot, block in enumerate(traversal)}
            event_tree = BStarTree(
                block_at=tuple(traversal),
                left=tuple(
                    slot_of[event_left[block]] if event_left[block] != -1 else -1
                    for block in traversal
                ),
                right=tuple(
                    slot_of[event_right[block]] if event_right[block] != -1 else -1
                    for block in traversal
                ),
                rotated=tuple(
                    compacted[problem.blocks[block].name].rotated for block in traversal
                ),
            )
            decoded = _decode_bstar_tree(problem, event_tree, validate=True)
            source_width = max(
                placement.x + placement.width for placement in compacted_values
            )
            source_height = max(
                placement.y + placement.height for placement in compacted_values
            )
            if decoded.width <= source_width and decoded.height <= source_height:
                return event_tree

    # 非典型输入最后退回按 x 分组的保守构造；调用方会再次解码并记录初态
    # 是否满足固定轮廓，因此不会把转换失败静默当作可行。
    by_x: dict[int, list[Placement]] = {}
    for placement in compacted_values:
        by_x.setdefault(placement.x, []).append(placement)
    for group in by_x.values():
        group.sort(key=lambda placement: (placement.y, placement.name))
    if 0 not in by_x:
        return None

    left_by_block = [-1] * len(problem.blocks)
    right_by_block = [-1] * len(problem.blocks)
    root_block = block_index[by_x[0][0].name]
    for first, second in zip(by_x[0], by_x[0][1:]):
        right_by_block[block_index[first.name]] = block_index[second.name]

    processed: list[Placement] = list(by_x[0])
    for x in sorted(value for value in by_x if value != 0):
        group = by_x[x]
        lowest = group[0]
        candidates = [
            placement for placement in processed if placement.x + placement.width == x
        ]
        if not candidates:
            return None

        def anchor_key(placement: Placement) -> tuple[int, int, int, str]:
            overlaps = not (
                placement.y + placement.height <= lowest.y
                or lowest.y + lowest.height <= placement.y
            )
            return (
                0 if overlaps else 1,
                abs(placement.y + placement.height - lowest.y),
                -placement.y,
                placement.name,
            )

        anchor = min(candidates, key=anchor_key)
        anchor_index = block_index[anchor.name]
        if left_by_block[anchor_index] != -1:
            return None
        left_by_block[anchor_index] = block_index[lowest.name]
        for first, second in zip(group, group[1:]):
            right_by_block[block_index[first.name]] = block_index[second.name]
        processed.extend(group)

    traversal: list[int] = []
    stack = [root_block]
    seen: set[int] = set()
    while stack:
        node = stack.pop()
        if node in seen:
            return None
        seen.add(node)
        traversal.append(node)
        if right_by_block[node] != -1:
            stack.append(right_by_block[node])
        if left_by_block[node] != -1:
            stack.append(left_by_block[node])
    if len(traversal) != len(problem.blocks):
        return None

    slot_of = {block: slot for slot, block in enumerate(traversal)}
    placement_by_name = compacted
    return BStarTree(
        block_at=tuple(traversal),
        left=tuple(
            slot_of[left_by_block[block]] if left_by_block[block] != -1 else -1
            for block in traversal
        ),
        right=tuple(
            slot_of[right_by_block[block]] if right_by_block[block] != -1 else -1
            for block in traversal
        ),
        rotated=tuple(placement_by_name[problem.blocks[block].name].rotated for block in traversal),
    )


def _hpwl2(dataset: FloorplanDataset, placements: tuple[Placement, ...]) -> int:
    centers = {
        placement.name: (
            2 * placement.x + placement.width,
            2 * placement.y + placement.height,
        )
        for placement in placements
    }
    for terminal in dataset.terminals:
        doubled_x = round(2 * terminal.x)
        doubled_y = round(2 * terminal.y)
        if abs(2 * terminal.x - doubled_x) > 1e-9 or abs(2 * terminal.y - doubled_y) > 1e-9:
            raise ValueError(f"{terminal.name}: Terminal 坐标必须是 0.5 的整数倍")
        centers[terminal.name] = (doubled_x, doubled_y)
    total = 0
    for net in dataset.nets:
        points = [centers[pin] for pin in net.pins]
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        total += max(xs) - min(xs) + max(ys) - min(ys)
    return total


class _Evaluator:
    def __init__(
        self,
        problem: FloorplanProblem,
        outline_limit: int,
        objective: str,
        dataset: FloorplanDataset | None,
    ) -> None:
        if objective not in {"feasibility", "hpwl"}:
            raise ValueError("objective 必须是 feasibility 或 hpwl")
        if objective == "hpwl" and dataset is None:
            raise ValueError("HPWL 搜索必须提供完整数据集")
        self.problem = problem
        self.outline_limit = outline_limit
        self.objective = objective
        self.dataset = dataset
        self.maximum_extent = sum(max(block.width, block.height) for block in problem.blocks)
        terminal_values = [
            coordinate
            for terminal in (dataset.terminals if dataset else ())
            for coordinate in (2 * terminal.x, 2 * terminal.y)
        ]
        coordinate_low = min([0.0, *terminal_values])
        coordinate_high = max([2.0 * self.maximum_extent, *terminal_values])
        self.hpwl_upper = max(
            1.0,
            2.0 * (coordinate_high - coordinate_low) * len(dataset.nets)
            if dataset
            else 1.0,
        )
        self.violation_upper = max(1, 2 * self.maximum_extent**2)

    def evaluate(self, tree: BStarTree) -> _Evaluation:
        decoded = _decode_bstar_tree(self.problem, tree, validate=False)
        overflow_width = max(0, decoded.width - self.outline_limit)
        overflow_height = max(0, decoded.height - self.outline_limit)
        violation = overflow_width**2 + overflow_height**2
        total_hpwl2 = _hpwl2(self.dataset, decoded.placements) if self.dataset else 0
        if self.objective == "feasibility":
            energy = violation / self.violation_upper
            if violation:
                energy += (decoded.width + decoded.height) / (
                    self.violation_upper * max(1, self.maximum_extent)
                )
        elif violation == 0:
            energy = total_hpwl2 / self.hpwl_upper
        else:
            energy = 1.0 + violation / self.violation_upper
            energy += 0.01 * total_hpwl2 / self.hpwl_upper
        return _Evaluation(decoded, violation, total_hpwl2, energy)


def _parent_array(tree: BStarTree) -> list[int]:
    parents = [-1] * len(tree.block_at)
    for node, (left, right) in enumerate(zip(tree.left, tree.right, strict=True)):
        if left != -1:
            parents[left] = node
        if right != -1:
            parents[right] = node
    return parents


def _perturb(
    tree: BStarTree,
    problem: FloorplanProblem,
    outline_limit: int,
    rng: Random,
) -> tuple[BStarTree, str]:
    count = len(tree.block_at)
    operations = ["rotate", "swap"]
    if count > 1:
        operations.append("move")
    operation = rng.choice(operations)
    block_at = list(tree.block_at)
    left = list(tree.left)
    right = list(tree.right)
    rotated = list(tree.rotated)

    if operation == "rotate":
        candidates = []
        for node, block_index in enumerate(block_at):
            block = problem.blocks[block_index]
            if block.width == block.height:
                continue
            normal_fits = block.width <= outline_limit and block.height <= outline_limit
            rotated_fits = block.height <= outline_limit and block.width <= outline_limit
            if normal_fits and rotated_fits:
                candidates.append(node)
        if not candidates:
            operation = "swap"
        else:
            node = rng.choice(candidates)
            rotated[node] = not rotated[node]

    if operation == "swap":
        if count > 1:
            first, second = rng.sample(range(count), 2)
            block_at[first], block_at[second] = block_at[second], block_at[first]
            rotated[first], rotated[second] = rotated[second], rotated[first]

    if operation == "move":
        # 移动叶节点相当于论文 Op2 的安全子集。它避免一次搬动巨大子树造成
        # 轮廓剧烈跳变，同时仍能通过反复摘叶/插叶改变完整树拓扑。
        leaves = [
            node
            for node in range(1, count)
            if left[node] == -1 and right[node] == -1
        ]
        if not leaves:
            operation = "swap"
            first, second = rng.sample(range(count), 2)
            block_at[first], block_at[second] = block_at[second], block_at[first]
            rotated[first], rotated[second] = rotated[second], rotated[first]
            return BStarTree(tuple(block_at), tuple(left), tuple(right), tuple(rotated)), operation
        source = rng.choice(leaves)
        descendants = {source}
        targets = [
            (node, side)
            for node in range(count)
            if node not in descendants
            for side, child in (("left", left[node]), ("right", right[node]))
            if child == -1
        ]
        if not targets:
            operation = "swap"
            first, second = rng.sample(range(count), 2)
            block_at[first], block_at[second] = block_at[second], block_at[first]
            rotated[first], rotated[second] = rotated[second], rotated[first]
        else:
            parents = _parent_array(tree)
            parent = parents[source]
            if left[parent] == source:
                left[parent] = -1
            else:
                right[parent] = -1
            target, side = rng.choice(targets)
            if side == "left":
                left[target] = source
            else:
                right[target] = source

    return BStarTree(tuple(block_at), tuple(left), tuple(right), tuple(rotated)), operation


def _rank(evaluation: _Evaluation, objective: str) -> tuple[int, int, int]:
    if objective == "hpwl":
        return evaluation.violation, evaluation.total_hpwl2, evaluation.decoded.width + evaluation.decoded.height
    return evaluation.violation, evaluation.decoded.width + evaluation.decoded.height, evaluation.total_hpwl2


def fast_simulated_annealing(
    problem: FloorplanProblem,
    *,
    outline_limit: int,
    objective: str,
    dataset: FloorplanDataset | None = None,
    initial_tree: BStarTree | None = None,
    iterations_per_restart: int = 10_000,
    restarts: int = 4,
    seed: int = 20260810,
    time_limit: float = 60.0,
    initial_acceptance_probability: float = 0.9,
    pseudo_greedy_c: float = 100.0,
    pseudo_greedy_epochs: int = 7,
    stop_on_first_feasible: bool = False,
) -> FastSAResult:
    """运行论文式三阶段 Fast-SA，并以严格可行优先次序保存最佳解。"""

    if outline_limit <= 0:
        raise ValueError("outline_limit 必须为正整数")
    if iterations_per_restart <= 0 or restarts <= 0 or time_limit <= 0:
        raise ValueError("迭代数、重启数和时间限制必须为正")
    if not 0 < initial_acceptance_probability < 1:
        raise ValueError("初始劣解接受概率必须位于 (0, 1)")

    started = perf_counter()
    deadline = started + time_limit
    rng = Random(seed)
    evaluator = _Evaluator(problem, outline_limit, objective, dataset)
    completed_iterations = accepted_moves = uphill_accepted = feasible_evaluations = 0
    rotate_attempts = move_attempts = swap_attempts = 0
    first_temperature = 0.0
    final_temperature = 0.0
    best_tree: BStarTree | None = None
    best_evaluation: _Evaluation | None = None

    found_target = False
    completed_restarts = 0
    for restart in range(restarts):
        if perf_counter() >= deadline:
            break
        if restart == 0 and initial_tree is not None:
            current_tree = initial_tree
            validate_bstar_tree(current_tree, len(problem.blocks))
        else:
            current_tree = complete_bstar_tree(
                problem,
                rng=rng,
                outline_limit=outline_limit,
            )
        current = evaluator.evaluate(current_tree)
        completed_restarts += 1
        feasible_evaluations += int(current.violation == 0)
        if best_evaluation is None or _rank(current, objective) < _rank(best_evaluation, objective):
            best_tree, best_evaluation = current_tree, current

        calibration_deltas: list[float] = []
        probe_tree = current_tree
        probe = current
        for _ in range(min(50, max(10, len(problem.blocks)))):
            proposal_tree, _ = _perturb(probe_tree, problem, outline_limit, rng)
            proposal = evaluator.evaluate(proposal_tree)
            delta = proposal.energy - probe.energy
            if delta > 0:
                calibration_deltas.append(delta)
            probe_tree, probe = proposal_tree, proposal
        average_uphill = (
            sum(calibration_deltas) / len(calibration_deltas)
            if calibration_deltas
            else 1e-3
        )
        initial_temperature = -average_uphill / log(initial_acceptance_probability)
        if first_temperature == 0.0:
            first_temperature = initial_temperature
        recent_change = average_uphill
        moves_per_epoch = max(10, len(problem.blocks))

        for iteration in range(iterations_per_restart):
            if perf_counter() >= deadline:
                break
            epoch = iteration // moves_per_epoch + 1
            if epoch == 1:
                temperature = initial_temperature
            elif epoch <= pseudo_greedy_epochs:
                temperature = (
                    initial_temperature
                    * max(recent_change, 1e-9)
                    / (epoch * pseudo_greedy_c) ** 2
                )
            else:
                temperature = (
                    initial_temperature * max(recent_change, 1e-9) / epoch
                )
            final_temperature = temperature

            proposal_tree, operation = _perturb(current_tree, problem, outline_limit, rng)
            rotate_attempts += int(operation == "rotate")
            move_attempts += int(operation == "move")
            swap_attempts += int(operation == "swap")
            proposal = evaluator.evaluate(proposal_tree)
            feasible_evaluations += int(proposal.violation == 0)
            delta = proposal.energy - current.energy
            recent_change = 0.9 * recent_change + 0.1 * abs(delta)
            accept = delta <= 0 or (
                temperature > 0 and rng.random() < exp(-delta / temperature)
            )
            completed_iterations += 1
            if accept:
                accepted_moves += 1
                uphill_accepted += int(delta > 0)
                current_tree, current = proposal_tree, proposal
            if best_evaluation is None or _rank(proposal, objective) < _rank(
                best_evaluation, objective
            ):
                best_tree, best_evaluation = proposal_tree, proposal
            if stop_on_first_feasible and best_evaluation.violation == 0:
                found_target = True
                break
        if found_target:
            break

    if best_tree is None or best_evaluation is None:
        raise RuntimeError("Fast-SA 未执行任何布局评估")
    stats = FastSAStats(
        objective=objective,
        outline_limit=outline_limit,
        seed=seed,
        restarts=restarts,
        completed_restarts=completed_restarts,
        requested_iterations_per_restart=iterations_per_restart,
        time_limit_seconds=time_limit,
        initial_acceptance_probability=initial_acceptance_probability,
        pseudo_greedy_c=pseudo_greedy_c,
        pseudo_greedy_epochs=pseudo_greedy_epochs,
        completed_iterations=completed_iterations,
        accepted_moves=accepted_moves,
        uphill_accepted_moves=uphill_accepted,
        feasible_evaluations=feasible_evaluations,
        rotate_attempts=rotate_attempts,
        move_attempts=move_attempts,
        swap_attempts=swap_attempts,
        initial_temperature=first_temperature,
        final_temperature=final_temperature,
        best_violation=best_evaluation.violation,
        best_width=best_evaluation.decoded.width,
        best_height=best_evaluation.decoded.height,
        wall_time_seconds=perf_counter() - started,
    )
    return FastSAResult(
        tree=best_tree,
        placements=best_evaluation.decoded.placements,
        width=best_evaluation.decoded.width,
        height=best_evaluation.decoded.height,
        violation=best_evaluation.violation,
        total_hpwl2=(best_evaluation.total_hpwl2 if dataset is not None else None),
        stats=stats,
    )
