import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from lib.ui_delivery_inputs_ios import freeze


class IOSDeliveryInputsTests(unittest.TestCase):
    def test_freeze_keeps_missing_runtime_evidence_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "ios"
            source.mkdir()
            (source / "Main.swift").write_text("struct Main {}", encoding="utf-8")
            inventory = root / "inventory.json"
            inventory.write_text(json.dumps({
                "schema_version": 2,
                "source_project_root": str(source),
                "scope": "full_ui",
                "units": [{
                    "unit_id": "ios.0001.Main",
                    "page_id": "page_0001_Main",
                    "required_states": [{"state_id": "default", "responsibility": "content"}],
                    "output": {"file": "entry/src/main/ets/pages/Main.ets"},
                }],
            }), encoding="utf-8")
            rc = freeze(["--project-root", str(root), "--inventory", str(inventory)])
            self.assertEqual(rc, 0)
            result = json.loads((root / "spec/execution/ui-inputs/index.json").read_text())
            self.assertEqual(len(result["packets"]), 1)
            self.assertEqual(result["packets"][0]["required_states"][0]["evidence"]["status"], "missing")


if __name__ == "__main__":
    unittest.main()
