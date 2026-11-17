import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
INSTALLER = ROOT / "migbot/scripts/migbot-install.py"
EXECUTE = ROOT / "migbot/skills/i2h-execute"
SCRIPTS = Path(".claude/skills/i2h-execute/scripts")


def install(project, *args):
    return subprocess.run(
        [sys.executable, "-B", "-X", "utf8", str(INSTALLER), "--project", str(project), *args],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
    )


def gate(project, entry, *args):
    return subprocess.run(
        [sys.executable, "-B", "-X", "utf8", str(project / SCRIPTS / entry), *args],
        cwd=project, capture_output=True, text=True, encoding="utf-8",
    )


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def write_json(path, data):
    return write(path, json.dumps(data, ensure_ascii=False))


def delivery_fixture(project):
    home = "entry/src/main/ets/pages/Home.ets"
    card = "entry/src/main/ets/pages/Card.ets"
    valid_home = (
        "import { Card as DeliveredCard } from './Card';\n"
        "export struct Home {\n"
        "  build() { Column() { Text('home'); this.cardSlot() } }\n"
        "  @Builder cardSlot() { DeliveredCard() }\n"
        "}\n"
    )
    valid_card = (
        "@Component export struct Card {\n"
        "  @Prop loading: boolean = false;\n"
        "  build() { Column() { if (this.loading) { this.loadingBody() } else { Text('card') } } }\n"
        "  @Builder loadingBody() { Text('loading') }\n"
        "}\n"
    )
    write(project / home, valid_home)
    write(project / card, valid_card)
    units = [
        {
            "unit_id": "home", "page_id": "p-home", "presentation_role": "routed_page",
            "output": {"file": home, "symbol": "Home", "builder": "build"},
            "required_builders": ["cardSlot"], "required_states": [{"state_id": "default"}],
        },
        {
            "unit_id": "card", "page_id": "p-card", "presentation_role": "embedded",
            "output": {"file": card, "symbol": "Card", "builder": "build"},
            "integration": {"host_file": home, "host_builder": "Home.cardSlot", "child_symbol": "Card"},
            "required_states": [{"state_id": "default"}, {"state_id": "loading"}],
        },
    ]
    inventory = write_json(project / "spec/baseline/ui-delivery-approved.json", {
        "schema_version": 2, "status": "approved", "scope": "full_ui", "units": units,
    })
    card_report = None
    for unit in units:
        name = unit["unit_id"]
        data = {
            "unit_id": name, "dispatch_id": f"fixture-{name}-1", "packet_sha256": "a" * 64,
            "state_implementations": [
                {"state_id": state["state_id"], "symbol": unit["output"]["symbol"]}
                for state in unit["required_states"]
            ],
        }
        path = write_json(project / f"spec/execution/conversion-reports/{name}.json", data)
        if name == "card":
            card_report = path, data
    return inventory, (project / home, valid_home), (project / card, valid_card), card_report


