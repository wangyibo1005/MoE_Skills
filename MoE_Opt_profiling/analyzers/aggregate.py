from __future__ import annotations

import math
import statistics
from typing import Any, Callable


def _isfinite(x: float | None) -> bool:
    return x is not None and not math.isnan(x) and math.isfinite(x)


def _percentile_nearest_sorted(sorted_vals: list[float], p: float) -> float | None:
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (len(sorted_vals) - 1) * (p / 100.0)
    lo = int(math.floor(k))
    hi = int(math.ceil(k))
    if lo == hi:
        return sorted_vals[lo]
    return sorted_vals[lo] + (k - lo) * (sorted_vals[hi] - sorted_vals[lo])


def filter_rows(
    rows: list[dict[str, Any]],
    *,
    device_id: int | None = None,
    op_type: str | None = None,
    op_type_contains: str | None = None,
    task_type: str | None = None,
    op_name_contains: str | None = None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in rows:
        if device_id is not None:
            if r.get("Device_id") != device_id:
                continue
        ot = r.get("OP Type")
        if op_type and (ot is None or str(ot) != op_type):
            continue
        if op_type_contains and (
            ot is None or op_type_contains.lower() not in str(ot).lower()
        ):
            continue
        tt = r.get("Task Type")
        if task_type and (tt is None or str(tt) != task_type):
            continue
        on = r.get("Op Name")
        if op_name_contains and (on is None or op_name_contains not in str(on)):
            continue
        out.append(r)
    return out


def aggregate_by(
    rows: list[dict[str, Any]],
    key: str,
    duration_col: str = "Task Duration(us)",
    wait_col: str = "Task Wait Time(us)",
    aicore_col: str = "aicore_time(us)",
    aiv_col: str = "aiv_time(us)",
    cube_col: str = "cube_utilization(%)",
) -> list[dict[str, Any]]:
    """Group rows by `key` column; compute counts and duration / wait stats."""
    groups: dict[Any, list[dict[str, Any]]] = {}
    for r in rows:
        gk = r.get(key)
        if gk is None or (isinstance(gk, float) and math.isnan(gk)):
            gk = "__missing__"
        groups.setdefault(gk, []).append(r)

    summaries: list[dict[str, Any]] = []
    for gk, gr in groups.items():
        durs = [float(x) for x in (_row_float(r, duration_col) for r in gr) if _isfinite(x)]
        waits = [float(x) for x in (_row_float(r, wait_col) for r in gr) if _isfinite(x)]
        aic = [float(x) for x in (_row_float(r, aicore_col) for r in gr) if _isfinite(x)]
        aiv = [float(x) for x in (_row_float(r, aiv_col) for r in gr) if _isfinite(x)]
        cube = [float(x) for x in (_row_float(r, cube_col) for r in gr) if _isfinite(x)]

        def pack(name: str, xs: list[float]) -> dict[str, float | None]:
            if not xs:
                return {
                    f"{name}_count": 0,
                    f"{name}_sum": None,
                    f"{name}_mean": None,
                    f"{name}_p50": None,
                    f"{name}_p95": None,
                }
            s = sorted(xs)
            return {
                f"{name}_count": len(xs),
                f"{name}_sum": float(sum(xs)),
                f"{name}_mean": float(statistics.mean(xs)),
                f"{name}_p50": _percentile_nearest_sorted(s, 50),
                f"{name}_p95": _percentile_nearest_sorted(s, 95),
            }

        row: dict[str, Any] = {
            "group_key": str(gk),
            "op_count": len(gr),
        }
        row.update(pack("task_duration_us", durs))
        row.update(pack("task_wait_us", waits))
        if aic:
            row.update(pack("aicore_us", aic))
        if aiv:
            row.update(pack("aiv_us", aiv))
        if cube:
            row.update(pack("cube_util_pct", cube))
        summaries.append(row)

    summaries.sort(key=lambda x: x.get("task_duration_us_sum") or 0.0, reverse=True)
    return summaries


def _row_float(r: dict[str, Any], col: str) -> float | None:
    v = r.get(col)
    if v is None:
        return None
    if isinstance(v, (int, float)):
        x = float(v)
        return x if _isfinite(x) else None
    return None


def overview(rows: list[dict[str, Any]]) -> dict[str, Any]:
    durs = [float(x) for x in (_row_float(r, "Task Duration(us)") for r in rows) if _isfinite(x)]
    waits = [float(x) for x in (_row_float(r, "Task Wait Time(us)") for r in rows) if _isfinite(x)]
    types = {str(r.get("OP Type")) for r in rows if r.get("OP Type") is not None}
    task_types = {str(r.get("Task Type")) for r in rows if r.get("Task Type") is not None}
    devices = {r.get("Device_id") for r in rows if r.get("Device_id") is not None}
    return {
        "row_count": len(rows),
        "unique_op_types": len(types),
        "unique_task_types": len(task_types),
        "device_ids": sorted(devices),
        "total_task_duration_us": float(sum(durs)) if durs else 0.0,
        "total_task_wait_us": float(sum(waits)) if waits else 0.0,
    }
