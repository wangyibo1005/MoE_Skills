from __future__ import annotations

import argparse
import sys
from pathlib import Path

from analyzers.aggregate import aggregate_by, filter_rows, overview
from analyzers.compare import compare_summaries
from analyzers.profiling_compare_bundle import build_compare_bundle, render_profiling_report_md
from analyzers.loader import load_op_summary_csv
from analyzers.reporter import (
    build_markdown_compare,
    build_markdown_single,
    ensure_dir,
    write_csv,
    write_json,
)
from analyzers.viz import (
    try_plot_compare_delta_bar,
    try_plot_operator_duration_scatter,
)


def default_out_dir_single(csv_path: Path) -> Path:
    """Same directory as CSV: ``<stem>_op_summary_out``."""
    return csv_path.parent / f"{csv_path.stem}_op_summary_out"


def default_out_dir_compare(baseline_path: Path, candidate_path: Path) -> Path:
    """Beside baseline CSV: ``<baseline_stem>_vs_<candidate_stem>_op_summary_out``."""
    return baseline_path.parent / f"{baseline_path.stem}_vs_{candidate_path.stem}_op_summary_out"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Analyze Ascend msprof op_summary_*.csv: aggregate, compare, visualize.",
    )
    p.add_argument(
        "--input",
        "-i",
        default=None,
        help="Path to op_summary_*.csv (single-file mode)",
    )
    p.add_argument(
        "--baseline",
        default=None,
        help="Baseline op_summary CSV (compare mode)",
    )
    p.add_argument(
        "--candidate",
        default=None,
        help="Candidate op_summary CSV (compare mode)",
    )
    p.add_argument(
        "--output-dir",
        "-o",
        default=None,
        help="Output directory (default: beside input CSV — <name>_op_summary_out; compare: beside baseline — <base>_vs_<cand>_op_summary_out)",
    )
    p.add_argument(
        "--group-by",
        default="OP Type",
        help="Column to aggregate on (default: OP Type). Examples: 'Task Type', 'Op Name'.",
    )
    p.add_argument(
        "--device-id",
        type=int,
        default=None,
        help="Filter rows to this Device_id",
    )
    p.add_argument(
        "--op-type",
        default=None,
        help="Exact match filter on OP Type column",
    )
    p.add_argument(
        "--op-type-contains",
        default=None,
        help="Case-insensitive substring filter on OP Type",
    )
    p.add_argument(
        "--task-type",
        default=None,
        help="Exact match filter on Task Type",
    )
    p.add_argument(
        "--op-name-contains",
        default=None,
        help="Substring filter on Op Name",
    )
    p.add_argument(
        "--top-n",
        type=int,
        default=25,
        help="Rows in markdown tables and default chart depth",
    )
    p.add_argument(
        "--no-charts",
        action="store_true",
        help="Skip matplotlib PNG generation",
    )
    p.add_argument(
        "--manifest",
        default=None,
        help=(
            "Compare mode only: optional JSON manifest "
            "(version_info, run_config, parse_rules.phase_map, decision_hints)."
        ),
    )
    return p.parse_args(argv)


def run_single(args: argparse.Namespace) -> int:
    path = Path(args.input).expanduser().resolve()
    if not path.is_file():
        print(f"Input not found: {path}", file=sys.stderr)
        return 1

    _, rows = load_op_summary_csv(path)
    filt = filter_rows(
        rows,
        device_id=args.device_id,
        op_type=args.op_type,
        op_type_contains=args.op_type_contains,
        task_type=args.task_type,
        op_name_contains=args.op_name_contains,
    )
    ov = overview(filt)
    summaries = aggregate_by(filt, args.group_by)

    if args.output_dir is None:
        out_dir = default_out_dir_single(path).resolve()
    else:
        out_dir = Path(args.output_dir).expanduser().resolve()
    ensure_dir(out_dir)

    summary_payload: dict = {
        "overview": ov,
        "by_group": summaries,
        "meta": {"input": str(path), "group_by": args.group_by},
    }

    focus_payload = None
    if args.op_type and filt:
        from analyzers.operator_analysis import (
            TRIM_LARGEST_DURATION_COUNT,
            compute_operator_focus,
        )

        focus_payload = compute_operator_focus(
            filt,
            op_type=args.op_type,
            trim_top_durations=TRIM_LARGEST_DURATION_COUNT,
        )
        focus_json = {
            k: v
            for k, v in focus_payload.items()
            if k
            not in (
                "durations_all_samples",
                "durations_trimmed_samples",
            )
        }
        summary_payload["operator_focus"] = focus_json
        write_json(out_dir / "operator_focus.json", focus_json)

    write_json(out_dir / "summary.json", summary_payload)

    fieldnames = list(summaries[0].keys()) if summaries else ["group_key"]
    write_csv(out_dir / "by_group.csv", summaries, fieldnames)

    filtered_any = any(
        x is not None
        for x in (
            args.device_id,
            args.op_type,
            args.op_type_contains,
            args.task_type,
            args.op_name_contains,
        )
    )

    scatter_md = ""
    if not args.no_charts:
        if args.op_type and filt and focus_payload is not None:
            from analyzers.operator_analysis import (
                operator_duration_scatter_data,
            )

            xs, ys, hi, used_st = operator_duration_scatter_data(filt)
            sub_cn = (
                "时间列有效：已按 Task Start Time(us) 从早到晚排序后编号"
                if used_st
                else "无有效 Task Start Time：横轴为过滤后的原始行顺序"
            )
            sub_en = (
                "Time valid: sorted by Task Start Time (asc.)"
                if used_st
                else "No valid Task Start Time: index = filtered row order"
            )
            ok_s = try_plot_operator_duration_scatter(
                xs,
                ys,
                hi,
                str(out_dir / "operator_duration_scatter.png"),
                title=f"{args.op_type}: Task Duration per call (scatter)",
                subtitle=sub_en,
            )
            if ok_s:
                scatter_md = (
                    "\n\n### Task Duration 散点图\n\n"
                    "![单算子 Task Duration 散点](operator_duration_scatter.png)\n\n"
                    f"*纵轴：Task Duration (us)；横轴：{sub_cn}；**绿色虚线**为全样本算术平均耗时；**橙色叉**与统计表里「自动剔除」的极大 Duration 样本一致。*\n"
                )
            else:
                print(
                    "Note: scatter plot not generated (matplotlib missing or no data).",
                    file=sys.stderr,
                )

    focus_md_extra = ""
    if args.op_type and filt and focus_payload is not None:
        from analyzers.operator_analysis import format_stats_table_md, narrative_cn

        focus_md_extra = (
            "\n\n## 单算子分析（OP Type）\n\n"
            + format_stats_table_md(focus_payload)
            + scatter_md
            + "\n"
            + narrative_cn(focus_payload)
        )

    md = build_markdown_single(
        str(path),
        ov,
        summaries,
        group_key=args.group_by,
        top_n=args.top_n,
        filtered=filtered_any,
        chart_gallery=[],
        charts_skipped=args.no_charts,
    )
    md += focus_md_extra
    (out_dir / "report.md").write_text(md, encoding="utf-8")

    print("op_summary analysis done.")
    print(f"Rows: {ov.get('row_count', 0)}  Output: {out_dir}")
    return 0


