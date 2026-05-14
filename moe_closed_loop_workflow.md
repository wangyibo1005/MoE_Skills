# 昇腾 MoE 算子闭环：编排说明（Workflow）

**集合命名：** MoE 算子自演进 Skill 集合；目录级总览参见同路径 [`README.md`](README.md)。

**可视化：** [`ascend_moe_closed_loop_4skills.png`](ascend_moe_closed_loop_4skills.png)。

本文规定**步骤顺序**、**各工具目录的职责边界**以及**推荐协作分区**。  
各子目录 `SKILL.md` **仅承载本工具自身的**输入、输出与命令说明；工具间编排关系与数据口径约束**以本文为唯一权威说明**，不得在单个 Skill 文档中维护重复的跨工具对照表。

---

## 构建标签与约束

| 标签 | 定义 | 允许的使用方式 |
|------|------|----------------|
| **baseline_clean** | 基准侧的**不含打点**，或与表格化性能对比**语义兼容**的构建 | **正式性能 profiling**：`op_summary` 等均可用作性能对比的基准依据之一 |
| **candidate_clean** | 候选变更的**不含打点**，或与表格化性能对比**语义兼容**的构建 | **正式性能 profiling**：与 **`baseline_clean`** 对照以得出数值结论 |
| **candidate_trace** | 为打点 / trace **单独派生**的构建 | **仅**用于 trace 及打点归因分析；其结果**禁止**用作正式性能 profiling 的结论依据 |

**强制约束**

1. **`baseline_clean`** 与 **`candidate_clean`** 的数据可用于**正式性能** profiling。  
2. **`candidate_trace`** **仅**用于 trace 及打点归因。  
3. **含打点实现**之构建不得以任何形式冒充**正式性能** profiling 数据源；一旦发生误采集，须在材料中明文声明该数据集**作废**。  
4. 基于 profiling 的结论与基于 trace 的结论须**分项表述并标注来源**，禁止在单一句子中混淆两类证据且不注明数据来源。

---

## 设计原则

1. **单一职责**：每个工具目录对应一类可追溯产物；阶段间依赖通过**文件路径、构建标签及口径约定**传导。  
2. **编排外置**：串联顺序与子集裁剪（是否执行 trace）由本文与协调方约定；各子目录 `SKILL.md` 不写入全局编排表。  
3. **人在回路（Human-in-the-loop）**：下一迭代的 **`candidate_clean`** 现阶段由工程师根据 **`next_action.md`** 制备；本文不预设全自动改码—合入主线的工程流程。  
4. **演进接口**：**`candidate_change_suggestion`** 可对齐后续「自动生成补丁」类技能的结构化输入；当前形态为**可读建议文本**，不可替代人工编码与评审。

---

## MoE_Opt_* 技能目录与 Workflow Step 对照

四套技能的**目录名**均以 **`MoE_Opt_`** 为前缀，并与编排步骤一一对应；口头上的 **Skill 1–4** 与表中 **Step 2–5** 同序（**前置**不包含在内）。

| 目录（相对于 `.cursor/skills/`） | 职责摘要 | Workflow Step | 俗称 |
|----------------------------------|-----------|---------------|------|
| **`MoE_Opt_profiling/`** | `op_summary` 对比与结构化性能结论 | Step 2 | Skill 1 |
| **`MoE_Opt_auto_trace/`** | **auto_trace**：**自动打点**（源码插桩）、**`candidate_trace`** 构建、`trace.json`／`point_map.json` | Step 3 | Skill 2（**auto_trace**） |
| **`MoE_Opt_trace_analysis/`** | 对 **`trace.json`** 做统计与归因报告 | Step 4 | Skill 3 |
| **`MoE_Opt_experiment_record/`** | manifest 收口：**`experiment_report.md`**、**`decision.yaml`**、**`next_action.md`** 等 | Step 5 | Skill 4 |

