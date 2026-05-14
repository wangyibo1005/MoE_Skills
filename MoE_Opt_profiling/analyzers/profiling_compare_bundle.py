"""Structured outputs for baseline_clean vs candidate_clean op_summary compares."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from analyzers.profiling_manifest import decision_thresholds, load_manifest_json, phase_for_group


def _safe_pct(candidate: float, baseline: float) -> float | None:
    if baseline == 0.0:
        return None
    return 100.0 * (candidate - baseline) / baseline


def rollup_phase_totals(
    summaries_b: list[dict[str, Any]],
    summaries_c: list[dict[str, Any]],
    *,
    phase_rules: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    b_by = {str(r["group_key"]): r for r in summaries_b}
    c_by = {str(r["group_key"]): r for r in summaries_c}
    keys = sorted(set(b_by) | set(c_by))

    buckets: dict[str, dict[str, float]] = {}
    for k in keys:
        ph = phase_for_group(k, phase_rules)
        bb = buckets.setdefault(ph, {"baseline_us": 0.0, "candidate_us": 0.0})
        bs = float((b_by.get(k) or {}).get("task_duration_us_sum") or 0.0)
        cs = float((c_by.get(k) or {}).get("task_duration_us_sum") or 0.0)
        bb["baseline_us"] += bs
        bb["candidate_us"] += cs

    rows: list[dict[str, Any]] = []
    for ph, v in sorted(buckets.items(), key=lambda x: -(x[1]["baseline_us"] + x[1]["candidate_us"])):
        bu, cu = v["baseline_us"], v["candidate_us"]
        dp = _safe_pct(cu, bu) if bu else None
        rows.append(
            {
                "phase": ph,
                "baseline_task_duration_us_sum": round(bu, 3),
                "candidate_task_duration_us_sum": round(cu, 3),
                "delta_task_duration_us_sum": round(cu - bu, 3),
                "delta_pct_vs_baseline": None if dp is None else round(dp, 4),
            }
        )
    return rows


def key_kernels_top(cmp_rows: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in cmp_rows[:limit]:
        out.append(
            {
                "group_key": r.get("group_key"),
                "baseline_task_duration_us_sum": r.get("baseline_task_duration_us_sum"),
                "candidate_task_duration_us_sum": r.get("candidate_task_duration_us_sum"),
                "delta_task_duration_us_sum": r.get("delta_task_duration_us_sum"),
                "delta_pct_vs_baseline": r.get("delta_task_duration_pct_vs_baseline"),
            }
        )
    return out


def _pick_improve_regress(cmp_rows: list[dict[str, Any]], *, limit: int) -> tuple[list, list]:
    improvements: list[dict[str, Any]] = []
    regressions: list[dict[str, Any]] = []
    for r in cmp_rows:
        d = r.get("delta_task_duration_us_sum")
        if d is None:
            continue
        fd = float(d)
        entry = {
            "group_key": r.get("group_key"),
            "delta_task_duration_us_sum": round(fd, 3),
            "delta_pct_vs_baseline": r.get("delta_task_duration_pct_vs_baseline"),
        }
        if fd < 0:
            improvements.append(entry)
        elif fd > 0:
            regressions.append(entry)
    improvements.sort(key=lambda x: abs(float(x["delta_task_duration_us_sum"])), reverse=True)
    regressions.sort(key=lambda x: abs(float(x["delta_task_duration_us_sum"])), reverse=True)
    return improvements[:limit], regressions[:limit]


def compute_performance_hint(
    overall_pct: float | None,
    phase_rows: list[dict[str, Any]],
    manifest: dict[str, Any],
    cmp_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    th = decision_thresholds(manifest)
    nb = float(th["neutral_band_pct"])
    heavy = float(th["heavy_phase_pct"])

    dh = manifest.get("decision_hints") or {}
    if not isinstance(dh, dict):
        dh = {}
    force_trace = bool(dh.get("force_need_trace_analysis"))
    if force_trace:
        return {
            "verdict": "need_trace_analysis",
            "rationale": "manifest decision_hints.force_need_trace_analysis is true",
        }

    if overall_pct is None or math.isnan(overall_pct):
        return {"verdict": "neutral", "rationale": "overall change ratio undefined (zero baseline total)"}

    if overall_pct <= -nb:
        base = "improved"
    elif overall_pct >= nb:
        base = "regressed"
    else:
        base = "neutral"

    opposing_heavy = False
    for pr in phase_rows:
        dp = pr.get("delta_pct_vs_baseline")
        if dp is None:
            continue
        dpf = float(dp)
        if base == "improved" and dpf >= heavy:
            opposing_heavy = True
        elif base == "regressed" and dpf <= -heavy:
            opposing_heavy = True
        elif base == "neutral" and abs(dpf) >= heavy:
            opposing_heavy = True

    if cmp_rows:
        for r in cmp_rows[: min(40, len(cmp_rows))]:
            dp = r.get("delta_task_duration_pct_vs_baseline")
            if dp is None:
                continue
            dpf = float(dp)
            if base == "improved" and dpf >= heavy:
                opposing_heavy = True
            elif base == "regressed" and dpf <= -heavy:
                opposing_heavy = True

    ambiguous_overall = abs(overall_pct) < nb
    strong_mixed = base in ("improved", "regressed") and opposing_heavy

    if strong_mixed or opposing_heavy or (ambiguous_overall and opposing_heavy):
        return {
            "verdict": "need_trace_analysis",
            "rationale": "heavy opposing phase deltas or mixed signals vs overall; recommend candidate_trace attribution",
            "underlying": base,
            "overall_delta_pct_vs_baseline": overall_pct,
        }

    rationale: list[str] = []
    if base == "improved":
        rationale.append(f"candidate total Task Duration lower than baseline by about {abs(overall_pct):.2f}% (lower wall time).")
    elif base == "regressed":
        rationale.append(f"candidate total Task Duration higher than baseline by about {overall_pct:.2f}%.")
    else:
        rationale.append(f"total Task Duration delta within ±{nb:.1f}% band.")
    return {
        "verdict": base,
        "rationale": " ".join(rationale),
        "overall_delta_pct_vs_baseline": overall_pct,
    }


def build_compare_bundle(
    *,
    baseline_path: str,
    candidate_path: str,
    baseline_rows_ov: dict[str, Any],
    candidate_rows_ov: dict[str, Any],
    summaries_b: list[dict[str, Any]],
    summaries_c: list[dict[str, Any]],
    cmp_rows: list[dict[str, Any]],
    group_by: str,
    manifest_path: str | Path | None,
    top_kernel: int = 25,
    top_phase: int = 32,
    top_delta_list: int = 15,
) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = load_manifest_json(manifest_path) if manifest_path else {}
    prules = manifest.get("parse_rules") or {}
    phase_map = prules.get("phase_map") if isinstance(prules, dict) else None
    if not isinstance(phase_map, list):
        phase_map = []

    b_total = float(baseline_rows_ov.get("total_task_duration_us") or 0.0)
    c_total = float(candidate_rows_ov.get("total_task_duration_us") or 0.0)
    overall_pct = _safe_pct(c_total, b_total) if b_total else None

    phase_rows = rollup_phase_totals(summaries_b, summaries_c, phase_rules=phase_map)
    kern_top = key_kernels_top(cmp_rows, limit=max(top_kernel, len(cmp_rows)))
    impr, reg = _pick_improve_regress(cmp_rows, limit=top_delta_list)

    hint = compute_performance_hint(
        overall_pct if overall_pct is not None else None,
        phase_rows,
        manifest,
        cmp_rows=cmp_rows,
    )

    manifest_path_str = str(Path(manifest_path).resolve()) if manifest_path else None

    profile_summary = {
        "schema_version": "1.0",
        "role": "profile_summary",
        "group_by": group_by,
        "manifest_path": manifest_path_str,
        "manifest_provided": bool(manifest),
        "version_info": manifest.get("version_info") if manifest else {},
        "run_config": manifest.get("run_config") if manifest else {},
        "totals": {
            "baseline_total_task_duration_us": round(b_total, 3),
            "candidate_total_task_duration_us": round(c_total, 3),
            "delta_us": round(c_total - b_total, 3),
            "delta_pct_vs_baseline": None if overall_pct is None else round(overall_pct, 4),
        },
        "key_kernels_task_duration_us_sum": kern_top[:top_kernel],
        "key_phases_task_duration_us_sum": phase_rows[:top_phase],
        "performance_decision_hint": hint,
    }

    primary_points: list[str] = []
    for r in impr[:5]:
        primary_points.append(
            "improved group {}: Δ sum {:.3f} us, Δ% {}".format(
                r["group_key"],
                r["delta_task_duration_us_sum"],
                r.get("delta_pct_vs_baseline"),
            )
        )
    for r in reg[:5]:
        primary_points.append(
            "regressed group {}: Δ sum {:.3f} us, Δ% {}".format(
                r["group_key"],
                r["delta_task_duration_us_sum"],
                r.get("delta_pct_vs_baseline"),
            )
        )

    profile_compare = {
        "schema_version": "1.0",
        "role": "profile_compare",
        "group_by_field": group_by,
        "manifest": manifest if manifest else {},
        "totals": profile_summary["totals"],
        "by_group_top_abs_delta": kern_top[:top_kernel],
        "by_phase_task_duration_us_sum": phase_rows,
        "top_improvements_by_sum_duration_delta": impr,
        "top_regressions_by_sum_duration_delta": reg,
        "primary_performance_change_points": primary_points[:top_delta_list],
        "csv_inputs": {"baseline_csv": baseline_path, "candidate_csv": candidate_path},
        "performance_decision_hint": hint,
    }

    return profile_summary, profile_compare


def render_profiling_report_md(
    *,
    baseline_path: str,
    candidate_path: str,
    profile_summary: dict[str, Any],
    profile_compare: dict[str, Any],
) -> str:
    hint = profile_summary.get("performance_decision_hint") or {}
    verdict = hint.get("verdict", "?")
    rat = hint.get("rationale", "")
    totals = profile_summary.get("totals") or {}

    lines: list[str] = []
    lines.append("# Profiling performance comparison")
    lines.append("")
    lines.append("**Scope:** baseline_clean vs candidate_clean `op_summary` only. Instrumented builds are not valid for these wall-time deltas.")
    lines.append("")
    lines.append(f"- **Baseline CSV**: `{baseline_path}`")
    lines.append(f"- **Candidate CSV**: `{candidate_path}`")
    lines.append("")
    lines.append("## Totals Task Duration sums")
    lines.append("")
    lines.append(f"- **Baseline total**: {totals.get('baseline_total_task_duration_us')} us")
    lines.append(f"- **Candidate total**: {totals.get('candidate_total_task_duration_us')} us")
    lines.append(f"- **Δ us**: {totals.get('delta_us')}")
    lines.append(f"- **Δ % vs baseline**: {totals.get('delta_pct_vs_baseline')}")
    lines.append("")
    lines.append("## Performance decision hint")
    lines.append("")
    lines.append(f"- **verdict**: `{verdict}`")
    lines.append(f"- **rationale**: {rat}")
    if hint.get("underlying"):
        lines.append(f"- **underlying_total_label**: `{hint.get('underlying')}`")
    lines.append("")
    need_trace = verdict == "need_trace_analysis"
    lines.append(
        f"- **Suggested follow-up**: {'**candidate_trace** + trace_analysis for phase-level WHY.**' if need_trace else 'Optional trace only if WHY is needed.'}"
    )
    lines.append("")
    lines.append("## Largest |Δ| by group")
    lines.append("")
    lines.append("| group | Δ sum dur (us) | Δ % |")
    lines.append("|---|---:|---:|")
    for r in profile_compare.get("by_group_top_abs_delta", [])[:15]:
        lines.append(
            "| {gk} | {d} | {dp} |".format(
                gk=r.get("group_key"),
                d=r.get("delta_task_duration_us_sum"),
                dp=r.get("delta_pct_vs_baseline"),
            )
        )
    lines.append("")
    lines.append("## Phase rollups (regex `phase_map` on `group_by` labels; `_unmapped` without match)")
    lines.append("")
    lines.append("| phase | base sum | cand sum | Δ % |")
    lines.append("|---|---:|---:|---:|")
    for pr in profile_compare.get("by_phase_task_duration_us_sum", [])[:20]:
        lines.append(
            "| {ph} | {bu} | {cu} | {dp} |".format(
                ph=pr.get("phase"),
                bu=pr.get("baseline_task_duration_us_sum"),
                cu=pr.get("candidate_task_duration_us_sum"),
                dp=pr.get("delta_pct_vs_baseline"),
            )
        )
    lines.append("")
    lines.append("_See also `profile_summary.json`, `profile_compare.json`, `performance_decision_hint.json`._")
    lines.append("")
    return "\n".join(lines)
