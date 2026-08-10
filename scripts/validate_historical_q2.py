"""用当前 Q2 几何与 HPWL 口径审计 Git 历史中的布局结果。"""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import subprocess

from vlsi_floorplan.bstar import FastSAStats
from vlsi_floorplan.data import parse_dataset
from vlsi_floorplan.q1 import Placement
from vlsi_floorplan.q2 import (
    Q2ConstructionStats,
    Q2Solution,
    compute_net_hpwl2,
    validate_q2_solution,
)


def _empty_annealing_stats(side: int, seed: int) -> FastSAStats:
    return FastSAStats(
        objective="historical-validation-only",
        outline_limit=side,
        seed=seed,
        restarts=0,
        completed_restarts=0,
        requested_iterations_per_restart=0,
        time_limit_seconds=0.0,
        initial_acceptance_probability=0.0,
        pseudo_greedy_c=0.0,
        pseudo_greedy_epochs=0,
        completed_iterations=0,
        accepted_moves=0,
        uphill_accepted_moves=0,
        feasible_evaluations=0,
        rotate_attempts=0,
        move_attempts=0,
        swap_attempts=0,
        initial_temperature=0.0,
        final_temperature=0.0,
        best_violation=0,
        best_width=side,
        best_height=side,
        wall_time_seconds=0.0,
    )


def _read_git_json(commit: str, path: str) -> dict[str, object]:
    completed = subprocess.run(
        ["git", "show", f"{commit}:{path}"],
        check=True,
        capture_output=True,
    )
    return json.loads(completed.stdout.decode("utf-8"))


def validate_historical_result(commit: str, dataset_name: str) -> dict[str, object]:
    path = f"outputs/q2/{dataset_name}/seed_20260810/solution.json"
    payload = _read_git_json(commit, path)
    dataset = parse_dataset(
        Path("附件") / f"{dataset_name}.blocks",
        Path("附件") / f"{dataset_name}.nets",
        Path("附件") / f"{dataset_name}.pl",
    )
    placements = tuple(Placement(**record) for record in payload["placements"])
    recorded_net_hpwl2 = tuple(int(value) for value in payload["net_hpwl2"])
    recomputed_net_hpwl2 = compute_net_hpwl2(dataset, placements)
    total_hpwl2 = int(payload["total_hpwl2"])
    construction_payload = payload["construction"]
    construction = Q2ConstructionStats(
        attempts=int(construction_payload["attempts"]),
        feasible_attempts=int(construction_payload["feasible_attempts"]),
        initial_hpwl2=int(construction_payload["initial_hpwl2"]),
        bstar_seed_available=False,
        bstar_seed_feasible=False,
        wall_time_seconds=float(construction_payload["wall_time_seconds"]),
    )
    solution = Q2Solution(
        method=f"historical-cp-sat-validated-from-{commit}",
        dead_space_ratio=float(payload["dead_space_ratio"]),
        chip_side=float(payload["chip_side"]),
        coordinate_limit=int(payload["integer_coordinate_limit"]),
        total_block_area=int(payload["total_block_area"]),
        placements=placements,
        net_hpwl2=recorded_net_hpwl2,
        total_hpwl2=total_hpwl2,
        construction=construction,
        feasibility_annealing=None,
        annealing=_empty_annealing_stats(int(payload["integer_coordinate_limit"]), int(payload["seed"])),
        seed=int(payload["seed"]),
    )
    validate_q2_solution(dataset, solution)
    optimization_objective = int(payload["optimization_phase"]["objective_hpwl2"])
    return {
        "dataset": dataset_name,
        "source_commit": commit,
        "source_path": path,
        "geometry_and_current_validator": "PASS",
        "recorded_net_hpwl_matches_current": recorded_net_hpwl2 == recomputed_net_hpwl2,
        "recorded_total_hpwl2": total_hpwl2,
        "recomputed_total_hpwl2": sum(recomputed_net_hpwl2),
        "recomputed_total_hpwl": sum(recomputed_net_hpwl2) / 2,
        "historical_optimization_objective_hpwl2": optimization_objective,
        "optimization_objective_matches_current": optimization_objective
        == sum(recomputed_net_hpwl2),
        "placement_count": len(placements),
        "coordinate_limit": solution.coordinate_limit,
        "construction": asdict(construction),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", default="bba147b")
    args = parser.parse_args()
    results = [
        validate_historical_result(args.commit, dataset_name)
        for dataset_name in ("n100", "n200", "n300")
    ]
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
