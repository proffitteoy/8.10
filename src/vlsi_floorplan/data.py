"""赛题附件的严格解析。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


_HEADER_RE = re.compile(r"^(NumHardBlocks|NumTerminals)\s*:\s*(\d+)\s*$")
_NET_HEADER_RE = re.compile(r"^(NumNets|NumPins)\s*:\s*(\d+)\s*$")
_NET_DEGREE_RE = re.compile(r"^NetDegree\s*:\s*(\d+)\s*$")
_BLOCK_RE = re.compile(r"^(\S+)\s+block\s+(\d+)\s+(.+?)\s*$")
_TERMINAL_RE = re.compile(r"^(\S+)\s+terminal\s*$")
_POINT_RE = re.compile(r"\((-?\d+)\s*,\s*(-?\d+)\)")
_PLACEMENT_RE = re.compile(
    r"^(\S+)\s+([-+]?\d+(?:\.\d+)?)\s+([-+]?\d+(?:\.\d+)?)\s*$"
)


@dataclass(frozen=True, slots=True)
class Block:
    """一个允许旋转 90° 的矩形 HardBlock。"""

    name: str
    width: int
    height: int

    @property
    def area(self) -> int:
        return self.width * self.height


@dataclass(frozen=True, slots=True)
class FloorplanProblem:
    """问题 1 所需的模块集合及附件元数据。"""

    source: Path
    blocks: tuple[Block, ...]
    terminal_names: tuple[str, ...]

    @property
    def total_block_area(self) -> int:
        return sum(block.area for block in self.blocks)


@dataclass(frozen=True, slots=True)
class Net:
    """一个由若干模块或 Terminal 引脚组成的线网。"""

    pins: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Terminal:
    """`.pl` 中给出的固定引脚坐标。"""

    name: str
    x: float
    y: float


@dataclass(frozen=True, slots=True)
class FloorplanDataset:
    """通过三种附件格式交叉校验后的完整数据集。"""

    problem: FloorplanProblem
    nets: tuple[Net, ...]
    terminals: tuple[Terminal, ...]

    @property
    def pin_count(self) -> int:
        return sum(len(net.pins) for net in self.nets)


def _rectangle_dimensions(name: str, declared_vertices: int, text: str) -> tuple[int, int]:
    points = [(int(x), int(y)) for x, y in _POINT_RE.findall(text)]
    if declared_vertices != 4 or len(points) != 4:
        raise ValueError(f"{name}: 问题 1 只支持由 4 个顶点描述的矩形")

    xs = sorted({point[0] for point in points})
    ys = sorted({point[1] for point in points})
    if len(xs) != 2 or len(ys) != 2:
        raise ValueError(f"{name}: 顶点不能构成轴对齐矩形")

    expected = {(x, y) for x in xs for y in ys}
    if set(points) != expected:
        raise ValueError(f"{name}: 缺少矩形角点或存在重复角点")

    width = xs[1] - xs[0]
    height = ys[1] - ys[0]
    if width <= 0 or height <= 0:
        raise ValueError(f"{name}: 宽高必须为正数")
    return width, height


def parse_blocks(path: str | Path) -> FloorplanProblem:
    """读取 `.blocks`，并验证声明数量、名称唯一性和矩形几何。"""

    source = Path(path)
    headers: dict[str, int] = {}
    blocks: list[Block] = []
    terminals: list[str] = []
    names: set[str] = set()

    for line_number, raw_line in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line:
            continue

        if match := _HEADER_RE.fullmatch(line):
            key, value = match.groups()
            if key in headers:
                raise ValueError(f"{source}:{line_number}: 重复的 {key} 声明")
            headers[key] = int(value)
            continue

        if match := _BLOCK_RE.fullmatch(line):
            name, vertex_count, vertices = match.groups()
            if name in names:
                raise ValueError(f"{source}:{line_number}: 重复名称 {name}")
            width, height = _rectangle_dimensions(name, int(vertex_count), vertices)
            blocks.append(Block(name=name, width=width, height=height))
            names.add(name)
            continue

        if match := _TERMINAL_RE.fullmatch(line):
            name = match.group(1)
            if name in names:
                raise ValueError(f"{source}:{line_number}: 重复名称 {name}")
            terminals.append(name)
            names.add(name)
            continue

        raise ValueError(f"{source}:{line_number}: 无法识别的记录：{line}")

    required_headers = {"NumHardBlocks", "NumTerminals"}
    missing_headers = required_headers - headers.keys()
    if missing_headers:
        raise ValueError(f"{source}: 缺少声明 {sorted(missing_headers)}")
    if len(blocks) != headers["NumHardBlocks"]:
        raise ValueError(
            f"{source}: HardBlock 声明 {headers['NumHardBlocks']} 个，实际 {len(blocks)} 个"
        )
    if len(terminals) != headers["NumTerminals"]:
        raise ValueError(
            f"{source}: Terminal 声明 {headers['NumTerminals']} 个，实际 {len(terminals)} 个"
        )
    if not blocks:
        raise ValueError(f"{source}: 至少需要一个 HardBlock")

    return FloorplanProblem(
        source=source.resolve(),
        blocks=tuple(blocks),
        terminal_names=tuple(terminals),
    )


def parse_nets(path: str | Path) -> tuple[Net, ...]:
    """读取 `.nets`，严格验证每个 `NetDegree` 分组及总引脚数。"""

    source = Path(path)
    headers: dict[str, int] = {}
    records: list[tuple[int, str]] = []
    for line_number, raw_line in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line:
            continue
        if match := _NET_HEADER_RE.fullmatch(line):
            key, value = match.groups()
            if key in headers:
                raise ValueError(f"{source}:{line_number}: 重复的 {key} 声明")
            headers[key] = int(value)
        else:
            records.append((line_number, line))

    required_headers = {"NumNets", "NumPins"}
    missing_headers = required_headers - headers.keys()
    if missing_headers:
        raise ValueError(f"{source}: 缺少声明 {sorted(missing_headers)}")

    nets: list[Net] = []
    cursor = 0
    while cursor < len(records):
        line_number, line = records[cursor]
        match = _NET_DEGREE_RE.fullmatch(line)
        if not match:
            raise ValueError(f"{source}:{line_number}: 期望 NetDegree，实际为 {line}")
        degree = int(match.group(1))
        if degree <= 0:
            raise ValueError(f"{source}:{line_number}: NetDegree 必须为正")
        cursor += 1
        if cursor + degree > len(records):
            raise ValueError(f"{source}:{line_number}: 线网声明 {degree} 个引脚，但文件已截断")

        pins: list[str] = []
        for pin_line_number, pin in records[cursor : cursor + degree]:
            if _NET_DEGREE_RE.fullmatch(pin):
                raise ValueError(
                    f"{source}:{pin_line_number}: 上一线网尚缺引脚就遇到新的 NetDegree"
                )
            if len(pin.split()) != 1:
                raise ValueError(f"{source}:{pin_line_number}: 非法引脚名称 {pin}")
            pins.append(pin)
        nets.append(Net(pins=tuple(pins)))
        cursor += degree

    if len(nets) != headers["NumNets"]:
        raise ValueError(f"{source}: 线网声明 {headers['NumNets']} 个，实际 {len(nets)} 个")
    pin_count = sum(len(net.pins) for net in nets)
    if pin_count != headers["NumPins"]:
        raise ValueError(f"{source}: 引脚声明 {headers['NumPins']} 个，实际 {pin_count} 个")
    return tuple(nets)


def parse_pl(path: str | Path) -> tuple[Terminal, ...]:
    """读取 `.pl`，拒绝重复名称和非数值坐标。"""

    source = Path(path)
    terminals: list[Terminal] = []
    names: set[str] = set()
    for line_number, raw_line in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line:
            continue
        match = _PLACEMENT_RE.fullmatch(line)
        if not match:
            raise ValueError(f"{source}:{line_number}: 非法 Terminal 坐标记录 {line}")
        name, x, y = match.groups()
        if name in names:
            raise ValueError(f"{source}:{line_number}: 重复 Terminal {name}")
        names.add(name)
        terminals.append(Terminal(name=name, x=float(x), y=float(y)))
    return tuple(terminals)


def parse_dataset(
    blocks_path: str | Path,
    nets_path: str | Path,
    pl_path: str | Path,
) -> FloorplanDataset:
    """读取并交叉验证 `.blocks`、`.nets`、`.pl` 三个文件。"""

    problem = parse_blocks(blocks_path)
    nets = parse_nets(nets_path)
    terminals = parse_pl(pl_path)
    terminal_names = set(problem.terminal_names)
    coordinate_names = {terminal.name for terminal in terminals}
    if coordinate_names != terminal_names:
        missing = sorted(terminal_names - coordinate_names)
        unexpected = sorted(coordinate_names - terminal_names)
        raise ValueError(f"Terminal 坐标集合不一致：缺少 {missing}，多出 {unexpected}")

    known_nodes = {block.name for block in problem.blocks} | terminal_names
    unknown_pins = sorted({pin for net in nets for pin in net.pins if pin not in known_nodes})
    if unknown_pins:
        raise ValueError(f"线网引用未知节点：{unknown_pins}")
    return FloorplanDataset(problem=problem, nets=nets, terminals=terminals)
