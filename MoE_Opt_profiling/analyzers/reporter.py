from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Any


def ensure_dir(path: str | Path) -> None:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)


def write_json(path: str | Path, data: Any) -> None:
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_csv(path: str | Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    ensure_dir(Path(path).parent)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: "" if r.get(k) is None else r[k] for k in fieldnames})


def chart_gallery_markdown(embeds: list[tuple[str, str]]) -> str:
    if not embeds:
        return ""
    lines: list[str] = ["## Charts", ""]
    for fn, cap in embeds:
        lines.append(f"### {cap}")
        lines.append(f"![{cap}]({fn})")
        lines.append("")
    return "\n".join(lines)


def build_markdown_single(
    input_path: str,
    overview: dict[str, Any],
    summaries: list[dict[str, Any]],
    *,
    group_key: str,
    top_n: int,
    filtered: bool,
    chart_gallery: list[tuple[str, str]] | None = None,
    charts_skipped: bool = False,
) -> str:
    lines: list[str] = []
    lines.append("# op_summary profiling report")
    lines.append("")
    lines.append(f"- **Input**: `{input_path}`")
    lines.append(f"- **Rows**: {overview.get('row_count', 0)}")
    lines.append(f"- **Group by**: `{group_key}`")
    if filtered:
        lines.append("- **Note**: filters applied (see CLI args)")
    lines.append("")
    lines.append("## Overview")
    lines.append("")
    lines.append(f"- Unique OP Types: **{overview.get('unique_op_types', 0)}**")
    lines.append(f"- Unique Task Types: **{overview.get('unique_task_types', 0)}**")
    lines.append(f"- Total Task Duration (us): **{overview.get('total_task_duration_us', 0.0):.3f}**")
    lines.append(f"- Total Task Wait (us): **{overview.get('total_task_wait_us', 0.0):.3f}**")
    lines.append("")
    lines.append(f"## Top {top_n} groups by total Task Duration")
    lines.append("")
    lines.append("| group | op_count | sum dur (us) | mean dur (us) | p50 | p95 | sum wait (us) |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for s in summaries[:top_n]:
        lines.append(
            "| {gk} | {oc} | {sd:.3f} | {md} | {p50} | {p95} | {sw} |".format(
                gk=s.get("group_key", ""),
                oc=s.get("op_count", 0),
                sd=float(s.get("task_duration_us_sum") or 0.0),
                md=fmt_opt(s.get("task_duration_us_mean")),
                p50=fmt_opt(s.get("task_duration_us_p50")),
                p95=fmt_opt(s.get("task_duration_us_p95")),
                sw=fmt_opt(s.get("task_wait_us_sum")),
            )
        )
    lines.append("")
    if charts_skipped:
        lines.append("## Charts")
        lines.append("")
        lines.append("_未生成图（使用了 `--no-charts`）。_")
        lines.append("")
    else:
        block = chart_gallery_markdown(chart_gallery or [])
        if block:
            lines.append(block)
    return "\n".join(lines)


def fmt_opt(x: Any) -> str:
    if x is None:
        return ""
    if isinstance(x, float):
        return f"{x:.3f}"
    return str(x)


def build_markdown_compare(
    baseline_path: str,
    candidate_path: str,
    compare_rows: list[dict[str, Any]],
    *,
    top_n: int,
    chart_gallery: list[tuple[str, str]] | None = None,
    charts_skipped: bool = False,
) -> str:
    lines: list[str] = []
    lines.append("# op_summary baseline vs candidate")
    lines.append("")
    lines.append(f"- **Baseline**: `{baseline_path}`")
    lines.append(f"- **Candidate**: `{candidate_path}`")
    lines.append("")
    lines.append(f"## Largest |Δ| sum(Task Duration) (top {top_n})")
    lines.append("")
    lines.append("| OP Type | base cnt | cand cnt | base sum dur | cand sum dur | Δ sum | Δ % |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for r in compare_rows[:top_n]:
        lines.append(
            "| {t} | {bc} | {cc} | {bs} | {cs} | {d} | {dp} |".format(
                t=r.get("group_key", ""),
                bc=r.get("baseline_op_count"),
                cc=r.get("candidate_op_count"),
                bs=fmt_opt(r.get("baseline_task_duration_us_sum")),
                cs=fmt_opt(r.get("candidate_task_duration_us_sum")),
                d=fmt_opt(r.get("delta_task_duration_us_sum")),
                dp=fmt_opt(r.get("delta_task_duration_pct_vs_baseline")),
            )
        )
    lines.append("")
    if charts_skipped:
        lines.append("## Charts")
        lines.append("")
        lines.append("_未生成图（使用了 `--no-charts`）。_")
        lines.append("")
    else:
        block = chart_gallery_markdown(chart_gallery or [])
        if block:
            lines.append(block)
        else:
            lines.append("## Charts")
            lines.append("")
            lines.append(
                "_未生成对比图（通常未安装 matplotlib）。可 `pip install matplotlib` 后重跑。_"
            )
            lines.append("")
    return "\n".join(lines)
