"""Load profiling compare manifest JSON (baseline/candidate/run/parse meta)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def load_manifest_json(path: str | Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        raise FileNotFoundError(f"Manifest not found: {p}")
    data = json.loads(p.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def phase_for_group(group_key: str, rules: list[dict[str, Any]] | None) -> str:
    """Longest-pattern-wins regex phase mapping on group label (e.g. OP Type string)."""
    if not rules:
        return "_unmapped"
    gk = str(group_key)
    best_phase = "_unmapped"
    best_pat_len = -1
    for rule in rules:
        pat = str(rule.get("pattern", ""))
        ph = str(rule.get("phase", "_unmapped"))
        try:
            if pat and re.search(pat, gk):
                lp = len(pat)
                if lp > best_pat_len:
                    best_pat_len = lp
                    best_phase = ph
        except re.error:
            continue
    return best_phase


def decision_thresholds(manifest: dict[str, Any]) -> dict[str, float]:
    dh = manifest.get("decision_hints") or {}
    if not isinstance(dh, dict):
        dh = {}
    return {
        "neutral_band_pct": float(dh.get("neutral_band_pct", 2.0)),
        "heavy_phase_pct": float(dh.get("heavy_phase_pct", 15.0)),
        "overall_trace_trigger_pct": float(dh.get("overall_trace_trigger_pct", 10.0)),
    }
