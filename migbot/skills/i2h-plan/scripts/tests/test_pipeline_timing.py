import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

from pipeline_timing import record


class PipelineTimingTest(unittest.TestCase):
    stages = ("i2h-spec", "i2h-plan", "i2h-execute", "i2h-verify")

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        self.flags = dict(runtime_plan=True, visual_and_ut=True, behavior=True)
        self.run_id = None

    def capture(self, action, stage, clock, completed):
        preflight = {"resume_stage": stage, "stages": [
            {"stage": name, "complete": name in completed} for name in self.stages
        ]}
        with patch("pipeline_timing.time.monotonic", return_value=clock):
            receipt = record(self.root, preflight, self.flags, action, stage, self.run_id)
        self.run_id = receipt["run_id"]
        return receipt

    def test_continuous_span_includes_failed_verify_and_gaps(self):
        completed = set()
        for index, stage in enumerate(self.stages[:3]):
            self.capture("start", stage, index * 10, completed)
            completed.add(stage)
            self.capture("finish", stage, index * 10 + 2, completed)
        self.capture("start", "i2h-verify", 30, completed)
        failed = self.capture("finish", "i2h-verify", 120, completed)
        self.assertIsNone(failed["wall_seconds"])
        self.capture("start", "i2h-verify", 200, completed)
        completed.add("i2h-verify")
        result = self.capture("finish", "i2h-verify", 7200, completed)
        self.assertEqual(result["scope"], "full")
        self.assertEqual(result["wall_seconds"], 7200)
        self.assertFalse(result["under_two_hours"])
        attempts = json.loads(Path(result["path"]).read_bytes())["attempts"]
        self.assertEqual([item["wall_seconds"] for item in attempts], [2, 2, 2, 90, 7000])

    def test_resumed_scope_and_interruption(self):
        initial = self.capture("start", "i2h-verify", 70, set(self.stages[:3]))
        report = json.loads(Path(initial["path"]).read_bytes())
        self.assertEqual(initial["attempt_status"], "running")
        self.assertIsNone(report["attempts"][0]["ended_at"])
        final = self.capture("finish", "i2h-verify", 75, set(self.stages))
        self.assertEqual(final["scope"], "partial")
        self.assertIsNone(final["under_two_hours"])

    def test_cli_records_pending_spec_without_advancing_gate(self):
        result = subprocess.run(
            [sys.executable, "-B", str(SCRIPTS / "pipeline_resume.py"), "--project-root", str(self.root),
             "--summary", "--timing", "start", "--timing-stage", "i2h-spec"],
            capture_output=True, encoding="utf-8", timeout=15,
        )
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(json.loads(result.stdout)["timing"]["attempt_status"], "running")
        self.assertFalse((self.root / "spec/baseline/spec-complete.txt").exists())


if __name__ == "__main__":
    unittest.main()
