from __future__ import annotations

import math
import statistics
from typing import Any


def _isfinite(x: float | None) -> bool:
    return x is not None and not math.isnan(x) and math.isfinite(x)


def percentile_sorted(sorted_vals: list[float], p: float) -> float | None:
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


def describe_floats(xs: list[float], label: str) -> dict[str, Any]:
    if not xs:
        return {
            "label": label,
            "count": 0,
            "min": None,
            "max": None,
            "sum": None,
            "mean": None,
            "std": None,
            "p25": None,
            "p50": None,
            "p75": None,
            "p95": None,
            "cv": None,
        }
    s = sorted(xs)
    m = float(statistics.mean(xs))
    st = float(statistics.stdev(xs)) if len(xs) > 1 else 0.0
    cv = (st / m) if m != 0 else None
    return {
        "label": label,
        "count": len(xs),
        "min": s[0],
        "max": s[-1],
        "sum": float(sum(xs)),
        "mean": m,
        "std": st,
        "p25": percentile_sorted(s, 25),
        "p50": percentile_sorted(s, 50),
        "p75": percentile_sorted(s, 75),
        "p95": percentile_sorted(s, 95),
        "cv": cv,
    }
