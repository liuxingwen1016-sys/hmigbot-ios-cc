"""New-project end-to-end regressions for runtime references and UI delivery."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib

SKILLS = Path(__file__).resolve().parents[3]
for skill in ("a2h-spec", "a2h-plan", "a2h-execute"):
    sys.path.insert(0, str(SKILLS / skill / "scripts"))
import ui_evidence as evidence
import promote_android_fast_traverse as promoter
import runtime_view
import ui_pipeline
import ui_delivery
import ui_delivery_inputs
import validate_runtime_snapshots
import ui_stage1_gate
import stage1_visual_scope
import stage1_acceptance
import stage1_reachability
import ui_dispatch
import runtime_inputs

def png():
    def chunk(kind, payload):
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 320, 640, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress((b"\0" + b"\0" * 960) * 640)) + chunk(b"IEND", b""))

class DeliveryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.spec = self.root / "spec"
        self.run = self.spec / ".a2h/android-fast-traverse/run1/android_traverse_screenshots"
        self.source = self.root / "android/Main.kt"
        self.source.parent.mkdir()
        self.source.write_text("class Main { val child = ForecastFragment() }\n")
        self.citation = {"file": str(self.source), "line": 1}
        self.pages = ["page_0001_Main", "page_0002_Forecast", "page_0003_Vip"]
        for page, activity in zip(self.pages, ["org.source.Main", "org.source.Forecast", "org.source.Vip"]):
            snap = self.spec / "baseline/ui-snapshots" / page
            evidence.save(snap / "meta.json", {"activity": activity, "view_xml_origin": "static_synthetic"})
            (snap / "view.xml").write_text('<hierarchy synthesized="true"><node class="LinearLayout" bounds=""/></hierarchy>')
        self.records = [self.capture("page_0040_Main", "weather", 2), self.capture("manual_0068_Main", "forecast", 1)]
        evidence.save(self.run / "index.json", self.records)
        evidence.save(self.run / "_aft/state.json", {"status": "completed_with_gaps", "package": "org.installed",
                                                     "serial": "test-device", "density": 420})
        evidence.save(self.run / "_aft/report.json", {"status": "completed_with_gaps"})
        self.mapping = {"schema_version": 3, "pages": [
            {"page_id": self.pages[0], "states": [
                {"state_id": "weather", "source_page_ids": [self.records[0]["page_id"]], "review": "weather content"},
                {"state_id": "forecast", "source_page_ids": [self.records[1]["page_id"]], "review": "forecast tab"}]},
            {"page_id": self.pages[1], "states": [], "host_bindings": [
                {"state_id": "default", "host_page_id": self.pages[0], "host_state_id": "forecast",
                 "source_component": "org.source.ForecastFragment", "source_refs": [self.citation],
                 "region_px": [10, 10, 300, 500], "review": "source binds forecastTab to this content"}]},
            {"page_id": self.pages[2], "states": [], "zero_mapping": {
                "status": "condition_unmet", "reason": "login gate", "source_refs": [self.citation]}}]}

    def tearDown(self):
        self.tmp.cleanup()

    def capture(self, capture_id, label, count):
        capture_dir = self.run / capture_id
        capture_dir.mkdir(parents=True)
        pngs, xmls = [], []
        for i in range(count):
            p, x = capture_dir / f"{i}.png", capture_dir / f"{i}.xml"
            p.write_bytes(png())
            x.write_text('<hierarchy><node package="org.installed" class="FrameLayout" bounds="[0,0][320,640]">'
                         '<node class="TextView" resource-id="org.installed:id/hky" text="' + label +
                         '" bounds="[20,20][200,100]" clickable="true"/></node></hierarchy>')
            pngs.append(p.relative_to(self.run).as_posix())
            xmls.append(x.relative_to(self.run).as_posix())
        meta = {"page_id": capture_id, "timestamp": "2026-10-19T00:00:00Z", "activity_info": {"resumed_activity": "org.installed/org.source.Main"},
                "screenshots": pngs, "view_xmls": xmls, "screenshot": pngs[0], "view_xml": xmls[0],
                "density_factor": 2.625, "aft": {"kind": "manual", "drift": None}}
        evidence.save(capture_dir / "meta.json", meta)
        return meta

    def promote(self):
        return promoter.promote(self.root, self.run, self.mapping)

    def inventory(self):
        return {"schema_version": 1, "scope": "full_ui", "approved": True, "approved_by": "plan-gate",
                "budget": {"text_tokens_per_window": 1000, "pngs_per_window": 1},
                "units": [{
                    "unit_id": "main.shell", "page_id": self.pages[0], "component": "org.source.Main",
                    "presentation_role": "routed_page", "required": True,
                    "required_states": [{"state_id": "weather", "arrival_mode": "formal"},
                                        {"state_id": "forecast", "arrival_mode": "preview"}],
                    "source_refs": [self.citation], "generation_owner": "main", "integration_owner": "closer",
                    "output": {"file": "entry/src/main/ets/pages/MainPage.ets", "symbol": "MainPage", "builder": "build"},
                    "input_alternatives": {}, "integration": None},
                    {"unit_id": "main.forecast", "page_id": self.pages[1], "component": "org.source.ForecastFragment",
                     "presentation_role": "embedded", "required": True,
                     "required_states": [{"state_id": "default", "arrival_mode": "preview"}],
                     "source_refs": [self.citation], "generation_owner": "forecast", "integration_owner": "closer",
                     "output": {"file": "entry/src/main/ets/components/ForecastContent.ets", "symbol": "ForecastContent", "builder": "build"},
                     "integration": {"host_file": "entry/src/main/ets/pages/MainPage.ets",
                                     "host_builder": "tabWeatherLine", "child_symbol": "ForecastContent"},
                     "input_alternatives": {}}],
                "exclusions": [{"page_id": self.pages[2], "reason": "selected channel excludes VIP",
                                "decision_ref": "plan-gate", "source_refs": [self.citation]}]}

    def frozen(self):
        self.promote()
        path = self.spec / "baseline/plans/stage1-ui-delivery.json"
        evidence.save(path, ui_delivery.approve(self.root, self.inventory(), "session:test-user-approval"))
        ui_delivery_inputs.freeze(self.root, path)
        return validate_runtime_snapshots.load_packets(self.root)

    def code_and_reports(self):
        packets = self.frozen()
        for packet_path, packet in packets:
            unit = packet["unit"]
            dispatched = ui_dispatch.dispatch(self.root, unit["unit_id"])
            path = self.root / unit["output"]["file"]
            path.parent.mkdir(parents=True, exist_ok=True)
            code = ("struct MainPage { build() { Column() { Text('weather') } }\n"
                    "@Builder tabWeatherLine() { ForecastContent() }\n}\n") if unit["unit_id"] == "main.shell" else (
                    "struct ForecastContent { build() { Column() { Text('forecast') } } }\n")
            path.write_text(code)
            report = {"unit_id": unit["unit_id"], "dispatch_id": dispatched["dispatch_id"], "packet_sha256": evidence.digest(packet_path),
                      "input_applications": [{"input_id": i["input_id"], "code_anchor": {"file": unit["output"]["file"], "line": 1}}
                                             for i in packet["required_inputs"]],
                      "state_implementations": [{"state_id": s["state_id"], "symbol": unit["output"]["symbol"]}
                                                for s in unit["required_states"]]}
            evidence.save(self.spec / "execution/conversion-reports" / (unit["unit_id"] + ".json"), report)
            ui_dispatch.complete(self.root, dispatched["dispatch_id"])
        return packets

    def test_preflight_needs_selection_partial_and_ready(self):
        result = ui_pipeline.preflight(self.root)
        self.assertEqual(result["status"], "needs_selection")
        self.assertFalse(result["dispatch_allowed"])
        evidence.save(self.spec / ".a2h/ui-capture-policy.json", {"ui_facts_policy": "static-v1"})
        self.assertEqual(ui_pipeline.preflight(self.root)["missing_fields"], ["runtime_capture_policy"])
        ui_pipeline.configure(argparse.Namespace(project_root=self.root, facts="static-v1", runtime="progressive", reason="test user choice"))
        self.assertTrue(ui_pipeline.preflight(self.root)["dispatch_allowed"])

    def test_invalid_policy_does_not_dispatch(self):
        evidence.save(self.spec / ".a2h/ui-capture-policy.json", {"ui_facts_policy": "invalid"})
        self.assertEqual(ui_pipeline.preflight(self.root)["status"], "invalid")

    def test_mapping_uses_full_class_all_frames_and_preserves_static_tree(self):
        static = (self.spec / "baseline/ui-snapshots" / self.pages[0] / "view.xml").read_bytes()
        draft = promoter.draft(self.root, self.run)
        self.assertEqual(len(draft["pages"][0]["states"]), 2)
        self.promote()
        states = evidence.validate_refs(self.spec, self.pages[0])
        self.assertEqual([len(s["frames"]) for s in states], [2, 1])
        self.assertEqual((self.spec / "baseline/ui-snapshots" / self.pages[0] / "view.xml").read_bytes(), static)
        self.assertFalse(list((self.spec / "baseline/ui-snapshots").glob("**/android-runtime.png")))
        self.assertFalse(list((self.spec / "baseline/ui-snapshots").glob("**/view.static.xml")))

    def test_identity_mismatch_rejected_before_any_reference_write(self):
        self.mapping["pages"][0]["page_id"], self.mapping["pages"][2]["page_id"] = self.pages[2], self.pages[0]
        with self.assertRaisesRegex(ValueError, "Activity"):
            self.promote()
        self.assertFalse(list((self.spec / "baseline/ui-snapshots").glob("*/runtime-refs.json")))

    def test_draft_states_require_semantic_review(self):
        with self.assertRaisesRegex(ValueError, "review"):
            promoter.promote(self.root, self.run, promoter.draft(self.root, self.run))

    def test_host_binding_resolves_scoped_nodes(self):
        packets = self.frozen()
        child = next(p for _, p in packets if p["unit_id"] == "main.forecast")
        tree = evidence.read(self.spec / child["states"][0]["frames"][0]["parsed"]["path"])
        self.assertEqual(tree["node_count"], 1)
        self.assertEqual(tree["nodes"][0]["text"], "forecast")
        self.assertAlmostEqual(tree["nodes"][0]["bounds_vp"][0], 20 / 2.625, places=3)

    def test_reference_hash_change_detected(self):
        self.promote()
        path = self.run / self.records[0]["view_xml"]
        path.write_text("<hierarchy/>")
        with self.assertRaisesRegex(ValueError, "hash"):
            evidence.validate_refs(self.spec, self.pages[0])

    def test_missing_required_state_cannot_be_silently_dropped(self):
        self.promote()
        inventory = self.inventory()
        inventory["units"][0]["required_states"].append({"state_id": "calendar", "arrival_mode": "preview"})
        path = self.spec / "baseline/plans/stage1-ui-delivery.json"
        evidence.save(path, ui_delivery.approve(self.root, inventory, "session:test-approval"))
        with self.assertRaisesRegex(ValueError, "required state"):
            ui_delivery_inputs.freeze(self.root, path)

    def test_packet_input_removal_breaks_dispatch_seal(self):
        packets = self.frozen()
        path, packet = packets[0]
        packet["required_inputs"].pop()
        evidence.save(path, packet)
        with self.assertRaisesRegex(ValueError, "hash"):
            validate_runtime_snapshots.load_packets(self.root)

    def test_camelcase_and_comment_only_host_slots_fail(self):
        self.code_and_reports()
        self.assertEqual(ui_stage1_gate.check(self.root)["status"], "PASS")
        path = self.root / "entry/src/main/ets/pages/MainPage.ets"
        path.write_text("struct MainPage { build() { Column() {} }\n"
                        "@Builder tabWeatherLine() { /* ForecastContent() */ }\n}\n")
        result = ui_stage1_gate.check(self.root)
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(any("slot" in e["detail"] for e in result["errors"]))

    def test_converter_cannot_omit_input_application(self):
        self.code_and_reports()
        path = self.spec / "execution/conversion-reports/main.shell.json"
        report = evidence.read(path)
        report["input_applications"].pop()
        evidence.save(path, report)
        self.assertEqual(ui_stage1_gate.check(self.root)["status"], "FAIL")

    def test_visual_scope_uses_explicit_pairs_and_referenced_baselines(self):
        self.frozen()
        scope = stage1_visual_scope.build_scope(self.root)
        self.assertEqual(len(scope["pairs"]), 3)
        self.assertEqual({p["arrival_mode"] for p in scope["pairs"]}, {"formal", "preview"})
        self.assertEqual(len(scope["pairs"][0]["android_frames"]), 1)

    def test_xml_parser_completes_large_single_line(self):
        path = self.root / "long.xml"
        path.write_text("<hierarchy>" + '<node class="TextView" text="large" bounds="[0,0][10,10]"/>' * 2000 + "</hierarchy>")
        tree = runtime_view.parse_view(path, 2.625)
        self.assertGreater(tree["source_bytes"], 79000)
        self.assertEqual(tree["node_count"], 2000)

    def test_path_escape_rejected(self):
        with self.assertRaisesRegex(ValueError, "outside"):
            evidence.inside(self.spec, "../android/Main.kt")

    def test_source_change_invalidates_input_packet(self):
        self.frozen()
        self.source.write_text("changed source\n")
        with self.assertRaisesRegex(ValueError, "source decision changed"):
            validate_runtime_snapshots.load_packets(self.root)

    def test_imported_page_is_not_reported_as_runtime_reachable(self):
        pages = self.root / "entry/src/main/ets/pages"
        pages.mkdir(parents=True)
        (pages / "Index.ets").write_text("import MainPage from './MainPage';")
        (pages / "MainPage.ets").write_text("struct MainPage {}")
        self.assertIn((pages / "MainPage.ets").resolve(), stage1_reachability.reachable(self.root.resolve(), (pages/'Index.ets').resolve()))
        report=stage1_reachability.check(self.root,{'schema_version':1,'unit_id':'imports',
            'entry_file':'entry/src/main/ets/pages/Index.ets','pages':[{'page_id':self.pages[0],
            'state_id':'weather','output_file':'entry/src/main/ets/pages/MainPage.ets'}]})
        self.assertEqual(report['analysis'],'static_import_graph_only_not_runtime_navigation')
        self.assertNotIn('arrival_verified',report)

    def test_repair_budget_cannot_reset_using_new_report_name(self):
        self.code_and_reports()
        stage1_acceptance.archive_generation(self.root, "g0")
        scope_path = self.spec / "execution/stage1-visual-scope.json"
        evidence.save(scope_path, stage1_visual_scope.build_scope(self.root))
        for i in range(3):
            report = self.spec / f"execution/compile-candidate-{i}.json"
            evidence.save(report, {"status": "FAIL", "scope_sha256": evidence.digest(scope_path)})
            result = stage1_acceptance.record(self.root, scope_path, report, "compile")
            self.assertEqual(result["status"], "FAIL" if i == 2 else "REPAIR_REQUIRED")
        with self.assertRaisesRegex(ValueError, "terminal"):
            stage1_acceptance.record(self.root, scope_path, report, "compile")

    def test_empty_container_and_wrong_component_cannot_pass(self):
        self.code_and_reports()
        path = self.root / "entry/src/main/ets/pages/MainPage.ets"
        path.write_text("struct Helper { build() { Text('helper') } }\n"
                        "struct MainPage { build() { Column() {} }\n"
                        "@Builder tabWeatherLine() { ForecastContent() } }")
        result = ui_stage1_gate.check(self.root)
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("empty", result["errors"][0]["detail"])

    def test_composition_child_cannot_disappear_from_delivery_scope(self):
        self.promote()
        evidence.save(self.spec / "baseline/ui-snapshots" / self.pages[0] / "visual.json",
                      {"composition": {"children": [{"kind": "fragment", "class": "org.source.CalendarFragment"}]}})
        with self.assertRaisesRegex(ValueError, "composition child missing"):
            ui_delivery.validate(self.root, self.inventory())

    def test_required_bottom_bar_cannot_remain_empty(self):
        self.promote()
        inventory = self.inventory()
        inventory["units"][0]["required_builders"] = ["tabBar"]
        path = self.spec / "baseline/plans/stage1-ui-delivery.json"
        evidence.save(path, ui_delivery.approve(self.root, inventory, "session:test-approval"))
        ui_delivery_inputs.freeze(self.root, path)
        packets = validate_runtime_snapshots.load_packets(self.root)
        for packet_path, packet in packets:
            unit = packet["unit"]
            out = self.root / unit["output"]["file"]
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text("struct " + unit["output"]["symbol"] + " { build() { Text('content') } }")
        result = ui_stage1_gate.check(self.root)
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("tabBar", result["errors"][0]["detail"])

    def test_source_only_state_keeps_visual_blocked(self):
        self.promote()
        inventory = self.inventory()
        unit = copy.deepcopy(inventory["units"][0])
        unit.update(unit_id="vip", page_id=self.pages[2], component="org.source.Vip",
                    required_states=[{"state_id": "default", "arrival_mode": "preview"}],
                    output={"file": "entry/src/main/ets/pages/VipPage.ets", "symbol": "VipPage", "builder": "build"},
                    input_alternatives={})
        inventory["units"].append(unit)
        inventory["exclusions"] = []
        path = self.spec / "baseline/plans/stage1-ui-delivery.json"
        evidence.save(path, ui_delivery.approve(self.root, inventory, "session:test-approval"))
        ui_delivery_inputs.freeze(self.root, path)
        scope = stage1_visual_scope.build_scope(self.root)
        self.assertEqual(next(p for p in scope["pairs"] if p["unit_id"] == "vip")["status"], "BLOCKED")

    def test_generation_archive_preserves_first_code(self):
        self.code_and_reports()
        original = (self.root / "entry/src/main/ets/pages/MainPage.ets").read_bytes()
        stage1_acceptance.archive_generation(self.root, "g0")
        (self.root / "entry/src/main/ets/pages/MainPage.ets").write_text("changed")
        archived = self.spec / "execution/stage1-generation/g0/entry/src/main/ets/pages/MainPage.ets"
        self.assertEqual(archived.read_bytes(), original)
        with self.assertRaisesRegex(ValueError, "never overwrite"):
            stage1_acceptance.archive_generation(self.root, "g0")

    def test_reference_pair_redirect_is_rejected_even_with_correct_hash(self):
        self.promote()
        path = self.spec / "baseline/ui-snapshots" / self.pages[0] / "runtime-refs.json"
        refs = evidence.read(path)
        refs["states"][0]["frames"][0]["png"] = refs["states"][1]["frames"][0]["png"]
        evidence.save(path, refs)
        with self.assertRaisesRegex(ValueError, "pairing"):
            evidence.validate_refs(self.spec, self.pages[0])

    def test_measured_density_cannot_be_replaced_by_assumption(self):
        self.promote()
        path = self.spec / "baseline/ui-snapshots" / self.pages[0] / "runtime-refs.json"
        refs = evidence.read(path)
        refs["states"][0]["frames"][0]["density_factor"] = 3
        evidence.save(path, refs)
        with self.assertRaisesRegex(ValueError, "density"):
            evidence.validate_refs(self.spec, self.pages[0])

    def test_embedded_content_cannot_nest_navdestination(self):
        self.code_and_reports()
        path = self.root / "entry/src/main/ets/components/ForecastContent.ets"
        path.write_text("struct ForecastContent { build() { NavDestination() { Text('forecast') } } }")
        result = ui_stage1_gate.check(self.root)
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(any("NavDestination" in e["detail"] for e in result["errors"]))

    def test_blocked_environment_does_not_consume_repair_attempt(self):
        self.code_and_reports()
        stage1_acceptance.archive_generation(self.root, "g0")
        scope_path = self.spec / "execution/stage1-visual-scope.json"
        evidence.save(scope_path, stage1_visual_scope.build_scope(self.root))
        path = self.spec / "execution/compile.json"
        evidence.save(path, {"status": "BLOCKED", "scope_sha256": evidence.digest(scope_path), "reason": "device unavailable"})
        self.assertEqual(stage1_acceptance.record(self.root, scope_path, path, "compile")["status"], "BLOCKED")
        evidence.save(path, {"status": "FAIL", "scope_sha256": evidence.digest(scope_path)})
        result = stage1_acceptance.record(self.root, scope_path, path, "compile")
        self.assertEqual(result["attempt"], 0)
        self.assertEqual(result["status"], "REPAIR_REQUIRED")

    def test_draft_joins_canonical_fragment_before_emitting_units(self):
        self.mapping["pages"][1]["host_bindings"][0]["state_id"] = "calendar"
        self.promote()
        path = self.spec / "baseline/ui-snapshots" / self.pages[1] / "meta.json"
        evidence.save(path, {"activity": "org.source.ForecastFragment"})
        evidence.save(self.spec / "baseline/ui-snapshots" / self.pages[0] / "visual.json",
                      {"composition": {"children": [{"kind": "fragment", "class": "org.source.ForecastFragment", "source_ref": self.citation}]}})
        units = ui_delivery.draft(self.root)["units"]
        child = [u for u in units if u["component"] == "org.source.ForecastFragment"]
        self.assertEqual(len(child), 1)
        self.assertEqual(child[0]["page_id"], self.pages[1])
        self.assertEqual([s["state_id"] for s in child[0]["required_states"]], ["calendar"])
        self.assertEqual(child[0]["presentation_role"], "embedded")
        self.assertNotIn(self.pages[0], child[0]["unit_id"])

    def test_host_state_cannot_be_replaced_by_default(self):
        self.mapping["pages"][1]["host_bindings"][0]["state_id"] = "calendar"
        self.promote()
        with self.assertRaisesRegex(ValueError, "default"):
            ui_delivery.approve(self.root, self.inventory(), "session:approval")

    def test_host_binding_drives_role_without_optional_composition(self):
        self.mapping["pages"][1]["host_bindings"][0]["state_id"] = "calendar"
        self.promote()
        unit = next(u for u in ui_delivery.draft(self.root)["units"] if u["page_id"] == self.pages[1])
        self.assertEqual(unit["presentation_role"], "embedded")
        self.assertEqual([s["state_id"] for s in unit["required_states"]], ["calendar"])
        self.assertTrue(unit["source_refs"])

    def test_approval_is_bound_to_content_not_boolean(self):
        self.promote()
        inventory = ui_delivery.approve(self.root, self.inventory(), "session:approval")
        inventory["units"][0]["required_states"][1]["arrival_mode"] = "formal"
        with self.assertRaisesRegex(ValueError, "STALE"):
            ui_delivery.validate(self.root, inventory)

    def test_approval_detects_changed_evidence_behind_updated_hash(self):
        self.promote()
        inventory = ui_delivery.approve(self.root, self.inventory(), "session:approval")
        path = self.spec / "baseline/ui-snapshots" / self.pages[0] / "runtime-refs.json"
        refs = evidence.read(path)
        refs["states"][0]["frames"][0]["png"]["sha256"] = "b" * 64
        evidence.save(path, refs)
        with self.assertRaisesRegex(ValueError, "STALE"):
            ui_delivery.validate(self.root, inventory)

    def test_metadata_inventory_reference_reuse_is_automatic_and_strict(self):
        packets = self.code_and_reports()
        path, packet = packets[0]
        alternate = self.spec / "baseline/plans/identical-inventory.json"
        alternate.write_text(json.dumps(evidence.read(self.spec / packet["inventory"]["path"]), separators=(",", ":")))
        changed = copy.deepcopy(packet)
        changed["inventory"] = evidence.bound_file(self.spec, alternate)
        candidate = self.spec / "execution/metadata-candidate.json"
        evidence.save(candidate, changed)
        report = evidence.read(self.spec / "execution/conversion-reports/main.shell.json")
        receipt = ui_dispatch.reuse_metadata(self.root, report["dispatch_id"], candidate)
        self.assertEqual(receipt["rule"], "same-content-v1")
        changed["states"][0]["frames"][0]["region_px"][0] += 1
        evidence.save(candidate, changed)
        with self.assertRaisesRegex(ValueError, "STALE"):
            ui_dispatch.reuse_metadata(self.root, report["dispatch_id"], candidate)

    def test_wrong_inventory_reference_cannot_reuse_result(self):
        _, packet = self.code_and_reports()[0]
        inventory = evidence.read(self.spec / packet["inventory"]["path"])
        inventory["units"][0]["required_states"][0]["region_px"] = [0, 0, 100, 100]
        changed_inventory = self.spec / "changed.json"
        evidence.save(changed_inventory, inventory)
        packet["inventory"] = evidence.bound_file(self.spec, changed_inventory)
        candidate = self.spec / "candidate.json"
        evidence.save(candidate, packet)
        with self.assertRaisesRegex(ValueError, "STALE"):
            ui_dispatch.reuse_metadata(self.root, "main.shell.attempt-1", candidate)

    def test_unaffected_unit_can_reuse_when_another_unit_changes(self):
        self.code_and_reports()
        path = self.spec / "baseline/plans/stage1-ui-delivery.json"
        inventory = evidence.read(path)
        inventory["units"][1]["required_states"][0]["arrival_mode"] = "formal"
        evidence.save(path, ui_delivery.approve(self.root, inventory, "session:approved-state-change"))
        ui_delivery_inputs.freeze(self.root, path)
        packets = dict((p["unit_id"], file) for file, p in validate_runtime_snapshots.load_packets(self.root))
        ui_dispatch.reuse_metadata(self.root, "main.shell.attempt-1", packets["main.shell"])
        report = evidence.read(self.spec / "execution/conversion-reports/main.shell.json")
        ui_dispatch.validate_handoff(self.root, packets["main.shell"], report)
        with self.assertRaisesRegex(ValueError, "STALE"):
            ui_dispatch.reuse_metadata(self.root, "main.forecast.attempt-1", packets["main.forecast"])

    def test_dispatch_lists_actual_unit_and_absolute_image_paths(self):
        packets = self.frozen()
        result = ui_dispatch.dispatch(self.root, "main.forecast")
        prompt = Path(result["prompt_path"]).read_text()
        child = next(p for _, p in packets if p["unit_id"] == "main.forecast")
        self.assertIn("org.source.ForecastFragment", prompt)
        self.assertIn(child["unit"]["output"]["file"], prompt)
        self.assertIn(result["packet"]["sha256"], prompt)
        for frame in child["states"][0]["frames"]:
            self.assertIn(str(evidence.check_file(self.spec, frame["working_png"])), prompt)

    def test_dispatch_original_images_works_without_png_copies(self):
        self.promote()
        path = self.spec / "baseline/plans/stage1-ui-delivery.json"
        evidence.save(path, ui_delivery.approve(self.root, self.inventory(), "session:approval"))
        ui_delivery_inputs.freeze(self.root, path, working_copies=False)
        result = ui_dispatch.dispatch(self.root, "main.forecast")
        prompt = Path(result["prompt_path"]).read_text()
        self.assertIn(str(self.run), prompt)
        self.assertFalse(list((self.spec / "baseline/ui-snapshots").glob("*/runtime/**/*.png")))

    def test_hash_chain_detects_record_edit(self):
        self.frozen()
        ui_dispatch.dispatch(self.root, "main.shell")
        ui_dispatch.dispatch(self.root, "main.forecast")
        path = self.spec / "execution/ui-dispatch/events.jsonl"
        path.write_text(path.read_text().replace('"attempt": 1', '"attempt": 9', 1))
        with self.assertRaisesRegex(ValueError, "chain changed"):
            ui_dispatch.events(self.root)

    def test_report_reseal_cannot_pass_handoff(self):
        self.code_and_reports()
        path = self.spec / "execution/conversion-reports/main.shell.json"
        report = evidence.read(path)
        report["packet_sha256"] = "f" * 64
        evidence.save(path, report)
        self.assertEqual(ui_stage1_gate.check(self.root)["status"], "FAIL")

    def test_anchor_warning_does_not_require_report_repair(self):
        packets = self.frozen()
        for packet_path, packet in packets:
            unit = packet["unit"]
            record = ui_dispatch.dispatch(self.root, unit["unit_id"])
            path = self.root / unit["output"]["file"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("struct " + unit["output"]["symbol"] + " { build() { Text('UI') } @Builder tabWeatherLine() { ForecastContent() } }")
            report = {"unit_id": unit["unit_id"], "dispatch_id": record["dispatch_id"], "packet_sha256": evidence.digest(packet_path),
                      "input_applications": [{"input_id": i["input_id"]} for i in packet["required_inputs"]],
                      "state_implementations": [{"state_id": s["state_id"], "symbol": "descriptive.symbol"} for s in unit["required_states"]]}
            evidence.save(self.spec / "execution/conversion-reports" / (unit["unit_id"] + ".json"), report)
            ui_dispatch.complete(self.root, record["dispatch_id"])
        result = ui_stage1_gate.check(self.root)
        self.assertEqual(result["status"], "PASS")
        self.assertTrue(result["warnings"])
        self.assertFalse(result["stage1_complete"])

    def test_free_text_does_not_unlock_no_capture_fallback(self):
        self.promote()
        inventory = self.inventory()
        inventory["units"][0]["required_states"].append({"state_id": "calendar", "arrival_mode": "preview"})
        inventory["units"][0]["input_alternatives"]["state.calendar"] = {"reason": "progressive pending", "source_refs": [self.citation]}
        path = self.spec / "inventory.json"
        evidence.save(path, ui_delivery.approve(self.root, inventory, "session:approval"))
        with self.assertRaisesRegex(ValueError, "binding error"):
            ui_delivery_inputs.freeze(self.root, path)

    def test_every_window_is_independently_parseable(self):
        self.promote()
        evidence.save(self.spec / "baseline/ui-snapshots" / self.pages[0] / "visual.json",
                      {"nodes": [{"node_key": str(i), "label": "label\nwith quotes \" / value" * 10} for i in range(200)]})
        path = self.spec / "inventory.json"
        evidence.save(path, ui_delivery.approve(self.root, self.inventory(), "session:approval"))
        ui_delivery_inputs.freeze(self.root, path)
        for _, packet in validate_runtime_snapshots.load_packets(self.root):
            for reference in packet["windows"]:
                self.assertTrue(evidence.read(evidence.check_file(self.spec, reference))["items"])

    def test_host_frames_exclude_child_and_child_geometry_is_local(self):
        packets = self.frozen()
        host = next(p for _, p in packets if p["unit_id"] == "main.shell")
        regions = [f["region_px"] for s in host["states"] if s["state_id"] == "forecast" for f in s["frames"]]
        for region in regions:
            self.assertEqual(runtime_inputs.subtract(region, [10, 10, 300, 500]), [region])
        child = next(p for _, p in packets if p["unit_id"] == "main.forecast")
        frame = child["states"][0]["frames"][0]
        node = evidence.read(self.spec / frame["parsed"]["path"])["nodes"][0]
        self.assertEqual(node["bounds_local_px"], [10, 10, 190, 90])
        self.assertIsNone(node["parent_id"])
        self.assertEqual(struct.unpack(">II", (self.spec / frame["working_png"]["path"]).read_bytes()[16:24]), (290, 490))

    def test_new_controls_require_expansion_but_duplicates_do_not(self):
        self.records[0] = self.capture("new_capture", "new-control", 1)
        index = evidence.read(self.run / "index.json") + [self.records[0]]
        evidence.save(self.run / "index.json", index)
        self.mapping["pages"][0]["states"][0]["source_page_ids"].append("new_capture")
        packets = self.frozen()
        host = next(p for _, p in packets if p["unit_id"] == "main.shell")
        state = host["states"][0]
        self.assertEqual([f["selection"] for f in state["frames"]], ["representative", "required_expansion"])
        self.assertEqual(len(state["optional_frames"]), 1)

    def test_prepare_repeat_rebuilds_identical_runtime_cache(self):
        self.frozen()
        snapshot_root = self.spec / "baseline/ui-snapshots"
        before = {str(p.relative_to(snapshot_root)): p.read_bytes() for p in snapshot_root.rglob("*") if p.is_file()}
        ui_delivery_inputs.freeze(self.root, self.spec / "baseline/plans/stage1-ui-delivery.json")
        after = {str(p.relative_to(snapshot_root)): p.read_bytes() for p in snapshot_root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_missing_g0_blocks_handoff_and_stage1_summary(self):
        self.frozen()
        scope_path = self.spec / "scope.json"
        evidence.save(scope_path, stage1_visual_scope.build_scope(self.root))
        with self.assertRaises(FileNotFoundError):
            stage1_acceptance.summary(self.root, scope_path)

    def test_cli_acceptance_from_neutral_directory_without_pythonpath(self):
        self.code_and_reports()
        script = SKILLS / "a2h-execute/scripts/stage1_acceptance.py"
        env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        for args in (["--help"], ["--project-root", str(self.root), "--kind", "g0"]):
            result = subprocess.run([sys.executable, str(script), *args], cwd=self.tmp.name, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.spec / "execution/stage1-generation/g0/manifest.json").is_file())

    def test_missing_visual_results_cannot_be_stage1_complete(self):
        self.code_and_reports()
        stage1_acceptance.archive_generation(self.root, "g0")
        scope_path = self.spec / "scope.json"
        evidence.save(scope_path, stage1_visual_scope.build_scope(self.root))
        result = stage1_acceptance.summary(self.root, scope_path)
        self.assertEqual(result["structural"], "PASS")
        self.assertEqual(result["status"], "BLOCKED")
        self.assertFalse(result["stage1_complete"])

    def acceptance_fixture(self):
        self.code_and_reports()
        stage1_acceptance.archive_generation(self.root, "g0")
        scope_path = self.spec / "scope.json"
        scope = stage1_visual_scope.build_scope(self.root)
        evidence.save(scope_path, scope)
        receipt = self.spec / "execution/test-build.json"
        evidence.save(receipt, {"status": "PASS", "scope_sha256": evidence.digest(scope_path),
                                "source_sha256": stage1_acceptance.source_digest(self.root), "hap_sha256": "test-hap"})
        compile_report = self.spec / "compile.json"
        evidence.save(compile_report, {"status": "PASS", "scope_sha256": evidence.digest(scope_path),
                                      "build_receipt": evidence.bound_file(self.spec, receipt)})
        stage1_acceptance.record(self.root, scope_path, compile_report, "compile")
        rows = []
        for pair in scope["pairs"]:
            arrival = self.spec / "execution" / (pair["pair_id"] + ".arrival.json")
            evidence.save(arrival, {"pair_id": pair["pair_id"], "status": "PASS", "arrival_mode": pair["arrival_mode"],
                                    "build_receipt": evidence.bound_file(self.spec, receipt), "install_receipt": evidence.bound_file(self.spec, receipt)})
            rows.append({"pair_id": pair["pair_id"], "verdict": "PASS", "arrival_mode": pair["arrival_mode"],
                         "arrival_receipt": evidence.bound_file(self.spec, arrival), "comparisons": [
                             {"comparison_id": f["comparison_id"], "android_png_sha256": f["png"]["sha256"],
                              "android_region_px": f["region_px"], "harmony_png": f["working_png"], "harmony_xml": f["xml"], "verdict": "PASS"}
                             for f in pair["android_frames"]]})
        report = self.spec / "visual-report.json"
        evidence.save(report, {"scope_sha256": evidence.digest(scope_path), "pairs": rows})
        return scope_path, report

    def test_acceptance_pass_requires_all_states_and_current_sources(self):
        scope, report = self.acceptance_fixture()
        stage1_acceptance.record(self.root, scope, report)
        result = stage1_acceptance.summary(self.root, scope)
        self.assertTrue(result["stage1_complete"])
        self.assertTrue(result["assessment_complete"])
        (self.root / "entry/src/main/ets/pages/MainPage.ets").write_text("changed after comparison")
        with self.assertRaisesRegex(ValueError, "STALE"):
            stage1_acceptance.summary(self.root, scope)

    def test_visual_frame_region_cannot_be_omitted(self):
        scope, report = self.acceptance_fixture()
        data = evidence.read(report)
        host = next(p for p in data["pairs"] if len(p["comparisons"]) > 1)
        host["comparisons"].pop()
        evidence.save(report, data)
        with self.assertRaisesRegex(ValueError, "frame/region"):
            stage1_acceptance.record(self.root, scope, report)

    def test_assessment_complete_with_blocked_is_not_acceptance_pass(self):
        scope, report = self.acceptance_fixture()
        data = evidence.read(report)
        data["pairs"][0] = {"pair_id": data["pairs"][0]["pair_id"], "verdict": "BLOCKED", "reason": "device path unavailable"}
        evidence.save(report, data)
        stage1_acceptance.record(self.root, scope, report)
        result = stage1_acceptance.summary(self.root, scope)
        self.assertTrue(result["assessment_complete"])
        self.assertFalse(result["stage1_complete"])
        self.assertEqual(result["status"], "BLOCKED")

    def test_failed_full_g0_archive_can_retry_without_partial_publication(self):
        self.code_and_reports()
        report = self.spec / "execution/conversion-reports/main.forecast.json"
        original = report.read_bytes()
        report.unlink()
        with self.assertRaises(FileNotFoundError):
            stage1_acceptance.archive_generation(self.root, "g0")
        self.assertFalse((self.spec / "execution/stage1-generation/g0").exists())
        report.write_bytes(original)
        stage1_acceptance.archive_generation(self.root, "g0")
        self.assertTrue(stage1_acceptance.require_g0(self.root))

    def test_consumption_distinguishes_host_child_regions(self):
        import ui_consumption
        packets = self.code_and_reports()
        result = ui_consumption.report(self.root)
        self.assertFalse(result["visual_verified"])
        self.assertEqual(result["unique_declared_observed_originals"], 0)
        host_regions = {tuple(r["region_px"]) for r in result["rows"] if r["unit_id"] == "main.shell" and r["state_id"] == "forecast"}
        child_regions = {tuple(r["region_px"]) for r in result["rows"] if r["unit_id"] == "main.forecast"}
        self.assertFalse(host_regions & child_regions)

    def test_retry_does_not_replace_first_generation_in_global_g0(self):
        packets = self.code_and_reports()
        path = self.root / "entry/src/main/ets/pages/MainPage.ets"
        first = path.read_bytes()
        dispatched = ui_dispatch.dispatch(self.root, "main.shell", attempt=2)
        path.write_text("struct MainPage { build() { Text('repaired') } @Builder tabWeatherLine() { ForecastContent() } }")
        report_path = self.spec / "execution/conversion-reports/main.shell.json"
        report = evidence.read(report_path)
        report["dispatch_id"] = dispatched["dispatch_id"]
        evidence.save(report_path, report)
        ui_dispatch.complete(self.root, dispatched["dispatch_id"])
        stage1_acceptance.archive_generation(self.root, "g0")
        self.assertEqual((self.spec / "execution/stage1-generation/g0/entry/src/main/ets/pages/MainPage.ets").read_bytes(), first)

    def test_invalid_report_is_archived_as_failed_first_output(self):
        self.frozen()
        dispatched = ui_dispatch.dispatch(self.root, "main.shell")
        output = self.root / "entry/src/main/ets/pages/MainPage.ets"
        output.parent.mkdir(parents=True)
        output.write_text("first failed output")
        report = self.spec / "execution/conversion-reports/main.shell.json"
        report.parent.mkdir(parents=True)
        report.write_text("{ invalid first report")
        result = ui_dispatch.complete(self.root, dispatched["dispatch_id"])
        self.assertEqual(result["status"], "ARCHIVED_INVALID_REPORT")
        self.assertEqual(evidence.check_file(self.spec, result["report"]).read_bytes(), report.read_bytes())

    def test_partial_state_gap_is_recorded_without_hiding_observed_states(self):
        self.mapping["pages"][0]["state_gaps"] = [{"state_id": "login_state", "status": "condition_unmet", "reason": "source login requirement", "source_refs": [self.citation]}]
        self.promote()
        inventory = self.inventory()
        inventory["units"][0]["required_states"].append({"state_id": "login_state", "arrival_mode": "preview"})
        path = self.spec / "inventory.json"
        evidence.save(path, ui_delivery.approve(self.root, inventory, "session:approval"))
        ui_delivery_inputs.freeze(self.root, path)
        packet = next(p for _, p in validate_runtime_snapshots.load_packets(self.root) if p["unit_id"] == "main.shell")
        self.assertEqual([s["visual_baseline_status"] for s in packet["states"]], ["READY", "READY", "BLOCKED"])

    def test_png_crop_preserves_pixels_across_sub_and_up_filters(self):
        from runtime_png import crop_png
        def chunk(kind, data):
            return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        source = self.root / "colored.png"
        # RGB pixels: row0=(10,20,30),(30,50,70); row1=(11,22,33),(44,55,66).
        filtered = bytes([1, 10, 20, 30, 20, 30, 40, 2, 1, 2, 3, 14, 5, 252])
        source.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(filtered)) + chunk(b"IEND", b""))
        target = self.root / "crop.png"
        crop_png(source, target, [1, 0, 2, 2])
        raw = target.read_bytes()
        offset, compressed = 8, b""
        while offset < len(raw):
            length = struct.unpack(">I", raw[offset:offset+4])[0]
            if raw[offset+4:offset+8] == b"IDAT": compressed += raw[offset+8:offset+8+length]
            offset += length + 12
        self.assertEqual(zlib.decompress(compressed), bytes([0, 30, 50, 70, 0, 44, 55, 66]))

if __name__ == "__main__":
    unittest.main()
