# 2026 年华数杯 B 题：VLSI 布图规划设计

本仓库用于完成 VLSI 布图规划设计的数学建模、算法实验、结果可视化和论文撰写。当前已完成原始数据校验、问题 1 混合优化、问题 2 的 CP-SAT 与 B\*-Tree + Fast-SA 对照、问题 3 的三数据集多种子边界实验，以及问题 4 图 3 的正交异形模块精确求解。

快速入口：[文档导航](./docs/README.md) · [结果清单与保留规则](./outputs/README.md)

## 赛题目标

赛题包含四个相互递进的问题：

1. 在无固定芯片轮廓、无模块连线时，最小化包围全部矩形模块的轮廓面积；同面积下优先选择长宽比更接近 1 的布局。
2. 在死区比例为 0.15 的固定正方形轮廓内，满足模块不重叠、不越界，并最小化所有线网的总半周长线长（HPWL）。
3. 对三组数据分别搜索仍存在可行布局的最小死区比例，并在该比例下重新优化总 HPWL。
4. 将问题 1 扩展到包含 L 型、T 型和矩形模块且允许四向旋转的情形。

问题定义以 [B题 VLSI布图规划设计.pdf](./B题%20VLSI布图规划设计.pdf) 为准。

## 仓库内容

| 路径 | 作用 |
|---|---|
| `B题 VLSI布图规划设计.pdf` | 赛题原文与附件格式说明 |
| `ref/` | B\*-Tree、Fast-SA 等参考论文与参考文献 |
| `附件/` | `n100`、`n200`、`n300` 三组只读基准数据 |
| `src/vlsi_floorplan/` | 附件解析、问题 1—4 的模型、搜索、认证、结果校验与输出 |
| `tests/` | 数据完整性、异常输入和手算小例测试 |
| `outputs/q1_hybrid/`、`outputs/q2/`、`outputs/q2_bstar/`、`outputs/q3/`、`outputs/q4/` | 各问题的代表结果、算法对照、多种子统计与布局图 |
| `AGENTS.md` | 本项目的协作、建模和验证契约 |
| `docs/` | 冷启动及专项参考说明 |

## 环境与命令

- Python：3.12（本次验证为 3.12.13）
- 依赖管理：uv
- 直接求解器：OR-Tools CP-SAT 9.15.6755（由 `uv.lock` 固定）

安装依赖：

```powershell
uv sync
```

若受限 Windows 环境的用户级 uv 缓存不可写，可先设置仓库内缓存：

```powershell
$env:UV_CACHE_DIR = "$PWD\.uv-cache"
uv sync
```

运行测试：

```powershell
uv run python -m unittest discover -s tests -v
```

求解单组问题 1 数据：

```powershell
uv run python -m vlsi_floorplan.cli 附件\n100.blocks `
  --output-dir outputs\q1\n100\seed_20260810 `
  --area-time-limit 20 --shape-time-limit 5 `
  --workers 8 --seed 20260810
```

命令输出 `solution.json` 和 `layout.svg`。JSON 保存完整模块坐标、旋转状态、目标值、求解状态、下界、时间、随机种子和 worker 数。

尝试求解单组问题 2 数据：

```powershell
uv run python -m vlsi_floorplan.q2_cli 附件\n100.blocks 附件\n100.nets 附件\n100.pl `
  --output-dir outputs\q2_bstar\n100\seed_20260810 `
  --optimization-time-limit 60 `
  --iterations-per-restart 30000 --restarts 2 `
  --seed 20260810
```

问题 2 使用 B\*-Tree 隐式编码相对位置，轮廓压紧解码自动产生无重叠布局，并以 Rotate、Move、Swap 和三阶段 Fast-SA 搜索固定轮廓内的低 HPWL 解。MaxRects 只提供初始可行上界；若 B\*-Tree 搜索未改进该上界，输出会明确保留 incumbent。Fast-SA 结果是限时可行上界，不提供 HPWL 全局最优证明。

启动单组问题 3 边界搜索：

```powershell
uv run python -m vlsi_floorplan.q3_cli 附件\n100.blocks 附件\n100.nets 附件\n100.pl `
  --output-dir outputs\q3\n100\seed_20260810 `
  --exact-time-limit 30 --exact-workers 8 `
  --seed 20260810
```

