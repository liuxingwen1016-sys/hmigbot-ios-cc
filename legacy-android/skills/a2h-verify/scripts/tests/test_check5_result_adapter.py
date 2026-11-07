import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

import check5_result_adapter as adapter
from check5_result_adapter import adapt_validated_result, run_adapter  # noqa: E402


def write_run(root, setting="INSTALLED_UNVERIFIED", interaction="INSTALLED_UNVERIFIED"):
    lanes = {}
    for lane, domain, terminal in (("setting", "setting_effect", setting), ("interaction", "interaction_handler", interaction)):
        path = root / lane / "result.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        value = {"schema_version": 1, "domain": domain, "mode": "fast_fix", "finalized": True,
                 "terminal_state": terminal, "verification_status": "NOT_PERFORMED",
                 "correctness_claim": "TARGET_RUNTIME_VERIFIED" if terminal == "RUNTIME_VERIFIED" else "NONE",
                 "build_status": "PASS", "install_status": "PASS", "changed_files": ["pages/Page.ets"]}
        path.write_text(json.dumps(value), encoding="utf-8")
        lanes[lane] = {"terminal_state": terminal, "result": {"path": str(path.resolve()), "sha256": adapter.sha256(path)}}
    value = {"schema_version": 1, "mode": "unified-effect-result", "finalized": True,
             "terminal_state": "FINISHED_NOT_INSTALLED_UNVERIFIED", "correctness_claim": "NONE",
             "workflow_complete": True, "semantic_review_complete": True, "errors": {}, "lanes": lanes}
    (root / "result.json").write_text(json.dumps(value), encoding="utf-8")
    return value


