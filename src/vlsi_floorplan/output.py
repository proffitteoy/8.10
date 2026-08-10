"""问题 1、问题 2 结果的可复算 JSON 与轻量 SVG 输出。"""

from __future__ import annotations

from dataclasses import asdict
from html import escape
import json
from pathlib import Path

from .data import FloorplanDataset, FloorplanProblem
from .q1 import Q1Solution
from .q2 import Q2Solution
from .q3 import Q3Solution


def write_solution_json(problem: FloorplanProblem, solution: Q1Solution, path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "dataset": problem.source.stem,
        "source": str(problem.source),
        "block_count": len(problem.blocks),
        "terminal_count": len(problem.terminal_names),
        "width": solution.width,
        "height": solution.height,
        "area": solution.area,
        "total_block_area": solution.total_block_area,
        "dead_space_ratio": solution.dead_space_ratio,
        "aspect_ratio": solution.aspect_ratio,
        "area_proven_optimal": solution.area_proven_optimal,
        "lexicographic_proven_optimal": solution.lexicographic_proven_optimal,
        "method": solution.method,
        "seed": solution.seed,
        "workers": solution.workers,
        "construction": asdict(solution.construction),
        "area_phase": asdict(solution.area_phase),
        "shape_phase": asdict(solution.shape_phase) if solution.shape_phase else None,
        "factor_search": asdict(solution.factor_search) if solution.factor_search else None,
        "placements": [asdict(placement) for placement in solution.placements],
    }
    destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return destination


def write_solution_svg(solution: Q1Solution, path: str | Path, canvas_size: int = 1200) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    margin = 50
    scale = min((canvas_size - 2 * margin) / solution.width, (canvas_size - 2 * margin) / solution.height)
    drawing_width = solution.width * scale
    drawing_height = solution.height * scale
    label_enabled = len(solution.placements) <= 120

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{canvas_size}" height="{canvas_size}" viewBox="0 0 {canvas_size} {canvas_size}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<rect x="{margin}" y="{margin}" width="{drawing_width:.3f}" height="{drawing_height:.3f}" fill="none" stroke="#111827" stroke-width="2"/>',
    ]
    for index, placement in enumerate(solution.placements):
        x = margin + placement.x * scale
        y = margin + (solution.height - placement.y - placement.height) * scale
        width = placement.width * scale
        height = placement.height * scale
        hue = (index * 137.508) % 360
        lines.append(
            f'<rect x="{x:.3f}" y="{y:.3f}" width="{width:.3f}" height="{height:.3f}" '
            f'fill="hsl({hue:.1f},65%,78%)" stroke="#374151" stroke-width="0.8"><title>{escape(placement.name)}</title></rect>'
        )
        if label_enabled and width >= 24 and height >= 12:
            lines.append(
                f'<text x="{x + width / 2:.3f}" y="{y + height / 2 + 3:.3f}" text-anchor="middle" '
                f'font-family="sans-serif" font-size="9" fill="#111827">{escape(placement.name)}</text>'
            )
    lines.append(
        f'<text x="{margin}" y="{canvas_size - 18}" font-family="sans-serif" font-size="14" fill="#111827">'
        f'{solution.width} × {solution.height}; area={solution.area}; aspect={solution.aspect_ratio:.4f}; dead-space={solution.dead_space_ratio:.4%}'
        "</text>"
    )
    lines.append("</svg>")
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return destination


