# Trace Analysis Skill

这个工程用于解析算子打点产生的 Chrome/Perfetto `trace.json`，按 phase、category、core group、tid 和 raw name 统计耗时，并生成可读性能分析报告。

项目的核心对象是 `trace.json`，不是某一个固定算子。当前仓库自带的默认配置来自 UMDK FusedDeepMoe 场景，因此对 `fused_deep_moe` 的 trace 最友好；分析其他算子时，可以复用解析、统计、图表和报告能力，并通过替换 `--phase-map` 来适配新的 trace label。

## 输入模型

使用时建议把上下文分成三类：

- `TRACE_JSON`：必需，待分析的 trace 文件。
- `SOURCE_ROOT`：可选，算子源码工程目录，例如本仓库中的 `umdk`。
- `OPERATOR`：可选，算子名，例如 `fused_deep_moe`。

当前 CLI 直接消费的是 `TRACE_JSON` 和 `PHASE_MAP`。`SOURCE_ROOT` 与 `OPERATOR` 目前主要作为 agent 阅读源码、理解打点语义、维护 phase map 和诊断上下文时使用。

## 功能

- 解析 Chrome/Perfetto trace JSON。
- 支持 `ph == "X"` 完整事件和 `ph == "B" / "E"` 成对事件。
- 将 trace name 映射到稳定 phase。
- 按 phase、category、core group、tid、raw name 聚合耗时。
- 输出 CSV、JSON、Markdown 报告和统计图。
- 计算 phase overlap 和外层阶段 bubble。
- 安装 `matplotlib` 时自动生成 core group 覆盖、category 占比和 top phase 统计图。
- 生成确定性 `Automatic Diagnosis`。
- 可选调用外部 LLM 命令，把统计上下文扩展为专家分析段落。

## 运行方式

基础命令模板：

```bash
python3 app.py \
  --trace <TRACE_JSON> \
  --phase-map <PHASE_MAP> \
  --output-dir <OUTPUT_DIR> \
  --top-n 20
```

如果使用默认配置，可以省略 `--phase-map`：

```bash
python3 app.py \
  --trace <TRACE_JSON> \
  --output-dir <OUTPUT_DIR> \
  --top-n 20
```

例如分析仓库内示例 trace：

```bash
python3 app.py \
  --trace examples/trace.json \
  --phase-map config/phase_map.yaml \
  --output-dir output/trace \
  --top-n 20
```

输出目录会包含 `report.md`、`summary.json`、`diagnosis.json`、`statistical_summary.md`、各类 `*.csv`，以及总是生成的 `llm_prompt.md`。如果本机安装了 `matplotlib`，还会自动生成 `analysis_charts.png` 并嵌入 `report.md`。

## Phase Map

`--phase-map` 是把某个算子的 trace label 接入通用分析框架的关键配置。

默认配置：

```text
config/phase_map.yaml
```

它目前覆盖 UMDK FusedDeepMoe 的典型打点，例如 `processing`、`dispatch-gmm1`、`gmm2-combine` 以及它们的子阶段。

分析其他算子时，应优先做两件事：

- 从 trace 中观察 raw name 分布，确认主要 label。
- 新建或修改 phase map，把这些 label 归入稳定 phase 和 category。

## 源码上下文

如果用户提供源码工程目录和算子名，agent 可以进入 source-aware 工作方式：

```text
TRACE_JSON   = /path/to/trace.json
SOURCE_ROOT  = /path/to/source_project
OPERATOR     = fused_deep_moe
PHASE_MAP    = config/phase_map.yaml 或对应算子的映射配置
```

当前 CLI 尚未直接提供 `--source-root` 或 `--operator` 参数，但源码上下文仍然有价值。agent 可以读取源码中的 `TRACE_POINT(...)`、`MoeTracing(...)`、`point_map.json` 或 trace mapping，理解 trace name 的来源，并辅助维护 phase map。

## 图表

图表需要本机安装 `matplotlib`。Skill 会默认尝试生成统计分析图；如果没有安装 `matplotlib`，会跳过图表，主报告和表格仍会正常输出。

`analysis_charts.png` 包含：

- core group wall 覆盖。
- 非 container category 的 `total_us` 饼图。
- top phase by `union_us`。

完整 trace 时间线更适合继续用 Perfetto UI 查看。

## LLM 分析

LLM 调用是可选能力。外部命令需要从 stdin 读取 prompt，并把分析文本写到 stdout。

```bash
python3 app.py \
  --trace <TRACE_JSON> \
  --phase-map <PHASE_MAP> \
  --output-dir <OUTPUT_DIR> \
  --llm-analysis \
  --llm-command "<your-llm-cli>"
```

也可以通过环境变量配置：

```bash
export TRACE_ANALYSIS_LLM_CMD="<your-llm-cli>"
python3 app.py \
  --trace <TRACE_JSON> \
  --phase-map <PHASE_MAP> \
  --output-dir <OUTPUT_DIR> \
  --llm-analysis
```

## 验证

```bash
python3 -m unittest discover -s tests
```

也可以用任意实际 trace 做端到端验证：

```bash
python3 app.py \
  --trace <TRACE_JSON> \
  --phase-map <PHASE_MAP> \
  --output-dir <OUTPUT_DIR> \
  --top-n 20
```

## 目录

- `app.py`：命令行入口。
- `analyzers/`：parser、phase mapper、指标、诊断、报告、图表和 LLM prompt 生成逻辑。
- `config/phase_map.yaml`：当前默认 trace label 到 phase/category 的映射。
- `examples/trace.json`：保留的示例 trace。
- `tests/`：单元测试。
- `SKILL.md`：作为 Codex Skill 使用时的执行说明。
- `docs/`：设计说明和示例报告图片。
- `umdk/`：用于对照打点来源的 UMDK 示例源码工程。

## 当前限制

- 当前没有显式 `--operator` 或 `--source-root` CLI 参数。
- 不同算子主要通过 `--phase-map` 适配。
- 未映射到 phase 的事件当前不会进入 phase 统计表。
- core group 规则目前仍以内置 UMDK 1C2V 约定为主。
- 部分自动诊断规则仍带有 FusedDeepMoe 经验，需要继续拆分为通用规则和算子规则。

## GitHub 注意事项

`examples/trace.json` 约 96 MiB，低于 GitHub 单文件 100 MiB 硬限制，但可能触发大文件提醒。后续如果需要保留更大的真实 trace，建议使用 Git LFS，或者只提交小型脱敏样例。
