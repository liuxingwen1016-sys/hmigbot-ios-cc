import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

from pipeline_timing import record, report, runtime_sha256


class PipelineTimingTest(unittest.TestCase):
    stages = ("i2h-spec", "i2h-plan", "i2h-execute", "i2h-verify")

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        self.flags = dict(runtime_plan=True, visual_and_ut=True, behavior=True, bound_visual=True)
        self.run_id = None
        self.target_input = "a" * 64
        self.plan_identity = "b" * 64
        self.verification = {
            "report_sha256": "d" * 64, "visual_evidence": {"report_sha256": "e" * 64},
            "behavior_evidence": {"report_sha256": "f" * 64, "plan_sha256": "0" * 64},
        }
        self.patch_runtime = patch("pipeline_timing.runtime_sha256", return_value="c" * 64)
        self.runtime = self.patch_runtime.start()
        self.addCleanup(self.patch_runtime.stop)

    def capture(self, action, stage, clock, completed, *, wall_offset=0):
        resume = next((name for name in self.stages if name not in completed), "i2h-retrospect")
        preflight = {"resume_stage": resume, "target_input_sha256": self.target_input,
                     "verification": self.verification if resume == "i2h-retrospect" else {},
                     "stages": [{"stage": name, "complete": name in completed,
                                 "checks": {"marker": {"artifact_set_sha256": self.plan_identity}}}
                                for name in self.stages]}
        with patch("pipeline_timing.time.monotonic", return_value=clock), \
                patch("pipeline_timing.time.time", return_value=1_800_000_000 + clock + wall_offset):
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
        self.assertIsNone(failed["under_two_hours"])
        self.assertEqual(failed["observed_wall_seconds"], 120)
        self.assertEqual(failed["first_verify_ready_seconds"], 22)
        self.assertEqual(failed["first_verify_start_seconds"], 30)
        self.assertEqual(failed["observed_after_first_verify_seconds"], 90)
        self.assertEqual(json.loads(Path(failed["path"]).read_bytes())["observed_wall_seconds"], 120)
        retry = self.capture("start", "i2h-verify", 200, completed)
        self.assertEqual(retry["observed_until"], failed["observed_until"])
        self.assertEqual(retry["observed_wall_seconds"], 120)
        observed = report(self.root, self.run_id)
        self.assertEqual(observed["running_attempt"]["stage"], "i2h-verify")
        self.assertIsNone(observed["running_attempt"]["seconds"])
        self.assertEqual(observed["between_finished_attempts_seconds"], 24)
        self.assertEqual(observed["after_first_verify_start"]["observed_seconds"], 90)
        completed.add("i2h-verify")
        result = self.capture("finish", "i2h-verify", 7200, completed)
        self.assertEqual(result["scope"], "full")
        self.assertEqual(result["wall_seconds"], 7200)
        self.assertEqual(result["observed_wall_seconds"], 7200)
        self.assertFalse(result["under_two_hours"])
        self.assertEqual(result["observed_after_first_verify_seconds"], 7170)
        attempts = json.loads(Path(result["path"]).read_bytes())["attempts"]
        self.assertEqual([item["wall_seconds"] for item in attempts], [2, 2, 2, 90, 7000])
        observed = report(self.root, self.run_id)
        self.assertEqual(observed["finished_attempt_seconds"], 7096)
        self.assertEqual(observed["between_finished_attempts_seconds"], 104)
        self.assertEqual(observed["after_first_verify_start"], {
            "finished_attempts": 2, "attempt_seconds": 7090, "observed_seconds": 7170,
        })
        self.assertEqual(observed["stages"]["i2h-verify"], {
            "finished_attempts": 2, "incomplete_attempts": 1, "seconds": 7090,
        })

    def test_full_timing_detects_scope_changes_even_if_plan_is_restored(self):
        completed = set()
        for index, stage in enumerate(self.stages[:3]):
            self.capture("start", stage, index * 10, completed)
            completed.add(stage)
            self.capture("finish", stage, index * 10 + 2, completed)
        original_identity = self.plan_identity
        self.plan_identity = "a" * 64
        self.capture("start", "i2h-verify", 30, completed)
        self.plan_identity = original_identity
        result = self.capture("finish", "i2h-verify", 40, set(self.stages))
        self.assertEqual(result["scope_gaps"], ["approved_plan_changed"])
        self.assertEqual(result["scope"], "partial")
        self.assertIsNone(result["under_two_hours"])

    def test_clock_discontinuity_retains_observation_without_certifying_deadline(self):
        completed = set()
        for index, stage in enumerate(self.stages[:3]):
            self.capture("start", stage, index * 10, completed)
            completed.add(stage)
            self.capture("finish", stage, index * 10 + 2, completed)
        self.capture("start", "i2h-verify", 30, completed)
        result = self.capture("finish", "i2h-verify", 7100, set(self.stages), wall_offset=180)
        self.assertEqual(result["scope"], "partial")
        self.assertEqual(result["scope_gaps"], ["clock_discontinuity"])
        self.assertEqual(result["observed_wall_seconds"], 7100)
        self.assertIsNone(result["under_two_hours"])
        observed = report(self.root, self.run_id)
        self.assertEqual(observed["clock_validation"], "discontinuous")
        self.assertEqual(observed["utc_elapsed_seconds"], 7280)

    def test_deadline_remains_strict_when_clock_difference_is_small(self):
        completed = set()
        for index, stage in enumerate(self.stages[:3]):
            self.capture("start", stage, index * 10, completed)
            completed.add(stage)
            self.capture("finish", stage, index * 10 + 2, completed)
        self.capture("start", "i2h-verify", 30, completed)
        result = self.capture("finish", "i2h-verify", 7199.5, set(self.stages), wall_offset=1)
        self.assertEqual(result["scope"], "full")
        self.assertFalse(result["under_two_hours"])

    def test_full_timing_requires_machine_evidence_at_verify_and_rejects_a_preexisting_run(self):
        from acceptance_plan import BEHAVIOR_REPORT
        from hashlib import sha256

        behavior_path = self.root / BEHAVIOR_REPORT
        behavior_path.parent.mkdir(parents=True)
        behavior_path.write_text("earlier behavior evidence", encoding="utf-8")
        self.verification["behavior_evidence"]["report_sha256"] = sha256(behavior_path.read_bytes()).hexdigest()
        for expectation in ("preexisting_verify_evidence", "bound_verify_evidence_missing"):
            with self.subTest(expectation=expectation):
                self.run_id = None
                completed = set()
                if expectation == "bound_verify_evidence_missing":
                    self.verification.pop("visual_evidence")
                for index, stage in enumerate(self.stages):
                    self.capture("start", stage, index * 10, completed)
                    completed.add(stage)
                    result = self.capture("finish", stage, index * 10 + 2, completed)
                self.assertEqual(result["scope_gaps"], [expectation])
                self.assertEqual(result["scope"], "partial")
                self.assertIsNone(result["under_two_hours"])

    def test_resumed_scope_and_interruption(self):
        initial = self.capture("start", "i2h-verify", 70, set(self.stages[:3]))
        report = json.loads(Path(initial["path"]).read_bytes())
        self.assertEqual(initial["attempt_status"], "running")
        self.assertIsNone(initial["observed_wall_seconds"])
        self.assertIsNone(report["attempts"][0]["ended_at"])
        final = self.capture("finish", "i2h-verify", 75, set(self.stages))
        self.assertEqual(final["scope"], "partial")
        self.assertIsNone(final["under_two_hours"])

    def test_target_input_change_preserves_running_attempt(self):
        receipt = self.capture("start", "i2h-spec", 0, set())
        path = Path(receipt["path"])
        before = path.read_bytes()
        self.target_input = "b" * 64
        with self.assertRaisesRegex(ValueError, "target input changed"):
            self.capture("finish", "i2h-spec", 10, {"i2h-spec"})
        self.assertEqual(path.read_bytes(), before)

    def test_clock_rollback_between_attempts_preserves_the_receipt(self):
        self.capture("start", "i2h-spec", 50, set())
        finished = self.capture("finish", "i2h-spec", 62, {"i2h-spec"})
        path = Path(finished["path"])
        before = path.read_bytes()
        with self.assertRaisesRegex(ValueError, "monotonic clock changed"):
            self.capture("start", "i2h-plan", 59, {"i2h-spec"})
        self.assertEqual(path.read_bytes(), before)

    def test_runtime_change_preserves_running_attempt(self):
        receipt = self.capture("start", "i2h-spec", 0, set())
        path = Path(receipt["path"])
        before = path.read_bytes()
        self.runtime.return_value = "d" * 64
        with self.assertRaisesRegex(ValueError, "CC runtime changed"):
            self.capture("finish", "i2h-spec", 10, {"i2h-spec"})
        self.assertEqual(path.read_bytes(), before)

    def test_runtime_fingerprint_tracks_installed_helpers_and_ignores_cache(self):
        scripts = self.root / ".claude/skills/i2h-plan/scripts"
        scripts.mkdir(parents=True)
        (scripts / "pipeline_timing.py").write_text("clock", encoding="utf-8")
        shared = self.root / ".migbot/bin/scripts"
        shared.mkdir(parents=True)
        helper = shared / "stage.py"
        helper.write_text("version one", encoding="utf-8")
        original = runtime_sha256(scripts)
        (scripts / "__pycache__").mkdir()
        (scripts / "__pycache__/runtime.pyc").write_bytes(b"compiled")
        self.assertEqual(runtime_sha256(scripts), original)
        helper.write_text("version two", encoding="utf-8")
        self.assertNotEqual(runtime_sha256(scripts), original)

    def test_fresh_run_binds_input_when_spec_finishes(self):
        self.target_input = None
        self.capture("start", "i2h-spec", 0, set())
        self.target_input = "b" * 64
        outcome = self.capture("finish", "i2h-spec", 10, {"i2h-spec"})
        receipt = json.loads(Path(outcome["path"]).read_bytes())
        self.assertEqual(receipt["target_input_sha256"], self.target_input)

    def test_previous_flags_cannot_qualify_for_full_timing(self):
        del self.flags["bound_visual"]
        completed = set()
        for index, stage in enumerate(self.stages):
            self.capture("start", stage, index * 10, completed)
            completed.add(stage)
            result = self.capture("finish", stage, index * 10 + 2, completed)
        self.assertEqual(result["scope"], "partial")
        self.assertIsNone(result["under_two_hours"])

    def test_historical_receipt_without_runtime_fingerprint_is_partial(self):
        completed = set()
        for index, stage in enumerate(self.stages):
            start = self.capture("start", stage, index * 10, completed)
            if not completed:
                path = Path(start["path"])
                historical = json.loads(path.read_bytes())
                historical.pop("runtime_sha256")
                path.write_text(json.dumps(historical), encoding="utf-8")
            completed.add(stage)
            result = self.capture("finish", stage, index * 10 + 2, completed)
        self.assertEqual(result["scope"], "partial")
        self.assertIsNone(result["under_two_hours"])

    def test_cli_records_pending_spec_without_advancing_gate(self):
        result = subprocess.run(
            [sys.executable, "-I", "-B", "-X", "utf8", str(SCRIPTS / "pipeline_resume.py"), "--project-root", str(self.root),
             "--summary", "--timing", "start", "--timing-stage", "i2h-spec"],
            capture_output=True, encoding="utf-8", timeout=15,
        )
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(json.loads(result.stdout)["timing"]["attempt_status"], "running")
        self.assertFalse((self.root / "spec/baseline/spec-complete.txt").exists())

    def test_report_cli_validates_legacy_records_read_only_and_retains_unknown_end(self):
        started = self.capture("start", "i2h-spec", 10, set())
        self.capture("finish", "i2h-spec", 25, {"i2h-spec"})
        self.capture("start", "i2h-plan", 30, {"i2h-spec"})
        path = Path(started["path"])
        legacy = json.loads(path.read_bytes())
        legacy["attempts"][0].pop("end_monotonic")
        path.write_text(json.dumps(legacy), encoding="utf-8")
        before = path.read_bytes()
        command = [sys.executable, "-I", "-B", "-X", "utf8", str(SCRIPTS / "pipeline_resume.py"),
                   "--project-root", str(self.root), "--timing-report", "--timing-run", self.run_id]
        result = subprocess.run(command, capture_output=True, encoding="utf-8", timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        summary = json.loads(result.stdout)
        self.assertEqual(summary["clock_basis"], "monotonic_with_legacy_estimated_ends")
        self.assertEqual(summary["observed_wall_seconds"], 15)
        self.assertIsNone(summary["finished_verify_wall_seconds"])
        self.assertIsNone(summary["running_attempt"]["seconds"])
        self.assertEqual(path.read_bytes(), before)

        legacy["observed_wall_seconds"] = 200
        path.write_text(json.dumps(legacy), encoding="utf-8")
        result = subprocess.run(command, capture_output=True, encoding="utf-8", timeout=15)
        self.assertEqual(result.returncode, 2)
        self.assertIn("recorded wall span differs", result.stderr)


if __name__ == "__main__":
    unittest.main()
