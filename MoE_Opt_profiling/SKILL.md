---
name: MoE_Opt-profiling
description: >-
  MoE_Opt_profiling (Skill 1, workflow Step 2): Ascend msprof op_summary baseline_clean vs candidate_clean:
  profile_summary.json, profile_compare.json, profiling_report.md, performance_decision_hint.
  Single-file drill-down, Task Duration scatter. Triggers: op_summary, profiling, FusedDeepMoe, baseline candidate compare.
---

# MoE_Opt_profiling · op_summary Profiling 对比

## 范围与红线

本技能从 **`op_summary_*.csv`**（或同源 msprof 算子汇总表）生成统计与对比结论；与 **`moe_closed_loop_workflow.md`** 中 **Step 2**（目录 **`MoE_Opt_profiling/`**）对齐：须在 **`baseline_clean` / `candidate_clean`** 下**未混入 trace 插桩、且未改变算子对外契约/融合语义**的前提下采集的数据。

| 素材 | 在本技能中的用途 |
|------|------------------|
| **`op_summary_*.csv`** | **数值对比证据**（谁更快、分布与聚合指标） |
| **`trace.json`、插桩重编译产物** | **不在本技能内解析**；若与性能结论同事讨论，须与上表分开口径 |

**红线**：性能「谁好谁坏」**只**建立在 **clean** profiling 导出的 `op_summary`（或同源 msprof 导出）之上。误用含 trace 插桩或改动 `profiling_data` 输出位等影响图融合的构建做对比时，须在结论中声明 **无效**。

多步骤闭环的总体顺序与目录对照见 **`moe_closed_loop_workflow.md`**（与本文件同级目录）。

---

## MoE_Opt_profiling — 输入与输出

**目标**：在 **baseline_clean** 与 **candidate_clean** 上判断**真实性能**变化；**不得**使用 **candidate_trace** 或任何**带打点**构建产出的 `op_summary` 参与「谁更快」结论。

### 输入

1. **baseline_clean profiling 原始结果**：CLI **`--baseline`**，**msprof `op_summary*.csv`**。
2. **candidate_clean profiling 原始结果**：CLI **`--candidate`**，同源 CSV。
3. **baseline_clean 版本信息**：写入可选 **`--manifest`** JSON 的 **`version_info.baseline_clean`**：`commit`、`branch`、`build_config_summary` 等。
4. **candidate_clean 版本信息**：**`version_info.candidate_clean`**；`patch_notes`、`diff_ref` 等可选。
5. **运行配置**：**`run_config`**（如 `shape`、`dtype`、`rank`、`global_bs`、`topk`、`expert_num`、`case_name`），与 prof 采集场景一致。
6. **profiling 解析规则**：**`parse_rules`**。本工具以 **`--group-by`** 聚合后的 **label** 为逻辑 kernel 键（默认 **`OP Type`**，可改为 **`Op Name`** / **`Task Type`**）。**Phase 映射**：**`parse_rules.phase_map`** 为 `pattern`/`phase` 正则列表，按**较长 pattern 优先**将 label 归入 phase，并对 **Task Duration** 做 sum 汇总。**关键指标**：**`key_metrics`** 为文档性列表；实现侧以 **sum(Task Duration)** 与 **Δ% vs baseline** 为主。

清单样例：**`schemas/profiling_manifest.example.json`**。

### 输出（对比模式）

1. **`profile_summary.json`**：`totals`、Δ 与 **delta_pct_vs_baseline**、`key_kernels_*`、`key_phases_*`、`performance_decision_hint`。
2. **`profile_compare.json`**：按组与按 phase 的结构化对比、变快/变慢列表、主要变化点摘要。
3. **`profiling_report.md`**：给人读的 totals、hint、表格式摘要；文末引用 JSON 文件名。
4. **`performance_decision_hint.json`**：字段 **`performance_decision_hint`** 为 **`improved` \| `regressed` \| `neutral` \| `need_trace_analysis`**，另含 **`detail`**。

另有兼容：`report.md`、`compare_summary.json`、`compare_by_group.csv`、Δ 条形图 PNG。使用 **`--manifest path.json`** 写入版本与解析规则，便于归档与演进记录引用。

