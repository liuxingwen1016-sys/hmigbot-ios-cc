import os
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))
import ios_xctest_accessibility as helper  # noqa: E402


class ExternalAccessibilityProbeTests(unittest.TestCase):
    def test_append_probe_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Tests/UITests/CuikeUITests.swift"
            source.parent.mkdir(parents=True)
            source.write_text("import XCTest\nfinal class CuikeUITests: XCTestCase {}\n", encoding="utf-8")

            helper.append_probe(root, "Tests/UITests/CuikeUITests.swift")
            first = source.read_text(encoding="utf-8")
            helper.append_probe(root, "Tests/UITests/CuikeUITests.swift")
            second = source.read_text(encoding="utf-8")

            self.assertIn(helper.PROBE_MARKER, first)
            self.assertEqual(first, second)

    def test_run_probe_requires_output_environment(self):
        previous = os.environ.pop("TEST_RUNNER_I2H_UI_JSON_OUT", None)
        try:
            with tempfile.TemporaryDirectory() as directory:
                project = Path(directory) / "Cuike.xcodeproj"
                project.mkdir()
                args = type(
                    "Args",
                    (),
                    {
                        "project": str(project),
                        "scheme": "Cuike",
                        "destination": "platform=iOS Simulator,id=test",
                        "derived_data": str(Path(directory) / "dd"),
                        "test_source": "Tests/UITests/CuikeUITests.swift",
                        "log": None,
                        "timeout": 1,
                    },
                )()
                with self.assertRaisesRegex(RuntimeError, "I2H_UI_JSON_OUT"):
                    helper.run_probe(args)
        finally:
            if previous is not None:
                os.environ["TEST_RUNNER_I2H_UI_JSON_OUT"] = previous


if __name__ == "__main__":
    unittest.main()
