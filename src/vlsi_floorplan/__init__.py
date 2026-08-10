"""华数杯 VLSI 布图规划模型与实验工具。"""

from .data import (
    Block,
    FloorplanDataset,
    FloorplanProblem,
    Net,
    Terminal,
    parse_blocks,
    parse_dataset,
    parse_nets,
    parse_pl,
)
from .q1 import Placement, Q1Solution, solve_q1, validate_solution
from .q2 import (
    Q2ConstructionStats,
    Q2Solution,
    compute_net_hpwl2,
    solve_q2,
    validate_q2_solution,
)
from .q3 import Q3Solution, check_exact_feasibility, solve_q3, validate_q3_solution
from .q4 import (
    ComponentRect,
    OrthogonalModule,
    Q4Placement,
    Q4Solution,
    figure3_modules,
    generate_orientations,
    solve_q4,
    validate_q4_solution,
)

__all__ = [
    "Block",
    "FloorplanDataset",
    "FloorplanProblem",
    "Net",
    "Placement",
    "Q1Solution",
    "Q2Solution",
    "Q2ConstructionStats",
    "Q3Solution",
    "Q4Placement",
    "Q4Solution",
    "ComponentRect",
    "OrthogonalModule",
    "Terminal",
    "parse_blocks",
    "parse_dataset",
    "parse_nets",
    "parse_pl",
    "compute_net_hpwl2",
    "check_exact_feasibility",
    "solve_q1",
    "solve_q2",
    "solve_q3",
    "solve_q4",
    "figure3_modules",
    "generate_orientations",
    "validate_solution",
    "validate_q2_solution",
    "validate_q3_solution",
    "validate_q4_solution",
]
