import json
import sys
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))
import ios_runtime_capture_plan as capture_plan  # noqa: E402


class CapturePlanTests(unittest.TestCase):
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
