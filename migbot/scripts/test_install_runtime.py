import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
INSTALLER = ROOT / "migbot/install.sh"


class InstallRuntimeTests(unittest.TestCase):
    def test_legacy_installer_options_and_runtime_entries(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project = root / "harmony"
            ios = root / "ios"
            project.mkdir()
            ios.mkdir()
            subprocess.run(
                [str(INSTALLER), "--project", str(project), "--ios", str(ios), "--lang", "en"],
                check=True,
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            config = json.loads((project / ".migbot/config.json").read_text())
            self.assertEqual(config["language"], "en")
            self.assertTrue(Path(config["ios"]).is_absolute() or config["ios"])
            for name in ("i2h", "i2h-tool", "i2h-bootstrap"):
                entry = project / ".migbot/bin" / name
                self.assertTrue(entry.is_file(), name)
                self.assertTrue(os.access(entry, os.X_OK), name)

    def test_upgrade_preserves_unknown_user_skill(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project = root / "harmony"
            project.mkdir()
            subprocess.run([str(INSTALLER), "--project", str(project)], check=True, cwd=ROOT, capture_output=True)
            custom = project / ".claude/skills/my-custom-skill/SKILL.md"
            custom.parent.mkdir(parents=True)
            custom.write_text("---\nname: my-custom-skill\n---\n")
            subprocess.run([str(INSTALLER), "--project", str(project)], check=True, cwd=ROOT, capture_output=True)
            self.assertTrue(custom.is_file())

    def test_installed_pipeline_resume_imports_shared_marker_contract(self):
        """The installed skill must resolve helpers from the project .migbot tree."""
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp) / "harmony"
            project.mkdir()
            subprocess.run([str(INSTALLER), "--project", str(project)], check=True, cwd=ROOT, capture_output=True)
            resume = project / ".claude/skills/i2h-plan/scripts/pipeline_resume.py"
            self.assertTrue(resume.is_file())
            completed = subprocess.run(
                [sys.executable, str(resume), "--project-root", str(project)],
                check=False,
                capture_output=True,
                text=True,
            )
            # An empty project is incomplete, but a missing marker_contract
            # import would fail before emitting the deterministic JSON status.
            self.assertEqual(completed.returncode, 1, completed.stderr)
            status = json.loads(completed.stdout.strip().splitlines()[-1])
            self.assertEqual(status["resume_stage"], "i2h-spec")


if __name__ == "__main__":
    unittest.main()
