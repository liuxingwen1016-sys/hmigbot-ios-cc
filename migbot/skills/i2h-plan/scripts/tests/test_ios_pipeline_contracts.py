import json
import tempfile
import unittest
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "i2h-spec/scripts"))
sys.path.insert(0, str(ROOT / "i2h-plan/scripts"))

import ui_evidence
import ui_delivery
import ui_state_ownership


class IOSPipelineContractTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "Views").mkdir()
        (self.root / "Views/HomeView.swift").write_text(
            'import SwiftUI\nstruct HomeView: View {\n'
            '  @State private var count: Int = 0\n'
            '  var body: some View { VStack { Button("Go") { count += 1 } } }\n}\n',
            encoding="utf-8",
        )
        (self.root / "Assets.xcassets/Accent.colorset").mkdir(parents=True)
        (self.root / "Assets.xcassets/Accent.colorset/Contents.json").write_text(
            '{"colors":[{"idiom":"universal","color":{"components":{"red":"1.0","green":"0.0","blue":"0.0","alpha":"1.0"}}}]}',
            encoding="utf-8",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_evidence_and_res_index_share_hash(self):
        output = self.root / "spec/.i2h/resources-inventory.json"
        ui_evidence.run(str(self.root), str(output), str(self.root / "spec/baseline/res-index"))
        evidence = json.loads(output.read_text())
        expected = evidence["target_input_sha256"]
        for path in (self.root / "spec/baseline/res-index").glob("*.json"):
            self.assertEqual(json.loads(path.read_text())["target_input_sha256"], expected)
        self.assertEqual(json.loads((output.parent / "target-input.json").read_text())["target_input_sha256"], expected)
        self.assertEqual(evidence["resources"]["summary"]["view_count"], 1)

    def test_project_skeleton_is_generated_from_same_evidence(self):
        output = self.root / "spec/.i2h/resources-inventory.json"
        ui_evidence.run(str(self.root), str(output), str(self.root / "spec/baseline/res-index"))
        skeleton = ui_evidence.build_skeleton(json.loads(output.read_text()))
        self.assertEqual(skeleton["swiftui_views"][0]["class_name"], "HomeView")
        self.assertEqual(skeleton["target_input_sha256"], json.loads(output.read_text())["target_input_sha256"])

    def test_delivery_draft_validates_and_ownership_is_explicit(self):
        output = self.root / "spec/.i2h/resources-inventory.json"
        ui_evidence.run(str(self.root), str(output), str(self.root / "spec/baseline/res-index"))
        inventory = ui_delivery.draft(self.root, self.root / "draft.json")
        checked = ui_delivery.validate(self.root, inventory)
        self.assertEqual(checked["status"], "validated")
        approved = ui_delivery.approve(self.root, checked, "test:review")
        self.assertEqual(approved["status"], "approved")
        ownership = ui_state_ownership.review(self.root, approved)
        self.assertEqual(ownership["status"], "PASS")

    def test_delivery_keeps_external_ios_source_root_and_hashes_refs(self):
        harmony = self.root / "harmony"
        harmony.mkdir()
        output = harmony / "spec/.i2h/resources-inventory.json"
        ui_evidence.run(str(self.root), str(output), str(harmony / "spec/baseline/res-index"))
        inventory = ui_delivery.draft(harmony, harmony / "draft.json")
        self.assertEqual(inventory["source_project_root"], str(self.root.resolve()))
        self.assertIn("sha256", inventory["units"][0]["source_refs"][0])
        self.assertEqual(ui_delivery.validate(harmony, inventory)["status"], "validated")

    def test_duplicate_content_ownership_fails(self):
        inventory = {
            "schema_version": 2,
            "scope": "full_ui",
            "units": [
                {"unit_id": "a", "owned_ui_roles": ["content"], "required_states": [{"state_id": "default", "arrival_mode": "preview", "responsibility": "content"}]},
                {"unit_id": "b", "owned_ui_roles": ["content"], "required_states": [{"state_id": "default", "arrival_mode": "preview", "responsibility": "content"}]},
            ],
        }
        result = ui_state_ownership.review(self.root, inventory)
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("DUPLICATE_CONTENT_OWNERSHIP", {item["code"] for item in result["errors"]})

    def test_default_content_state_is_scoped_per_page(self):
        inventory = {
            "schema_version": 2,
            "scope": "full_ui",
            "units": [
                {"unit_id": "home", "page_id": "page_home", "owned_ui_roles": ["content"],
                 "required_states": [{"state_id": "default", "arrival_mode": "preview", "responsibility": "content"}]},
                {"unit_id": "settings", "page_id": "page_settings", "owned_ui_roles": ["content"],
                 "required_states": [{"state_id": "default", "arrival_mode": "preview", "responsibility": "content"}]},
            ],
        }
        result = ui_state_ownership.review(self.root, inventory)
        self.assertEqual(result["status"], "PASS")


if __name__ == "__main__":
    unittest.main()