**前置（闭环外，不配 Step 序号）：** 由工程师依据上一轮 **`next_action.md`** 在算子工程中制备 **`candidate_clean`** 并完成 **baseline_clean／candidate_clean** 侧的 **`op_summary` 采集**。部分文档将之称为「下一轮人工环节」，与上文 **前置** 指同一职责，**不与 Step 2–5 并列编号**，以免与 Profiling Step 混淆。

---

## 四 Skill 串联总览（与流程图对齐）

应在 **`baseline_clean`** 与 **`candidate_clean`** 上分别采集 profiling，导出同源 **`op_summary*.csv`**（或工程等价的 msprof 汇总表），再进入上表四套目录中的工具。**Skill 1–4** 与 **`MoE_Opt_*`** 目录及 Workflow **Step 2–5** 的对应关系见上一节对照表。

```
baseline_clean profiling ─┐
                          ├──► Skill 1：Profiling 对比（MoE_Opt_profiling）
candidate_clean profiling ┘
        │
        ├── profile_compare.json
        ├── profiling_report.md
        ├── performance_decision_hint.json（见 Skill 1 产物定义）
        └── profile_summary.json、report.md 等（详见 Skill 1 文档）

        └─► 需要进行阶段级归因时
                │
candidate_clean 源码与观测／sample 配置
        │
        ▼
Skill 2：**auto_trace** — 自动打点与 trace／Chrome 全链路（`MoE_Opt_auto_trace`）
        │
        ├──► candidate_trace 构建产物（独立构建标签）
        ├── trace.json（基于 candidate_trace 采集）
        ├── point_map.json（工程侧亦可能命名为 trace_point_map.json）
        └── 相对基线的插桩改动说明：可采用 trace_patch.diff 或等价 git diff 导出

        ▼
Skill 3：trace 解析与统计（MoE_Opt_trace_analysis）

        【收口用规范文件名】（Skill 4 归档及检索）
          trace_analysis.json   ← 工具默认常为 summary.json
          trace_report.md         ← report.md
          optimization_clues.md    ← 常为 statistical_summary.md
          bottleneck_explanation.json ← 常为 diagnosis.json
        字段与 manifest：见 MoE_Opt_experiment_record/SKILL.md

        ▼
profile_compare.json + trace 归因工件 + candidate_clean 侧 patch.diff
        + 版本信息、run_config、决策规则（metadata / manifest）
        │
        ▼
Skill 4：实验记录与演进决策（MoE_Opt_experiment_record）
        │
        ├── experiment_report.md
        ├── decision.yaml
        ├── next_action.md
        ├── candidate_change_suggestion.md
        ├── evolution_index.jsonl（追加一条记录）
        └── experiment/ 归档（含副本与 report/）

        ▼
责任方依据 next_action 制备下一轮 candidate_clean → 重复 baseline／candidate profiling → Skill 1
```

---

## 四工具：输入／输出契约

下表映射四个工具目录。**不包含**工程侧人工制备 **`candidate_clean`** 的步骤（见「人在回路闭环」）。

| 工具目录 | 主要输入 | 主要输出 |
|----------|----------|----------|
| `MoE_Opt_profiling/` | 源于 **`baseline_clean`** 及／或 **`candidate_clean`** 的 `op_summary*.csv`；对比模式可同时指定 baseline／candidate CSV；可选 **`--manifest`** JSON（版本、运行与解析规则） | **`profile_summary.json`**、**`profile_compare.json`**、**`profiling_report.md`**、**`performance_decision_hint.json`**、`compare_summary.json`、`compare_by_group.csv`、`report.md`、图件（可选） |
| `MoE_Opt_auto_trace/`（**auto_trace**） | 目标算子与工程；**`candidate_trace`** 下 **`MoE_Opt_auto_trace`** 所需自动打点改造、编译与 sample／测试配置 | `trace.json`、`point_map.json` 及插桩构建产物 |
| `MoE_Opt_trace_analysis/` | **`candidate_trace`** 下采集的 `trace.json`；可选 phase 映射配置 | 输出目录内 `report.md`、`summary.json`、图表及统计附件等 |
| `MoE_Opt_experiment_record/` | manifest 及 Skill 1／Skill 3／**`candidate_clean`** 相关工件的路径引用；不对算子源码施加变更 | **`experiment_report.md`**、**`decision.yaml`**（accept | continue | reject | failed）、**`next_action.md`**、**`candidate_change_suggestion.md`**、**`evolution_index.jsonl`**、**`experiment/`** 归档 |

