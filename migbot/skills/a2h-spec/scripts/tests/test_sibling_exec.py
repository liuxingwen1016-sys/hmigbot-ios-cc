import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import sibling_exec as se  # noqa: E402


class SiblingExecTest(unittest.TestCase):
    def test_source_mode_uses_real_interpreter(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "dialog_inventory.py"
            script.write_text("def main(): pass\n", encoding="utf-8")
            with mock.patch.object(se, "_frozen", return_value=False):
                got = se._command_for(script, ["--compact"])
            self.assertEqual(got, [sys.executable, str(script), "--compact"])

    def test_frozen_cross_skill_uses_target_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            scripts = Path(tmp) / "android-ui-graph-builder/scripts"
            script = scripts / "dialog_inventory.py"
            script.parent.mkdir(parents=True)
            script.write_text("launcher", encoding="utf-8")
            entry = scripts / "bin" / se._platform_tag() / "_entry.dist" / se._ENTRY_NAME
            entry.parent.mkdir(parents=True)
            entry.write_text("binary", encoding="utf-8")
            entry.chmod(0o755)
            with mock.patch.object(se, "_frozen", return_value=True):
                got = se._command_for(script, ["--android-root", "/tmp/app"])
            self.assertEqual(got, [str(entry), "dialog_inventory", "--android-root", "/tmp/app"])

    def test_frozen_source_fallback_never_uses_bundled_executable(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "dialog_inventory.py"
            script.write_text("def main(): pass\n", encoding="utf-8")
            with mock.patch.object(se, "_frozen", return_value=True), \
                    mock.patch.object(se.shutil, "which", side_effect=lambda name: "/usr/bin/python3" if name == "python3" else None):
                got = se._command_for(script, [])
            self.assertEqual(got, ["/usr/bin/python3", str(script)])


if __name__ == "__main__":
    unittest.main()
