# 2026 年华数杯 B 题：VLSI 布图规划设计

本仓库保存四问的模型、实现、测试和可复算结果。赛题定义以 [B题 VLSI布图规划设计.pdf](./B题%20VLSI布图规划设计.pdf) 为准，`附件/`、赛题 PDF 和 `ref/` 均为只读原始材料。

## 当前可直接写入报告的结果

| 问题 | n100 | n200 | n300 | 结论口径 |
|---|---:|---:|---:|---|
| Q1 最好可行面积 | 186934 | 182756 | 285360 | 限时最好可行解，未证明全局最优 |
| Q2 最好已知 HPWL | 276085.5 | 542908.5 | 823577.0 | 历史布局已用当前校验器复验通过 |
| Q3 最好可行边长 | 436 | 431 | 537 | 固定预算最好可行值，未证明严格最小 |
| Q3 对应死区率 | 5.9025% | 5.7286% | 5.5639% | 按对应整数正方形边长复算 |
| Q3 对应布局 HPWL | 298120.0 | 557007.0 | 833931.0 | 只复算现有布局，未在最终边长充分优化 HPWL |

Q4 图 3 的最小轮廓为 `6×4`，最小面积为 **24**，死区为 0。该结论达到模块总面积下界，已严格证明。

详细结果、JSON 和布局图见 [outputs/README.md](./outputs/README.md)。四问建模与实验文档见 [docs/README.md](./docs/README.md)。

## 结果口径

- Q1 的三组面积是当前最好可行上界。相同面积下仍各有一个更接近正方形的因子对未完全判定，因此不写成“全局最优布局”。
- Q2 采用 commit `bba147b` 中的更优布局，并已用当前 validator 与 HPWL 计算器重新验证。n300 的旧求解统计字段相差 2，但布局、逐网 HPWL、记录总值和当前复算值一致，故采用复算总值 823577.0。
- Q3 按已经结束的固定计算预算报告最好可行值，不再继续搜索。`minimum_dead_space_proven=false`，论文中统一写“固定预算下找到的最小死区率”或“best-known feasible”。
- Q3 表中的 HPWL 是最终边长对应合法布局的当前代码复算值，不声称为该边长下的最小 HPWL。

## 目录

| 路径 | 内容 |
|---|---|
| `src/vlsi_floorplan/` | 数据解析、四问模型、搜索、校验与输出 |
| `tests/` | 数据、几何、HPWL 和搜索行为测试 |
| `outputs/` | 当前代表结果、布局图和少量审计记录 |
| `docs/` | 建模与实验说明 |
| `附件/` | n100、n200、n300 原始数据（只读） |
| `ref/` | 参考论文（只读） |

## 环境与验证

- Python 3.12
- uv
- OR-Tools CP-SAT（版本由 `uv.lock` 固定）

安装依赖：

```powershell
uv sync
```

运行完整测试：

```powershell
uv run python -m unittest discover -s tests -v
```

主要命令：

```powershell
# Q1
uv run python -m vlsi_floorplan.cli 附件\n100.blocks --output-dir outputs\q1\n100\seed_20260810

# Q2
uv run python -m vlsi_floorplan.q2_cli 附件\n100.blocks 附件\n100.nets 附件\n100.pl --output-dir outputs\q2_bstar\n100\seed_20260810

# Q3
uv run python -m vlsi_floorplan.q3_cli 附件\n100.blocks 附件\n100.nets 附件\n100.pl --output-dir outputs\q3\n100\seed_20260810

# Q4
uv run python -m vlsi_floorplan.q4_cli --output-dir outputs\q4\figure3 --workers 1 --seed 20260810
```

原始输入不得覆盖、重命名或写入运行结果。新的实验结果统一写入 `outputs/`，并保留数据集、参数、随机种子、终止条件、可行性和目标值。