---

## 在对话里「只报算子名」能否直接出报告？

**可以。** 在 Cursor 中已加载本 skill 的前提下，用户**不必记命令**，只需说明要写进 **`OP Type`** 列的算子名（如 `FusedDeepMoe`），并**指明或 @ 对应的 `op_summary` CSV**；若工作区里只有一个匹配的 `op_summary*.csv`，Agent 可在一句确认后用之。

**Agent 必做**：在技能目录下执行（**不要**让用户选输出目录或去极值参数；默认结果在 CSV 旁的 `<文件名>_op_summary_out/`）：

```bash
python3 ~/.cursor/skills/MoE_Opt_profiling/app.py \
  -i "<CSV 绝对路径>" \
  --op-type "<与 OP Type 列一致的名称>" \
  --top-n 25
```

完成后向用户汇报 **`report.md` 路径**（及同目录下 `summary.json`、`operator_focus.json`、PNG 若已安装 matplotlib）。

**注意**：算子名必须与 CSV 中 **`OP Type`** 完全一致；不清楚时可用 `head -1` 看表头，或对 `OP Type` 列做 `sort -u` 再让用户点选。

---

## Profiling 产物里先看什么

常见目录下会有大量文件；**`op_summary*.csv`（或命名相近的 operator summary）是核心表**：一行近似为一次任务/算子实例记录，含 **OP Type**（统计聚合主键之一）、**Op Name**（实例名）、**Task Duration(us)**、**Task Wait Time(us)**、**aicore_time / aiv_time**、**cube_utilization** 等。

参考列名（与典型 msprof 导出一致；若工具版本列有增减，以实际 CSV 表头为准）：

`Device_id`, `OP Type`, `Task Type`, `Op Name`, `Task Duration(us)`, `Task Wait Time(us)`, `aicore_time(us)`, `aiv_time(us)`, `cube_utilization(%)` …

---

## Agent 执行原则

1. **路径**：从用户请求或工作区确认 `op_summary` CSV 的**绝对路径**；不要用文档里的占位路径执行。
2. **输出目录**：**不传 `-o` 时默认写在输入 CSV 同目录**下，子目录名为 **`<文件名>_op_summary_out`**（例如 `foo.csv` → `foo_op_summary_out/`）。对比模式默认在 **baseline CSV 同目录**下 **`"<baseline>_vs_<candidate>_op_summary_out"`**。需要时再显式传 **`-o` / `--output-dir`**。
3. **用户自然语言映射**：当用户说「**请分析某某算子**」（名称对应 CSV 列 **`OP Type`**，如 `FusedDeepMoe`）时，应运行单文件模式并加上 **`--op-type <名称>`**。**去掉 Duration 极大值**由工具**内置固定策略**自动完成（见下条），**不要**要求用户选「剔几条」**不要**把 trace 插桩版本的 op_summary 当性能对比依据（见上文红线）。
4. **对比实验**：同时给出 **`--baseline`** 与 **`--candidate`** 两个文件时进入对比模式；聚合键默认为 **`OP Type`**，可通过 **`--group-by`** 改为 `Task Type`、`Op Name` 等（列名需与 CSV 表头一致）。
5. **单算子深挖**：启用 `--op-type` 时，**自动**在有效样本中按 Task Duration **从大到小**去掉**至多 3 条**（样本不足则少剔，详见代码常量 `TRIM_LARGEST_DURATION_COUNT`），再算「稳健」列的 mean / p50 / p95 与 Wait、cube 的配对统计；**report.md** 末尾 **「结论要点」** 为规则化中文解读（非 LLM）；需 **PNG** 时安装 **`matplotlib`**（`pip install -r requirements.txt`）。
6. **可视化**：默认尝试生成 PNG；若未安装 matplotlib，仍会输出 **JSON/CSV/Markdown**，并在 stderr 提示安装可选依赖。

---

## 运行方式

技能根目录：`~/.cursor/skills/MoE_Opt_profiling/`（与 `MoE_Opt_trace_analysis`、`MoE_Opt_auto_trace` 并列）。

