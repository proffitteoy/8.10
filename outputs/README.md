# 结果清单

本目录只区分两类内容：

1. **当前代表结果**：报告和论文应引用；
2. **历史/对照记录**：仅用于复核算法过程，不再作为当前结论。

## 当前代表结果

| 问题 | n100 | n200 | n300 | 代表文件 |
|---|---:|---:|---:|---|
| Q1 面积 | 186934 | 182756 | 285360 | `q1_hybrid/summary.csv` |
| Q2 HPWL | 276085.5 | 542908.5 | 823577.0 | `q2/<dataset>/seed_20260810/solution.json` |
| Q3 边长 | 436 | 431 | 537 | `q3/<dataset>/best_known/solution.json` |
| Q3 死区率 | 5.9025% | 5.7286% | 5.5639% | `q3/best_known_summary.csv` |
| Q3 对应布局 HPWL | 298120.0 | 557007.0 | 833931.0 | `q3/<dataset>/best_known/solution.json` |

Q4 当前代表结果位于 `q4/figure3/`：轮廓 `6×4`，面积 24，死区为 0，并已严格证明最优。

## 结论边界

- Q1：限时最好可行面积，不宣称全局最优；同面积长宽比也未完全证明最优。
- Q2：三份历史更优布局已通过当前几何 validator 与逐网 HPWL 复算。审计记录为 `q2/historical_validation.json`。
- Q3：固定计算预算内的最好可行边长，`minimum_dead_space_proven=false`。对应 HPWL 只是合法布局的复算值，`hpwl_optimized=false`。
- Q4：面积 24 等于模块总面积下界，属于严格最优结论。

## 当前目录索引

| 路径 | 状态 | 用途 |
|---|---|---|
| `q1_hybrid/` | 当前 | Q1 代表布局与汇总 |
| `q1_space/` | 当前辅助 | Q1 搜索空间与因子对分析 |
| `q2/` | 当前 | Q2 最好已知 CP-SAT 布局 |
| `q2/historical_validation.json` | 当前审计 | Q2 历史布局复验记录 |
| `q2_bstar/` | 对照 | B\*-Tree + Fast-SA 多种子实验 |
| `q3/<dataset>/best_known/` | 当前 | Q3 最好可行布局及布局图 |
| `q3/best_known_summary.csv` | 当前 | Q3 报告汇总 |
| `q3/historical_boundary_runs.csv` | 历史 | Q3 初始多种子边界实验，不用于当前结论 |
| `q4/figure3/` | 当前 | Q4 严格最优布局 |

## 引用规则

- 报告中的数值统一从本页“当前代表结果”或对应 JSON/CSV 读取。
- JSON 与 SVG 成对保留；截图不能替代可复算 JSON。
- 不再从 Git 历史或旧汇总直接抄数。若历史布局更优，必须先通过当前校验器，再恢复为当前代表结果。
- 赛题 PDF、`附件/` 和 `ref/` 不属于结果清理范围。
