import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]


class PrepareDialogArtifactsTest(unittest.TestCase):
    def test_prepare_all_materializes_separate_dialog_snapshot(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            android = base / "android"
            project = base / "project"
            java = android / "app/src/main/java/com/example"
            layout = android / "app/src/main/res/layout"
            java.mkdir(parents=True)
            layout.mkdir(parents=True)
            project.mkdir()
            (java / "D.java").write_text(
                "package com.example;\n"
                "class Host extends Fragment { void x(){ new D().show(fm, null); } }\n"
                "class D extends DialogFragment { Object onCreateView(){ return inflater.inflate(R.layout.dialog_x); } }\n",
                encoding="utf-8")
            (layout / "dialog_x.xml").write_text(
                '<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android" '
                'android:layout_width="match_parent" android:layout_height="wrap_content"/>',
                encoding="utf-8")
            cmd = [sys.executable, str(SCRIPTS / "prepare_dialog_artifacts.py"),
                   "--project-root", str(project), "--android-root", str(android), "--prepare-all"]
            proc = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            inv = json.loads((project / "spec/.a2h/spec-run/dialog-inventory.json").read_text())
            d = next(x for x in inv["candidates"] if x["source_fqn"] == "com.example.D")
            snap = project / d["snapshot_ref"]
            self.assertTrue((snap / "meta.json").is_file())
            self.assertTrue((snap / "view.xml").is_file())
            self.assertEqual(json.loads((snap / "meta.json").read_text())["activity"], "com.example.D")
            self.assertFalse((project / "spec/baseline/ui-snapshots").exists())


if __name__ == "__main__":
    unittest.main()