### Step 5（Skill 4）核心产出语义

| 产出 | 说明 |
|------|------|
| **`next_action.md`** | 驱动下一版 **`candidate_clean`**：可含继续打点、补充用例集、回滚或重跑等事项。 |
| **`decision.yaml`** | 结构化决策占位（accept／continue／reject／failed）；供自动化与人工批注共用。 |
| **`candidate_change_suggestion.md`** | 面向实现的文字建议；**不作为**补丁或合并请求替代品。 |
| **`experiment_report.md` 及 `experiment/`** | 复现线索与报告正文。**`evolution_index.jsonl`** 追加一行以实现历史可追溯检索。 |

---

## 人在回路：最小闭环

单次迭代末尾，收口阶段产出 **`next_action.md`**、**`candidate_change_suggestion.md`** 及 **`decision.yaml`** 后，**工程师**实施变更并导出下一 **`candidate_clean`**，随后重新采集 **`baseline_clean`／`candidate_clean`** 侧的 `op_summary`，进入下一轮四工具链路。**打点专属构建始终对应 `candidate_trace` 路径。**

信息流示意：Skill 4 收口 **`next_action.md`** → 人工制备 **`candidate_clean`** → **`op_summary` profiling** → 按需经 **`candidate_trace`** 与分析工具完成归因。

---

## 闭环步骤与工具映射

与图示一致：**`candidate_clean`** 由闭环外人工制备为本流程前置条件；其后 **Step 2–5** 与四工具逐一对应。

| 步骤 | 目的 | 典型产物 | 工具目录 |
|------|------|----------|-----------|
| **前置** | 依据上一轮 **`next_action.md`** 制备 **`candidate_clean`** | 可执行二进制、wheel 等交付物 | 工程责任人；非本 Skill 仓库内工具 |
| **Step 2** | Profiling **对比（仅 clean）** | `op_summary*.csv`、`profile_summary.json`、`profile_compare.json`、`profiling_report.md`、`performance_decision_hint.json`、`report.md`、`compare_delta_top.png`（可选）、`compare_summary.json` | `MoE_Opt_profiling/` |
| **Step 3** | **auto_trace**：**自动打点**、派生 **`candidate_trace`**、`trace.json` | `trace.json`、`point_map.json` 等 | `MoE_Opt_auto_trace/` |
| **Step 4** | Trace **解析与归因** | `report.md`、`summary.json` 及分析目录内附件（命名以 Skill 3 文档为准） | `MoE_Opt_trace_analysis/` |
| **Step 5** | **实验记录与演进决策** | **`experiment_report.md`**、**`decision.yaml`**、**`next_action.md`**、**`candidate_change_suggestion.md`**、**`evolution_index.jsonl`**、**`metadata.yaml`**、`report/` 下归档副本 | `MoE_Opt_experiment_record/` |

**常规数据次序**：在 **`candidate_clean`** 已就绪时，应先完成 **clean 侧 profiling（Step 2）**，按需执行 **trace 构建（Step 3）** 与 **trace 分析（Step 4）**，最后汇入 **收口（Step 5）**。

---

## 流程变体（子集裁剪）

并非每轮均需执行 Step 3–4；收口仍可落盘，但须在材料中明示**本轮缺失的证据类别**。

