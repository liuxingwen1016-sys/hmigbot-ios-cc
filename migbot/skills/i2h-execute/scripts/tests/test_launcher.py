import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sys

SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))
import _launcher  # noqa: E402


class LauncherTests(unittest.TestCase):
    def test_legacy_bundle_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "_entry.bin"
            binary.write_bytes(b"spec/.a2h/open-findings.json a2h-execute")
            compatible, reason = _launcher.bundle_compatibility(binary)
        self.assertFalse(compatible)
        self.assertIn("legacy bundle markers", reason)

    def test_current_bundle_requires_i2h_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "_entry.bin"
            binary.write_bytes(b"spec/.i2h/plan-coverage.json i2h-execute")
            compatible, reason = _launcher.bundle_compatibility(binary)
        self.assertTrue(compatible)
        self.assertEqual(reason, "current i2h bundle")

    def test_stale_bundle_uses_python_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "_entry.bin"
            binary.write_bytes(b"spec/.a2h/open-findings.json")
            stderr = io.StringIO()
            with patch.object(_launcher, "bundled_executable", return_value=binary), patch("sys.stderr", stderr):
                result = _launcher.dispatch("ui_delivery_gate", ["--project-root", "."], fallback=lambda argv: 17)
        self.assertEqual(result, 17)
        self.assertIn("using Python fallback", stderr.getvalue())

    def test_stale_bundle_without_fallback_blocks(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "_entry.bin"
            binary.write_bytes(b"spec/.a2h/open-findings.json")
            stderr = io.StringIO()
            with patch.object(_launcher, "bundled_executable", return_value=binary), patch("sys.stderr", stderr):
                result = _launcher.dispatch("ui_delivery_gate", [])
        self.assertEqual(result, 2)
        self.assertIn("no Python fallback", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