def write_q2_solution_json(
    dataset: FloorplanDataset,
    solution: Q2Solution,
    path: str | Path,
) -> Path:
    """写出问题 2 的固定轮廓、逐网 HPWL、求解状态和完整布局。"""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "dataset": dataset.problem.source.stem,
        "sources": {
            "blocks": str(dataset.problem.source),
            "nets": str(dataset.problem.source.with_suffix(".nets")),
            "pl": str(dataset.problem.source.with_suffix(".pl")),
        },
        "block_count": len(dataset.problem.blocks),
        "terminal_count": len(dataset.terminals),
        "net_count": len(dataset.nets),
        "pin_count": dataset.pin_count,
        "dead_space_ratio": solution.dead_space_ratio,
        "chip_side": solution.chip_side,
        "integer_coordinate_limit": solution.coordinate_limit,
        "effective_integer_dead_space_ratio": solution.effective_integer_dead_space_ratio,
        "total_block_area": solution.total_block_area,
        "total_hpwl": solution.total_hpwl,
        "total_hpwl2": solution.total_hpwl2,
        "hpwl_proven_optimal": solution.hpwl_proven_optimal,
        "method": solution.method,
        "seed": solution.seed,
        "construction": asdict(solution.construction),
        "feasibility_annealing": (
            asdict(solution.feasibility_annealing)
            if solution.feasibility_annealing is not None
            else None
        ),
        "annealing": asdict(solution.annealing),
        "net_hpwl2": list(solution.net_hpwl2),
        "placements": [asdict(placement) for placement in solution.placements],
    }
    destination.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return destination


def write_q2_solution_svg(
    solution: Q2Solution,
    path: str | Path,
    canvas_size: int = 1200,
) -> Path:
    """绘制真实公式边长的正方形轮廓和 HardBlock 布局。"""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    margin = 50
    scale = (canvas_size - 2 * margin) / solution.chip_side
    drawing_size = solution.chip_side * scale
    label_enabled = len(solution.placements) <= 120

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{canvas_size}" height="{canvas_size}" viewBox="0 0 {canvas_size} {canvas_size}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<rect x="{margin}" y="{margin}" width="{drawing_size:.3f}" height="{drawing_size:.3f}" fill="none" stroke="#111827" stroke-width="2"/>',
    ]
    for index, placement in enumerate(solution.placements):
        x = margin + placement.x * scale
        y = margin + (solution.chip_side - placement.y - placement.height) * scale
        width = placement.width * scale
        height = placement.height * scale
        hue = (index * 137.508) % 360
        lines.append(
            f'<rect x="{x:.3f}" y="{y:.3f}" width="{width:.3f}" height="{height:.3f}" '
            f'fill="hsl({hue:.1f},65%,78%)" stroke="#374151" stroke-width="0.8"><title>{escape(placement.name)}</title></rect>'
        )
        if label_enabled and width >= 24 and height >= 12:
            lines.append(
                f'<text x="{x + width / 2:.3f}" y="{y + height / 2 + 3:.3f}" text-anchor="middle" '
                f'font-family="sans-serif" font-size="9" fill="#111827">{escape(placement.name)}</text>'
            )
    lines.append(
        f'<text x="{margin}" y="{canvas_size - 18}" font-family="sans-serif" font-size="14" fill="#111827">'
        f'L={solution.chip_side:.6f}; integer-limit={solution.coordinate_limit}; '
        f'HPWL={solution.total_hpwl:g}; method={escape(solution.method)}'
        "</text>"
    )
    lines.append("</svg>")
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return destination


def write_q3_solution_json(
    dataset: FloorplanDataset,
    solution: Q3Solution,
    path: str | Path,
) -> Path:
    """写出第三问的边长上下界证据、两阶段统计和最终布局。"""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "dataset": dataset.problem.source.stem,
        "sources": {
            "blocks": str(dataset.problem.source),
            "nets": str(dataset.problem.source.with_suffix(".nets")),
            "pl": str(dataset.problem.source.with_suffix(".pl")),
        },
        "block_count": len(dataset.problem.blocks),
        "terminal_count": len(dataset.terminals),
        "net_count": len(dataset.nets),
        "pin_count": dataset.pin_count,
        "method": solution.method,
        "chip_side": solution.chip_side,
        "total_block_area": solution.total_block_area,
        "dead_space_ratio": solution.dead_space_ratio,
        "minimum_dead_space_proven": solution.minimum_dead_space_proven,
        "total_hpwl": solution.total_hpwl,
        "total_hpwl2": solution.total_hpwl2,
        "seed": solution.seed,
        "initial_construction": asdict(solution.initial_construction),
        "boundary_search": asdict(solution.boundary_search),
        "hpwl_annealing": asdict(solution.hpwl_annealing),
        "net_hpwl2": list(solution.net_hpwl2),
        "placements": [asdict(placement) for placement in solution.placements],
    }
    destination.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return destination
