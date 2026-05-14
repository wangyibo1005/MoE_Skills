#!/usr/bin/env python3
"""Copy evolution record template with placeholders replaced."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser(description="Initialize evolution_record.md from template.")
    p.add_argument(
        "--experiment-id",
        required=True,
        help="Experiment name or ID (e.g. moe_202605_candidate_a).",
    )
    p.add_argument(
        "-o",
        "--output",
        required=True,
        type=Path,
        help="Output markdown path.",
    )
    p.add_argument(
        "--date",
        default="",
        help="Record date (default: today, local).",
    )
    args = p.parse_args()

    root = Path(__file__).resolve().parent.parent
    template = root / "templates" / "evolution_record.template.md"
    if not template.is_file():
        print(f"Template not found: {template}", flush=True)
        return 1

    d = args.date.strip() or str(date.today())
    text = template.read_text(encoding="utf-8")
    text = text.replace("{{EXPERIMENT_ID}}", args.experiment_id)
    text = text.replace("{{DATE}}", d)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding="utf-8")
    print(f"Wrote {args.output.resolve()}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
