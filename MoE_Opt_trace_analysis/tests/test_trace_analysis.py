from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from analyzers.parser import parse_trace_json
from analyzers.metrics import build_phase_instances
from analyzers.phase_mapper import PhaseMapper


class TraceAnalysisTests(unittest.TestCase):
    def test_parse_begin_end_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            trace_path = os.path.join(tmpdir, "trace.json")
            trace = {
                "traceEvents": [
                    {"name": "processing", "ph": "B", "ts": 0, "pid": 1, "tid": "type0_core000"},
                    {"name": "dispatch-gmm1", "ph": "B", "ts": 20, "pid": 1, "tid": "type0_core000"},
                    {"name": "dispatch-gmm1", "ph": "E", "ts": 80, "pid": 1, "tid": "type0_core000"},
                    {"name": "gmm2-combine", "ph": "B", "ts": 90, "pid": 1, "tid": "type1_core000"},
                    {"name": "gmm2-combine", "ph": "E", "ts": 180, "pid": 1, "tid": "type1_core000"},
                    {"name": "processing", "ph": "E", "ts": 200, "pid": 1, "tid": "type0_core000"},
                ]
            }
            with open(trace_path, "w", encoding="utf-8") as f:
                json.dump(trace, f)

            events = parse_trace_json(trace_path)

        self.assertEqual(len(events), 3)
        self.assertEqual(events[0].name, "processing")
        self.assertEqual(events[0].dur, 200)

    def test_phase_mapper_matches_specific_wait_label(self) -> None:
        mapper = PhaseMapper(os.path.join(ROOT, "config", "phase_map.yaml"))
        phase = mapper.map_event_name("gmm2-combine block-epilogue shared-wait-combine [extra:0] #0")
        self.assertEqual(phase, "gmm2_combine_shared_wait_combine")

    def test_core_group_is_inferred_from_tid(self) -> None:
        mapper = PhaseMapper(os.path.join(ROOT, "config", "phase_map.yaml"))
        rows = build_phase_instances(
            [
                {
                    "name": "dispatch-gmm1",
                    "ts_start": 0,
                    "ts_end": 1,
                    "dur": 1,
                    "pid": 0,
                    "tid": "type0_core000",
                    "args": {},
                },
                {
                    "name": "gmm2-combine block-epilogue waiting",
                    "ts_start": 0,
                    "ts_end": 1,
                    "dur": 1,
                    "pid": 0,
                    "tid": "type1_core003",
                    "args": {},
                },
                {
                    "name": "gmm2-combine combine-wait-status",
                    "ts_start": 0,
                    "ts_end": 1,
                    "dur": 1,
                    "pid": 0,
                    "tid": "type2_core007",
                    "args": {},
                },
            ],
            mapper,
        )
        self.assertEqual([row["core_group"] for row in rows], ["cube", "vector_recv", "vector_send"])

    def test_app_generates_automatic_report_without_third_party_dependencies(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            trace_path = os.path.join(tmpdir, "trace.json")
            output_dir = os.path.join(tmpdir, "out")
            trace = {
                "traceEvents": [
                    {"name": "processing", "ph": "B", "ts": 0, "pid": 1, "tid": "type0_core000"},
                    {"name": "dispatch-gmm1", "ph": "B", "ts": 10, "pid": 1, "tid": "type0_core000"},
                    {"name": "dispatch-gmm1", "ph": "E", "ts": 40, "pid": 1, "tid": "type0_core000"},
                    {"name": "gmm2-combine block-epilogue shared-wait-combine", "ph": "B", "ts": 50, "pid": 1, "tid": "type0_core001"},
                    {"name": "gmm2-combine block-epilogue shared-wait-combine", "ph": "E", "ts": 150, "pid": 1, "tid": "type0_core001"},
                    {"name": "processing", "ph": "E", "ts": 200, "pid": 1, "tid": "type0_core000"},
                ]
            }
            with open(trace_path, "w", encoding="utf-8") as f:
                json.dump(trace, f)

            result = subprocess.run(
                [
                    sys.executable,
                    os.path.join(ROOT, "app.py"),
                    "--trace",
                    trace_path,
                    "--output-dir",
                    output_dir,
                ],
                cwd=ROOT,
                check=False,
                text=True,
                capture_output=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(os.path.exists(os.path.join(output_dir, "report.md")))
            self.assertTrue(os.path.exists(os.path.join(output_dir, "bubble_summary.csv")))
            self.assertTrue(os.path.exists(os.path.join(output_dir, "llm_prompt.md")))
            self.assertTrue(os.path.exists(os.path.join(output_dir, "statistical_summary.md")))
            with open(os.path.join(output_dir, "report.md"), "r", encoding="utf-8") as f:
                report = f.read()
            self.assertIn("## Statistical Highlights", report)
            self.assertIn("Top non-container phases", report)
            with open(os.path.join(output_dir, "diagnosis.json"), "r", encoding="utf-8") as f:
                diagnosis = json.load(f)
            self.assertIn("wait", diagnosis["headline"])

    def test_app_can_insert_external_llm_analysis(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            trace_path = os.path.join(tmpdir, "trace.json")
            output_dir = os.path.join(tmpdir, "out")
            fake_llm_path = os.path.join(tmpdir, "fake_llm.py")
            trace = {
                "traceEvents": [
                    {"name": "processing", "ph": "B", "ts": 0, "pid": 1, "tid": "type0_core000"},
                    {"name": "gmm2-combine block-epilogue shared-wait-combine", "ph": "B", "ts": 10, "pid": 1, "tid": "type1_core000"},
                    {"name": "gmm2-combine block-epilogue shared-wait-combine", "ph": "E", "ts": 100, "pid": 1, "tid": "type1_core000"},
                    {"name": "processing", "ph": "E", "ts": 120, "pid": 1, "tid": "type0_core000"},
                ]
            }
            with open(trace_path, "w", encoding="utf-8") as f:
                json.dump(trace, f)
            with open(fake_llm_path, "w", encoding="utf-8") as f:
                f.write("import sys\n_ = sys.stdin.read()\nprint('LLM says wait is on vector_recv.')\n")

            result = subprocess.run(
                [
                    sys.executable,
                    os.path.join(ROOT, "app.py"),
                    "--trace",
                    trace_path,
                    "--output-dir",
                    output_dir,
                    "--llm-analysis",
                    "--llm-command",
                    f"{sys.executable} {fake_llm_path}",
                ],
                cwd=ROOT,
                check=False,
                text=True,
                capture_output=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            with open(os.path.join(output_dir, "report.md"), "r", encoding="utf-8") as f:
                report = f.read()
            self.assertIn("## LLM Analysis", report)
            self.assertIn("LLM says wait is on vector_recv.", report)


if __name__ == "__main__":
    unittest.main()
