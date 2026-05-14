# 演进实验记录：{{EXPERIMENT_ID}}

| 字段 | 内容 |
|------|------|
| **实验标识** | {{EXPERIMENT_ID}} |
| **记录日期** | {{DATE}} |
| **记录人 / 触发** | （可选） |
| **Baseline clean** | （分支或 commit；用于真实性能 prof 的 `baseline_clean` 说明） |
| **Candidate clean** | （分支或 commit；用于真实性能 prof 的 `candidate_clean`） |
| **Candidate trace** | （若本轮有归因：打点构建 `candidate_trace`，与 clean 区分开） |

**说明**：性能依据**仅**来自 baseline_clean / candidate_clean 采集的 **op_summary**；**candidate_trace** 只做 trace 归因，不得记入「谁更快」。

---

## 1. 本轮假设 / 目标

（一句话：本轮改动希望验证什么。）

---

## 2. 产物路径（便于复查）

| 物料 | 路径 |
|------|------|
| Clean：`op_summary` / profiling `report.md` | （填写） |
| Clean：对比输出目录（若有） | （填写或 N/A） |
| Trace 构建：`trace.json` | （填写） |
| Trace 分析：`report.md` | （填写） |
| Trace 分析：`trace_analysis_summary.md`（若有） | （填写或 N/A） |
| 可选：源码与 trace 对照文档 | （填写或 N/A） |

---

## 3. 证据 A：性能对比（仅 baseline_clean / candidate_clean）

**口径**：`op_summary` 等**仅**来自 **baseline_clean** 与 **candidate_clean** 采集；**排除**带打点或破坏图语义的构建。

- （摘录要点 1：例如 Top 组、Δ%、关注点 OP Type）
- （摘录要点 2）
- （摘录要点 3）

**说明**：若仅有单次 run、无 baseline 对比，写明「单次 prof，无对比」。

---

## 4. 证据 B：Trace 归因（仅 candidate_trace → 分析产物）

**口径**：**`trace.json` 仅来自 candidate_trace**；经 trace 分析工具得到的报告**不参与**「谁更快」数值对比。

- （摘录要点 1：主要瓶颈阶段 / 类别）
- （摘录要点 2：等待 / overlap / bubble）
- （摘录要点 3）

**长文引用**：详见 `（填写相对或绝对路径）`。

---

## 5. 红线自检

| 检查项 | 是 / 否 / 不明 | 说明 |
|--------|------------------|------|
| 性能结论仅基于 clean op_summary（或声明无效） | | |
| Trace 归因与 clean 场景一致或可接受差异已说明 | | |
| 未把 trace 构建的 prof 当作「谁更快」依据 | | |
| Profiling 与 trace 是否同一 case / 同款输入规模 | | |

---

## 6. 风险与局限

- （场景、采样次数、未覆盖路径、与主线分支差异等）

---

## 7. 演进决策（必选其一）

**选中项**：`Accept` / `Continue` / `Reject`（保留一项，删去另两项标题或划掉）

### Accept（采纳 candidate）

- **依据**：（perf + 归因如何支持合入）
- **后续**：candidate 作为下一轮 **baseline** 的约定（分支/标签）

### Continue（继续实验）

- **依据**：（为何尚不能 Accept / Reject）
- **概要**：下一轮方向一句话；**可执行条目见 §8 next_action**。

### Reject（放弃本 candidate）

- **依据**：（perf / 归因 / 工程风险）
- **回退策略**：（恢复 baseline 的方式）

---

## 8. next_action **必填**

供协调者与工程师执行下一轮闭环；**本节不代表**已对仓库做任何自动修改。**当前约定**：由工程师据此实现下一版 **`candidate_clean`**，再采集 op_summary。

- **Accept 时**：合并、打标签或归档层面的动作。
- **Continue 时**：下一版 **`candidate_clean` 的任务清单**：文件或模块边界、要做的事、建议验证命令。
- **Reject 时**：回退基准、废弃分支等与 baseline 对齐的动作。

---

## 9. candidate_change_suggestion **可选**

对源码或配置的**候选修改意图**书面化：范围、思路、风险；**不**等价于补丁或 PR。**后续**可延伸至独立 **自动 patch 生成** 技能。

- （条目或写「无 / 本轮不展开」）

---

## 10. 闭环输出核对（勾选）

- [ ] 性能结论仅基于 **baseline_clean / candidate_clean** 的 profiling
- [ ] Trace 归因仅基于 **candidate_trace**，且已与性能结论分项书写
- [ ] **未**将带打点版本作为真实性能 prof 依据
- [ ] 决策与依据已写清；**next_action** 已填写
- [ ] candidate_change_suggestion 已填写或明示「无」
