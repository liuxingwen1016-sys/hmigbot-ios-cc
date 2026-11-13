from contextlib import redirect_stdout
from hashlib import sha256
from io import StringIO
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
from gate_plan_complete import GateCheck, PlanCompletionGate


class IOSPipelineContractTest(unittest.TestCase):
    def test_strict_visual_validation_refuses_unpaired_draft_before_approval(self):
        manifest = self.root / "draft.json"
        receipt = self.root / "receipt.json"
        inventory = {"schema_version": 2, "status": "draft", "units": [
            {"unit_id": "u", "page_id": "p", "owned_ui_roles": ["content"],
             "output": {"file": "entry/src/main/ets/Home.ets", "symbol": "Home"},
             "required_states": [{"state_id": "normal", "arrival_mode": "formal"}]}
        ], "verification_states": [
            {"verification_id": "bad", "owner": "other", "page_id": "p", "state_id": "normal"}
        ]}
        ui_delivery.write(manifest, inventory)
        flags = ["--project-root", str(self.root), "--inventory", str(manifest), "--require-runtime-plan"]
        self.assertEqual(ui_delivery.main(["validate", *flags, "--receipt-only", "--out", str(receipt)]), 2)
        self.assertEqual({row["code"] for row in json.loads(receipt.read_bytes())["validation"]["errors"]},
                         {"unbound_verification_rows", "missing_visual_states"})
        with self.assertRaisesRegex(ValueError, "unbound_verification_rows"):
            ui_delivery.approve(self.root, inventory, "fixture confirmation", require_runtime_plan=True)
        inventory["verification_states"] = []
        ui_delivery.write(manifest, ui_delivery.add_visual_pairs(inventory))
        self.assertEqual(ui_delivery.main(["validate", *flags, "--receipt-only", "--out", str(receipt)]), 0)

    def test_pair_states_keeps_journey_and_fills_only_missing_visual_pairs(self):
        draft = {"schema_version": 2, "status": "draft", "units": [
            {"unit_id": "u", "page_id": "p", "required_states": [
                {"state_id": "normal", "arrival_mode": "formal"}, {"state_id": "editing", "arrival_mode": "formal"}
            ]}
        ], "verification_states": [
            {"verification_id": "normal-pair", "owner": "u", "page_id": "p", "state_id": "normal"},
            {"page_id": "p", "state_id": "journey", "source_test": "Tests.swift#testJourney"},
        ]}
        result = ui_delivery.add_visual_pairs(draft)
        self.assertEqual(result["behavior_journeys"], [draft["verification_states"][1]])
        self.assertEqual(result["verification_states"][0], draft["verification_states"][0])
        self.assertEqual(result["verification_states"][1]["state_id"], "editing")
        self.assertEqual(ui_delivery.add_visual_pairs(result), result)
        with self.assertRaisesRegex(ValueError, "requires a schema-2 draft"):
            ui_delivery.add_visual_pairs({**draft, "status": "approved"})
        draft["units"].append({"unit_id": "other", "page_id": "p", "required_states": [{"state_id": "editing"}]})
        with self.assertRaisesRegex(ValueError, "explicit visual owner"):
            ui_delivery.add_visual_pairs(draft)

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

    def test_plan_gate_success_preserves_canonical_marker(self):
        gate = PlanCompletionGate(str(self.root))
        gate.checks = [GateCheck('plan check', True, 'valid')]
        marker = gate.plans_dir / 'complete.txt'
        marker.parent.mkdir(parents=True)
        original = b'{"schema_version":2,"stage":"i2h-plan","status":"PASS"}\n'
        marker.write_bytes(original)
        with redirect_stdout(StringIO()):
            gate._print_results()
        self.assertEqual(marker.read_bytes(), original)
        marker.unlink()
        with redirect_stdout(StringIO()):
            gate._print_results()
        self.assertFalse(marker.exists())

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

    def test_delivery_preserves_modal_presentation_and_embedded_components(self):
        (self.root / "App").mkdir()
        (self.root / "App/CuikeApp.swift").write_text(
            "import SwiftUI\n"
            "struct RootView: View {\n"
            "  var body: some View {\n"
            "    TabView { HomeView() }\n"
            "      .sheet(isPresented: .constant(true)) { SettingsView() }\n"
            "      .fullScreenCover(isPresented: .constant(false)) { BrewView() }\n"
            "  }\n}\n",
            encoding="utf-8",
        )
        (self.root / "Views/SettingsView.swift").write_text(
            "import SwiftUI\nstruct SettingsView: View { var body: some View { Text(\"Settings\") } }\n",
            encoding="utf-8",
        )
        (self.root / "Views/BrewView.swift").write_text(
            "import SwiftUI\nstruct BrewView: View { var body: some View { Text(\"Brew\") } }\n",
            encoding="utf-8",
        )
        (self.root / "Views/Theme.swift").write_text(
            "import SwiftUI\nstruct PrimaryButton: View { var body: some View { Button(\"Go\") {} } }\n",
            encoding="utf-8",
        )
        output = self.root / "spec/.i2h/resources-inventory.json"
        ui_evidence.run(str(self.root), str(output), str(self.root / "spec/baseline/res-index"))
        inventory = ui_delivery.draft(self.root, self.root / "draft.json")
        by_name = {unit["component"]: unit for unit in inventory["units"]}
        self.assertEqual(by_name["ios.SettingsView"]["presentation_role"], "hosted_destination")
        self.assertEqual(by_name["ios.SettingsView"]["presentation"]["harmony_mapping"], "bindSheet")
        self.assertEqual(by_name["ios.BrewView"]["presentation"]["harmony_mapping"], "bindContentCover")
        self.assertNotIn("ios.PrimaryButton", by_name)
        self.assertIn(
            "PrimaryButton",
            {item["view_name"] for item in inventory["component_exclusions"]},
        )

    def test_delivery_carries_source_ui_obligations(self):
        (self.root / "Views/SettingsView.swift").write_text(
            'import SwiftUI\nstruct SettingsView: View {\n'
            '  var body: some View { Form { Picker("外观", selection: .constant(0)) { Text("跟随系统") }\n'
            '    Toggle("通知", isOn: .constant(true))\n'
            '    Button("完成") {} } }\n}\n',
            encoding="utf-8",
        )
        output = self.root / "spec/.i2h/resources-inventory.json"
        ui_evidence.run(str(self.root), str(output), str(self.root / "spec/baseline/res-index"))
        inventory = ui_delivery.draft(self.root, self.root / "draft.json")
        settings = next(unit for unit in inventory["units"] if unit["component"] == "ios.SettingsView")
        obligations = settings["source_obligations"]
        self.assertEqual([row["kind"] for row in obligations["interactive_controls"]], ["picker", "toggle", "button"])
        self.assertTrue(obligations["has_form"])

    def test_plan_requires_every_explicit_swiftui_tab_host_slot(self):
        (self.root / "Views/RootView.swift").write_text(
            'struct RootView: View {\n'
            '  var body: some View {\n'
            '    TabView(selection: $selection) {\n'
            '      NavigationStack { HomeView() }.tabItem { Text("Home") }\n'
            '      Tab("Saved", systemImage: "star") { NavigationStack { SavedView() } }\n'
            '      // OtherView().tabItem { Text("Comment") }\n'
            '    }.sheet(isPresented: $show) { OtherView() }\n'
            '  }\n}\n',
            encoding="utf-8",
        )
        for view in ("SavedView", "OtherView"):
            (self.root / f"Views/{view}.swift").write_text(
                f'struct {view}: View {{ var body: some View {{ Text("Body") }} }}',
                encoding="utf-8",
            )
        evidence = self.root / "spec/.i2h/resources-inventory.json"
        ui_evidence.run(str(self.root), str(evidence), str(self.root / "spec/baseline/res-index"))
        draft = self.root / "draft.json"
        inventory = ui_delivery.draft(self.root, draft)
        units = {unit["output"]["symbol"]: unit for unit in inventory["units"]}
        self.assertNotIn("swiftui_tab_roots", units["OtherView"]["presentation"])
        errors = ui_delivery.validate_tab_integrations(self.root, inventory)
        self.assertEqual([(row["child"], row["source_ref"]["line"]) for row in errors],
                         [("HomeView", 4), ("SavedView", 5)])
        receipt = self.root / "validation.json"
        with redirect_stdout(StringIO()):
            code = ui_delivery.main(["validate", "--receipt-only", "--project-root", str(self.root),
                                     "--inventory", str(draft), "--out", str(receipt)])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(receipt.read_bytes())["validation"]["errors"], errors)
        with self.assertRaisesRegex(ValueError, "SWIFTUI_TAB_HOST_SLOT_MISSING"):
            ui_delivery.approve(self.root, inventory, "confirmation")

        host = units["RootView"]["output"]
        for error in errors:
            child = error["child"]
            units[child]["integration"] = {
                "host_file": host["file"], "host_builder": f'{host["symbol"]}.tabContent',
                "child_symbol": child, "source_ref": error["source_ref"],
            }
        self.assertEqual(ui_delivery.approve(self.root, inventory, "confirmation")["status"], "approved")
        units["SavedView"]["integration"]["host_file"] = units["OtherView"]["output"]["file"]
        self.assertEqual([row["child"] for row in ui_delivery.validate_tab_integrations(self.root, inventory)],
                         ["SavedView"])

    def test_approval_reuses_single_manifest_and_keeps_the_validation_digest(self):
        evidence = self.root / "spec/.i2h/resources-inventory.json"
        ui_evidence.run(str(self.root), str(evidence), str(self.root / "spec/baseline/res-index"))
        manifest = self.root / "spec/baseline/ui-delivery-approved.json"
        ui_delivery.draft(self.root, manifest)
        receipt = evidence.with_name("ui-delivery-validation.json")
        common = ["--project-root", str(self.root), "--inventory", str(manifest)]
        with redirect_stdout(StringIO()):
            self.assertEqual(ui_delivery.main(["validate", "--receipt-only", *common, "--out", str(receipt)]), 0)
            candidate = manifest.read_bytes()
            validation = receipt.read_bytes()
            self.assertEqual(ui_delivery.main(["approve", *common, "--confirmation-ref", "confirmed",
                                               "--validation-receipt", str(receipt), "--out", str(manifest)]), 0)
        approved = json.loads(manifest.read_bytes())
        self.assertEqual(approved["status"], "approved")
        self.assertEqual(approved["units"], json.loads(candidate)["units"])
        self.assertEqual(approved["approval"]["candidate_sha256"], sha256(candidate).hexdigest())
        self.assertEqual(approved["approval"]["validation_receipt_sha256"], sha256(validation).hexdigest())
        self.assertEqual(list(manifest.parent.glob("*delivery*.json")), [manifest])
        self.assertEqual(receipt.read_bytes(), validation)

    def test_delivery_derives_immersive_safearea_from_source(self):
        (self.root / "Views/FullScreenView.swift").write_text(
            'import SwiftUI\nstruct FullScreenView: View {\n'
            '  var body: some View { Color.black.ignoresSafeArea() }\n}\n',
            encoding="utf-8",
        )
        output = self.root / "spec/.i2h/resources-inventory.json"
        ui_evidence.run(str(self.root), str(output), str(self.root / "spec/baseline/res-index"))
        inventory = ui_delivery.draft(self.root, self.root / "draft.json")
        unit = next(item for item in inventory["units"] if item["component"] == "ios.FullScreenView")
        self.assertTrue(unit["needs_immersive_safearea"])
        self.assertEqual(unit["immersive_safearea"]["evidence"][0]["kind"], "ignoresSafeArea")
        self.assertEqual(ui_delivery.validate(self.root, inventory)["status"], "validated")

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

    def test_delivery_rejects_inconsistent_presentation_mapping(self):
        output = self.root / "spec/.i2h/resources-inventory.json"
        ui_evidence.run(str(self.root), str(output), str(self.root / "spec/baseline/res-index"))
        inventory = ui_delivery.draft(self.root, self.root / "draft.json")
        inventory["units"][0]["presentation_role"] = "hosted_destination"
        inventory["units"][0]["presentation"]["source"] = ".sheet"
        inventory["units"][0]["presentation"]["harmony_mapping"] = "NavDestination"
        checked = ui_delivery.validate(self.root, inventory)
        self.assertEqual(checked["status"], "invalid")
        codes = {item["code"] for item in checked["validation"]["errors"]}
        self.assertIn("PRESENTATION_MAPPING_MISMATCH", codes)
        self.assertIn("SHEET_MAPPING_MISMATCH", codes)

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
