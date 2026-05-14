from __future__ import annotations

from typing import Any

from analyzers.stats_utils import describe_floats, _isfinite

DURATION_COL = "Task Duration(us)"
WAIT_COL = "Task Wait Time(us)"
AICORE_COL = "aicore_time(us)"
AIV_COL = "aiv_time(us)"
CUBE_COL = "cube_utilization(%)"
START_TIME_COL = "Task Start Time(us)"

# 单算子分析：自动去掉 Task Duration 最大的 K 条再做稳健统计；不对用户暴露 CLI。
TRIM_LARGEST_DURATION_COUNT = 3


def row_float(r: dict[str, Any], col: str) -> float | None:
    v = r.get(col)
    if v is None:
        return None
    if isinstance(v, (int, float)):
        x = float(v)
        return x if _isfinite(x) else None
    return None


def operator_duration_scatter_data(
    rows: list[dict[str, Any]],
) -> tuple[list[int], list[float], list[bool], bool]:
    """
    Chronological order: sort by Task Start Time(us) when present; rows without valid
    start time are placed after, in stable order.
    highlight[i] is True for the TRIM_LARGEST_DURATION_COUNT largest Task Durations.
    Returns (xs, ys, highlight, used_any_start_time).
    """
    rows_valid = [r for r in rows if _isfinite(row_float(r, DURATION_COL))]
    if not rows_valid:
        return [], [], [], False

    used_start = any(_isfinite(row_float(r, START_TIME_COL)) for r in rows_valid)

    def sort_key(r: dict[str, Any]) -> tuple[int, float, int]:
        st = row_float(r, START_TIME_COL)
        if _isfinite(st):
            return (0, float(st), 0)
        return (1, 0.0, id(r))

    rows_chrono = sorted(rows_valid, key=sort_key)

    ys = [float(row_float(r, DURATION_COL) or 0.0) for r in rows_chrono]
    n = len(ys)

    k = min(TRIM_LARGEST_DURATION_COUNT, max(0, n - 1))
    order_by_dur = sorted(range(n), key=lambda i: ys[i], reverse=True)
    out_idx = set(order_by_dur[:k])
    highlight = [i in out_idx for i in range(n)]
    xs = list(range(n))
    return xs, ys, highlight, used_start


def trim_largest_k_rows_by_duration(
    rows: list[dict[str, Any]],
    max_remove: int,
    *,
    duration_col: str = DURATION_COL,
) -> tuple[list[dict[str, Any]], list[float]]:
    """
    Remove up to `max_remove` rows with the largest Task Duration.
    Only rows with a finite Task Duration participate in ranking; at least one
    such row is kept whenever possible.
    """
    if max_remove <= 0 or not rows:
        return list(rows), []

    valid_pairs: list[tuple[dict[str, Any], float]] = []
    for r in rows:
        d = row_float(r, duration_col)
        if _isfinite(d):
            valid_pairs.append((r, float(d)))

    if not valid_pairs:
        return list(rows), []

    valid_pairs.sort(key=lambda x: x[1], reverse=True)
    n = len(valid_pairs)
    k = min(max_remove, max(0, n - 1))
    removed_durs = [d for _, d in valid_pairs[:k]]
    kept_valid = [r for r, _ in valid_pairs[k:]]
    return kept_valid, removed_durs


def build_column_series(rows: list[dict[str, Any]], col: str) -> list[float]:
    xs: list[float] = []
    for r in rows:
        x = row_float(r, col)
        if _isfinite(x):
            xs.append(float(x))
    return xs