def run_compare(args: argparse.Namespace) -> int:
    bp = Path(args.baseline).expanduser().resolve()
    cp = Path(args.candidate).expanduser().resolve()
    if not bp.is_file() or not cp.is_file():
        print("Baseline or candidate file not found.", file=sys.stderr)
        return 1

    def load_filter(p: Path) -> list:
        _, rows = load_op_summary_csv(p)
        return filter_rows(
            rows,
            device_id=args.device_id,
            op_type=args.op_type,
            op_type_contains=args.op_type_contains,
            task_type=args.task_type,
            op_name_contains=args.op_name_contains,
        )

    br = load_filter(bp)
    cr = load_filter(cp)
    sb = aggregate_by(br, args.group_by)
    sc = aggregate_by(cr, args.group_by)
    cmp_rows = compare_summaries(sb, sc)
    ov_b = overview(br)
    ov_c = overview(cr)

    if args.output_dir is None:
        out_dir = default_out_dir_compare(bp, cp).resolve()
    else:
        out_dir = Path(args.output_dir).expanduser().resolve()
    ensure_dir(out_dir)

    write_json(
        out_dir / "compare_summary.json",
        {
            "meta": {
                "baseline": str(bp),
                "candidate": str(cp),
                "group_by": args.group_by,
                "manifest": str(Path(args.manifest).resolve()) if args.manifest else None,
            },
            "compare": cmp_rows,
        },
    )
    write_csv(
        out_dir / "compare_by_group.csv",
        cmp_rows,
        list(cmp_rows[0].keys()) if cmp_rows else ["group_key"],
    )
    chart_gallery: list[tuple[str, str]] = []
    if not args.no_charts:
        ok = try_plot_compare_delta_bar(
            cmp_rows,
            str(out_dir / "compare_delta_top.png"),
            top_n=args.top_n,
        )
        if ok:
            chart_gallery.append(
                ("compare_delta_top.png", "Baseline vs Candidate：Δ sum(Task Duration)（条形图）")
            )
        else:
            print("Note: matplotlib not available; skipped compare_delta_top.png.", file=sys.stderr)

    md = build_markdown_compare(
        str(bp),
        str(cp),
        cmp_rows,
        top_n=args.top_n,
        chart_gallery=chart_gallery,
        charts_skipped=args.no_charts,
    )
    (out_dir / "report.md").write_text(md, encoding="utf-8")

    ps, pc = build_compare_bundle(
        baseline_path=str(bp),
        candidate_path=str(cp),
        baseline_rows_ov=ov_b,
        candidate_rows_ov=ov_c,
        summaries_b=sb,
        summaries_c=sc,
        cmp_rows=cmp_rows,
        group_by=args.group_by,
        manifest_path=args.manifest,
        top_kernel=args.top_n,
    )
    write_json(out_dir / "profile_summary.json", ps)
    write_json(out_dir / "profile_compare.json", pc)
    hint = ps.get("performance_decision_hint") or {}
    verdict = hint.get("verdict", "neutral")
    write_json(
        out_dir / "performance_decision_hint.json",
        {
            "schema_version": "1.0",
            "performance_decision_hint": verdict,
            "detail": hint,
        },
    )
    pr_md = render_profiling_report_md(
        baseline_path=str(bp),
        candidate_path=str(cp),
        profile_summary=ps,
        profile_compare=pc,
    )
    (out_dir / "profiling_report.md").write_text(pr_md, encoding="utf-8")

    print("Compare done.")
    print(f"Output: {out_dir}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.baseline and args.candidate:
        return run_compare(args)
    if args.input:
        return run_single(args)
    print("Provide --input for single-file mode, or --baseline and --candidate for compare.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
