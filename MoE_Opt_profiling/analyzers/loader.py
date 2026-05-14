from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any


def _strip_cell(value: str) -> str:
    return value.replace("\t", "").strip()


def _to_float(value: str) -> float | None:
    s = _strip_cell(value)
    if not s or s.upper() == "N/A":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _to_int(value: str) -> int | None:
    s = _strip_cell(value)
    if not s or s.upper() == "N/A":
        return None
    try:
        return int(float(s))
    except ValueError:
        return None


_NUMERIC_HINT = re.compile(r"Time\(us\)|cycles|ratio|utilization|%?\)$|_rate$")


def load_op_summary_csv(path: Path) -> tuple[list[str], list[dict[str, Any]]]:
    """
    Load Ascend op_summary_*.csv (comma-separated, quoted fields allowed).
    Coerces obvious numeric columns to float; keeps strings for names/shapes.
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    reader = csv.DictReader(text.splitlines())
    fieldnames = reader.fieldnames
    if not fieldnames:
        raise ValueError(f"Empty or invalid CSV: {path}")

    rows: list[dict[str, Any]] = []
    for raw in reader:
        row: dict[str, Any] = {}
        for k in fieldnames:
            v = raw.get(k, "") or ""
            if k is None:
                continue
            key = k.strip()
            val = _strip_cell(v) if isinstance(v, str) else v
            if _NUMERIC_HINT.search(key) or key in {
                "Device_id",
                "Model ID",
                "Task ID",
                "Stream ID",
                "Block Dim",
                "Mix Block Dim",
                "Context ID",
            }:
                if key in {"Device_id", "Model ID", "Task ID", "Stream ID", "Block Dim", "Mix Block Dim", "Context ID"}:
                    row[key] = _to_int(str(val)) if val != "" else None
                else:
                    row[key] = _to_float(str(val)) if val != "" else None
            else:
                row[key] = val if val != "" else None
        rows.append(row)

    return list(fieldnames), rows
