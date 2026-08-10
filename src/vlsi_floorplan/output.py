"""问题 1 结果的可复算 JSON 与轻量 SVG 输出。"""

from __future__ import annotations

from dataclasses import asdict
from html import escape
import json
from pathlib import Path

from .data import FloorplanProblem
from .q1 import Q1Solution


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
        "area_phase": asdict(solution.area_phase),
        "shape_phase": asdict(solution.shape_phase) if solution.shape_phase else None,
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

