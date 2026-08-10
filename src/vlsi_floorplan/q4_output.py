"""问题 4 的可复算 JSON 与真实异形几何 SVG 输出。"""

from __future__ import annotations

from dataclasses import asdict
from html import escape
import json
from pathlib import Path

from .q4 import OrthogonalModule, Q4Placement, Q4Solution


def write_q4_solution_json(
    modules: tuple[OrthogonalModule, ...],
    solution: Q4Solution,
    path: str | Path,
) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "case": "figure3",
        "module_count": len(modules),
        "width": solution.width,
        "height": solution.height,
        "area": solution.area,
        "total_module_area": solution.total_module_area,
        "dead_space_ratio": solution.dead_space_ratio,
        "aspect_ratio": solution.aspect_ratio,
        "area_proven_optimal": solution.area_proven_optimal,
        "lexicographic_proven_optimal": solution.lexicographic_proven_optimal,
        "proof": {
            "area_lower_bound": solution.total_module_area,
            "feasible_area": solution.area,
            "reason": "模块总面积下界与可行轮廓面积相等",
        },
        "method": solution.method,
        "seed": solution.seed,
        "workers": solution.workers,
        "modules": [asdict(module) for module in modules],
        "search": asdict(solution.search),
        "placements": [asdict(placement) for placement in solution.placements],
    }
    destination.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return destination


def _boundary_edges(placement: Q4Placement) -> set[tuple[int, int, int, int]]:
    edges: set[tuple[int, int, int, int]] = set()
    for rect in placement.components:
        for x in range(placement.x + rect.x, placement.x + rect.right):
            for y in range(placement.y + rect.y, placement.y + rect.top):
                cell_edges = (
                    (x, y, x + 1, y),
                    (x + 1, y, x + 1, y + 1),
                    (x, y + 1, x + 1, y + 1),
                    (x, y, x, y + 1),
                )
                for edge in cell_edges:
                    if edge in edges:
                        edges.remove(edge)
                    else:
                        reverse = (edge[2], edge[3], edge[0], edge[1])
                        if reverse in edges:
                            edges.remove(reverse)
                        else:
                            edges.add(edge)
    return edges


def write_q4_solution_svg(
    solution: Q4Solution,
    path: str | Path,
    canvas_size: int = 900,
) -> Path:
    """绘制各模块的真实 T/L/矩形轮廓，而不是模块包围盒。"""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    margin = 70
    footer = 55
    available_width = canvas_size - 2 * margin
    available_height = canvas_size - 2 * margin - footer
    scale = min(available_width / solution.width, available_height / solution.height)
    drawing_width = solution.width * scale
    drawing_height = solution.height * scale
    origin_x = (canvas_size - drawing_width) / 2
    origin_y = margin

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{canvas_size}" height="{canvas_size}" viewBox="0 0 {canvas_size} {canvas_size}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<rect x="{origin_x:.3f}" y="{origin_y:.3f}" width="{drawing_width:.3f}" height="{drawing_height:.3f}" fill="#f8fafc" stroke="#111827" stroke-width="3"/>',
    ]

    for index, placement in enumerate(solution.placements):
        hue = (index * 137.508) % 360
        fill = f"hsl({hue:.1f},65%,76%)"
        for rect in placement.components:
            x = origin_x + (placement.x + rect.x) * scale
            y = origin_y + (
                solution.height - placement.y - rect.y - rect.height
            ) * scale
            lines.append(
                f'<rect x="{x:.3f}" y="{y:.3f}" width="{rect.width * scale:.3f}" '
                f'height="{rect.height * scale:.3f}" fill="{fill}" stroke="none"/>'
            )
        for x1, y1, x2, y2 in sorted(_boundary_edges(placement)):
            svg_x1 = origin_x + x1 * scale
            svg_y1 = origin_y + (solution.height - y1) * scale
            svg_x2 = origin_x + x2 * scale
            svg_y2 = origin_y + (solution.height - y2) * scale
            lines.append(
                f'<line x1="{svg_x1:.3f}" y1="{svg_y1:.3f}" x2="{svg_x2:.3f}" '
                f'y2="{svg_y2:.3f}" stroke="#1f2937" stroke-width="2"/>'
            )
        label_x = origin_x + (placement.x + placement.width / 2) * scale
        label_y = origin_y + (
            solution.height - placement.y - placement.height / 2
        ) * scale
        lines.append(
            f'<text x="{label_x:.3f}" y="{label_y + 5:.3f}" text-anchor="middle" '
            f'font-family="sans-serif" font-size="18" font-weight="600" fill="#111827">'
            f'{escape(placement.name)}</text>'
        )

    lines.append(
        f'<text x="{canvas_size / 2:.3f}" y="{canvas_size - 28}" text-anchor="middle" '
        f'font-family="sans-serif" font-size="17" fill="#111827">'
        f'{solution.width} × {solution.height}; area={solution.area}; '
        f'dead-space={solution.dead_space_ratio:.0%}; optimal={str(solution.area_proven_optimal).lower()}'
        "</text>"
    )
    lines.append("</svg>")
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return destination