class Check5ResultAdapterTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.result_path = self.root / "result.json"

    def adapt(self, value):
        self.result_path.write_text(json.dumps(value), encoding="utf-8")
        return adapt_validated_result(value, self.result_path)

    def update_lane(self, value, lane, **fields):
        path = self.root / lane / "result.json"
        native = json.loads(path.read_text(encoding="utf-8"))
        native.update(fields)
        path.write_text(json.dumps(native), encoding="utf-8")
        value["lanes"][lane]["result"]["sha256"] = adapter.sha256(path)

    def test_scope_ownership_preserves_responsibility_and_evidence_without_changing_status(self):
        incomplete = {
            "version": 1, "stage": "BASELINE_REVIEW", "complete": False,
            "unresolved_count": 2, "outside_selected_scope": ["outside-hazard"],
            "records": [
                {"hazard_id": "sdk-hazard", "steward_contract_id": "click-1", "status": "UNRESOLVED",
                 "evidence": "SDK declaration does not resolve the caller state.",
                 "evidence_gap": {"kind": "SDK_SEMANTICS_UNCONFIRMED",
                                  "checked_sources": ["sdk/api.d.ts"], "missing_fact": "Caller state"},
                 "review_handoff": {"related_contract_ids": ["click-2"], "confirmed_contract_ids": [],
                                    "next_action": "RECONCILE_EXISTING_REVIEW_EVIDENCE",
                                    "grants_repair_authority": False}},
                {"hazard_id": "owner-hazard", "steward_contract_id": "click-3",
                 "status": "OWNER_INCOMPLETE", "owner_contract_id": "click-4",
                 "repair_owner_paths": ["Service.ets"], "missing_owner_paths": ["Service.ets"],
                 "evidence": "The confirmed owner is missing from the repair targets."},
            ],
        }
        complete = {"version": 1, "stage": "BASELINE_REVIEW", "complete": True,
                    "unresolved_count": 0, "outside_selected_scope": [], "records": []}
        for ownership in (incomplete, complete):
            with self.subTest(complete=ownership["complete"]):
                value = write_run(self.root)
                value.update(scope_ownership=ownership, semantic_review_complete=ownership["complete"])
                self.update_lane(value, "interaction", scope_ownership=ownership)
                adapted = self.adapt(value)
                self.assertEqual(ownership, adapted["scope_ownership"])
                self.assertEqual(ownership, adapted["lanes"]["interaction"]["scope_ownership"])
                self.assertNotIn("scope_ownership", adapted["lanes"]["setting"])
                self.assertEqual(ownership["complete"], adapted["semantic_review_complete"])
                self.assertEqual("WARN", adapted["status"])
                self.assertTrue(adapted["report_only"])
                self.assertFalse(adapted["correctness_verified"])

    def test_legacy_results_do_not_invent_scope_ownership(self):
        adapted = self.adapt(write_run(self.root))
        self.assertNotIn("scope_ownership", adapted)
        for lane in adapted["lanes"].values():
            self.assertNotIn("scope_ownership", lane)
        self.assertEqual("WARN", adapted["status"])

    def test_static_handoffs_preserve_owner_and_current_evidence_in_contract_summaries(self):
        value = write_run(self.root)
        contracts = [{
            "contract_id": "click-1", "baseline_verdict": "FIX_REQUIRED", "latest_execution": "PARTIAL",
            "static_gaps": [{"kind": "CONFIRMED_STATIC_HANDOFF", "evidence": {
                "kind": "PLATFORM_CONTRACT", "reference": "ExampleAPI", "owner_paths": ["Service.ets"],
                "unowned_paths": ["Service.ets"], "evidence": "The current caller still lacks readiness.",
                "next_action": "REVIEW_OWNER_BEFORE_REPAIR", "grants_repair_authority": False,
                "source_evidence": [{"path": "Service.ets", "sha256": "a" * 64,
                                     "line": 10, "excerpt": "player.start();"}],
            }}],
        }]
        self.update_lane(value, "interaction", contract_summaries=contracts,
                         static_gap_contract_ids=["click-1"])
        adapted = self.adapt(value)
        self.assertEqual(contracts, adapted["lanes"]["interaction"]["contract_summaries"])
        self.assertEqual(["click-1"], adapted["lanes"]["interaction"]["static_gap_contract_ids"])
        self.assertEqual("WARN", adapted["status"])

    def test_failed_validation_does_not_publish_ownership_or_reuse_old_summary(self):
        value = write_run(self.root)
        ownership = {"version": 1, "complete": True, "unresolved_count": 0, "records": []}
        value["scope_ownership"] = ownership
        self.update_lane(value, "interaction", scope_ownership=ownership)
        self.result_path.write_text(json.dumps(value), encoding="utf-8")
        original = self.result_path.read_bytes()
        skill = self.root / "skill"
        (skill / "scripts").mkdir(parents=True)
        (skill / "scripts/unified_pipeline.py").write_text("raise SystemExit(2)", encoding="utf-8")
        summary = self.root / "summary.json"
        summary.write_text(json.dumps({"status": "WARN", "scope_ownership": ownership,
                                       "lanes": {"interaction": {"scope_ownership": ownership}}}), encoding="utf-8")
        self.assertEqual(0, run_adapter(skill, self.root, summary))
        result = json.loads(summary.read_text(encoding="utf-8"))
        self.assertEqual("ERROR", result["status"])
        self.assertEqual("FAIL", result["result_validation"])
        self.assertNotIn("scope_ownership", result)
        self.assertNotIn("lanes", result)
        self.assertEqual(original, self.result_path.read_bytes())

    def test_lane_terminal_mapping_and_report_only(self):
        for lane, mapping in (("setting", adapter.TERMINAL_TO_CHECK_STATUS), ("interaction", adapter.INTERACTION_TERMINALS)):
            for terminal, expected in mapping.items():
                with self.subTest(lane=lane, terminal=terminal):
                    value = write_run(self.root, **{lane: terminal})
                    adapted = self.adapt(value)
                    self.assertEqual(expected, adapted["lanes"][lane]["status"])
                    self.assertTrue(adapted["report_only"])
                    self.assertFalse(adapted["correctness_verified"])
                    self.assertNotEqual("PASS", adapted["status"])

    def test_build_failure_not_hidden_by_unified_finished(self):
        self.assertEqual("ERROR", self.adapt(write_run(self.root, interaction="BUILD_FAILED_NOT_INSTALLED"))["status"])

    def test_continuation_keeps_inherited_and_executed_stages_separate(self):
        value = write_run(self.root)
        fields = {
            "repair_mode": "round-2-continuation",
            "continuation": {"path": str(self.root / "continuation.json"), "sha256": "validated-upstream"},
            "inherited_stages": ["baseline-review", "round-1"],
            "executed_stages": ["quick-review", "round-2"],
        }
        value.update(fields)
        adapted = self.adapt(value)
        for key, expected in fields.items():
            self.assertEqual(expected, adapted[key])
        self.assertEqual("WARN", adapted["status"])
        self.assertFalse(adapted["correctness_verified"])

    def test_target_runtime_pass_keeps_scope_without_promoting_setting(self):
        adapted = self.adapt(write_run(self.root, interaction="RUNTIME_VERIFIED"))
        self.assertEqual("WARN", adapted["status"])
        self.assertEqual("NONE", adapted["lanes"]["setting"]["correctness_claim"])
        self.assertEqual("TARGET_RUNTIME_VERIFIED", adapted["lanes"]["interaction"]["correctness_claim"])

    def test_global_incomplete_and_errors_are_errors(self):
        for key, val in (("terminal_state", "WORKFLOW_INCOMPLETE"), ("workflow_complete", False), ("errors", {"dispatch": "gap"})):
            value = write_run(self.root)
            value[key] = val
            self.assertEqual("ERROR", self.adapt(value)["status"])

    def test_unknown_or_provisional_results_rejected(self):
        for key, val in (("finalized", False), ("schema_version", 2), ("terminal_state", "NEW_SUCCESS"), ("correctness_claim", "PASS"), ("mode", "fast_fix")):
            value = write_run(self.root)
            value[key] = val
            with self.assertRaises(ValueError):
                self.adapt(value)

    def test_missing_lane_rejected(self):
        value = write_run(self.root)
        del value["lanes"]["interaction"]
        with self.assertRaises(ValueError):
            self.adapt(value)

    def test_lane_hash_and_path_drift_rejected(self):
        for field, replacement in (("sha256", "bad"), ("path", str(self.root / "elsewhere.json"))):
            value = write_run(self.root)
            value["lanes"]["setting"]["result"][field] = replacement
            with self.assertRaises(ValueError):
                self.adapt(value)

    def test_missing_validator_and_child_failure_are_nonblocking_errors(self):
        skill = self.root / "skill"
        summary = self.root / "summary.json"
        self.assertEqual(0, run_adapter(skill, self.root, summary))
        failure = json.loads(summary.read_text())
        self.assertEqual("FAIL", failure["result_validation"])
        self.assertEqual("CHECK-5", failure["check_id"])
        self.assertEqual("check5_behavior_effect_adapter", failure["domain"])
        self.assertTrue(failure["report_only"])
        (skill / "scripts").mkdir(parents=True)
        (skill / "scripts/unified_pipeline.py").write_text("raise SystemExit(2)", encoding="utf-8")
        self.assertEqual(0, run_adapter(skill, self.root, summary))
        self.assertEqual("ERROR", json.loads(summary.read_text())["status"])
        with patch("check5_result_adapter.subprocess.run", side_effect=FileNotFoundError(2, "not found")):
            self.assertEqual(0, run_adapter(skill, self.root, summary))
        self.assertIn("could not start", json.loads(summary.read_text())["validation_error"])

    def test_successful_child_validation_still_rejects_provisional_and_malformed(self):
        skill = self.root / "skill"
        (skill / "scripts").mkdir(parents=True)
        (skill / "scripts/unified_pipeline.py").write_text("print('{}')", encoding="utf-8")
        summary = self.root / "summary.json"
        for value in ({"schema_version": 1, "mode": "unified-effect-result", "finalized": False},
                      dict(write_run(self.root), lanes={"setting": None, "interaction": None})):
            self.result_path.write_text(json.dumps(value), encoding="utf-8")
            self.assertEqual(0, run_adapter(skill, self.root, summary))
            self.assertEqual("ERROR", json.loads(summary.read_text())["status"])

    def test_real_unified_init_validate_does_not_count_as_completion(self):
        skill = SCRIPT_DIR.parents[1] / "arkts-behavior-verify"
        android = self.root / "android"
        arkts = self.root / "arkts"
        android.mkdir()
        (arkts / "entry/src/main/ets").mkdir(parents=True)
        out = arkts / "spec/run"
        subprocess.run([sys.executable, "-B", str(skill / "scripts/unified_pipeline.py"), "init", "--out", str(out),
                        "--android-root", str(android), "--arkts-root", str(arkts), "--max-agents", "1"],
                       check=True, capture_output=True)
        summary = out / "adapter.json"
        self.assertEqual(0, run_adapter(skill, out, summary))
        self.assertEqual("ERROR", json.loads(summary.read_text())["status"])

    def test_validated_run_exports_both_lanes(self):
        write_run(self.root)
        skill = self.root / "skill"
        (skill / "scripts").mkdir(parents=True)
        (skill / "scripts/unified_pipeline.py").write_text("print('{}')", encoding="utf-8")
        summary = self.root / "summary.json"
        self.assertEqual(0, run_adapter(skill, self.root, summary))
        result = json.loads(summary.read_text())
        self.assertEqual("WARN", result["status"])
        self.assertEqual("CHECK-5", result["check_id"])
        self.assertEqual("check5_behavior_effect_adapter", result["domain"])
        self.assertEqual("CHECK-5.1", result["lanes"]["setting"]["check_id"])
        self.assertEqual("CHECK-5.2", result["lanes"]["interaction"]["check_id"])
        self.assertEqual({"setting", "interaction"}, set(result["lanes"]))
        self.assertEqual(["pages/Page.ets"], result["lanes"]["setting"]["changed_files"])

    def test_output_blocked_run_stays_unsealed_and_resumes_without_reinitializing(self):
        skill = SCRIPT_DIR.parents[1] / "arkts-behavior-verify"
        android, arkts, out = self.root / "android", self.root / "arkts", self.root / "run"
        android.mkdir()
        (arkts / "entry/src/main/ets").mkdir(parents=True)
        command = [sys.executable, "-B", str(skill / "scripts/unified_pipeline.py")]
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1")

        def call(*args):
            return subprocess.run([*command, *args], capture_output=True, text=True,
                                  encoding="utf-8", env=env)

        initialized = call("init", "--out", str(out), "--android-root", str(android),
                           "--arkts-root", str(arkts), "--max-agents", "1")
        self.assertEqual(0, initialized.returncode, initialized.stderr)
        config_bytes = (out / "run-config.json").read_bytes()
        result_bytes = (out / "result.json").read_bytes()
        helper = out / "interaction/temporary-author.py"
        helper.write_text("# temporary citation assembly\n", encoding="utf-8")
        blocked = call("finalize", "--out", str(out))
        self.assertNotEqual(0, blocked.returncode)
        self.assertIn("OUTPUT_INTEGRITY_BLOCKED", blocked.stdout + blocked.stderr)
        summary = out / "behavior-effect-adapter.json"
        self.assertEqual(0, run_adapter(skill, out, summary))
        self.assertEqual("FAIL", json.loads(summary.read_text())["result_validation"])
        self.assertEqual(result_bytes, (out / "result.json").read_bytes())
        self.assertFalse((out / "result.lock.json").exists())

        helper.rename(self.root / "temporary-author.py")
        resumed = call("finalize", "--out", str(out))
        self.assertEqual(0, resumed.returncode, resumed.stderr)
        self.assertEqual(0, run_adapter(skill, out, summary))
        result = json.loads(summary.read_text())
        self.assertEqual("PASS", result["result_validation"])
        self.assertEqual("ERROR", result["status"])  # No real Review/Repair in this fixture.
        self.assertFalse(result["workflow_complete"])
        self.assertEqual(config_bytes, (out / "run-config.json").read_bytes())

    def test_setting_cannot_inherit_runtime_correctness(self):
        value = write_run(self.root)
        path = self.root / "setting/result.json"
        native = json.loads(path.read_text())
        native["correctness_claim"] = "TARGET_RUNTIME_VERIFIED"
        path.write_text(json.dumps(native), encoding="utf-8")
        value["lanes"]["setting"]["result"]["sha256"] = adapter.sha256(path)
        with self.assertRaisesRegex(ValueError, 'must not claim correctness'):
            self.adapt(value)


class ValidatorCommandTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.exporter = self.root / "unified_pipeline.py"
        self.env = patch.dict(os.environ, {}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_source_keeps_versioned_or_custom_interpreter(self) -> None:
        for executable in ("/venv/bin/python3.12", "/custom/my-python"):
            with self.subTest(executable=executable), patch.object(sys, "executable", executable):
                self.assertEqual(executable, adapter._validator_command(self.exporter, self.root)[0])

    def test_bundled_source_falls_back_after_broken_alias(self) -> None:
        with patch.object(adapter, "__compiled__", True, create=True), \
             patch.object(adapter.shutil, "which", side_effect=lambda name: name), \
             patch.object(adapter.subprocess, "run", side_effect=[
                 subprocess.CompletedProcess([], 1, "", "broken alias"),
                 subprocess.CompletedProcess([], 0, "arkts-python-ok\n", ""),
             ]) as run:
            self.assertEqual("python3", adapter._validator_command(self.exporter, self.root)[0])
            self.assertEqual(2, run.call_count)

    def test_explicit_py_launcher_selects_python3(self) -> None:
        with patch.dict(os.environ, {"ARKTS_PYTHON": "py"}), \
             patch.object(adapter.shutil, "which", return_value="py.exe"), \
             patch.object(adapter.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "arkts-python-ok", "")):
            self.assertEqual(["py.exe", "-3"], adapter._validator_command(self.exporter, self.root)[:2])

    def test_invalid_explicit_override_is_not_silently_ignored(self) -> None:
        with patch.dict(os.environ, {"ARKTS_PYTHON": "missing-python"}), \
             patch.object(adapter.shutil, "which", return_value=None):
            with self.assertRaisesRegex(FileNotFoundError, "missing-python"):
                adapter._validator_command(self.exporter, self.root)

    def test_probe_timeout_becomes_structured_error(self) -> None:
        self.exporter.write_text("# source", encoding="utf-8")
        skill = self.root / "skill"
        (skill / "scripts").mkdir(parents=True)
        (skill / "scripts" / self.exporter.name).write_text("# source", encoding="utf-8")
        summary = self.root / "summary.json"
        with patch.object(adapter, "__compiled__", True, create=True), \
             patch.object(adapter.shutil, "which", return_value="python.exe"), \
             patch.object(adapter.subprocess, "run", side_effect=subprocess.TimeoutExpired("probe", 10)):
            self.assertEqual(0, run_adapter(skill, self.root, summary))
        self.assertEqual("FAIL", json.loads(summary.read_text(encoding="utf-8"))["result_validation"])

    def test_real_child_preserves_unicode_and_target_skill_dir(self) -> None:
        skill = self.root / "子 Skill"
        scripts = skill / "scripts"
        scripts.mkdir(parents=True)
        (scripts / "unified_pipeline.py").write_text(
            "import os, sys\nfrom pathlib import Path\n"
            "assert Path(os.environ['ARKTS_SKILL_DIR']) == Path(__file__).parent\n"
            "print('校验失败', file=sys.stderr)\nraise SystemExit(2)\n", encoding="utf-8")
        summary = self.root / "summary.json"
        with patch.dict(os.environ, {"ARKTS_SKILL_DIR": "wrong-parent"}):
            self.assertEqual(0, run_adapter(skill, self.root, summary))
        self.assertEqual("校验失败", json.loads(summary.read_text(encoding="utf-8"))["validation_error"])


if __name__ == "__main__":
    unittest.main()
