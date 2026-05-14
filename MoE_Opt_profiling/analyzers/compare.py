from __future__ import annotations

from typing import Any


def compare_summaries(
    baseline: list[dict[str, Any]],
    candidate: list[dict[str, Any]],
    *,
    key_field: str = "group_key",
) -> list[dict[str, Any]]:
    def by_key(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        return {r[key_field]: r for r in rows}

    b = by_key(baseline)
    c = by_key(candidate)
    keys = sorted(set(b) | set(c))
    out: list[dict[str, Any]] = []
    for k in keys:
        br = b.get(k)
        cr = c.get(k)
        b_sum = (br or {}).get("task_duration_us_sum")
        c_sum = (cr or {}).get("task_duration_us_sum")
        b_cnt = (br or {}).get("op_count") or 0
        c_cnt = (cr or {}).get("op_count") or 0
        delta = None
        delta_pct = None
        if b_sum is not None and c_sum is not None:
            delta = float(c_sum) - float(b_sum)
            if float(b_sum) != 0.0:
                delta_pct = 100.0 * delta / float(b_sum)
        out.append(
            {
                key_field: k,
                "baseline_op_count": b_cnt,
                "candidate_op_count": c_cnt,
                "baseline_task_duration_us_sum": b_sum,
                "candidate_task_duration_us_sum": c_sum,
                "delta_task_duration_us_sum": delta,
                "delta_task_duration_pct_vs_baseline": delta_pct,
            }
        )
    out.sort(key=lambda r: abs(r.get("delta_task_duration_us_sum") or 0.0), reverse=True)
    return out
