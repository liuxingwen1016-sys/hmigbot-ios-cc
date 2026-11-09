"""External detectors and the shell entrypoint must never reuse a stale PASS.

Uses real child processes for timeout/crash cases; no HarmonyOS SDK is required.
Run with unittest discovery or directly with Python.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import structural_loop as SL

PASSING_AUDIT = {"summary": {"FAIL": 0, "WARN": 0}, "findings": []}
FAILING_AUDIT = {"summary": {"FAIL": 1, "WARN": 0}, "findings": []}


class BoundedDetectorTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.out = self.root / "detector.json"
        self.env = patch.dict(os.environ)
        self.env.start()
        self.addCleanup(self.env.stop)
        os.environ.pop("ARKTS_DETECTOR_TIMEOUT_S", None)

    def command(self, code):
        return patch.object(SL, "_detector_cmd", return_value=[sys.executable, "-c", code])

    def writer(self, payload, tail=""):
        return (f"from pathlib import Path; Path({str(self.out)!r}).write_text("
                f"{json.dumps(payload)!r}, encoding='utf-8'); {tail}")

    def audit(self):
        return SL._safe_detector("audit", lambda: SL._run_audit(self.root, "all", self.out), self.out)

    def assert_failed_audit(self, result):
        self.assertFalse(result["passed"])
        self.assertGreater(SL._build_iteration_state(0, result, None).total_fail(), 0)

    def test_hanging_detector_is_bounded_and_nonconvergent(self):
        before = time.monotonic()
        with patch.object(SL, "DETECTOR_TIMEOUT", .2), self.command("import time; time.sleep(30)"):
            result = self.audit()
        self.assertLess(time.monotonic() - before, 3)
        self.assert_failed_audit(result)
        self.assertIn("超时", result["error"])

    def test_old_pass_is_removed_before_crash(self):
        self.out.write_text(json.dumps(PASSING_AUDIT), encoding="utf-8")
        with self.command("import sys; sys.exit(3)"):
            self.assert_failed_audit(self.audit())
        self.assertEqual(json.loads(self.out.read_text())["summary"]["FAIL"], 1)

    def test_pass_written_before_timeout_is_rejected(self):
        written = self.root / "pass-was-written"
        with patch.object(SL, "DETECTOR_TIMEOUT", .2), self.command(
                self.writer(PASSING_AUDIT, f"Path({str(written)!r}).touch(); import time; time.sleep(30)")):
            self.assert_failed_audit(self.audit())
        self.assertTrue(written.exists(), "detector must write PASS before timing out")

    def test_pass_written_before_abnormal_exit_is_rejected(self):
        for code in (1, 3):
            with self.subTest(code=code), self.command(
                    self.writer(PASSING_AUDIT, f"import sys; sys.exit({code})")):
                self.assert_failed_audit(self.audit())

    def test_normal_pass_and_findings_exit_one_are_read(self):
        for code, payload in ((0, PASSING_AUDIT), (1, FAILING_AUDIT)):
            with self.subTest(code=code), self.command(
                    self.writer(payload, f"import sys; sys.exit({code})")):
                self.assertEqual(SL._run_audit(self.root, "all", self.out), payload)

    def test_wiring_findings_exit_one_are_read(self):
        payload = {"categories": {"C1": {"pass": 0, "fail": 1, "details": []}},
                   "repair_actions": [{"current_state": "wire missing dependency"}]}
        with self.command(self.writer(payload, "import sys; sys.exit(1)")):
            self.assertEqual(SL._run_wiring(self.root, 1, self.out), payload)

    def test_audit_handoff_findings_exit_one_are_read(self):
        payload = dict(PASSING_AUDIT, handoff_escape_hatches=[{"file": "handoff.md"}])
        with self.command(self.writer(payload, "import sys; sys.exit(1)")):
            result = SL._run_audit(self.root, "all", self.out)
        self.assertEqual(result, payload)
        self.assertGreater(SL._build_iteration_state(0, result, None).total_fail(), 0)

    def test_audit_missing_or_invalid_required_fields_are_fail(self):
        payloads = [{}, {"summary": {"FAIL": 0, "WARN": 0}},
                    {"summary": {"FAIL": 0}, "findings": []},
                    {"summary": {"FAIL": "0", "WARN": 0}, "findings": []},
                    {"summary": {"FAIL": -1, "WARN": 0}, "findings": []},
                    {"summary": {"FAIL": False, "WARN": 0}, "findings": []}]
        for payload in payloads:
            with self.subTest(payload=payload), self.command(self.writer(payload)):
                self.assert_failed_audit(self.audit())

    def test_ledger_missing_or_invalid_required_fields_are_fail(self):
        payloads = [{}, {"summary": {"FAIL": 0}, "findings": []},
                    {"summary": {"FAIL": 0, "WARN": 0}, "findings": None}]
        for payload in payloads:
            with self.subTest(payload=payload), self.command(self.writer(payload)):
                result = SL._run_pipeline_ledger(self.root, self.out)
            self.assertEqual(result["summary"]["FAIL"], 1)

    def test_wiring_missing_or_invalid_required_fields_are_fail(self):
        category = {"C1": {"pass": 1, "fail": 0, "details": []}}
        payloads = [{}, {"categories": category}, {"categories": {}, "repair_actions": []},
                    {"categories": category, "repair_actions": {}},
                    {"categories": {"C1": {"pass": 1}}, "repair_actions": []},
                    {"categories": {"C1": {"pass": 0, "fail": 1, "details": []}},
                     "repair_actions": []}]
        for payload in payloads:
            with self.subTest(payload=payload), self.command(self.writer(payload)):
                result = SL._safe_detector("wiring", lambda: SL._run_wiring(self.root, 1, self.out), self.out)
            self.assertFalse(result["passed"])
            self.assertGreater(SL._build_iteration_state(0, None, result).total_fail(), 0)

    def test_icon_requires_boolean_passed_and_preserves_brief_reports(self):
        for payload in ({}, {"skipped": True}, {"passed": "true"}):
            launcher = [sys.executable, "-c", self.writer(payload)]
            with self.subTest(payload=payload), patch.object(SL, "_icon_autofix_launcher", return_value=launcher):
                self.assertFalse(SL._run_icon_sizing(self.root, self.out)["passed"])
        for payload in ({"passed": True, "skipped": True, "reason": "no ETS roots"},
                        {"passed": False, "error": "autofix failed"}):
            launcher = [sys.executable, "-c", self.writer(payload)]
            with self.subTest(payload=payload), patch.object(SL, "_icon_autofix_launcher", return_value=launcher):
                self.assertEqual(SL._run_icon_sizing(self.root, self.out), payload)

    def test_ledger_no_output_is_fail(self):
        self.out.write_text(json.dumps(PASSING_AUDIT), encoding="utf-8")
        with self.command("import sys; sys.exit(1)"):
            result = SL._run_pipeline_ledger(self.root, self.out)
        self.assertEqual(result["summary"]["FAIL"], 1)
        self.assertGreater(SL._build_iteration_state(0, None, None, ledger=result).total_fail(), 0)

    def test_ledger_pass_written_before_timeout_is_fail(self):
        with patch.object(SL, "DETECTOR_TIMEOUT", .2), self.command(
                self.writer(PASSING_AUDIT, "import time; time.sleep(30)")):
            result = SL._run_pipeline_ledger(self.root, self.out)
        self.assertEqual(result["summary"]["FAIL"], 1)
        self.assertIn("超时", result["error"])

    def test_cannot_remove_old_output_does_not_launch_detector(self):
        self.out.write_text(json.dumps(PASSING_AUDIT), encoding="utf-8")
        with patch.object(Path, "unlink", side_effect=PermissionError("locked")), \
                patch.object(SL, "_detector_cmd") as command:
            result = self.audit()
        command.assert_not_called()
        self.assert_failed_audit(result)
        self.assertIn("旧产物无法作废", result["error"])

    def test_invalid_timeout_is_fail_without_launch(self):
        os.environ["ARKTS_DETECTOR_TIMEOUT_S"] = "nan"
        with patch.object(SL, "_detector_cmd") as command:
            self.assert_failed_audit(self.audit())
        command.assert_not_called()

    def test_stricter_detector_timeout_cap_is_preserved(self):
        os.environ["ARKTS_DETECTOR_TIMEOUT_S"] = "30"
        before = time.monotonic()
        with self.command("import time; time.sleep(30)"):
            reason = SL._run_detector(SL.AUDIT_SCRIPT, [], self.out, timeout_cap=.2)
        self.assertLess(time.monotonic() - before, 3)
        self.assertIn("超时", reason)

    def test_unreadable_result_is_fail(self):
        with self.command(f"from pathlib import Path; Path({str(self.out)!r}).write_text('{{')"):
            self.assert_failed_audit(self.audit())

    def test_frozen_executable_uses_entry_subcommand(self):
        dist = self.root / "_entry.dist"
        dist.mkdir()
        fake_python = dist / "python"
        entry = dist / ("_entry.exe" if os.name == "nt" else "_entry.bin")
        for path in (fake_python, entry):
            path.write_text("")
            path.chmod(0o755)
        with patch.object(SL.sys, "executable", str(fake_python)), \
                patch.object(SL, "__compiled__", True, create=True):
            command = SL._detector_cmd(SL.WIRING_SCRIPT, ["--slice", "1"])
        self.assertEqual(command[:2], [str(entry), "verify_slice_wiring"])

    @unittest.skipUnless(os.name == "posix", "POSIX process-group regression")
    def test_timeout_also_stops_detector_child_process(self):
        marker = self.root / "orphan-wrote-result"
        child = f"import time; from pathlib import Path; time.sleep(.5); Path({str(marker)!r}).touch()"
        code = (f"import subprocess,sys,time; subprocess.Popen([sys.executable, '-c', {child!r}]); "
                "time.sleep(30)")
        with patch.object(SL, "DETECTOR_TIMEOUT", .2), self.command(code):
            self.assert_failed_audit(self.audit())
        time.sleep(.6)
        self.assertFalse(marker.exists(), "timed-out detector child remained alive")

    def test_icon_uses_resolved_launcher_and_fresh_result(self):
        payload = {"passed": True}
        launcher = [sys.executable, "-c", self.writer(payload)]
        with patch.object(SL, "_icon_autofix_launcher", return_value=launcher), \
                patch.object(SL, "_detector_cmd", side_effect=AssertionError("must use icon launcher")):
            self.assertEqual(SL._run_icon_sizing(self.root, self.out), payload)


@unittest.skipUnless(shutil.which("bash"), "shell wrapper needs bash")
class LoopWrapperTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.scripts = self.root / "scripts"
        self.scripts.mkdir()
        self.wrapper = self.scripts / "run_loop.sh"
        shutil.copyfile(SCRIPTS / "run_loop.sh", self.wrapper)
        # Single quotes in paths must not become Python source in the summary parser.
        self.project = self.root / "project's directory"
        self.logs = self.project / "spec/execution/autofix-log/round-1"
        self.logs.mkdir(parents=True)
        self.result = self.logs / "loop-result-latest-stage-1.json"
        self.result.write_text(json.dumps(self.payload("CONVERGED")), encoding="utf-8")

    def payload(self, verdict):
        return {"verdict": verdict, "iteration": 2,
                "current_state": {"total_fail": 0 if verdict == "CONVERGED" else 1}}

    def run_loop(self, code, env=None):
        (self.scripts / "structural_loop.py").write_text(code, encoding="utf-8")
        return subprocess.run([shutil.which("bash"), str(self.wrapper), "--mode", "stage",
                               "--target", "1", "--round", "1", "--project-root", str(self.project),
                               "--diff-base", "HEAD"], capture_output=True, text=True, timeout=8, env=env)

    def write_then_exit(self, payload, code):
        text = json.dumps(payload)
        return ("import sys\nfrom pathlib import Path\n"
                "out = Path(sys.argv[sys.argv.index('--output-json') + 1])\n"
                f"out.write_text({text!r}, encoding='utf-8')\nsys.exit({code})\n")

    def assert_incomplete(self, proc):
        self.assertEqual(proc.returncode, 3, proc.stderr)
        self.assertIn("INCOMPLETE", proc.stderr)
        self.assertNotIn("CONVERGED", proc.stderr)
        self.assertFalse(self.result.exists())
        self.assertEqual(json.loads(Path(str(self.result) + ".prev").read_text())["verdict"], "CONVERGED")

    def test_crash_without_output_does_not_echo_old_converged(self):
        self.assert_incomplete(self.run_loop("import sys; sys.exit(3)"))

    def test_zero_exit_without_output_is_incomplete(self):
        self.assert_incomplete(self.run_loop("pass"))

    def test_pass_written_before_crash_is_not_reported(self):
        self.assert_incomplete(self.run_loop(self.write_then_exit(self.payload("CONVERGED"), 3)))

    def test_normal_continue_remains_actionable(self):
        proc = self.run_loop(self.write_then_exit(self.payload("CONTINUE"), 1))
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertIn("verdict=CONTINUE", proc.stderr)
        self.assertIn("dispatch repair worker", proc.stderr)

    def test_normal_converged_with_quote_in_path_is_reported(self):
        proc = self.run_loop(self.write_then_exit(self.payload("CONVERGED"), 0))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("verdict=CONVERGED", proc.stderr)

    def test_mismatched_verdict_is_incomplete(self):
        self.assert_incomplete(self.run_loop(self.write_then_exit(self.payload("CONVERGED"), 1)))

    def test_invalid_new_json_is_incomplete(self):
        code = ("import sys\nfrom pathlib import Path\n"
                "Path(sys.argv[sys.argv.index('--output-json')+1]).write_text('{')\n")
        self.assert_incomplete(self.run_loop(code))

    def test_invalid_state_shape_does_not_emit_partial_pass_summary(self):
        payload = self.payload("CONVERGED")
        payload["current_state"] = []
        self.assert_incomplete(self.run_loop(self.write_then_exit(payload, 0)))

    def test_archive_failure_prevents_new_scan(self):
        Path(str(self.result) + ".prev").mkdir()
        marker = self.root / "unexpected-launch"
        code = f"from pathlib import Path; Path({str(marker)!r}).touch()"
        proc = self.run_loop(code)
        self.assertEqual(proc.returncode, 3, proc.stderr)
        self.assertIn("INCOMPLETE", proc.stderr)
        self.assertNotIn("CONVERGED", proc.stderr)
        self.assertFalse(marker.exists())

    @unittest.skipUnless(os.name == "posix", "uses an isolated POSIX utility path")
    def test_no_interpreter_still_invalidates_old_result(self):
        commands = self.root / "commands"
        commands.mkdir()
        for command in ("dirname", "mkdir", "mv"):
            os.symlink(shutil.which(command), commands / command)
        env = dict(os.environ, PATH=str(commands))
        self.assert_incomplete(self.run_loop("pass", env))

    @unittest.skipUnless(os.name == "posix", "simulates a packaged POSIX entrypoint")
    def test_packaged_entry_still_runs_without_system_python(self):
        commands = self.root / "commands"
        commands.mkdir()
        for command in ("dirname", "mkdir", "mv", "sed"):
            os.symlink(shutil.which(command), commands / command)
        entry = self.scripts / "_entry.dist/_entry.bin"
        entry.parent.mkdir()
        entry.write_text(
            '#!/bin/bash\nwhile [[ $# -gt 0 ]]; do\n'
            '  if [[ "$1" == --output-json ]]; then OUTPUT="$2"; shift; fi\n'
            '  shift\ndone\n'
            f"printf '%s' '{json.dumps(self.payload('CONVERGED'))}' > \"$OUTPUT\"\n",
            encoding="utf-8")
        entry.chmod(0o755)
        proc = self.run_loop("raise AssertionError('source path should not run')",
                             dict(os.environ, PATH=str(commands)))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("CONVERGED", proc.stderr)
        self.assertEqual(json.loads(self.result.read_text())["verdict"], "CONVERGED")
        # command -v may find a Windows Store alias or unusable shim. A healthy
        # packaged entry must still work just as when Python is absent entirely.
        shim = commands / "python3"
        shim.write_text("#!/bin/bash\nexit 127\n", encoding="utf-8")
        shim.chmod(0o755)
        proc = self.run_loop("raise AssertionError('source path should not run')",
                             dict(os.environ, PATH=str(commands)))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("CONVERGED", proc.stderr)


if __name__ == "__main__":
    unittest.main()
