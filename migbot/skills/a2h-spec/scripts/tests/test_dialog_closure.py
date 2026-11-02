"""dialog_closure: one status per required Dialog, closure count gate, body identity,
presentation page type, and the deterministic closure report."""
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
BUILDER = SCRIPTS.parent.parent / "android-ui-graph-builder/scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(BUILDER))
import dialog_closure  # noqa: E402
import dialog_inventory  # noqa: E402

JAVA = """package com.ex;
class HostA extends Fragment {
  void a() { new Shared().show(fm, null); }
  void b() { new Lone().show(fm, null); }
  void c() { new SubA().show(fm, null); }
  void d() {
    new Confirm(ctx) { void ok() {} }.show();
    new Confirm(ctx) { void ok() {} }.show();
  }
}
class HostB extends Fragment {
  void a() { new Shared().show(fm, null); }
  void c() { new SubB().show(fm, null); }
}
class Shared extends DialogFragment {}
class Lone extends DialogFragment {}
abstract class BaseSort extends BottomSheetDialogFragment {
  View onCreateView() { return inflater.inflate(R.layout.sort_dialog, c, false); }
}
class SubA extends BaseSort {}
class SubB extends BaseSort {}
abstract class Confirm {
  void show() { new MaterialAlertDialogBuilder(ctx).show(); }
}
"""
FILE = "app/src/main/java/com/ex/Ui.java"
PAGE_A = "spec/baseline/ui/page_0001_HostA.md"
PAGE_B = "spec/baseline/ui/page_0002_HostB.md"


def section(title: str, anchor: str) -> str:
    return (f"### {title}\n- 源码锚点：{anchor}\n- 呈现形态：dialog\n- 触发入口与输入：button\n"
            "- 内容与初始值：无\n- 交互状态：无\n- 确认结果：无\n- 取消与关闭：dismiss\n\n")


