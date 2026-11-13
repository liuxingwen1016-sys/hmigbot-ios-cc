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
                 "IOSVisualGateTests.test_native_smoke_checks_cold_start_formal_coverage_and_same_installation",
                 "IOSVisualGateTests.test_visual_rounds_limit_critical_repairs_across_rebuilds"],
                cwd=project, capture_output=True, text=True, encoding="utf-8", timeout=45,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
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

            alternate_inventory = write(project / "spec/baseline/ui-approved-alt.json", inventory.read_text(encoding="utf-8"))
            compatibility = gate(project, "ui_delivery_gate.py", "--project-root", str(project),
                                 "--wiring-contract", str(alternate_inventory))
            self.assertEqual(compatibility.returncode, 0, compatibility.stdout + compatibility.stderr)
            self.assertEqual(json.loads(compatibility.stdout)["inventory"], alternate_inventory.relative_to(project).as_posix())

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
            packet_index = {"schema_version": 2, "inventory_source": {"sha256": hashlib.sha256(inventory.read_bytes()).hexdigest()},
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
            for name in ("lib/ios_stage1_summary.py", "capability_gate.py"):
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