### 单文件：聚合 + 图表

```bash
cd /home/wangyibo/.cursor/skills/MoE_Opt_profiling
# 不写 -o：报告与图默认落到与 CSV 同目录的 <csv名>_op_summary_out/
python3 app.py \
  --input /path/to/op_summary_xxx.csv \
  --group-by "OP Type" \
  --top-n 25
```

**过滤**（可选）：

- `--device-id 0`
- `--op-type FusedDeepMoe`（精确匹配 OP Type）
- `--op-type-contains Moe`（子串，大小写不敏感）
- `--task-type MIX_AIC`（精确匹配 Task Type）
- `--op-name-contains foo`（Op Name 子串）

**单算子（指定 OP Type）：分布 + 自动去极值 + 解读**（例如用户说「分析 FusedDeepMoe」）：

```bash
# 不写 -o：与输入 CSV 同目录下生成例如 my_run_op_summary_out/（目录名 = CSV 主文件名 + _op_summary_out）
python3 app.py -i /path/to/my_run.csv \
  --op-type FusedDeepMoe \
  --top-n 20
```

- **去极大值**：**内置、默认执行**，无需也不提供 CLI 开关。策略：在有效 Task Duration 上**自动去掉最大的 3 条**（可修改本 Skill 仓库内 **`analyzers/operator_analysis.py`** 中的常量 **`TRIM_LARGEST_DURATION_COUNT`** 以便团队统一调整）。
- 产出除全局表格外，另有 **`operator_focus.json`**、`report.md` 中的 **单算子统计表、散点图嵌入、结论要点**；单算子图为 **`operator_duration_scatter.png`**（含全样本平均耗时水平线；`--op-type`；需 matplotlib）。**`report.md` 与 PNG 同目录**，用相对路径嵌入，在 IDE/Cursor 中可直接预览。

安装可选依赖以生成 PNG：

```bash
pip install -r requirements.txt
```

### 双文件：baseline vs candidate

```bash
# 不写 -o：默认在 baseline 同目录下 <baseline>_vs_<candidate>_op_summary_out/
python3 app.py \
  --baseline /path/to/op_summary_baseline.csv \
  --candidate /path/to/op_summary_candidate.csv \
  --group-by "OP Type" \
  --top-n 25 \
  --manifest /path/to/profiling_manifest.json
```

`--manifest` 可选；样例见 `schemas/profiling_manifest.example.json`。

输出主要包括：

- **`profile_summary.json`**、**`profile_compare.json`**、**`profiling_report.md`**、**`performance_decision_hint.json`**：结构化结论与可读报告
- **`compare_summary.json`**、**`compare_by_group.csv`**、**`report.md`**、`compare_delta_top.png`（与上兼容）

`--no-charts` 可跳过所有 PNG。

---

## 输出解读（给 Agent / 人读）

- **`task_duration_us_sum`**：该组所有实例 ** wall 侧任务耗时总和**（微秒量级与导出工具一致），用于「谁占总体时间多」。
- **`task_wait_us_sum` / mean**：**等待**相关，适用于粗看调度/流水线气泡；**阶段级归因**需基于 **`trace.json` 的专用解析**（勿与下文混写成一句结论）。
- **`aicore_us` / `aiv_us`**：核上拆分时间，可与 **cube_util** 一起看算力利用。
- **对比模式**中 **`delta_task_duration_pct_vs_baseline`**：相对 baseline 总和变化百分比；关注 **绝对值大** 且 **与优化目标相关** 的 OP Type。

---

## 与 trace 归因的口径区分

- 需要 **阶段级根因** 时，应对 **`trace.json`** 走**独立**的解析与报告流程（输入输出与本文不同）。
- 不要在同一句结论里 **混用**「本表/本报告中的数值对比」与「trace 中某区间变长」而不说明前者来自 **clean profiling**、后者来自 **trace 归因**。

---

## Skill 自维护

与本 skill 相关的可复用结论（列名变更、工具版本差异、常见过滤组合）可在用户确认后写入本文件，保持与 `app.py` 行为一致。