| 目标 | 建议步骤 | Step 5 书写要求 |
|------|----------|-----------------|
| 仅答复**相对快慢或表格级耗时结论** | Step 2，Step 5 可选 | trace 证据标注为**本轮未采集**；说明是否仍存在归因空缺。 |
| **数值结论 + 阶段级归因** | Step 2 → 3 → 4 → 5 | profiling 与 trace **分列路径及口径**；红线条目逐项核对。 |
| **补强 trace、profiling 已由他方产出** | Step 3–4 为主，辅以 Step 5 | 明示 profiling **来源责任人、路径与日期**，避免无主数据引用。 |

**并行工程说明**：Step 2 与 Step 3 可隶属于不同流水线作业；语义上仍以 **先于 `candidate_trace` 完成 clean profiling 以建立数值锚点**，再在 trace 维度解释行为差异为佳。

---

## 各步骤输入与产出快照

以下为编排视图下的**契约摘要**；命令行参数与各目录 **`SKILL.md`** 所载内容为实施细节的依据。

| 步骤 | 主要输入 | 主要产出 |
|------|----------|----------|
| Step 2 | `op_summary*.csv`；可选 `--manifest`；CLI 过滤参数 | 「四工具契约」中 profiling 路径所列 JSON／MD、`report.md`、`compare_summary.json` |
| Step 3 | 算子源码路径、编译与 sample 约定 | `trace.json`、`point_map.json`（或工程等价物）、插桩二进制／包 |
| Step 4 | `trace.json`；可选 phase-map | 约定输出目录内的 `report.md`、`summary.json`、图表 |
| Step 5 | Skill 1／Skill 3／**`candidate_clean`** **路径**，manifest 内版本、`run_config`、决策规则 | **`experiment/`**（见 `MoE_Opt_experiment_record/scripts/build_experiment_closure.py`）；**`evolution_index.jsonl`** 追加一行 |

---

## 协作模型：协调方与子任务拆分（仅供参考）

宿主环境可不提供固定的「子 Agent」接口；就流程而言，可作如下角色划分：

| 角色 | 职责 |
|------|------|
| **协调会话** | 维护路径、分支、**`candidate_*`** 标识及红线自检结果；调度各工具调用；汇总 **`experiment_report.md`**、**`decision.yaml`**、**`next_action.md`** 等收口产出。 |
| **Profiling 子任务** | 读取 **clean** CSV，产出 `profile_summary.json`、`profile_compare.json`、`profiling_report.md`、`performance_decision_hint.json` 及 **`report.md`**。 |
| **auto_trace 子任务** | 仅限 **`MoE_Opt_auto_trace/`**：自动打点插桩、编译并使 **`trace.json`** 等落盘。 |
| **Trace 分析子任务** | 仅限 `MoE_Opt_trace_analysis`：由 **`trace.json`** 生成统计报告与图表。 |
| **记录／决策子任务** | 仅限 `MoE_Opt_experiment_record`：执行 **`scripts/build_experiment_closure.py`** 与 manifest（或等价手写归档），写入 **`experiment/`** 及 **`evolution_index.jsonl`**；**不改变**算子源码树。 |

单一会话内可顺序执行上述子任务；多会话并行时须由协调方传递**绝对路径**与**构建标签**（如 **`baseline_clean`**、**`candidate_trace`**）。

---

## 索引

| 事项 | 路径 |
|------|------|
| Profiling | `MoE_Opt_profiling/SKILL.md` |
| auto_trace（自动打点与 trace 采集） | `MoE_Opt_auto_trace/SKILL.md` |
| Trace 分析 | `MoE_Opt_trace_analysis/SKILL.md` |
| 闭环收口 | `MoE_Opt_experiment_record/SKILL.md` |
| 本文档 | **`moe_closed_loop_workflow.md`** |

---

## 修订纪律

闭环步骤或目录命名变更时，**仅修订本文及各 `SKILL.md` 中与该工具 CLI／产物直接相关的段落**；避免在四个 Skill 文档之间堆砌交叉重复的编排段落——编排语义统一回归本文。