def compute_operator_focus(
    rows: list[dict[str, Any]],
    *,
    op_type: str,
    trim_top_durations: int,
) -> dict[str, Any]:
    """
    Full vs trimmed (largest duration outliers removed) statistics for one OP Type slice.
    """
    rows_valid_duration = [r for r in rows if _isfinite(row_float(r, DURATION_COL))]
    skipped = len(rows) - len(rows_valid_duration)

    durs_all = build_column_series(rows_valid_duration, DURATION_COL)
    trimmed_rows, removed_durs = trim_largest_k_rows_by_duration(
        rows_valid_duration, trim_top_durations
    )

    durs_trim = build_column_series(trimmed_rows, DURATION_COL)
    waits_all = build_column_series(rows_valid_duration, WAIT_COL)
    waits_trim = build_column_series(trimmed_rows, WAIT_COL)
    aic_all = build_column_series(rows_valid_duration, AICORE_COL)
    aic_trim = build_column_series(trimmed_rows, AICORE_COL)
    aiv_all = build_column_series(rows_valid_duration, AIV_COL)
    aiv_trim = build_column_series(trimmed_rows, AIV_COL)
    cube_all = build_column_series(rows_valid_duration, CUBE_COL)
    cube_trim = build_column_series(trimmed_rows, CUBE_COL)

    return {
        "op_type": op_type,
        "row_count_input": len(rows),
        "row_count_with_valid_duration": len(rows_valid_duration),
        "skipped_rows_without_duration": skipped,
        "trim_top_durations_requested": trim_top_durations,
        "trim_top_durations_removed": len(removed_durs),
        "removed_task_duration_us": removed_durs,
        "durations_all_samples": durs_all,
        "durations_trimmed_samples": durs_trim,
        "duration_raw": describe_floats(durs_all, "Task Duration (us), all samples"),
        "duration_trimmed": describe_floats(durs_trim, "Task Duration (us), after removing largest durations"),
        "wait_raw": describe_floats(waits_all, "Task Wait (us), all samples"),
        "wait_trimmed": describe_floats(waits_trim, "Task Wait (us), paired with trimmed rows"),
        "aicore_raw": describe_floats(aic_all, "aicore_time (us)"),
        "aicore_trimmed": describe_floats(aic_trim, "aicore_time (us) trimmed"),
        "aiv_raw": describe_floats(aiv_all, "aiv_time (us)"),
        "aiv_trimmed": describe_floats(aiv_trim, "aiv_time (us) trimmed"),
        "cube_raw": describe_floats(cube_all, "cube_utilization (%)"),
        "cube_trimmed": describe_floats(cube_trim, "cube_utilization (%) trimmed"),
    }


def narrative_cn(focus: dict[str, Any]) -> str:
    """
    Deterministic, rule-based interpretation in Chinese (no LLM).
    """
    lines: list[str] = []
    ot = focus.get("op_type", "")
    n = focus.get("row_count_with_valid_duration") or focus.get("row_count_input", 0)
    k = focus.get("trim_top_durations_removed", 0)
    raw = focus.get("duration_raw") or {}
    tr = focus.get("duration_trimmed") or {}
    w_raw_mean = (focus.get("wait_raw") or {}).get("mean")
    d_raw_mean = raw.get("mean")
    d_tr_mean = tr.get("mean")
    cv_tr = tr.get("cv")
    cu_tr = (focus.get("cube_trimmed") or {}).get("mean")

    lines.append(f"### 针对 **{ot}** 的结论要点")
    lines.append("")
    lines.append(
        f"- **样本量**：有效 Task Duration 样本 **{n}** 条；按固定策略（Duration **从大到小**，**至多 {TRIM_LARGEST_DURATION_COUNT} 条**）自动剔除极值后，稳健统计样本 **{tr.get('count', 0)}** 条（无需用户配置）。"
    )
    if focus.get("skipped_rows_without_duration"):
        lines.append(
            f"- 另有 **{focus.get('skipped_rows_without_duration')}** 行缺少有效 Duration，未参与分布与剔除逻辑。"
        )

    if k > 0 and d_raw_mean and d_tr_mean:
        drop = float(d_raw_mean) - float(d_tr_mean)
        pct = 100.0 * drop / float(d_raw_mean) if float(d_raw_mean) != 0 else 0.0
        lines.append(
            f"- **耗时中心**：全样本平均 Task Duration 约 **{d_raw_mean:.3f} us**；去掉极端大值后平均约 **{d_tr_mean:.3f} us**（均值变化约 **{pct:.2f}%**）。"
        )
        if pct > 8:
            lines.append(
                "  - 解读：少数极大耗时对**算术平均**牵引明显；请**以 trimmed 的 mean / p50 为主**描述「典型」耗时，全样本均值仅作对照。"
            )
        elif pct <= 3:
            lines.append("  - 解读：极端大值对均值影响较小，全样本与 trimmed 指标大体一致。")

    if w_raw_mean is not None and d_raw_mean:
        ratio = float(w_raw_mean) / float(d_raw_mean) if float(d_raw_mean) != 0 else None
        if ratio is not None:
            lines.append(
                f"- **等待 vs 执行（粗看）**：全样本平均 Wait / 平均 Duration ≈ **{ratio:.4f}**。"
            )
            if ratio > 0.15:
                lines.append(
                    "  - 解读：等待在单笔耗时中占比偏高，可能与 **调度、流间依赖、同步或通信空泡** 有关；需要根因时可走 **Skill 3（Chrome trace）**。"
                )
            elif ratio < 0.03:
                lines.append("  - 解读：等待占比很低，瓶颈更可能在 **算子内核或算力利用**。")

    if cv_tr is not None:
        lines.append(f"- **离散程度（trimmed Duration）**：变异系数 CV ≈ **{cv_tr:.3f}**。")
        if cv_tr > 0.2:
            lines.append(
                "  - 解读：单次调用间耗时波动较大，常见于 **形状/负载变化或偶发排队**；对比实验请固定 case，并参考 p50/p95。"
            )
        elif cv_tr < 0.08:
            lines.append("  - 解读：耗时较集中，优化效果在统计上较容易稳定复现。")

    if cu_tr is not None:
        lines.append(f"- **Cube 利用（trimmed 子集均值）**：约 **{cu_tr:.2f}%**。")
        if cu_tr < 40:
            lines.append(
                "  - 解读：Cube 利用率偏低时，可优先排查 **tiling、MTE/搬移、非 matmul 路径** 等与算子形态的匹配度。"
            )
        elif cu_tr > 70:
            lines.append(
                "  - 解读：Cube 利用率较高时，进一步收益可能来自 **访存、并行度、或与其他阶段的重叠**。"
            )

    return "\n".join(lines)


