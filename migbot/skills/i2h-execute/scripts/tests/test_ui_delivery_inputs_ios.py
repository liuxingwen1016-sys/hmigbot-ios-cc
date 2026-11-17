import json
import sys
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from lib.stage1_visual_scope import FIXTURE_BINDINGS, approved_fixture_bindings, baseline, sync_runtime_capture
from lib.ui_delivery_inputs_ios import freeze


class IOSDeliveryInputsTests(unittest.TestCase):
    def test_partial_supplement_import_validates_provenance_and_retains_failed_states(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            page = "page_0001_Main"
            context = {"source_sha256": "a" * 64, "device_udid": "test-device",
                       "configuration_id": "Debug.uitesting", "app": {"bundle_id": "test.app"}}

            def write(path, value):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(value), encoding="utf-8")

            def capture(folder, state, manifest, *, extra=(), provenance=None, image=b"image"):
                state_dir = folder / page / "states" / state
                state_dir.mkdir(parents=True)
                (state_dir / "frame.png").write_bytes(image)
                write(state_dir / "tree.json", {"label": state})
                write(state_dir / "runtime-evidence.json", provenance or context)
                evidence = {"source_platform": "ios", "status": "audited", "page_id": page,
                            "state_id": state}
                for key, name in (("png", "frame.png"), ("ui_json", "tree.json")):
                    evidence[key + "_path"] = f"states/{state}/{name}"
                    evidence[key + "_sha256"] = sha256((state_dir / name).read_bytes()).hexdigest()
                write(folder / page / "meta.json", {"runtime_evidence_by_state": {state: evidence}})
                write(manifest, {"output_root": str(folder), "states": [
                    {"page_id": page, "state_id": state, "status": "captured", "output_dir": str(state_dir)}, *extra,
                ]})

            primary = root / "spec/execution/ios-runtime-capture/capture-plan-manifest.json"
            supplement = root / "supplement.json"
            capture(root / "primary", "default", primary)
            capture(root / "supplement", "archived", supplement,
                    extra=[{"page_id": page, "state_id": "missing", "status": "blocked",
                            "blocked_reason": "anchor absent"}])
            inventory = root / "spec/baseline/ui-delivery-approved.json"
            write(inventory, {"schema_version": 2, "status": "approved", "source_project_root": str(root), "units": [{
                "unit_id": "unit", "page_id": page, "required_states": [
                    {"state_id": state} for state in ("default", "archived", "missing")
                ],
            }]})
            flags = ["--project-root", str(root), "--inventory", str(inventory),
                     "--supplemental-capture-manifest"]
            self.assertEqual(freeze([*flags, str(supplement)]), 0)
            index = json.loads((root / "spec/execution/ui-inputs/index.json").read_bytes())
            imported = index["supplemental_runtime_captures"][0]
            self.assertEqual(imported["state_count"], 1)
            self.assertEqual(imported["blocked_states"][0]["reason"], "anchor absent")
            self.assertEqual([s["evidence"]["status"] for s in index["packets"][0]["required_states"]],
                             ["audited", "audited", "missing"])
            self.assertEqual(freeze([*flags, str(supplement)]), 0)
            index_path = root / "spec/execution/ui-inputs/index.json"
            frozen = index_path.read_bytes()
            repeated = json.loads(frozen)
            reused = repeated["supplemental_runtime_captures"][0]
            self.assertEqual(reused["state_count"], 1)
            self.assertEqual(reused["imported_state_count"], 0)
            self.assertEqual(reused["reused_states"], imported["states"])
            self.assertEqual(reused["blocked_states"], imported["blocked_states"])
            self.assertEqual(repeated["packets"], index["packets"])
            archived = root / "spec/baseline/ui-snapshots" / page / "states/archived/frame.png"
            archived.write_bytes(b"corrupt destination")
            with self.assertRaisesRegex(ValueError, "existing supplemental.*screenshot hash mismatch"):
                freeze([*flags, str(supplement)])
            self.assertEqual(index_path.read_bytes(), frozen)
            self.assertEqual(archived.read_bytes(), b"corrupt destination")
            stale = root / "wrong.json"
            capture(root / "wrong", "missing", stale, provenance={**context, "source_sha256": "b" * 64})
            with self.assertRaisesRegex(ValueError, "provenance mismatch"):
                freeze([*flags, str(stale)])
            conflict = root / "different.json"
            capture(root / "different", "default", conflict, image=b"replacement")
            with self.assertRaisesRegex(ValueError, "would replace captured state"):
                freeze([*flags, str(conflict)])

    def test_partial_primary_rejects_projection_and_keeps_blocked_state_after_replay(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            job = root / 'spec/execution/ios-runtime-jobs/fixture'
            output = job / 'states'
            page = 'Main'
            context = {'source_sha256': 'a' * 64, 'device_udid': 'sim',
                       'configuration_id': 'Debug', 'app': {'bundle_id': 'test.app'}}

            def write(path, data):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(data))
                return sha256(path.read_bytes()).hexdigest()

            def captured(folder, state):
                directory = folder / page / 'states' / state
                screenshot = write(directory / 'image.png', {'image': state})
                tree = write(directory / 'tree.json', {'nodes': []})
                write(directory / 'runtime-evidence.json', context)
                write(folder / page / 'meta.json', {'runtime_evidence_by_state': {state: {
                    'status': 'audited', 'source_platform': 'ios', 'page_id': page, 'state_id': state,
                    'png_path': f'states/{state}/image.png', 'png_sha256': screenshot,
                    'ui_json_path': f'states/{state}/tree.json', 'ui_json_sha256': tree,
                    'bundle_id': 'test.app', 'device': 'sim', 'build_id': 'fixture-build',
                }}})
                return {'page_id': page, 'state_id': state, 'status': 'captured',
                        'output_dir': str(directory)}

            rows = [
                {'page_id': page, 'state_id': 'search', 'status': 'blocked', 'blocked_reason': 'keyboard hidden'},
                captured(output, 'normal'),
            ]
            plan = job / 'capture-plan.json'
            inputs_sha = write(job / 'inputs.json', {
                'plan_sha256': write(plan, {'states': [{'page_id': page, 'state_id': item['state_id']} for item in rows]}),
                'source_sha256': 'a' * 64, 'device_id': 'sim', 'configuration_id': 'Debug', 'bundle_id': 'test.app',
            })
            manifest = {'status': 'partial', 'state_count': 2, 'captured_count': 1, 'blocked_count': 1,
                        'output_root': str(output), 'plan_path': str(plan), 'states': rows}
            original_sha = write(output / 'capture-plan-manifest.json', manifest)
            write(job / 'result.json', {'status': 'partial', 'exit_code': 2, 'inputs_sha256': inputs_sha,
                                        'manifest_sha256': original_sha})
            primary = root / 'spec/execution/ios-runtime-capture/capture-plan-manifest.json'
            write(primary, {**manifest, 'states': rows[1:], 'state_count': 1, 'blocked_count': 0})
            with self.assertRaisesRegex(ValueError, 'does not match the frozen job'):
                sync_runtime_capture(root, primary)

            write(primary, {**manifest, 'status': 'captured', 'states': rows[1:],
                            'state_count': 1, 'blocked_count': 0})
            with self.assertRaisesRegex(ValueError, 'does not match the frozen job'):
                sync_runtime_capture(root, primary)

            write(primary, manifest)
            # A previously present snapshot must not fill the current job's missing state.
            captured(root / 'spec/baseline/ui-snapshots', 'search')
            result = sync_runtime_capture(root, primary)
            self.assertEqual(result['status'], 'partial')
            self.assertEqual(result['blocked_states'][0]['reason'], 'keyboard hidden')
            with self.assertRaisesRegex(ValueError, 'keyboard hidden'):
                baseline(root, {'page_id': page, 'state_id': 'search'})

            inventory = root / 'spec/baseline/ui-delivery-approved.json'
            write(inventory, {'schema_version': 2, 'status': 'approved', 'source_project_root': str(root), 'units': [{'unit_id': 'Main', 'page_id': page,
                  'required_states': [{'state_id': 'normal'}, {'state_id': 'search'}]}]})
            supplement = root / 'supplement.json'
            folder = root / 'supplement'
            write(supplement, {'output_root': str(folder), 'states': [captured(folder, 'search')]})
            self.assertEqual(freeze(['--project-root', str(root), '--inventory', str(inventory),
                                    '--supplemental-capture-manifest', str(supplement)]), 0)
            sync_runtime_capture(root, primary)
            self.assertEqual(baseline(root, {'page_id': page, 'state_id': 'search'})['evidence_kind'],
                             'ios-accessibility-json')

    def test_fixture_approval_is_separate_from_the_ui_inventory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            owner = HERE.parents[2]
            shared = owner.parent / ".migbot/bin/scripts/pipeline" if owner.name == ".claude" else owner / "bin/scripts/pipeline"
            sys.path.insert(0, str(shared))
            from marker_contract import write_marker

            inventory = {"schema_version": 2, "status": "approved", "approval": {"confirmation_ref": "fixture"},
                         "units": [{"page_id": "Root", "required_states": [
                             {"state_id": "startup", "arrival_mode": "behavior"},
                             {"state_id": "default", "arrival_mode": "formal"},
                         ]}]}
            bindings = root / FIXTURE_BINDINGS
            bindings.parent.mkdir(parents=True)
            plan_path = bindings.parent / "complete.txt"
            inventory_path = root / "spec/baseline/ui-delivery-approved.json"
            payload = json.dumps(inventory).encode("utf-8")
            inventory_path.write_bytes(payload)
            receipt = {"schema_version": 1, "inventory_sha256": sha256(payload).hexdigest(),
                       "confirmation_ref": "local fixture",
                       "bindings": [{"page_id": "Root", "state_id": "startup",
                                     "fixture_capture_sha256": "b" * 64}]}
            bindings.write_text(json.dumps(receipt), encoding="utf-8")
            write_marker(plan_path, "i2h-plan", [inventory_path], "a" * 64, root=root)
            with self.assertRaisesRegex(ValueError, "approved Plan marker"):
                approved_fixture_bindings(root, inventory_path, inventory)
            write_marker(plan_path, "i2h-plan", [inventory_path, bindings], "a" * 64, root=root)
            self.assertEqual(approved_fixture_bindings(root, inventory_path, inventory), {("Root", "startup"): "b" * 64})
            self.assertEqual(inventory_path.read_bytes(), payload)
            receipt["bindings"][0]["state_id"] = "default"
            bindings.write_text(json.dumps(receipt), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "invalid approved fixture binding"):
                approved_fixture_bindings(root, inventory_path, inventory)

    def test_bound_fixture_admits_only_its_exact_state_and_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            page, state = "Root", "startup_failure"
            captures = root / "captures"
            output = captures / page / "states" / state
            output.mkdir(parents=True)
            def write(path, data):
                path.write_text(json.dumps(data), encoding="utf-8")

            reference = {"source_sha256": "a" * 64, "device_udid": "primary",
                         "configuration_id": "in-memory", "bundle_id": "test.app"}
            evidence = {**reference, "device_udid": "isolated", "configuration_id": "persistent",
                        "app": {"bundle_id": "test.app"}}
            write(output / "runtime-evidence.json", evidence)
            payloads = {
                "screenshot": ("state.png", b"fixture png"),
                "ui_json": ("tree.json", b"{}"),
                "foreground_receipt": ("foreground.json", b'{"launch_mode":"standard"}'),
                "foreground_ack": ("ack.json", b"{}"),
            }
            artifacts = {}
            for kind, (name, payload) in payloads.items():
                (output / name).write_bytes(payload)
                artifacts[kind] = {"path": name, "sha256": sha256(payload).hexdigest()}
            state_manifest = output / "manifest.json"
            write(state_manifest, {"schema": "hmigbot-ios-ui-evidence/1", "status": "audited",
                                   "page_id": page, "state_id": state, "launch_mode": "standard",
                                   "runtime_evidence": evidence, "artifacts": artifacts})
            pin = sha256(state_manifest.read_bytes()).hexdigest()
            captured = {"source_platform": "ios", "page_id": page, "state_id": state,
                        "status": "audited", "app": {"bundle_id": "test.app"}}
            for kind, prefix in (("screenshot", "png"), ("ui_json", "ui_json")):
                captured[prefix + "_path"] = f"states/{state}/" + artifacts[kind]["path"]
                captured[prefix + "_sha256"] = artifacts[kind]["sha256"]
            write(captures / page / "meta.json", {"runtime_evidence_by_state": {state: captured}})
            manifest = root / "batch.json"
            write(manifest, {"output_root": str(captures), "states": [
                {"page_id": page, "state_id": state, "status": "captured", "output_dir": str(output)},
            ]})

            with self.assertRaisesRegex(ValueError, "provenance mismatch"):
                sync_runtime_capture(root, manifest, supplement_context=reference, fixture_bindings={(page, "other"): pin})
            with self.assertRaisesRegex(ValueError, "capture digest mismatch"):
                sync_runtime_capture(root, manifest, supplement_context=reference, fixture_bindings={(page, state): "0" * 64})
            with self.assertRaisesRegex(ValueError, "source or bundle mismatch"):
                sync_runtime_capture(root, manifest, supplement_context={**reference, "source_sha256": "b" * 64},
                                     fixture_bindings={(page, state): pin})
            result = sync_runtime_capture(root, manifest, supplement_context=reference, fixture_bindings={(page, state): pin})
            self.assertEqual(result["state_count"], 1)
            with self.assertRaisesRegex(ValueError, "does not match the approved state binding"):
                baseline(root, {"page_id": page, "state_id": state})
            selection = {"page_id": page, "state_id": state, "fixture_capture_sha256": pin}
            self.assertEqual(baseline(root, selection)["fixture_capture_sha256"], pin)
            reused = sync_runtime_capture(root, manifest, supplement_context=reference, fixture_bindings={(page, state): pin})
            self.assertEqual(reused["reused_states"], result["states"])
            copied = root / "spec/baseline/ui-snapshots" / page / "states" / state / "foreground.json"
            copied.write_text('{"launch_mode":"ui_testing"}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "foreground_receipt digest mismatch"):
                baseline(root, selection)
            with self.assertRaisesRegex(ValueError, "foreground_receipt digest mismatch"):
                sync_runtime_capture(root, manifest, supplement_context=reference, fixture_bindings={(page, state): pin})

    def test_freeze_keeps_missing_runtime_evidence_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "ios"
            source.mkdir()
            (source / "Main.swift").write_text("struct Main {}", encoding="utf-8")
            inventory = root / "spec/baseline/ui-delivery-approved.json"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(json.dumps({
                "schema_version": 2,
                "status": "approved",
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