class InstallRuntimeTests(unittest.TestCase):
    def test_installed_spec_gate_rejects_explicit_grapheme_codepoint_mapping(self):
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            result = install(project)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            for name in ("ui-manifest.md", "feature-index.md", "ui/page_0001_demo.md"):
                write(project / "spec/baseline" / name, "fixture")
            feature = project / "spec/baseline/features/feat_001_demo.md"
            before = (
                "Swift String.count 按字素簇计数。\n"
                "使用 `Array.from(value).slice(0, 40).join('')` 与 iOS 一致。\n"
                "不要用 `Array.from(value).length` 作为字素计数。\n"
            )
            write(feature, before)
            gate_path = project / ".migbot/bin/scripts/linters/gate_spec_complete.py"
            command = [sys.executable, "-B", str(gate_path), str(project), "--report-only"]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            detail, = json.loads(result.stdout)["findings"]
            self.assertEqual(detail["rule"], "SPEC.SWIFT_GRAPHEME_MAPPING")
            self.assertTrue(detail["subject_ref"].endswith(":2"))
            ledger = project / "spec/.i2h/open-findings.json"
            self.assertFalse(ledger.exists())
            normal = subprocess.run(command[:-1], capture_output=True, text=True)
            self.assertEqual(normal.returncode, 2, normal.stdout + normal.stderr)
            self.assertIn(detail["finding_key"], ledger.read_text(encoding="utf-8"))
            write(feature, before.replace("Array.from(value).slice(0, 40).join('')", "characterPrefix(value, 40)"))
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(json.loads(result.stdout)["findings"], [])

    def test_installed_ut_inputs_read_ios_feature_specs(self):
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            result = install(project)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            scripts = project / ".claude/skills/arkts-ut-verifier/scripts"
            baseline = project / "spec/baseline/features"
            first = write(baseline / "feat_001_local_library.md",
                          "# F001 Local library\n\n## 验收标准\n- [ ] F001-AC01 Open library\n")
            second = write(baseline / "feat_f010_pet_health.md",
                           "# F010 Pet health\n\n## Acceptance Criteria\n- [x] F010-AC03 Edit record\n")
            feature_run = subprocess.run(
                [sys.executable, "-B", "-X", "utf8", str(scripts / "feature_inputs.py"),
                 "--project-root", "."],
                cwd=project, capture_output=True, text=True, encoding="utf-8",
            )
            self.assertEqual(feature_run.returncode, 0, feature_run.stderr)
            features = json.loads(feature_run.stdout)["features"]
            self.assertEqual([row["feature_file"] for row in features], [str(first.resolve()), str(second.resolve())])
            ac_run = subprocess.run(
                [sys.executable, "-B", "-X", "utf8", str(scripts / "ac_inputs.py"),
                 "--feature-file", features[1]["feature_file"], "--feature-id", "F010"],
                cwd=project, capture_output=True, text=True, encoding="utf-8",
            )
            self.assertEqual(ac_run.returncode, 0, ac_run.stderr)
            self.assertEqual([row["source_ac_id"] for row in json.loads(ac_run.stdout)], ["F010-AC03"])
            for script, argument, option in (
                ("generation_inventory.py", "--help", "--registered-ids"),
                ("hypium_results.py", "parse", "--expected-ids"),
                ("hypium_results.py", "metrics", "--input"),
            ):
                flags = [argument, "--help"] if argument != "--help" else [argument]
                command = [sys.executable, "-B", "-X", "utf8", str(scripts / script), *flags]
                result = subprocess.run(command, cwd=project, capture_output=True, text=True, encoding="utf-8")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(option, result.stdout)

    def test_installs_apple_sign_in_skill_with_its_references(self):
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            result = install(project)
            self.assertEqual(result.returncode, 0, result.stderr)
            skill = Path("ios-apple-sign-in-to-huawei")
            for name in ("SKILL.md", "references/account-kit.md", "references/HuaweiIdSignIn.ets"):
                supplied = ROOT / "migbot/skills" / skill / name
                installed = project / ".claude/skills" / skill / name
                self.assertEqual(installed.read_bytes(), supplied.read_bytes())

    def test_installed_batch_writeback_and_coverage(self):
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            installed = install(project)
            self.assertEqual(installed.returncode, 0, installed.stdout + installed.stderr)
            packet = "slice-01-F001"
            ac = "F001-AC01"
            deferred = "F001-AC02"
            other = "F002-AC01"
            other_packet = "slice-02-F002"
            write_json(project / "spec/.i2h/plan-coverage.json", {"packets": [{
                "packet_id": packet, "requirement_ids": [ac, deferred],
                "requirement_digests": {ac: "digest", deferred: "deferred-digest"},
            }, {
                "packet_id": other_packet, "requirement_ids": [other],
                "requirement_digests": {other: "other-digest"},
            }]})
            write_json(project / "spec/.i2h/requirements-index.json", {"requirements": [
                {"requirement_id": ac, "digest": "digest"},
                {"requirement_id": deferred, "digest": "deferred-digest"},
                {"requirement_id": other, "digest": "other-digest"},
            ]})
            outputs = []
            for name in ("First.ets", "Second.ets"):
                write(project / name, "// implementation\n")
                intent = write_json(project / (name + ".intent"), {
                    "packets": {packet: {"requirement_ids": [ac], "files": [name]}},
                })
                output = project / (name + ".json")
                result = gate(project, "build_writeback.py", str(intent), "--project-root", ".",
                              "--claims-only", "--out", str(output))
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                manifest = json.loads(output.read_text(encoding="utf-8"))["impl_claims"]
                self.assertEqual(manifest["executed_packets"], [packet])
                self.assertEqual([claim["requirement_id"] for claim in manifest["claims"]], [ac])
                outputs.append(str(output))
            result = gate(project, "apply_writeback.py", *outputs, "--project-root", ".", "--merge-evidence")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            ledger = json.loads((project / "spec/.i2h/impl-claims.json").read_text(encoding="utf-8"))
            self.assertEqual(ledger["claims"][0]["files"], ["First.ets", "Second.ets"])
            ledger_path = project / "spec/.i2h/impl-claims.json"
            before = ledger_path.read_bytes()
            bad = write_json(project / "bad.json", {"impl_claims": {"claims": [
                {**ledger["claims"][0], "files": []},
            ]}})
            for mode in ([], ["--merge-evidence"]):
                result = gate(project, "apply_writeback.py", str(bad), "--project-root", ".", *mode)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn("MISSING_IMPLEMENTATION_FILES", result.stderr)
                self.assertEqual(ledger_path.read_bytes(), before)
            result = gate(project, "apply_writeback.py", *outputs, "--project-root", ".", "--merge-evidence")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(ledger_path.read_bytes(), before)
            write(project / "spec/decision-ledger.md", f"## D-101 Scope\n\n- **延期 AC**: {deferred}\n")
            result = gate(project, "lint_execute_coverage.py", "--project-root", ".", "--final", "--report-only")
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            findings = json.loads(result.stdout)["sections"]["execute"]["findings"]
            self.assertEqual(findings, [
                {"rule": "EXECUTE.REQUIREMENT_DEFERRED", "subject": deferred,
                 "packet_id": packet, "decision_id": "D-101"},
                {"rule": "EXECUTE.REQUIREMENT_UNCLAIMED", "subject": other, "packet_id": other_packet},
            ])
            injected = {**ledger["claims"][0], "packet_id": other_packet, "requirement_id": other,
                        "files": [], "requirement_digest": "other-digest"}
            for overrides, rule in (({}, "MISSING_IMPLEMENTATION_FILES"),
                                    ({"files": ["First.ets"], "requirement_digest": "old"},
                                     "STALE_REQUIREMENT_DIGEST")):
                with self.subTest(rule=rule):
                    ledger["claims"] = [ledger["claims"][0], {**injected, **overrides}]
                    write_json(ledger_path, ledger)
                    result = gate(project, "lint_execute_coverage.py", "--project-root", ".", "--final", "--report-only")
                    self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                    rows = json.loads(result.stdout)["sections"]["execute"]["findings"]
                    self.assertEqual({row["rule"] for row in rows if row["subject"] == other}, {
                        f"EXECUTE.{rule}", "EXECUTE.REQUIREMENT_UNCLAIMED",
                    })
                    self.assertFalse((project / "spec/.i2h/open-findings.json").exists())

    def test_installed_structured_writeback_round_trip(self):
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            installed = install(project)
            self.assertEqual(installed.returncode, 0, installed.stdout + installed.stderr)
            inventory, _, _, _ = delivery_fixture(project)
            frozen = inventory.read_bytes()
            packet, ac = "slice-01-F001", "F001-AC01"
            write_json(project / "spec/.i2h/plan-coverage.json", {"packets": [{
                "packet_id": packet, "requirement_ids": [ac], "requirement_digests": {ac: "digest"},
            }]})
            write_json(project / "spec/.i2h/requirements-index.json", {
                "requirements": [{"requirement_id": ac, "digest": "digest"}],
            })
            registry = write(project / "spec/placeholder-registry.md",
                             "| P-ID | resolve_by | status | kind |\n"
                             "| P-S1-001 | Stage 3 | registered | forward-ref |\n")
            draft = write(project / "draft.md", "# Group 01\n\n## Slice 1 (F-001)\n- final_state: PASS\n")
            brief = project / "spec/execution/briefs/group_01_brief.md"
            intent_data = {
                "mode": "group", "id": "01",
                "packets": {packet: {"whole_packet": True, "files": ["entry/src/main/ets/pages/Home.ets"]}},
                "feature_index": {"implemented": ["F001"]},
                "ui_manifest": {"converted": ["home"]},
                "registry": {"resolve": ["P-S1-001"], "retag": [
                    {"pid": "P-S1-001", "column": "resolve_by", "value": "D-001"},
                ]},
                "brief": {"path": str(brief.relative_to(project).as_posix()), "content_file": "draft.md"},
            }
            intent = write_json(project / "intent.json", intent_data)
            manifest = project / "manifest.json"
            built = gate(project, "build_writeback.py", str(intent), "--project-root", ".", "--out", str(manifest))
            self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
            valid = manifest.read_bytes()
            ledger = project / "spec/.i2h/impl-claims.json"
            original_registry = registry.read_bytes()
            for invalid in (
                {"brief": {"path": "spec/baseline/ui-manifest.md", "content": "# invalid"}},
                {"ui_manifest": {"converted": ["home"], "verified": ["home"]}},
                {"feature_index": {"implemented": ["F999"]}},
            ):
                mutated = {**json.loads(valid), **invalid}
                write_json(manifest, mutated)
                applied = gate(project, "apply_writeback.py", str(manifest), "--project-root", ".")
                self.assertEqual(applied.returncode, 1, applied.stdout + applied.stderr)
                self.assertEqual(registry.read_bytes(), original_registry)
                self.assertFalse(ledger.exists())
                self.assertFalse(brief.exists())
            manifest.write_bytes(valid)
            planned = gate(project, "apply_writeback.py", str(manifest), "--project-root", ".", "--dry-run")
            self.assertEqual(planned.returncode, 0, planned.stdout + planned.stderr)
            self.assertFalse(ledger.exists())
            self.assertFalse(brief.exists())
            self.assertEqual(registry.read_bytes(), original_registry)
            applied = gate(project, "apply_writeback.py", str(manifest), "--project-root", ".")
            self.assertEqual(applied.returncode, 0, applied.stdout + applied.stderr)
            document = json.loads(ledger.read_bytes())
            self.assertEqual(document["closeout"], {"ui_converted": ["p-home"], "features_implemented": ["F001"]})
            self.assertEqual([row["requirement_id"] for row in document["claims"]], [ac])
            self.assertEqual(brief.read_bytes(), draft.read_bytes())
            self.assertIn("| D-001 | resolved |", registry.read_text(encoding="utf-8"))
            paths = (brief, registry, ledger)
            snapshot = [(path.read_bytes(), path.stat().st_mtime_ns) for path in paths]
            applied = gate(project, "apply_writeback.py", str(manifest), "--project-root", ".")
            self.assertEqual(applied.returncode, 0, applied.stdout + applied.stderr)
            self.assertEqual(snapshot, [(path.read_bytes(), path.stat().st_mtime_ns) for path in paths])
            self.assertEqual(inventory.read_bytes(), frozen)
            result = gate(project, "lint_execute_coverage.py", "--project-root", ".", "--final", "--report-only")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_installed_ui_batch_writeback_without_function_plan(self):
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            installed = install(project)
            self.assertEqual(installed.returncode, 0, installed.stdout + installed.stderr)
            delivery_fixture(project)
            brief = "spec/execution/briefs/batch_01_brief.md"
            intent = write_json(project / "intent.json", {
                "mode": "batch", "ui_manifest": {"converted": ["card"]},
                "brief": {"path": brief, "content": "# Batch 01\n"},
            })
            manifest = project / "manifest.json"
            result = gate(project, "build_writeback.py", str(intent), "--project-root", ".", "--out", str(manifest))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = gate(project, "apply_writeback.py", str(manifest), "--project-root", ".")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual((project / brief).read_text(encoding="utf-8"), "# Batch 01\n")
            data = json.loads((project / "spec/.i2h/impl-claims.json").read_text(encoding="utf-8"))
            self.assertEqual(data["closeout"]["ui_converted"], ["p-card"])
            self.assertEqual(data["claims"], [])

    def test_installed_functional_verify_and_recheck(self):
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            installed = install(project)
            self.assertEqual(installed.returncode, 0, installed.stdout + installed.stderr)
            for command in ('i2h-verify.md', 'i2h-verify-zh.md'):
                self.assertTrue((project / '.claude/commands' / command).is_file())
            test = project / '.claude/skills/i2h-plan/scripts/tests/test_acceptance_plan.py'
            result = subprocess.run(
                [sys.executable, '-E', '-B', '-X', 'utf8', str(test)],
                cwd=project, capture_output=True, encoding='utf-8', timeout=45,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            tests = project / '.claude/skills/i2h-verify/scripts/tests'
            result = subprocess.run(
                [sys.executable, '-E', '-B', '-X', 'utf8', '-m', 'unittest', 'discover',
                 '-s', str(tests), '-p', 'test_uitest_*.py'],
                cwd=project, capture_output=True, encoding='utf-8', timeout=45,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('Ran ', result.stderr)

    def test_installed_plan_checks_tab_hosts_and_approves_one_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            installed = install(project)
            self.assertEqual(installed.returncode, 0, installed.stdout + installed.stderr)
            test = project / '.claude/skills/i2h-plan/scripts/tests/test_ios_pipeline_contracts.py'
            result = subprocess.run(
                [sys.executable, '-E', '-B', '-X', 'utf8', str(test),
                 'IOSPipelineContractTest.test_plan_requires_every_explicit_swiftui_tab_host_slot',
                 'IOSPipelineContractTest.test_approval_reuses_single_manifest_and_keeps_the_validation_digest'],
                cwd=project, capture_output=True, encoding='utf-8', timeout=45,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            timing = test.with_name("test_pipeline_timing.py")
            result = subprocess.run(
                [sys.executable, "-E", "-B", "-X", "utf8", str(timing)],
                cwd=project, capture_output=True, encoding="utf-8", timeout=45,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_installed_plan_input_view_reads_approved_specification(self):
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            installed = install(project)
            self.assertEqual(installed.returncode, 0, installed.stdout + installed.stderr)
            path = project / "spec/baseline/ui-manifest.md"
            original = (
                "# Manifest\n## SwiftUI Views 清单\nRootView\n"
                "## 页面关系图\nRootView to Settings\n## 共享组件\nCard\n## Risks\nLarge unrelated block\n"
            )
            write(path, original)
            script = project / ".claude/skills/i2h-plan/scripts/plan_input_view.py"
            result = subprocess.run([sys.executable, "-B", "-X", "utf8", str(script), "--role", "ui"],
                                    cwd=project, text=True, capture_output=True, encoding="utf-8")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("RootView to Settings", result.stdout)
            self.assertNotIn("Large unrelated block", result.stdout)
            self.assertEqual(path.read_text(encoding="utf-8"), original)
            for entry, flags, expected in (
                ("i2h-plan/scripts/acceptance_plan.py", ["--help"], "evaluate"),
                ("i2h-spec/scripts/ios_capture_job.py", ["start", "--help"], "--device-id"),
            ):
                installed_entry = project / ".claude/skills" / entry
                check = subprocess.run([sys.executable, "-B", "-X", "utf8", str(installed_entry), *flags],
                                       cwd=project, text=True, capture_output=True, encoding="utf-8")
                self.assertEqual(check.returncode, 0, check.stderr)
                self.assertIn(expected, check.stdout)

    def test_installed_capability_gate_distinguishes_live_scanning(self):
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            installed = install(project)
            self.assertEqual(installed.returncode, 0, installed.stdout + installed.stderr)
            script = project / SCRIPTS / "tests/test_capability_gate.py"
            result = subprocess.run(
                [sys.executable, "-E", "-B", "-X", "utf8", str(script),
                 "CapabilityGateTests.test_packaged_command_keeps_still_and_live_modes_distinct"],
                cwd=project, capture_output=True, text=True, encoding="utf-8", timeout=45,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_installed_summary_runs_current_stage1_contract(self):
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            installed = install(project)
            self.assertEqual(installed.returncode, 0, installed.stderr)
            script = project / SCRIPTS / "tests/test_ios_stage1_visual_gate.py"
            result = subprocess.run(
                [sys.executable, "-E", "-B", "-X", "utf8", str(script),
                 "IOSVisualGateTests.test_summary_requires_existing_g1_and_replays_all_proof",
                 "IOSVisualGateTests.test_summary_preserves_latest_visual_on_an_idempotent_historical_replay",
                 "IOSVisualGateTests.test_native_next_preserves_compile_budget_across_changed_scope_paths",
                 "IOSVisualGateTests.test_capture_index_requires_bound_frames_and_stops_before_judgement",
                 "IOSVisualGateTests.test_verify_replays_bound_visual_and_rejects_changed_artifacts",
                 "IOSVisualGateTests.test_appearance_receipt_replays_group_and_image_identity",
                 "IOSVisualGateTests.test_native_smoke_checks_cold_start_formal_coverage_and_same_installation",
                 "IOSVisualGateTests.test_visual_rounds_limit_critical_repairs_across_rebuilds"],
                cwd=project, capture_output=True, text=True, encoding="utf-8", timeout=45,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            reuse = subprocess.run(
                [sys.executable, "-E", "-B", "-X", "utf8",
                 str(project / SCRIPTS / "tests/test_visual_review_reuse.py")],
                cwd=project, capture_output=True, text=True, encoding="utf-8", timeout=45,
            )
            self.assertEqual(reuse.returncode, 0, reuse.stdout + reuse.stderr)
            (project / SCRIPTS / "lib/ios_stage1_summary.py").unlink()
            broken = gate(project, "stage1_acceptance.py", "--project-root", str(project), "--kind", "summary")
            self.assertEqual(broken.returncode, 3, broken.stderr)
            self.assertIn("tool_error", broken.stderr)

    def test_legacy_installer_options_and_runtime_entries(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project = root / "harmony"
            ios = root / "ios"
            project.mkdir()
            ios.mkdir()
            completed = install(project, "--ios", str(ios), "--lang", "en")
            self.assertEqual(completed.returncode, 0, completed.stderr)
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
            self.assertEqual(install(project).returncode, 0)
            custom = project / ".claude/skills/my-custom-skill/SKILL.md"
            custom.parent.mkdir(parents=True)
            custom.write_text("---\nname: my-custom-skill\n---\n")
            self.assertEqual(install(project).returncode, 0)
            self.assertTrue(custom.is_file())

    def test_installed_pipeline_resume_imports_shared_marker_contract(self):
        """The installed skill must resolve helpers from the project .migbot tree."""
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp) / "harmony"
            project.mkdir()
            self.assertEqual(install(project).returncode, 0)
            resume = project / ".claude/skills/i2h-plan/scripts/pipeline_resume.py"
            self.assertTrue(resume.is_file())
            report = project / "spec/.i2h/resume-test.json"
            completed = subprocess.run(
                [sys.executable, str(resume), "--project-root", str(project), "--summary", "--out", str(report)],
                check=False,
                capture_output=True,
                text=True,
            )
            # An empty project is incomplete, but a missing marker_contract
            # import would fail before emitting the deterministic JSON status.
            self.assertEqual(completed.returncode, 1, completed.stderr)
            status = json.loads(completed.stdout.strip().splitlines()[-1])
            self.assertEqual(status["resume_stage"], "i2h-spec")
            self.assertEqual(status["view"], "summary")
            self.assertEqual(json.loads(report.read_text())["resume_stage"], status["resume_stage"])

    def test_installed_gate_validates_outputs_states_and_exact_host(self):
        self.assertFalse((EXECUTE / "scripts/bin").exists(), "release must exclude the old execute distribution")
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            completed = install(project)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            inventory, (home, valid_home), (card, valid_card), (report, report_data) = delivery_fixture(project)
            visual_help = gate(project, "stage1_visual_report.py", "--help")
            self.assertEqual(visual_help.returncode, 0, visual_help.stderr)
            self.assertIn("review-worklist", visual_help.stdout)
            for entry in ("ui_stage1_gate.py", "ui_delivery_gate.py"):
                help_result = gate(project, entry, "--help")
                self.assertEqual(help_result.returncode, 0, help_result.stderr)
                self.assertIn("--inputs-index", help_result.stdout)
                passed = gate(project, entry, "--project-root", str(project))
                self.assertEqual(passed.returncode, 0, passed.stderr)
                summary = json.loads(passed.stdout)
                self.assertEqual(summary["status"], "PASS")
                self.assertEqual(summary["result_scope"], "STRUCTURAL_ONLY")
                self.assertEqual(summary["wired_units"], ["home", "card"])
                self.assertFalse(summary["stage1_complete"])

            compatibility = gate(project, "ui_delivery_gate.py", "--project-root", str(project),
                                 "--wiring-contract", str(inventory))
            self.assertEqual(compatibility.returncode, 0, compatibility.stdout + compatibility.stderr)
            self.assertEqual(json.loads(compatibility.stdout)["inventory"], inventory.relative_to(project).as_posix())

            output = project / "reports/gate.json"
            for code, damage, restore in [
                ("output_missing", card.unlink, lambda: write(card, valid_card)),
                ("output_symbol_missing", lambda: write(card, valid_card.replace("struct Card", "struct Decoy")),
                 lambda: write(card, valid_card)),
                ("required_state_missing", lambda: write_json(report, {
                    **report_data, "state_implementations": report_data["state_implementations"][:1],
                }), lambda: write_json(report, report_data)),
                ("required_host_slot_unbound",
                 lambda: write(home, valid_home.replace("DeliveredCard()", "Text('unbound')") +
                               "// DeliveredCard()\nstruct Decoy { build() { DeliveredCard() } }"),
                 lambda: write(home, valid_home)),
                ("required_host_slot_unbound",
                 lambda: write(home, valid_home.replace("this.cardSlot()", "Text('no slot')")),
                 lambda: write(home, valid_home)),
                ("required_host_slot_unbound",
                 lambda: write(home, valid_home.replace("from './Card'", "from './Unrelated'")),
                 lambda: write(home, valid_home)),
                ("required_host_slot_unbound",
                 lambda: write(home, valid_home.replace("from './Card'", "from '@other/card'")),
                 lambda: write(home, valid_home)),
            ]:
                with self.subTest(code=code):
                    damage()
                    try:
                        failed = gate(project, "ui_delivery_gate.py", "--project-root", str(project),
                                      "--wiring-dir", str(inventory), "--output-json", str(output))
                        self.assertEqual(failed.returncode, 2, failed.stderr)
                        result = json.loads(output.read_text(encoding="utf-8"))
                        self.assertEqual(result["status"], "BLOCKED")
                        self.assertNotIn("card", result["wired_units"])
                        finding = next(row for row in result["failure_findings"] if row["code"] == code)
                        self.assertEqual(finding["unit_id"], "card")
                        self.assertEqual(finding["root_cause"], "product_defect")
                        if code == "required_state_missing":
                            self.assertEqual(finding["state_id"], "loading")
                    finally:
                        restore()

            failing_output = gate(project, "ui_stage1_gate.py", "--project-root", str(project),
                                  "--output-json", str(project))
            self.assertEqual(failing_output.returncode, 3)
            self.assertIn("tool_error", failing_output.stderr)

            inventory_data = json.loads(inventory.read_text(encoding="utf-8"))
            del inventory_data["units"][1]["integration"]
            write_json(inventory, inventory_data)
            missing_host = gate(project, "ui_stage1_gate.py", "--project-root", str(project))
            self.assertEqual(missing_host.returncode, 2)
            findings = json.loads(missing_host.stdout)["failure_findings"]
            self.assertTrue(any(row["code"] == "required_host_slot_missing" and row["unit_id"] == "card"
                                and row["root_cause"] == "product_defect" for row in findings))

            (project / SCRIPTS / "lib/ios_ui_delivery_gate.py").unlink()
            for entry in ("ui_stage1_gate.py", "ui_delivery_gate.py"):
                broken = gate(project, entry, "--help")
                self.assertEqual(broken.returncode, 3, broken.stderr)
                self.assertIn("tool_error", broken.stderr)

    def test_installed_gate_rejects_stale_frozen_inputs(self):
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            self.assertEqual(install(project).returncode, 0)
            inventory, _, _, _ = delivery_fixture(project)
            index = project / "spec/execution/ui-inputs/index.json"
            packet_index = {"schema_version": 2, "inventory_source": {
                                "path": inventory.relative_to(project).as_posix(),
                                "sha256": hashlib.sha256(inventory.read_bytes()).hexdigest()},
                            "packets": [{"unit_id": "home"}, {"unit_id": "card", "dispatch_id": "fixture-card-1"}]}
            write_json(index, packet_index)
            args = ("--project-root", str(project), "--inputs-index", str(index))
            completed = gate(project, "ui_stage1_gate.py", *args)
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            packet_index["packets"][1]["dispatch_id"] = "stale"
            write_json(index, packet_index)
            failed = gate(project, "ui_stage1_gate.py", *args)
            self.assertEqual(failed.returncode, 2)
            self.assertIn("conversion_report_stale", failed.stdout)

    def test_upgrade_rejects_damaged_candidate_before_touching_installed_skill(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project = root / "project"
            project.mkdir()
            self.assertEqual(install(project).returncode, 0)
            installed = project / SCRIPTS / "ui_delivery_gate.py"
            installed_before = installed.read_bytes()
            config = project / ".migbot/config.json"
            config_before = config.read_bytes()
            candidate = root / "candidate"
            skill = candidate / "migbot/skills/i2h-execute"
            shutil.copytree(EXECUTE, skill)
            for name in ("lib/ios_stage1_summary.py", "capability_gate.py", "lib/execute_claims.py"):
                with self.subTest(file=name):
                    damaged = skill / "scripts" / name
                    original = damaged.read_bytes()
                    damaged.write_bytes(original + b"\n# changed after packaging\n")
                    try:
                        result = install(project, "--repo-root", str(candidate))
                        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
                        self.assertIn("package_error", result.stderr)
                        self.assertIn(f"checksum mismatch: {name}", result.stderr)
                        self.assertEqual(installed.read_bytes(), installed_before)
                        self.assertEqual(config.read_bytes(), config_before)
                    finally:
                        damaged.write_bytes(original)
            self.assertEqual(gate(project, "ui_delivery_gate.py", "--help").returncode, 0)

    def test_upgrade_replaces_old_launcher_and_removes_stale_distributions(self):
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            self.assertEqual(install(project).returncode, 0)
            entry = project / SCRIPTS / "ui_delivery_gate.py"
            write(entry, "raise SystemExit(2)\n")
            summary_entry = project / SCRIPTS / "stage1_acceptance.py"
            write(summary_entry, "raise SystemExit(2)\n")
            for system, name in (("macos-arm64", "_entry.bin"), ("windows-x64", "_entry.exe")):
                write(project / SCRIPTS / "bin" / system / "_entry.dist" / name, "spec/.a2h a2h-execute")
            self.assertEqual(gate(project, entry.name, "--help").returncode, 2)
            result = install(project)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((project / SCRIPTS / "bin").exists())
            self.assertEqual(gate(project, entry.name, "--help").returncode, 0)
            summary = gate(project, summary_entry.name, "--project-root", str(project), "--kind", "summary")
            self.assertEqual(summary.returncode, 2, summary.stderr)
            self.assertEqual(json.loads(summary.stdout)["policy_gate"], "execute.stage1-summary")


if __name__ == "__main__":
    unittest.main()
