#!/usr/bin/env python3
"""Skill 4 closure: profiling + trace + candidate meta -> experiment_report, YAML, JSONL."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(path: Path | None) -> Any:
    if path is None or not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def load_text(path: Path | None, limit: int = 12000) -> str:
    if path is None or not path.is_file():
        return ""
    t = path.read_text(encoding="utf-8", errors="replace")
    if len(t) > limit:
        return t[:limit] + "\n\n… [truncated]\n"
    return t


def copy_if(src: Path | None, dst: Path) -> bool:
    if src is None or not src.is_file():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return True


def yn_existing(p: Path) -> str:
    return "yes" if p.is_file() else "no"


def yaml_quote(s: str) -> str:
    s = str(s)
    if s == "":
        return '""'
    if re.search(r"[\n:\"]", s):
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'
    return s


def write_metadata_yaml(path: Path, blob: dict[str, Any]) -> None:
    lines = [
        "# Auto-generated experiment metadata\n",
        f"generated_at: {yaml_quote(utc_now_iso())}\n",
        f"experiment_id: {yaml_quote(str(blob.get('experiment_id','')))}\n",
        "\nversions_json: |\n",
        json.dumps(blob.get("versions") or {}, indent=2, ensure_ascii=False),
        "\n\nrun_config_json: |\n",
        json.dumps(blob.get("run_config") or {}, indent=2, ensure_ascii=False),
        "\n\ndecision_rules_json: |\n",
        json.dumps(blob.get("decision_rules") or {}, indent=2, ensure_ascii=False),
        "\n",
    ]
    path.write_text("".join(lines), encoding="utf-8")


def write_decision_yaml(path: Path, body: dict[str, Any]) -> None:
    lines = ["# Auto-generated — edit after human review\n", f"generated_at: {yaml_quote(utc_now_iso())}\n"]
    for k, v in body.items():
        ks = str(k)
        if isinstance(v, bool):
            lines.append(f"{ks}: {str(v).lower()}\n")
        elif v is None:
            lines.append(f"{ks}: null\n")
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            lines.append(f"{ks}: {v}\n")
        elif isinstance(v, (dict, list)):
            lines.append(f'{ks}: {yaml_quote(json.dumps(v, ensure_ascii=False))}\n')
        else:
            lines.append(f"{ks}: {yaml_quote(str(v))}\n")
    path.write_text("".join(lines), encoding="utf-8")


def suggest_final_decision(
    *,
    hint_v: str | None,
    delta_pct: float | None,
    rules: dict[str, Any],
    has_trace_report: bool,
    missing_critical_prof: bool,
) -> tuple[str, str]:
    ov = rules.get("final_decision_override")
    if ov in ("accept", "continue", "reject", "failed"):
        return ov, "final_decision_override from manifest"

    if missing_critical_prof:
        return "failed", "missing profile_summary.json (Skill 1 required)"

    hint_v = (hint_v or "").strip()

    if hint_v == "need_trace_analysis":
        if req_trace and not has_trace_report:
            return (
                "continue",
                "need_trace_analysis: complete candidate_trace + Skill 3 before closing perf story",
            )
        return ("continue", "need_trace_analysis: review trace evidence and iterate candidate_clean")

    imp_thr = rules.get("performance_improve_pct_max_for_accept_hint")
    reg_thr = rules.get("performance_regress_pct_min_for_reject_hint")

    if hint_v == "regressed":
        return "reject", "profiling_hint regressed"

    if hint_v == "improved":
        if imp_thr is not None and delta_pct is not None:
            try:
                if float(delta_pct) <= float(imp_thr):
                    return "accept", f"hint improved and total Δ%<={imp_thr}"
            except (TypeError, ValueError):
                pass
        return "accept", "profiling_hint improved"

    if hint_v == "neutral":
        if reg_thr is not None and delta_pct is not None:
            try:
                if float(delta_pct) >= float(reg_thr):
                    return "reject", f"hint neutral but total Δ%>={reg_thr}"
            except (TypeError, ValueError):
                pass
        return "continue", "profiling_hint neutral"

    return "continue", "conservative default (unknown or empty prof hint)"


def build(ns: argparse.Namespace) -> int:
    man_path = Path(ns.manifest).expanduser().resolve()
    if not man_path.is_file():
        print(f"Manifest not found: {man_path}", file=sys.stderr)
        return 1

    blob = json.loads(man_path.read_text(encoding="utf-8"))
    exp_id = str(blob.get("experiment_id") or "unnamed_experiment")

    exp_root = Path(ns.experiment_dir).expanduser().resolve()
    exp_dir = exp_root / exp_id
    rep_dir = exp_dir / "report"
    rep_dir.mkdir(parents=True, exist_ok=True)

    s1 = blob.get("skill1_profiling") or {}
    s3 = blob.get("skill3_trace") or {}
    cand = blob.get("candidate_change") or {}

    ps = Path(s1["profile_summary_json"]).expanduser() if s1.get("profile_summary_json") else None
    pc = Path(s1["profile_compare_json"]).expanduser() if s1.get("profile_compare_json") else None
    pr_md = Path(s1["profiling_report_md"]).expanduser() if s1.get("profiling_report_md") else None
    ph_path = Path(s1["performance_decision_hint_json"]).expanduser() if s1.get(
        "performance_decision_hint_json"
    ) else None

    ta = Path(s3["trace_analysis_json"]).expanduser() if s3.get("trace_analysis_json") else None
    bn = Path(s3["bottleneck_explanation_json"]).expanduser() if s3.get(
        "bottleneck_explanation_json"
    ) else None
    tr_md = Path(s3["trace_report_md"]).expanduser() if s3.get("trace_report_md") else None
    oc_md = Path(s3["optimization_clues_md"]).expanduser() if s3.get(
        "optimization_clues_md"
    ) else None

    if s3.get("trace_output_dir_optional"):
        tp = Path(s3["trace_output_dir_optional"]).expanduser().resolve()
        if tp.is_dir():
            if ta is None or not ta.is_file():
                cand_ta = tp / "summary.json"
                ta = cand_ta if cand_ta.is_file() else ta
            if bn is None or not bn.is_file():
                cand_bn = tp / "diagnosis.json"
                bn = cand_bn if cand_bn.is_file() else bn
            if tr_md is None or not tr_md.is_file():
                cand_tr = tp / "report.md"
                tr_md = cand_tr if cand_tr.is_file() else tr_md
            if oc_md is None or not oc_md.is_file():
                cand_oc = tp / "statistical_summary.md"
                oc_md = cand_oc if cand_oc.is_file() else oc_md

    patch = Path(cand["patch_diff"]).expanduser() if cand.get("patch_diff") else None
    chg_txt = Path(cand["changed_files_txt"]).expanduser() if cand.get("changed_files_txt") else None
    chg_md = Path(cand["change_summary_md"]).expanduser() if cand.get("change_summary_md") else None
    intent = str(cand.get("intent_markdown") or "")

    missing_prof = ps is None or not ps.is_file()

    pj = load_json(ps if ps else None)
    delta_pct = None
    if isinstance(pj, dict):
        totals = pj.get("totals")
        if isinstance(totals, dict) and totals.get("delta_pct_vs_baseline") is not None:
            try:
                delta_pct = float(totals["delta_pct_vs_baseline"])
            except (TypeError, ValueError):
                delta_pct = None

    hj = load_json(ph_path if ph_path else None)
    hint_v: str | None = None
    if isinstance(hj, dict):
        hint_v = hj.get("performance_decision_hint")
        det = hj.get("detail")
        if isinstance(det, dict) and det.get("verdict"):
            hint_v = det["verdict"]

    rules = blob.get("decision_rules") or {}
    if not isinstance(rules, dict):
        rules = {}

    has_trace = tr_md is not None and tr_md.is_file()

    decision, decision_rationale = suggest_final_decision(
        hint_v=str(hint_v) if hint_v else None,
        delta_pct=delta_pct,
        rules=rules,
        has_trace_report=has_trace,
        missing_critical_prof=missing_prof,
    )

    copy_if(pc, exp_dir / "profile_compare.json")
    copy_if(ps, exp_dir / "profile_summary.json")
    copy_if(patch, exp_dir / "patch.diff")

    if ta is not None and ta.is_file():
        shutil.copy2(ta, exp_dir / "trace_analysis.json")
    if bn is not None and bn.is_file():
        shutil.copy2(bn, exp_dir / "bottleneck_explanation.json")

    copy_if(pr_md, rep_dir / "profiling_report.md")
    copy_if(tr_md, rep_dir / "trace_report.md")
    copy_if(oc_md, rep_dir / "optimization_clues.md")
    copy_if(chg_md, exp_dir / "change_summary.md")
    copy_if(chg_txt, exp_dir / "changed_files.txt")

    meta_blob = {
        "experiment_id": exp_id,
        "versions": blob.get("versions"),
        "run_config": blob.get("run_config"),
        "decision_rules": blob.get("decision_rules"),
    }
    write_metadata_yaml(exp_dir / "metadata.yaml", meta_blob)

    top_gain = ""
    top_loss = ""
    pf_imp = pj.get("key_kernels_task_duration_us_sum") if isinstance(pj, dict) else None
    if isinstance(pf_imp, list):
        gains = sorted(
            [x for x in pf_imp if isinstance(x, dict) and (x.get("delta_pct_vs_baseline") or 0) < 0],
            key=lambda x: float(x.get("delta_pct_vs_baseline") or 0),
        )
        losses = sorted(
            [x for x in pf_imp if isinstance(x, dict) and (x.get("delta_pct_vs_baseline") or 0) > 0],
            key=lambda x: float(x.get("delta_pct_vs_baseline") or 0),
            reverse=True,
        )
        if gains:
            g0 = gains[0]
            top_gain = f"{g0.get('group_key')}: Δ% {g0.get('delta_pct_vs_baseline')}"
        if losses:
            l0 = losses[0]
            top_loss = f"{l0.get('group_key')}: Δ% {l0.get('delta_pct_vs_baseline')}"

    bottleneck_one_liner = ""
    bd = load_json(bn if bn else None)
    if isinstance(bd, dict):
        bottleneck_one_liner = (
            str(bd.get("summary") or bd.get("headline") or "")
            or json.dumps(bd, ensure_ascii=False)[:800]
        )

    risk_level = "high" if hint_v == "need_trace_analysis" else ("medium" if missing_prof else "low")
    propose_baseline = decision == "accept" and hint_v == "improved"

    ta_dst = exp_dir / "trace_analysis.json"
    be_dst = exp_dir / "bottleneck_explanation.json"

    decision_body = {
        "decision": decision,
        "decision_rationale_auto": decision_rationale,
        "performance_delta_pct_vs_baseline": delta_pct,
        "profiling_decision_hint": hint_v,
        "major_gain_hint": top_gain,
        "major_regress_hint": top_loss,
        "attribution_note": bottleneck_one_liner[:2000] if bottleneck_one_liner else "",
        "risk_level": risk_level,
        "suggest_promote_candidate_as_new_baseline": propose_baseline,
        "artifacts_presence": {
            "profile_summary": yn_existing(exp_dir / "profile_summary.json"),
            "profile_compare": yn_existing(exp_dir / "profile_compare.json"),
            "trace_analysis": yn_existing(ta_dst),
            "bottleneck_explanation": yn_existing(be_dst),
            "trace_report_md": yn_existing(rep_dir / "trace_report.md"),
        },
    }
    write_decision_yaml(exp_dir / "decision.yaml", decision_body)

    experiment_report_md = "".join(
        [
            f"# Experiment report — {exp_id}\n\n",
            f"- **generated_at**: `{utc_now_iso()}`\n",
            f"- **decision.auto**: **`{decision}`** — {decision_rationale}\n\n",
            "## Versions (baseline_clean / candidate_clean / candidate_trace)\n\n",
            f"```json\n{json.dumps(blob.get('versions') or {}, indent=2, ensure_ascii=False)}\n```\n\n",
            "## Run configuration\n\n",
            f"```json\n{json.dumps(blob.get('run_config') or {}, indent=2, ensure_ascii=False)}\n```\n\n",
            "## Candidate modification intent\n\n",
            intent + "\n\n",
            "## Profiling (Skill 1)\n\n",
            f"- `performance_decision_hint`: **`{hint_v}`**\n",
            f"- total Duration Δ% vs baseline: **`{delta_pct}`**\n",
            "\n```text\n",
            load_text(pr_md, 8000),
            "\n```\n\n",
            "## Trace attribution (Skill 3)\n\n",
            "```text\n",
            load_text(tr_md, 8000),
            "\n```\n\n",
            "## Optimization clues\n\n",
            "```text\n",
            load_text(oc_md, 6000),
            "\n```\n\n",
            "## Risks\n\n",
            f"- auto risk tier: **{risk_level}**\n",
            "- verify **baseline_clean / candidate_clean / candidate_trace** labels before causal language.\n\n",
            "## Final judgment (automated scaffold)\n\n",
            f"- **decision**: **`{decision}`**\n",
            f"- **suggest promote candidate as new baseline**: **{propose_baseline}**\n",
        ]
    )
    (exp_dir / "experiment_report.md").write_text(experiment_report_md, encoding="utf-8")

    next_md = "".join(
        [
            f"# next_action — {exp_id}\n\n",
            "Drives manual **candidate_clean** in the next iteration; Skill 4 does **not** edit code.\n\n",
            f"- Profiling hint: `{hint_v}`; bundle decision: `{decision}`.\n\n",
        ]
    )
    if decision == "continue":
        next_md += (
            "- Tighten design on regressing aggregates (profile_compare.json) "
            + "or hotspots in bottleneck_explanation.json.\n"
            "- Re-profile **baseline_clean / candidate_clean** after changes.\n"
        )
        if hint_v == "need_trace_analysis":
            next_md += "- Complete **candidate_trace** + **MoE_Opt_trace_analysis** if attribution is incomplete.\n"
    elif decision == "accept":
        next_md += "- Promote/tag candidate; baseline the winning commit for subsequent work.\n"
    elif decision == "reject":
        next_md += "- Roll back candidate or abandon branch; rethink from profiling deltas.\n"
    else:
        next_md += "- Repair broken runs or absent artifacts; rerun Skill 1 profiling compare.\n"
    next_md += "\n## Case sweep\n\n- Re-run matrices described in metadata `run_config_json`.\n"
    next_md += "\n## MoE_Opt_auto_trace（auto_trace）\n\n- 仅在 **candidate_trace** 上启用；当阶段级归因仍不足时使用。\n"
    next_md += "\n## Rollback\n\n- If decision is reject or failed: prefer revert to baseline_clean commit in versions.\n"
    (exp_dir / "next_action.md").write_text(next_md, encoding="utf-8")

    sug = (
        f"# candidate_change_suggestion — {exp_id}\n\n"
        "Natural-language steering for engineers; **not** a generated patch.\n\n"
    )
    if top_loss:
        sug += f"- Probable pain point (aggregate regress): **{top_loss}**.\n"
    if bottleneck_one_liner:
        sug += "- Diagnosis pointer: {}\n".format(bottleneck_one_liner[:800])
    sug += "- Review archived `patch.diff` / `changed_files.txt` in this experiment directory.\n"
    sug += "- Cross-check bottleneck phases vs kernel focus from Skill 3 outputs.\n"
    sug += "- Validation: rerun the same profiling + trace harness after edits.\n"
    (exp_dir / "candidate_change_suggestion.md").write_text(sug, encoding="utf-8")

    idx_path = Path(ns.evolution_index).expanduser().resolve()
    idx_path.parent.mkdir(parents=True, exist_ok=True)
    rec = {
        "ts": utc_now_iso(),
        "experiment_id": exp_id,
        "decision": decision,
        "delta_pct_vs_baseline": delta_pct,
        "prof_hint": hint_v,
        "experiment_dir": str(exp_dir),
    }
    with idx_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"Experiment dir: {exp_dir}")
    print(f"Appended: {idx_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="MoE Skill 4 — experiment closure bundle.")
    ap.add_argument("--manifest", required=True)
    ap.add_argument(
        "--experiment-dir",
        required=True,
        help="Root directory (creates <experiment-id>/ subtree)",
    )
    ap.add_argument(
        "--evolution-index",
        default="./evolution_index.jsonl",
        help="Append one JSON record per closure run",
    )
    return build(ap.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
