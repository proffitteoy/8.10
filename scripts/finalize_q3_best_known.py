"""把固定预算内找到的 Q3 最好可行布局固化为统一结果。"""

from __future__ import annotations

import csv
from dataclasses import asdict
import json
from pathlib import Path
from types import SimpleNamespace

from vlsi_floorplan.data import parse_dataset
from vlsi_floorplan.output import write_q2_solution_svg
from vlsi_floorplan.q1 import Placement
from vlsi_floorplan.q2 import compute_net_hpwl2, validate_fixed_outline_placements


CASES = {
    "n100": {
        "side": 436,
        "lower_bound": 424,
        "source": Path("outputs/q3/n100/candidate_436_ten_minute.json"),
        "method": "fixed-width-local-search-10-minute",
    },
    "n200": {
        "side": 431,
        "lower_bound": 420,
        "source": Path("outputs/q3/n200/seed_20260810/solution.json"),
        "method": "maxrects-boundary-search",
    },
    "n300": {
        "side": 537,
        "lower_bound": 523,
        "source": Path("outputs/q3/n300/seed_20260810/solution.json"),
        "method": "maxrects-boundary-search",
    },
}


def main() -> int:
    summary_rows: list[dict[str, object]] = []
    for dataset_name, config in CASES.items():
        dataset = parse_dataset(
            Path("附件") / f"{dataset_name}.blocks",
            Path("附件") / f"{dataset_name}.nets",
            Path("附件") / f"{dataset_name}.pl",
        )
        source_payload = json.loads(config["source"].read_text(encoding="utf-8"))
        placements = tuple(Placement(**record) for record in source_payload["placements"])
        side = int(config["side"])
        validate_fixed_outline_placements(dataset, placements, side)
        net_hpwl2 = compute_net_hpwl2(dataset, placements)
        total_hpwl2 = sum(net_hpwl2)
        dead_space_ratio = side**2 / dataset.problem.total_block_area - 1.0
        destination = Path("outputs/q3") / dataset_name / "best_known"
        destination.mkdir(parents=True, exist_ok=True)
        payload = {
            "dataset": dataset_name,
            "result_status": "BEST_KNOWN_FEASIBLE_NOT_PROVEN_MINIMUM",
            "method": config["method"],
            "source_artifact": str(config["source"]),
            "search_budget": "final fixed 10-minute fixed-width search; no further search",
            "chip_side": side,
            "side_lower_bound": int(config["lower_bound"]),
            "side_feasible_upper_bound": side,
            "total_block_area": dataset.problem.total_block_area,
            "dead_space_ratio": dead_space_ratio,
            "minimum_dead_space_proven": False,
            "hpwl_optimized_at_final_side": False,
            "total_hpwl": total_hpwl2 / 2,
            "total_hpwl2": total_hpwl2,
            "net_hpwl2": list(net_hpwl2),
            "placements": [asdict(placement) for placement in placements],
            "validation": {
                "module_set_rotation_boundary_overlap": "PASS",
                "hpwl_recomputed_with_current_code": "PASS",
            },
        }
        (destination / "solution.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        svg_solution = SimpleNamespace(
            chip_side=float(side),
            coordinate_limit=side,
            placements=placements,
            total_hpwl=total_hpwl2 / 2,
            method=config["method"],
        )
        write_q2_solution_svg(svg_solution, destination / "layout.svg")
        summary_rows.append(
            {
                "dataset": dataset_name,
                "side_lower_bound": int(config["lower_bound"]),
                "best_known_feasible_side": side,
                "dead_space_ratio": dead_space_ratio,
                "total_hpwl": total_hpwl2 / 2,
                "minimum_proven": False,
                "hpwl_optimized": False,
                "source": str(config["source"]),
            }
        )

    with Path("outputs/q3/best_known_summary.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary_rows[0]))
        writer.writeheader()
        writer.writerows(summary_rows)
    print(json.dumps(summary_rows, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