class DialogClosure(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.src = Path(self.tmp) / "android"
        self.root = Path(self.tmp) / "project"
        (self.src / "app/src/main/java/com/ex").mkdir(parents=True)
        (self.src / FILE).write_text(JAVA, encoding="utf-8")
        (self.root / "spec/.a2h/spec-run").mkdir(parents=True)
        (self.root / "spec/baseline/ui").mkdir(parents=True)
        self.inv = dialog_inventory.extract_dialog_inventory(str(self.src))
        (self.root / dialog_closure.INVENTORY_REL).write_text(
            json.dumps(self.inv, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        self.cands = {c["source_fqn"].split(".")[-1]: c for c in self.inv["candidates"]}
        self.anons = sorted(self.inv["anonymous_instantiations"], key=lambda a: a["line"])
        self.assertEqual(len(self.anons), 2)
        snap = self.cands["SubA"]["snapshot_ref"]
        (self.root / snap).mkdir(parents=True)
        (self.root / snap / "meta.json").write_text(json.dumps({"activity": "com.ex.BaseSort"}))

        a1, a2 = self.anons
        self.page_a = (
            "# HostA\n## 页内弹窗 / 面板\n"
            + section("shared", f"`{FILE}` Shared")
            + section("lone", f"`{FILE}` Lone")
            + section("sort", f"`{FILE}` BaseSort")
            + section("confirm", f"`{FILE}` Confirm")
            + section("confirm-1", f"`Ui.java:{a1['line']}`")
            + section("confirm-2", f"`Ui.java:{a2['line']}`")
        )
        self.page_b = "# HostB\n## 页内弹窗 / 面板\n" + section("shared-consumer", f"`{FILE}`") \
            + section("sort-consumer", f"`{FILE}` SubB")
        self.rows = {
            "Shared": self._named("Shared", "dialog / centered", f"{PAGE_A}#shared",
                                  [f"{PAGE_A}#shared", f"{PAGE_B}#shared-consumer"], "shared_host_body"),
            "Lone": self._named("Lone", "dialog / centered", f"{PAGE_A}#lone", [f"{PAGE_A}#lone"], "host_inline"),
            "SubA": self._named("SubA", "modal_overlay / sheet", f"{PAGE_A}#sort", [f"{PAGE_A}#sort"],
                                "shared_host_body"),
            "SubB": self._named("SubB", "modal_overlay / sheet", f"{PAGE_A}#sort",
                                [f"{PAGE_B}#sort-consumer"], "shared_host_body"),
            "Confirm": self._named("Confirm", "dialog / confirm", f"{PAGE_A}#confirm",
                                   [f"{PAGE_A}#confirm"], "shared_host_body"),
            "anon1": self._anon(a1, f"{PAGE_A}#confirm", f"{PAGE_A}#confirm-1"),
            "anon2": self._anon(a2, f"{PAGE_A}#confirm", f"{PAGE_A}#confirm-2"),
        }
        self._write()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _named(self, short, presentation, body, instances, closure):
        c = self.cands[short]
        sites = sorted(f"{e['source_file']}:{e['line']}" for e in c["usage_edges"])
        return {"key": c["dialog_id"], "kind": "named", "fqn": c["source_fqn"], "sites": sites,
                "hosts": [h for h in c["host_fqns"] if h != "unresolved"], "presentation": presentation,
                "snap": c["snapshot_ref"] or "none", "body": body, "instances": instances,
                "closure": closure}

    def _anon(self, a, body, instance):
        return {"key": a["instance_id"], "kind": "anonymous", "fqn": a["base_fqn"],
                "sites": [f"{a['source_file']}:{a['line']}"], "hosts": a["host_fqns"],
                "presentation": "dialog / confirm", "snap": "none", "body": body,
                "instances": [instance], "closure": "shared_host_body"}

    def _write(self):
        (self.root / PAGE_A).write_text(self.page_a, encoding="utf-8")
        (self.root / PAGE_B).write_text(self.page_b, encoding="utf-8")
        br = "<br>".join
        lines = ["# UI", "dialog_index_schema: 1", "## 弹窗 / 面板索引",
                 "| dialog key | row kind | source FQN | call site | hosts | usage / presentation | "
                 "snapshot ref | body spec location | instance spec location | closure |",
                 "|---|---|---|---|---|---|---|---|---|---|"]
        for r in self.rows.values():
            lines.append(
                f"| `{r['key']}` | `{r['kind']}` | `{r['fqn']}` | {br(r['sites'])} | {br(r['hosts'])} | "
                f"{r['presentation']} | {r['snap']} | `{r['body']}` | {br(r['instances'])} | {r['closure']} |")
        (self.root / "spec/baseline/ui-manifest.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _run(self):
        return dialog_closure.validate_all(str(self.src), str(self.root), inventory=self.inv)

    def _rules(self, result, key=None):
        return {f["rule"] for f in result.findings
                if f["severity"] == "blocking" and (key is None or f["subject"] == key)}

    def _status(self, result, name):
        key = self.rows[name]["key"]
        return next(r["status"] for r in result.rows if r["dialog_key"] == key)

    # --- closure accounting ---------------------------------------------------------
    def test_valid_fixture_closes_every_required_row(self):
        result = self._run()
        self.assertEqual(self._rules(result), set(), result.findings)
        s = result.summary
        self.assertEqual((s["required"], s["closed"], s["invalid"], s["unaccounted"]), (7, 7, 0, 0))

    def test_shared_row_with_wrong_snapshot_is_invalid_and_blocks_the_count(self):
        """The old elif chain let shared_host_body rows skip snapshot validation."""
        self.rows["SubB"]["snap"] = "none"
        self._write()
        result = self._run()
        self.assertEqual(self._status(result, "SubB"), "invalid")
        self.assertIn("SPEC.DIALOG_SNAPSHOT_MISMATCH", self._rules(result, self.rows["SubB"]["key"]))
        self.assertIn("SPEC.DIALOG_CLOSURE_INCOMPLETE", self._rules(result))
        self.assertLess(result.summary["closed"], result.summary["required"])

    def test_missing_row_is_unaccounted(self):
        del self.rows["Lone"]
        self._write()
        result = self._run()
        self.assertEqual(result.summary["unaccounted"], 1)
        self.assertIn("SPEC.DIALOG_CLOSURE_INCOMPLETE", self._rules(result))

    # --- body identity (F2) --------------------------------------------------------------
    def test_unrelated_dialog_piled_onto_another_body_fails(self):
        """DS: six unrelated dialogs pointed at StreamingConfirmationDialog's section."""
        self.rows["Lone"]["body"] = f"{PAGE_A}#shared"
        self.rows["Lone"]["closure"] = "host_inline"
        self._write()
        result = self._run()
        self.assertEqual(self._status(result, "Lone"), "invalid")
        self.assertIn("SPEC.DIALOG_BODY_IDENTITY_MISMATCH", self._rules(result, self.rows["Lone"]["key"]))

    def test_instance_pointing_at_another_dialogs_section_fails(self):
        """DS: TimeRangeDialog's only instance link pointed at an unrelated section."""
        self.page_a += section("elsewhere", "`Other.java` Something")
        self.rows["Lone"]["instances"] = [f"{PAGE_A}#elsewhere"]
        self._write()
        result = self._run()
        self.assertIn("SPEC.DIALOG_BODY_IDENTITY_MISMATCH", self._rules(result, self.rows["Lone"]["key"]))

    def test_inheritance_family_may_share_one_body(self):
        result = self._run()
        self.assertEqual(self._status(result, "SubA"), "closed")
        self.assertEqual(self._status(result, "SubB"), "closed")

    def test_two_anonymous_instances_cannot_share_one_instance_section(self):
        self.rows["anon2"]["instances"] = [f"{PAGE_A}#confirm-1"]
        self._write()
        result = self._run()
        self.assertEqual(self._status(result, "anon2"), "invalid")
        self.assertIn("SPEC.DIALOG_BODY_IDENTITY_MISMATCH", self._rules(result, self.rows["anon1"]["key"]))

    def test_anonymous_section_must_cite_its_call_site_line(self):
        self.page_a = self.page_a.replace(f"`Ui.java:{self.anons[0]['line']}`", "`Ui.java`")
        self._write()
        result = self._run()
        self.assertEqual(self._status(result, "anon1"), "invalid")

    # --- presentation page type (F4) ------------------------------------------------------
    def test_presentation_page_type_must_match_inventory(self):
        for bad in ("dialog / sheet", "modal_overlay", "modal_overlay / "):
            self.rows["SubA"]["presentation"] = bad
            self._write()
            result = self._run()
            self.assertIn("SPEC.DIALOG_PRESENTATION_TYPE_MISMATCH",
                          self._rules(result, self.rows["SubA"]["key"]), bad)

    # --- approved skip --------------------------------------------------------------------
    def test_approved_skip_needs_no_body_or_snapshot(self):
        self.rows["Lone"].update(closure="approved_skip:D-007", body="none", instances=[])
        (self.root / "spec/decision-ledger.md").write_text(
            "### D-007 skip Lone\n- 状态：approved\n- 覆盖：com.ex.Lone\n", encoding="utf-8")
        self._write()
        result = self._run()
        self.assertEqual(self._status(result, "Lone"), "approved_skip")
        self.assertEqual(self._rules(result), set(), result.findings)
        (self.root / "spec/decision-ledger.md").write_text(
            "### D-007 skip Lone\n- 状态：proposed\n- 覆盖：com.ex.Lone\n", encoding="utf-8")
        self.assertIn("SPEC.DIALOG_SKIP_INVALID", self._rules(self._run()))

    # --- report ---------------------------------------------------------------------------
    def test_report_is_deterministic_apart_from_meta(self):
        a = dialog_closure.report_payload(self._run(), "t1")
        b = dialog_closure.report_payload(self._run(), "t2")
        a.pop("meta"), b.pop("meta")
        self.assertEqual(a, b)
        self.assertEqual(a["inventory_digest"], dialog_closure.digest(self.inv))

    def test_write_report_is_atomic_and_leaves_no_temp_files(self):
        path = dialog_closure.write_report(str(self.root), self._run())
        self.assertTrue(os.path.isfile(path))
        leftovers = [p for p in os.listdir(os.path.dirname(path)) if p.startswith(".dialog-closure-")]
        self.assertEqual(leftovers, [])


class Packaging(unittest.TestCase):
    def test_pipeline_never_passes_the_deprecated_legacy_flag(self):
        """Legacy mode is for manual old-baseline migration only; no pipeline command
        (a line that invokes lint_coverage.py / dialog_index.py) may pass the flag."""
        skill = SCRIPTS.parent
        offenders = []
        for md in list(skill.rglob("*.md")):
            for n, line in enumerate(md.read_text(encoding="utf-8").splitlines(), 1):
                if "--allow-legacy-dialog-pages" in line and \
                        ("lint_coverage.py" in line or "dialog_index.py" in line):
                    offenders.append(f"{md.name}:{n}")
        self.assertEqual(offenders, [])

    def test_script_compression_treats_dialog_closure_as_a_library(self):
        repo = next((p for p in SCRIPTS.parents if (p / "build/script-compression/scripts").is_dir()),
                    None)
        if repo is None:
            self.skipTest("build/script-compression not present (distributed copy)")
        sys.path.insert(0, str(repo / "build/script-compression/scripts"))
        import config
        kinds = config.classify_scripts_dir(str(SCRIPTS))
        self.assertEqual(kinds.get("dialog_closure"), "lib")
        self.assertEqual(kinds.get("lint_coverage"), "entry")


if __name__ == "__main__":
    unittest.main()
