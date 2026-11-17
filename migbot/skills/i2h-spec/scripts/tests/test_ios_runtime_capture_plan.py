import json
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import sys
import tempfile
from hashlib import sha256
import unittest
from unittest.mock import patch
from pathlib import Path
from types import SimpleNamespace

SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))
import ios_runtime_capture_plan as capture_plan  # noqa: E402
from ios_runtime_capture_batch import test_command as xctest_command, verify_launch_mode, verify_xctest_pair  # noqa: E402


class CapturePlanTests(unittest.TestCase):
    def test_batch_preflight_uses_same_validation_without_starting_the_simulator(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source = root / "ios"
            source.mkdir()
            (source / "App.xcodeproj").mkdir()
            (source / "UITests.swift").touch()
            plan = root / "plan.json"
            state = {"page_id": "home", "state_id": "default", "accessibility_command": "xctest_batch"}
            plan.write_text(json.dumps({"states": [state]}))
            output = root / "capture"
            args = ["--plan", str(plan), "--output-root", str(output), "--project-root", str(source),
                    "--project", "App.xcodeproj", "--scheme", "App", "--device-id", "planned-device",
                    "--bundle-id", "test.bundle", "--xctest-batch-size", "1", "--xctest-test-source", "UITests.swift"]
            with patch("ios_runtime_capture_batch.run_batches") as run:
                stdout = StringIO()
                with redirect_stdout(stdout):
                    self.assertEqual(capture_plan.main([*args, "--source-root", str(source), "--validate-only"]), 0)
                self.assertEqual(json.loads(stdout.getvalue())["mode"], "xctest_batch")
                self.assertFalse(output.exists())
                for flags, message in (([], "explicit --device-id"),
                                       (["--source-root", str(source), "--xctest-test-source", "../Outside.swift"],
                                        "relative to the staged source root")):
                    for dry_run in ([], ["--validate-only"]):
                        errors = StringIO()
                        with redirect_stderr(errors):
                            self.assertEqual(capture_plan.main([*args, *flags, *dry_run]), 2)
                        self.assertIn(message, errors.getvalue())
                        self.assertFalse(output.exists())
                run.assert_not_called()

    def test_batch_xcresult_uses_the_explicit_path(self):
        args = SimpleNamespace(device_id="approved-device", xctest_target="NativeUITests")
        command = xctest_command(args, Path("/test/build.xctestrun"), Path("/test/session/capture.xcresult"))
        self.assertEqual(command[command.index("-resultBundlePath") + 1], "/test/session/capture.xcresult")
        self.assertIn("platform=iOS Simulator,id=approved-device", command)
        self.assertIn("-only-testing:NativeUITests/I2HAccessibilityCaptureTests/testI2HAccessibilityCapture", command)

    def test_load_plan_rejects_duplicate_states(self):
        with self.subTest("duplicate"):
            with self._temporary_plan(
                {
                    "states": [
                        {"page_id": "page_0001_HomeView", "state_id": "normal", "accessibility_json": "a.json"},
                        {"page_id": "page_0001_HomeView", "state_id": "normal", "accessibility_json": "b.json"},
                    ]
                }
            ) as path:
                with self.assertRaisesRegex(ValueError, "duplicate page/state"):
                    capture_plan.load_plan(path)

    def test_load_plan_accepts_command_and_json_entries(self):
        with self._temporary_plan(
            {
                "states": [
                    {"page_id": "page_0001_HomeView", "state_id": "normal", "accessibility_command": "echo ok"},
                    {"page_id": "page_0002_BeanLibraryView", "state_id": "root", "accessibility_json": "bean.json"},
                ]
            }
        ) as path:
            payload = capture_plan.load_plan(path)
        self.assertEqual(len(payload["states"]), 2)

    def test_load_plan_rejects_malformed_navigation(self):
        with self._temporary_plan(
            {
                "states": [
                    {
                        "page_id": "page_0003_BeanLibraryView",
                        "state_id": "normal",
                        "accessibility_command": "echo ok",
                        "navigation": {"steps": [{"action": "tap", "target": {"element": "button"}}]},
                    }
                ]
            }
        ) as path:
            with self.assertRaisesRegex(ValueError, "needs identifier"):
                capture_plan.load_plan(path)

    def test_launch_mode_accepts_only_supported_batch_modes(self):
        state = {"page_id": "root", "state_id": "startup", "accessibility_command": "probe"}
        for mode in ("standard", "ui_testing", "arbitrary"):
            with self.subTest(mode=mode), self._temporary_plan({"states": [{**state, "launch_mode": mode}]}) as path:
                if mode == "arbitrary":
                    with self.assertRaisesRegex(ValueError, "launch_mode must be"):
                        capture_plan.load_plan(path)
                else:
                    self.assertEqual(capture_plan.load_plan(path)["states"][0]["launch_mode"], mode)

    def test_explicit_launch_mode_requires_matching_foreground_receipt(self):
        verify_launch_mode({}, {})
        verify_launch_mode({"launch_mode": "standard"}, {"launch_mode": "standard"})
        for receipt in ({}, {"launch_mode": "ui_testing"}):
            with self.subTest(receipt=receipt), self.assertRaisesRegex(RuntimeError, "launch_mode differs"):
                verify_launch_mode(receipt, {"launch_mode": "standard"})

    def test_async_anchor_wait_and_switch_value_keep_a_bounded_typed_plan(self):
        state = {"page_id": "settings", "accessibility_command": "probe", "capture_mode": "xctest_app"}
        anchor = {"element": "switch", "label": "Reminder", "value": "0"}
        navigation = {"steps": [], "anchors": [anchor], "anchor_wait_seconds": 2.5}
        with self._temporary_plan({"states": [{**state, "navigation": navigation}]}) as path:
            self.assertEqual(capture_plan.load_plan(path)["states"][0]["navigation"], navigation)
        for invalid, message in (
            ({**navigation, "anchor_wait_seconds": True}, "anchor_wait_seconds"),
            ({**navigation, "anchor_wait_seconds": 9}, "anchor_wait_seconds"),
            ({**navigation, "anchors": []}, "anchor_wait_seconds"),
            ({**navigation, "anchors": [{**anchor, "value": 0}]}, "value must be a string"),
        ):
            with self.subTest(navigation=invalid), self._temporary_plan({
                "states": [{**state, "navigation": invalid}],
            }) as path, self.assertRaisesRegex(ValueError, message):
                capture_plan.load_plan(path)

    def test_xctest_app_capture_requires_anchor(self):
        state = {
            "page_id": "scan", "state_id": "recognizing",
            "accessibility_command": "probe",
            "capture_mode": "xctest_app",
            "navigation": {"steps": []},
        }
        with self._temporary_plan({"states": [state]}) as plan:
            with self.assertRaisesRegex(ValueError, "requires navigation anchors"):
                capture_plan.load_plan(plan)

    def test_xctest_app_pair_rejects_changed_tree(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            png = root / "ios-runtime.png"
            tree = root / "ios-accessibility.json"
            png.write_bytes(b"\x89PNG\r\n\x1a\nsynthetic screenshot")
            tree.write_text('{"state_id": "recognizing"}')
            receipt = {
                "capture_mode": "xctest_app",
                "screenshot_sha256": sha256(png.read_bytes()).hexdigest(),
                "ui_json_sha256": sha256(tree.read_bytes()).hexdigest(),
            }
            verify_xctest_pair(receipt, png, tree)
            tree.write_text('{"state_id": "manual-editor"}')
            with self.assertRaisesRegex(RuntimeError, "ui_json_sha256 mismatch"):
                verify_xctest_pair(receipt, png, tree)

    def test_run_state_marks_nonzero_capture_blocked(self):
        original_run = capture_plan.subprocess.run

        def fake_run(*args, **kwargs):
            return type("Completed", (), {"returncode": 3, "stdout": "no json", "stderr": "blocked"})()

        capture_plan.subprocess.run = fake_run
        try:
            with __import__("tempfile").TemporaryDirectory() as directory:
                root = Path(directory)
                result = capture_plan.run_state(
                    base_args=["--project-root", "."],
                    state={"page_id": "page_0001_HomeView", "state_id": "normal", "accessibility_command": "false"},
                    output_root=root,
                    skip_build=False,
                    timeout=1,
                )
                self.assertEqual(result["status"], "blocked")
                self.assertEqual(result["exit_code"], 3)
                self.assertTrue((root / "page_0001_HomeView" / "states" / "normal" / "capture-plan.log").is_file())
        finally:
            capture_plan.subprocess.run = original_run

    def test_run_state_passes_navigation_json_to_capture(self):
        original_run = capture_plan.subprocess.run
        commands = []

        def fake_run(command, *args, **kwargs):
            commands.append(command)
            return type("Completed", (), {"returncode": 0, "stdout": "", "stderr": ""})()

        capture_plan.subprocess.run = fake_run
        try:
            with __import__("tempfile").TemporaryDirectory() as directory:
                result = capture_plan.run_state(
                    base_args=["--project-root", "."],
                    state={
                        "page_id": "page_0003_BeanLibraryView",
                        "state_id": "normal",
                        "accessibility_command": "echo ok",
                        "navigation": {
                            "steps": [{"action": "tap", "target": {"element": "tab_button", "label": "豆档案"}}],
                            "anchors": [{"element": "navigation_bar", "label": "豆档案"}],
                        },
                    },
                    output_root=Path(directory),
                    skip_build=True,
                    timeout=1,
                )
                self.assertEqual(result["status"], "captured")
                self.assertEqual(len(commands), 1)
                self.assertIn("--navigation-json", commands[0])
                encoded = commands[0][commands[0].index("--navigation-json") + 1]
                self.assertIn("豆档案", encoded)
        finally:
            capture_plan.subprocess.run = original_run

    def test_write_manifests_creates_project_local_handoff(self):
        with __import__("tempfile").TemporaryDirectory() as directory:
            root = Path(directory)
            output_root = root / "tmp-capture"
            output_root.mkdir()
            manifest = {
                "schema_version": 1,
                "status": "captured",
                "output_root": str(output_root),
                "states": [],
            }
            paths = capture_plan.write_manifests(root, output_root, manifest)
            self.assertTrue(Path(paths["output_manifest"]).is_file())
            handoff = Path(paths["handoff_manifest"])
            self.assertTrue(handoff.is_file())
            self.assertEqual(json.loads(handoff.read_text())["output_root"], str(output_root))

    def test_output_manifest_only_preserves_the_current_project_handoff(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project = root / "app"
            handoff = project / "spec/execution/ios-runtime-capture/capture-plan-manifest.json"
            handoff.parent.mkdir(parents=True)
            handoff.write_text("current capture")
            output = root / "probe"
            manifest = {"status": "partial"}
            paths = capture_plan.write_manifests(project, output, manifest, output_manifest_only=True)
            self.assertEqual(paths["handoff_manifest"], paths["output_manifest"])
            self.assertEqual(handoff.read_text(), "current capture")
            self.assertEqual(json.loads(Path(paths["output_manifest"]).read_text())["status"], "partial")

    def test_handoff_stays_outside_read_only_source_when_it_is_the_project_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source = root / "ios"
            source.mkdir()
            output = root / "captures"
            manifest = {"status": "captured"}
            paths = capture_plan.write_manifests(source, output, manifest, source)
            self.assertEqual(paths["output_manifest"], paths["handoff_manifest"])
            self.assertEqual(list(source.iterdir()), [])
            self.assertEqual(json.loads(Path(paths["output_manifest"]).read_text())["handoff_manifest"],
                             paths["output_manifest"])
            with self.assertRaisesRegex(ValueError, "outside the iOS source root"):
                capture_plan.write_manifests(source, source / "output", manifest, source)

    def _temporary_plan(self, payload):
        import tempfile

        class PlanContext:
            def __enter__(self_inner):
                self_inner.directory = tempfile.TemporaryDirectory()
                self_inner.path = Path(self_inner.directory.name) / "plan.json"
                self_inner.path.write_text(json.dumps(payload), encoding="utf-8")
                return self_inner.path

            def __exit__(self_inner, exc_type, exc, traceback):
                self_inner.directory.cleanup()

        return PlanContext()


if __name__ == "__main__":
    unittest.main()