def format_stats_table_md(focus: dict[str, Any]) -> str:
    """Markdown tables: raw vs trimmed for duration / wait / cube."""

    def num(v: Any) -> str:
        if v is None:
            return "—"
        try:
            return f"{float(v):.3f}"
        except (TypeError, ValueError):
            return "—"

    def row_metric(title: str, raw_key: str, trim_key: str) -> str:
        ra = focus.get(raw_key) or {}
        trm = focus.get(trim_key) or {}
        return (
            "| {t} | {c1} | {mn1} | {p501} | {p951} | {c2} | {mn2} | {p502} | {p952} |".format(
                t=title,
                c1=ra.get("count", 0),
                mn1=num(ra.get("mean")),
                p501=num(ra.get("p50")),
                p951=num(ra.get("p95")),
                c2=trm.get("count", 0),
                mn2=num(trm.get("mean")),
                p502=num(trm.get("p50")),
                p952=num(trm.get("p95")),
            )
        )

    lines: list[str] = []
    lines.append("### 单算子统计表（全样本 vs 去极端值后）")
    lines.append("")
    lines.append(
        f"*「去极端值」列：对本算子**自动**去掉 **Task Duration 最大的 {TRIM_LARGEST_DURATION_COUNT} 条**样本后再统计（总数不足时会少剔，且始终至少保留 1 条有效 Duration 样本）。*"
    )
    lines.append("")
    lines.append(
        "| 指标 | 全样本 n | mean | p50 | p95 | trimmed n | mean | p50 | p95 |"
    )
    lines.append("|---|--:|---:|---:|---:|--:|---:|---:|---:|")
    lines.append(row_metric("Task Duration (us)", "duration_raw", "duration_trimmed"))
    lines.append(row_metric("Task Wait (us)", "wait_raw", "wait_trimmed"))
    lines.append(row_metric("cube_util (%)", "cube_raw", "cube_trimmed"))
    lines.append("")
    if focus.get("removed_task_duration_us"):
        rem = focus["removed_task_duration_us"]
        lines.append(f"**自动剔除的 Task Duration 极大值（us）**（至多 {len(rem)} 个）: `{rem}`")
        lines.append("")
    return "\n".join(lines)