问题 3 在整数边长上二分搜索：B\*-Tree + Fast-SA 找到布局即可严格收紧可行上界；启发式未找到时，只有 CP-SAT 返回 `INFEASIBLE` 才能提高下界。CP-SAT 超时返回 `UNKNOWN` 时保留未决区间，随后仍在当前最小已知可行边长下执行第二阶段 HPWL 优化。

求解问题 4 的图 3 实例：

```powershell
uv run python -m vlsi_floorplan.q4_cli `
  --output-dir outputs\q4\figure3 `
  --workers 1 --seed 20260810
```

问题 4 将 L/T 型模块分解为互不重叠的组成矩形，预生成四向旋转，并对全部组成矩形施加二维非重叠约束。图 3 得到 `6×4`（等价于整体旋转后的 `4×6`）零死区布局；可行面积 24 等于模块总面积下界 24，因此最小面积得到严格证明。

## 数据格式

每组数据由同名的三个文件组成：

- `.blocks`：声明 HardBlock 和 Terminal。当前 HardBlock 均为矩形，顶点坐标给出其尺寸；Terminal 位置固定且不参与面积、重叠和越界约束。
- `.nets`：声明线网数量、引脚总数及各线网包含的节点。
- `.pl`：给出所有 Terminal 的固定二维坐标。

冷启动阶段的完整性核对结果如下：

| 数据集 | HardBlock | Terminal | 线网 | 引脚 | 模块总面积 |
|---|---:|---:|---:|---:|---:|
| `n100` | 100 | 334 | 885 | 1873 | 179501 |
| `n200` | 200 | 564 | 1585 | 3599 | 175696 |
| `n300` | 300 | 569 | 1893 | 4358 | 273170 |

三组数据的文件头声明均与实际记录数一致，所有线网节点均能在 `.blocks` 中找到，`.pl` 与 Terminal 集合一致。

## 统一计算口径

- 矩形模块可旋转 90°，旋转会交换宽高；问题 4 的模块可旋转 0°、90°、180°、270°。
- 模块不能重叠。固定轮廓问题中，模块还必须完全位于轮廓内。
- 问题 2 的正方形边长为：

  `sqrt(total_block_area * (1 + dead_space_ratio))`

- 每个 HardBlock 的引脚取模块几何中心，Terminal 引脚取 `.pl` 中的固定坐标。
- 单条线网的 HPWL 为其所有引脚最小外接矩形的宽与高之和；总 HPWL 为所有线网 HPWL 之和。

## 推荐工作流

1. 建立严格的数据解析和完整性校验，并用小型手算样例固定几何与 HPWL 口径。
2. 实现矩形布局表示、旋转、无重叠检测、轮廓计算和可视化。
3. 先完成问题 1，再加入 Terminal、线网与固定轮廓完成问题 2。
4. 用明确的精度、上下界和多随机种子实验处理问题 3。
5. 在复用问题 1 搜索框架的前提下，引入真实多边形几何处理问题 4。
6. 所有实验记录数据集、随机种子、参数、终止条件、运行时间、约束可行性和目标值。

问题 1 的直接求解模型、首轮结果和适用边界见 [docs/Q1直接求解实验.md](./docs/Q1直接求解实验.md)。该基线不使用 B\*-Tree 或模拟退火，也不把限时可行解表述为已证明的全局最优解。

问题 2 的现行 B\*-Tree + Fast-SA 实现及三数据集、三种子对照见 [docs/Q2-BStar-FastSA.md](./docs/Q2-BStar-FastSA.md)；旧直接模型实验保留在 [docs/Q2直接求解实验.md](./docs/Q2直接求解实验.md)。统一预算下 Fast-SA 未超过旧 CP-SAT，因此问题 2 当前最好 HPWL 仍取旧基线结果。

问题 3 的设计主线见 [docs/Q3设计.md](./docs/Q3设计.md)，三数据集多种子实验、认证区间和 `UNKNOWN` 语义见 [docs/Q3实现说明.md](./docs/Q3实现说明.md)。

问题 4 的模型修正、图 3 精确布局、面积最优性证明与产物说明见 [docs/Q4求解实验.md](./docs/Q4求解实验.md)。

## 原始材料保护

赛题 PDF、参考论文和 `附件/` 是原始输入，不应被修改或用于存放结果。后续产生的布局、图表、日志和汇总数据应写入独立输出目录，并保持可复现和可追溯。

现有建模、算法、实验和历史基线的阅读顺序见 [docs/README.md](./docs/README.md)。
