---
name: MoE_Opt-experiment-record
description: >-
  MoE_Opt_experiment_record（Skill 4，编排 Step 5）：合并 MoE_Opt_profiling 与 MoE_Opt_trace_analysis 的产物及 candidate 元数据，
  写入 experiment_report.md、decision.yaml、next_action.md、candidate_change_suggestion.md、evolution_index.jsonl 与 experiment/ 归档；不改算子源码。
  next_action.md 驱动工作流「前置」环节（人工制备 candidate_clean）。
---

# MoE_Opt_experiment_record · 实验记录与演进决策（收口）

**作用：** 将闭环收口为可追溯实验材料：汇总 **profiling 结论**、**trace 归因**、**candidate 变更信息** 与 **实验元数据**；**不修改**目标算子仓库源码。产出须驱动编排文档中的 **前置** 环节：工程师依据 **`next_action.md`** 制备下一轮 **`candidate_clean`**（与工作流表中「前置」同义；**不占用 Step 2–5 编号**）。

编排级红线见 **`moe_closed_loop_workflow.md`**。

---

## 输入（路径或清单）

| # | 类别 | 内容 |
|---|------|------|
| 1 | MoE_Opt_profiling（Skill 1） | `profile_summary.json`、`profile_compare.json`、`profiling_report.md`、`performance_decision_hint.json`（由 **`MoE_Opt_profiling/`** 对比模式产出） |
| 2 | MoE_Opt_trace_analysis（Skill 3，可选） | 收口用规范名：`trace_analysis.json`、`bottleneck_explanation.json`、`trace_report.md`、`optimization_clues.md`。与 **`MoE_Opt_trace_analysis/`** 运行时文件对应：`summary.json` → `trace_analysis.json`（复制归档）；`diagnosis.json`、`report.md`、`statistical_summary.md` 同理映射见 **`SKILL.md`**。manifest 可填各文件路径，或仅填 **`trace_output_dir_optional`**，由收口脚本补缺。 |
| 3 | candidate_clean 改动 | `patch.diff`、`changed_files.txt`、`change_summary.md`、**intent** 文本 |
| 4 | 版本信息 | baseline_clean / candidate_clean / candidate_trace 的 branch、commit、路径等 |
| 5 | 实验配置 | shape、dtype、rank、global_bs、expert_num、topk、case 名、运行环境 |
| 6 | 决策规则 | 性能阈值、当 **`performance_decision_hint` 为 `need_trace_analysis`** 时是否必须先具备 trace、`final_decision_override`（人工覆盖） |

**单一入口：** JSON manifest，样例见 **`schemas/experiment_closure_input.example.json`**。

---

## 输出（一次运行写入 `<experiment-dir>/<experiment_id>/`）

| 文件 | 说明 |
|------|------|
| **`experiment_report.md`** | 本轮说明、版本与 run_config、candidate 意图、profiling/trace 节选、风险、收口判断占位 |
| **`decision.yaml`** | `decision`: **accept \| continue \| reject \| failed**；性能 Δ%、收益/劣化摘要 hint、归因 note、risk、baseline 晋级建议；（首版由规则自动生成，**可人工批改**） |
| **`next_action.md`** | 下一轮优化方向、验证 case、是否需要继续打点/trace、rollback 指引 — **导向人工 `candidate_clean`** |
| **`candidate_change_suggestion.md`** | 给工程师的阅读型建议：**可能文件/phase**、验证建议；非补丁 |
| **`evolution_index.jsonl`** | 运行时 **追加一行** JSON，便于检索与 case 沉淀（路径由 **`--evolution-index`** 指定） |
| **目录布局** | `metadata.yaml`；根下 `patch.diff`、`profile_compare.json`、`trace_analysis.json`（若可提供）、`report/profiling_report.md`、`report/trace_report.md`、`report/optimization_clues.md` 等归档副本 |

**主命令：**

```bash
python3 scripts/build_experiment_closure.py \
  --manifest "/path/to/experiment_closure_manifest.json" \
  --experiment-dir "/path/to/experiments_parent" \
  --evolution-index "/path/to/evolution_index.jsonl"
```

产出目录：**`<experiment-dir>/<experiment_id>/`**。

---

## 红线

1. 性能段落只引用 **baseline_clean / candidate_clean** profiling。  
2. 归因只引用 **candidate_trace + `MoE_Opt_trace_analysis/`**；勿与 profiling 数值混写为单句且无来源标签。  
3. **打点构建**不作为真实性能依据。  
4. **`MoE_Opt_experiment_record`** **不**应用补丁、**不**改算子源码；**candidate_change_suggestion** 仅是文字。  
5. **自动 `decision` 不等于团队最终结论**；发布前须经人审 **`decision.yaml`**。

---

## 与遗留模板 `templates/evolution_record.template.md`

旧版单笔 Markdown 模板仍可手写或 `init_evolution_record.py` 起草；与 **`build_experiment_closure.py`** 并行不冲突。**推荐**新闭环优先采用 **manifest + `build_experiment_closure.py`**，以便与 **`MoE_Opt_profiling/`、`MoE_Opt_trace_analysis/`** 的产物命名对齐。

---

## Skill 自维护

manifest 字段与 **`MoE_Opt_trace_analysis/`** 实际产物名若有变动，应先更新该 Skill 的实现与 **`SKILL.md`**，再同步本节及 **`schemas/experiment_closure_input.example.json`**。
