#!/usr/bin/env python3
"""gate_ledger.py：放行条目的机械核对 + open-findings 放行标记（references/gate-handling.md）。

锚点：gpt1030_2（2026-10-18）全程无人值守，34 条决策里 23 条工具缺口、3 条未达标放行，
当时靠人逐条核证据；本测试把「证据行真实含该符号」「精确类不能放行」「编译门只能停」变成机械判据。
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

import _a2h_findings as findings  # noqa: E402
import gate_ledger  # noqa: E402

HEAD = """# Migration Decisions — demo

## 决策索引

| D-编号 | 类目 | 一行结论 | 状态 | 审批来源 |
|---|---|---|---|---|

## D 编号决策

"""


def tool_gap(did="D-010", gate="closure.wiring / C4_BUILDER_NOT_FOUND", evidence=None, count="2 / 4",
             output="`spec/out/wiring.json:2`", rounds=None):
    evidence = evidence or "`entry/src/main/ets/pages/Home.ets:3` `RecommendContent`；`app/src/Rec.kt:2` `RecommendFragment`"
    lines = [f"### {did} 接线检测不认 Content 嵌入", "- **类型**：工具缺口", f"- **门禁**：{gate}",
             "- **审批来源**：default-policy（gate-handling）", f"- **工具输出**：{output}",
             f"- **证据**：{evidence}", "- **漏认写法**：只认字面 XxxPage() 调用", f"- **涉及条目**：{count}"]
    if rounds:
        lines.append(f"- **已修轮次**：{rounds}")
    return "\n".join(lines + ["- **选定**：放行；同源 FAIL 复用本条", ""])


def unmet(did="D-011", gate="execute.fv1-final"):
    return "\n".join([f"### {did} FV-1 未达标放行", "- **类型**：未达标放行", f"- **门禁**：{gate}",
                      "- **审批来源**：default-policy（gate-handling）", "- **工具输出**：`spec/out/wiring.json`",
                      "- **已修轮次**：3", "- **剩余 FAIL**：孤儿 4 项", "- **选定**：放行继续", ""])


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.project = self.tmp / "harmony"
        self.android = self.tmp / "android"
        (self.project / "entry/src/main/ets/pages").mkdir(parents=True)
        (self.project / "spec/out").mkdir(parents=True)
        (self.android / "app/src").mkdir(parents=True)
        (self.project / "entry/src/main/ets/pages/Home.ets").write_text(
            "@Entry\n@ComponentV2\nstruct Home { build() { Column() { RecommendContent() } } }\n", encoding="utf-8")
        (self.project / "spec/out/wiring.json").write_text(json.dumps({"categories": {"C4_parent_replacement": {
            "details": [{"status": "FAIL", "failed_check": "C4_BUILDER_NOT_FOUND"}]}}}, indent=2) + "\n",
            encoding="utf-8")
        (self.android / "app/src/Rec.kt").write_text("package x\nclass RecommendFragment : Fragment()\n",
                                                     encoding="utf-8")
        self.registry = gate_ledger.load_registry()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _check(self, body):
        (self.project / "spec").mkdir(exist_ok=True)
        (self.project / "spec/decision-ledger.md").write_text(HEAD + body, encoding="utf-8")
        return gate_ledger.main(["check", "--project-root", str(self.project), "--android-root", str(self.android)])

    def _summary(self):
        return (self.project / "spec/gate-release/summary.md").read_text(encoding="utf-8")


class GateLedger(_Base):
    def test_valid_tool_gap_passes_and_writes_three_outputs(self):
        self.assertEqual(self._check(tool_gap() + unmet()), 0)
        out = self.project / "spec/gate-release"
        self.assertIn("| D-010 | closure.wiring / C4_BUILDER_NOT_FOUND | inference |", self._summary())
        focus = json.loads((out / "verify-focus.json").read_text(encoding="utf-8"))
        self.assertEqual([i["decision"] for i in focus["items"]], ["D-010", "D-011"])
        self.assertEqual(focus["items"][0]["harmony_locations"], ["entry/src/main/ets/pages/Home.ets:3"])
        feedback = (out / "tool-gap-feedback.md").read_text(encoding="utf-8")
        self.assertIn("verify_slice_wiring.py", feedback)
        self.assertIn("`app/src/Rec.kt:2` `RecommendFragment`", feedback)

    def test_fabricated_line_is_rejected(self):
        evidence = "`app/src/Rec.kt:1` `RecommendFragment`"   # 第 1 行是 package，±2 行内仍能读到第 2 行
        self.assertEqual(self._check(tool_gap(evidence=evidence)), 0)
        far = "`app/src/Rec.kt:9` `RecommendFragment`"
        self.assertEqual(self._check(tool_gap(evidence=far)), 1)
        self.assertIn("只有 2 行", self._summary())

    def test_symbol_not_on_cited_line_is_rejected(self):
        self.assertEqual(self._check(tool_gap(evidence="`app/src/Rec.kt:2` `HomeActivity`")), 1)
        self.assertIn("附近没有 `HomeActivity`", self._summary())

    def test_harmony_side_line_drift_is_tolerated_android_is_not(self):
        # 鸿蒙文件记账后被修复改动 → 行号漂移仍成立；安卓源码同样偏差 → 不成立
        drift = "`entry/src/main/ets/pages/Home.ets:1` `RecommendContent`；`app/src/Rec.kt:2` `RecommendFragment`"
        (self.project / "entry/src/main/ets/pages/Home.ets").write_text(
            "\n\n\n\n\n\n@Entry\nstruct Home { build() { RecommendContent() } }\n", encoding="utf-8")
        self.assertEqual(self._check(tool_gap(evidence=drift)), 0)
        self.assertIn("行号已漂移", self._summary())
        (self.android / "app/src/Rec.kt").write_text("\n\n\n\n\n\nclass RecommendFragment\n", encoding="utf-8")
        self.assertEqual(self._check(tool_gap(evidence=drift)), 1)

    def test_location_without_symbol_is_rejected(self):
        self.assertEqual(self._check(tool_gap(evidence="`app/src/Rec.kt:2`")), 1)

    def test_unknown_gate_is_rejected(self):
        self.assertEqual(self._check(tool_gap(gate="closure.made-up")), 1)
        self.assertIn("不在登记表", self._summary())

    def test_exact_gate_cannot_be_tool_gap_unless_rounds_spent(self):
        self.assertEqual(self._check(tool_gap(gate="plan.coverage / PLAN.REQUIREMENT_UNOWNED")), 1)
        self.assertEqual(self._check(tool_gap(gate="plan.coverage / PLAN.REQUIREMENT_UNOWNED", rounds="2")), 0)
        self.assertIn("🔴 精确类闸疑似缺陷", self._summary())

    def test_build_gate_is_never_released(self):
        self.assertEqual(self._check(unmet(gate="execute.build")), 1)

    def test_hard_rule_cannot_be_unmet(self):
        self.assertEqual(self._check(unmet(gate="closure.arkui-safety / ROUTE_PARAM_KEY_MISMATCH")), 1)
        self.assertEqual(self._check(unmet(gate="closure.arkui-safety / NAV_ROOT_COUNT")), 0)

    def test_high_release_ratio_is_flagged(self):
        self.assertEqual(self._check(tool_gap(count="3 / 4")), 0)
        self.assertIn("放行比例偏高", self._summary())
        self.assertEqual(self._check(tool_gap(count="1 / 10")), 0)
        self.assertNotIn("放行比例偏高", self._summary())

    def test_classify_bare_rule_id(self):
        hit = gate_ledger.resolve(self.registry, "C4_BUILDER_NOT_FOUND")
        self.assertEqual((hit["gate"], hit["class"]), ("closure.wiring", "inference"))
        self.assertEqual(gate_ledger.resolve(self.registry, "SPEC.AC_LINE_UNPARSEABLE")["class"], "exact")
        self.assertTrue(gate_ledger.resolve(self.registry, "ROUTE_PARAM_KEY_MISMATCH")["hard"])

    def test_several_rules_of_one_gate_in_one_entry(self):
        self.assertEqual(self._check(tool_gap(gate="closure.wiring / C4_BUILDER_NOT_FOUND、C4_REPLACEMENT_NOT_FOUND")), 0)
        # 混进别的门禁的规则 → 不成立；混进精确类规则 → 按精确类核
        self.assertEqual(self._check(tool_gap(gate="closure.wiring / C4_BUILDER_NOT_FOUND、NAV_ROOT_COUNT")), 1)
        self.assertEqual(self._check(tool_gap(gate="closure.wiring / C4_BUILDER_NOT_FOUND、C3_FWD_REF_NOT_REMOVED")), 1)

    def test_release_marks_findings_and_unblocks_downstream(self):
        section = "spec/lint_coverage"
        items = [findings.make("SPEC.DIALOG_UNACCOUNTED", "spec", "AppLoadDialog", "x"),
                 findings.make("SPEC.AC_LINE_UNPARSEABLE", "spec", "F001.md:3", "y")]
        findings.replace_section(str(self.project), section, items)
        self.assertEqual(len(findings.upstream_of(str(self.project), "plan")), 2)
        self._check(tool_gap(gate="spec.dialog-closure / SPEC.DIALOG_UNACCOUNTED", count="1 / 2"))
        rc = gate_ledger.main(["release", "--project-root", str(self.project), "--android-root", str(self.android),
                               "--decision", "D-010", "--section", section, "--rule", "SPEC.DIALOG_UNACCOUNTED"])
        self.assertEqual(rc, 0)
        left = findings.upstream_of(str(self.project), "plan")
        self.assertEqual([f["rule"] for f in left], ["SPEC.AC_LINE_UNPARSEABLE"])
        # 原 linter 重跑：同 finding_key 继承 decision_ref，仍列出但不阻断
        again = [findings.make("SPEC.DIALOG_UNACCOUNTED", "spec", "AppLoadDialog", "x")]
        data = findings.replace_section(str(self.project), section, again, after_repair=True)
        self.assertEqual(findings.exit_code(data["sections"][section]["findings"]), 0)
        self.assertIn("已放行 D-010", findings.render(data["sections"][section]["findings"], "spec"))

    def test_release_refuses_an_entry_that_fails_check(self):
        findings.replace_section(str(self.project), "spec/lint_coverage",
                                 [findings.make("SPEC.DIALOG_UNACCOUNTED", "spec", "A", "x")])
        self._check(tool_gap(evidence="`app/src/Rec.kt:2` `Nope`"))
        rc = gate_ledger.main(["release", "--project-root", str(self.project), "--android-root", str(self.android),
                               "--decision", "D-010", "--section", "spec/lint_coverage"])
        self.assertEqual(rc, 1)
        self.assertEqual(len(findings.upstream_of(str(self.project), "plan")), 1)

    def test_halted_section_is_lifted_by_release(self):
        section = "spec/lint_coverage"
        item = [findings.make("SPEC.UNCOVERED_ANCHOR_FILE", "spec", "a.kt", "x")]
        findings.replace_section(str(self.project), section, item)
        for _ in range(4):
            data = findings.replace_section(str(self.project), section,
                                            [findings.make("SPEC.UNCOVERED_ANCHOR_FILE", "spec", "a.kt", "x")],
                                            after_repair=True)
        self.assertTrue(data["sections"][section]["progress"]["halted"])
        self._check(unmet(gate="spec.coverage / SPEC.UNCOVERED_ANCHOR_FILE"))
        rc = gate_ledger.main(["release", "--project-root", str(self.project), "--decision", "D-011",
                               "--section", section])
        self.assertEqual(rc, 0)
        progress = findings.load(str(self.project))["sections"][section]["progress"]
        self.assertFalse(progress["halted"])
        self.assertEqual(findings.section_exit_code(str(self.project), section,
                                                    findings.load(str(self.project))["sections"][section]["findings"]), 0)

    def test_legacy_inline_fields_are_parsed(self):
        body = ("### D-002 AppLoadDialog 包装调用漏认\n"
                "- **类型**：工具缺口；**status**：approved；**approval_source**：user-instruction。\n")
        entries = gate_ledger.parse_ledger(HEAD + body)
        self.assertEqual((entries[0]["kind"], entries[0]["approval"]), ("工具缺口", "user-instruction"))


def undecidable(did="D-012", gate="spec.login-probe", output="`spec/out/wiring.json`"):
    return "\n".join([f"### {did} 缺后端", "- **类型**：阶段不可判定", f"- **门禁**：{gate}",
                      "- **审批来源**：default-policy（gate-handling）", f"- **工具输出**：{output}",
                      "- **缺什么**：可达后端", ""])


class LedgerHardening(_Base):
    """1018 独立复查（H1/H2/M1-M3/L6）：放行记账不能绕过「精确类必须修过」。"""

    def _seed(self, rules):
        findings.replace_section(str(self.project), "spec/lint_coverage",
                                 [findings.make(r, "spec", f"subject-{i}", "x") for i, r in enumerate(rules)])

    def _release(self, *extra):
        return gate_ledger.main(["release", "--project-root", str(self.project), "--android-root", str(self.android),
                                 *extra])

    def _open(self):
        return sorted(f["rule"] for f in findings.upstream_of(str(self.project), "plan"))

    def test_release_without_rule_never_touches_exact_or_other_gates(self):
        self._seed(["SPEC.UNCOVERED_ANCHOR_FILE", "SPEC.AC_LINE_UNPARSEABLE", "SPEC.DIALOG_UNACCOUNTED"])
        self._check(unmet(gate="spec.coverage"))
        self.assertEqual(self._release("--decision", "D-011"), 0)
        self.assertEqual(self._open(), ["SPEC.AC_LINE_UNPARSEABLE", "SPEC.DIALOG_UNACCOUNTED"])

    def test_release_rejects_wrong_section_unknown_rule_and_no_match(self):
        self._seed(["SPEC.UNCOVERED_ANCHOR_FILE"])
        self._check(unmet(gate="spec.coverage / SPEC.UNCOVERED_ANCHOR_FILE"))
        self.assertEqual(self._release("--decision", "D-011", "--section", "spec/lint-coverage"), 1)
        self.assertEqual(self._release("--decision", "D-011", "--rule", "SPEC.TYPO"), 1)
        self._seed(["SPEC.INSTANCE_UNACCOUNTED"])
        self.assertEqual(self._release("--decision", "D-011"), 1)      # 段里没有它覆盖的规则

    def test_gate_without_findings_section_needs_no_release(self):
        self._check(unmet())                                           # execute.fv1-final
        self.assertEqual(self._release("--decision", "D-011"), 1)

    def test_undecidable_is_only_for_env_or_inference(self):
        self.assertEqual(self._check(undecidable()), 0)
        self.assertEqual(self._check(undecidable(gate="execute.resources / missing")), 1)
        self.assertIn("阶段不可判定只用于", self._summary())
        self.assertEqual(self._check(undecidable(gate="closure.arkui-safety / ROUTE_PARAM_KEY_MISMATCH")), 1)

    def _loop_outputs(self):
        out = self.project / "spec/execution/autofix-log/round-1"
        out.mkdir(parents=True, exist_ok=True)
        (out / "audit-pipeline-iter2.json").write_text(json.dumps({"findings": [
            {"subtype": "naked-TODO", "severity_at_scope": "FAIL", "file": "a.ets"},
            {"subtype": "empty-body", "severity_at_scope": "WARN"}]}), encoding="utf-8")
        (out / "arkui-safety-pipeline-iter2.json").write_text(json.dumps({"findings": [
            {"rule_id": "ROUTE_PARAM_KEY_MISMATCH", "severity": "FAIL"},
            {"rule_id": "NAV_SHAPE_UNKNOWN", "severity": "WARN"}], "errors": []}), encoding="utf-8")
        (out / "orphans-pipeline-iter2.json").write_text(json.dumps({"orphans": [{"reason": "NO_IMPORTER"}]}),
                                                          encoding="utf-8")
        rel = "spec/execution/autofix-log/round-1/"
        (out / "loop-result-latest-pipeline-final.json").write_text(json.dumps({"verdict": "STALLED", "detector_json_paths": {
            "audit": rel + "audit-pipeline-iter2.json", "arkui-safety": rel + "arkui-safety-pipeline-iter2.json",
            "orphans": rel + "orphans-pipeline-iter2.json"}}), encoding="utf-8")
        (out / "loops-final-structural-closure.json").write_text(json.dumps({"final_state": "ESCALATED", "final_audit_fail": 1}),
                                                                 encoding="utf-8")
        return "`spec/execution/autofix-log/round-1/loops-final-structural-closure.json`"

    def test_aggregate_gate_is_checked_against_tool_output_not_wording(self):
        # 1018 二审 #1：FV-1 剩余 FAIL 里的精确类 / hard 规则按工具输出核，条目怎么写都绕不过
        out = self._loop_outputs()
        quiet = unmet(gate="execute.fv1-final").replace("`spec/out/wiring.json`", out).replace("孤儿 4 项", "若干项")
        self.assertEqual(self._check(quiet), 1)
        summary = self._summary()
        self.assertIn("naked-TODO×1", summary)
        self.assertIn("ROUTE_PARAM_KEY_MISMATCH×1", summary)
        # 两条闸缺陷都单列成工具缺口后，FV-1 的未达标放行才成立
        gaps = (tool_gap(did="D-020", gate="closure.skeleton / naked-TODO", rounds="2", output=out) +
                tool_gap(did="D-021", gate="closure.arkui-safety / ROUTE_PARAM_KEY_MISMATCH", output=out))
        self.assertEqual(self._check(gaps + quiet), 0)

    def test_lint_gate_entry_is_not_rejected_for_exact_items_left_in_queue(self):
        # 三个 lint 的精确类条目在队列里照常阻断，不因此拒掉同段推断类的未达标放行
        self._seed(["SPEC.UNCOVERED_ANCHOR_FILE", "SPEC.AC_LINE_UNPARSEABLE"])
        body = unmet(gate="spec.coverage").replace("`spec/out/wiring.json`", "`spec/.a2h/open-findings.json`")
        self.assertEqual(self._check(body), 0)
        self.assertEqual(self._release("--decision", "D-011"), 0)
        self.assertEqual(self._open(), ["SPEC.AC_LINE_UNPARSEABLE"])

    def test_wording_alone_no_longer_rejects(self):
        # 1018 二审 #8：正文提到 hard 规则名（"已修过"）而工具输出里没有它，不再误伤
        body = unmet(gate="closure.arkui-safety").replace("孤儿 4 项", "ROUTE_PARAM_KEY_MISMATCH 已修过；NAV 两项")
        self.assertEqual(self._check(body), 0)

    def test_output_checked_gate_needs_detector_json(self):
        (self.project / "spec/out/notes.txt").write_text("FV-1 没过\n", encoding="utf-8")
        self.assertEqual(self._check(unmet(gate="execute.fv1-final").replace("`spec/out/wiring.json`", "`spec/out/notes.txt`")), 1)
        self.assertIn("检测结果 JSON", self._summary())

    def test_exact_gate_tool_gap_must_name_rules(self):
        self.assertEqual(self._check(tool_gap(gate="closure.skeleton", rounds="2")), 1)
        self.assertIn("点名规则", self._summary())

    def test_evidence_cannot_point_at_the_ledger(self):
        # 1018 二审 #4：证据指向 ledger 自己；工具输出用大小写变体指向 ledger
        self.assertEqual(self._check(tool_gap(evidence="`spec/decision-ledger.md:3` `Migration`")), 1)
        self.assertEqual(self._check(tool_gap(output="`spec/Decision-Ledger.md`")), 1)

    def test_tool_gap_release_only_marks_named_subjects(self):
        # 1018 二审 #2：一条工具缺口只放它点到的对象
        findings.replace_section(str(self.project), "spec/lint_coverage", [
            findings.make("SPEC.DIALOG_UNACCOUNTED", "spec", "dlg_aaa", "required Dialog 未闭合：com.x.AppLoadDialog"),
            findings.make("SPEC.DIALOG_UNACCOUNTED", "spec", "dlg_bbb", "required Dialog 未闭合：com.x.PayDialog"),
            findings.make("SPEC.DIALOG_UNACCOUNTED", "spec", "dlg_ccc", "required Dialog 未闭合：com.x.ShareDialog")])
        body = tool_gap(gate="spec.dialog-closure / SPEC.DIALOG_UNACCOUNTED", count="1 / 3").replace(
            "只认字面 XxxPage() 调用", "AppLoadDialog 由静态辅助方法弹出，工具没认出")
        self._check(body)
        self.assertEqual(self._release("--decision", "D-010"), 0)
        left = sorted(f["subject"] for f in findings.upstream_of(str(self.project), "plan"))
        self.assertEqual(left, ["dlg_bbb", "dlg_ccc"])

    def test_tool_gap_release_without_named_subject_needs_matching_count(self):
        findings.replace_section(str(self.project), "spec/lint_coverage", [
            findings.make("SPEC.DIALOG_UNACCOUNTED", "spec", f"dlg_{i}", "x") for i in range(3)])
        self._check(tool_gap(gate="spec.dialog-closure / SPEC.DIALOG_UNACCOUNTED", count="1 / 3"))
        self.assertEqual(self._release("--decision", "D-010"), 1)
        self._check(tool_gap(gate="spec.dialog-closure / SPEC.DIALOG_UNACCOUNTED", count="3 / 3"))
        self.assertEqual(self._release("--decision", "D-010"), 0)

    def test_queue_gate_entry_lifts_the_brake_only(self):
        # 1018 二审 #3：按 classify 记的 findings.queue 条目能解除刹车，段里的实际 FAIL 照旧阻断
        section = "spec/lint_coverage"
        for _ in range(5):
            data = findings.replace_section(str(self.project), section,
                                            [findings.make("SPEC.UNCOVERED_ANCHOR_FILE", "spec", "a.kt", "x")],
                                            after_repair=True)
        self.assertTrue(data["sections"][section]["progress"]["halted"])
        self._check(undecidable(gate="findings.queue / LOOP.NOT_CONVERGING").replace("阶段不可判定", "未达标放行")
                    .replace("- **缺什么**：可达后端", "- **已修轮次**：3\n- **剩余 FAIL**：刹车"))
        self.assertEqual(self._release("--decision", "D-012", "--section", section), 0)
        body = findings.load(str(self.project))["sections"][section]
        self.assertFalse(body["progress"]["halted"])
        self.assertEqual([f["rule"] for f in findings.upstream_of(str(self.project), "plan")], ["SPEC.UNCOVERED_ANCHOR_FILE"])

    def test_queue_entry_citing_open_findings_is_accepted_and_keeps_round_cap(self):
        # 1018 三审 低1：队列门禁条目引用 open-findings 不被队列里的精确类条目拒；解除刹车不清零修复轮次
        section = "spec/lint_coverage"
        for _ in range(5):
            data = findings.replace_section(str(self.project), section,
                                            [findings.make("SPEC.UNCOVERED_ANCHOR_FILE", "spec", "a.kt", "x"),
                                             findings.make("SPEC.AC_LINE_UNPARSEABLE", "spec", "F1.md:3", "y")],
                                            after_repair=True)
        rounds = data["sections"][section]["progress"]["repair_rounds"]
        body = (undecidable(gate="findings.queue / LOOP.NOT_CONVERGING", output="`spec/.a2h/open-findings.json`")
                .replace("阶段不可判定", "未达标放行").replace("- **缺什么**：可达后端", "- **已修轮次**：3\n- **剩余 FAIL**：刹车"))
        self.assertEqual(self._check(body), 0)
        self.assertEqual(self._release("--decision", "D-012", "--section", section), 0)
        progress = findings.load(str(self.project))["sections"][section]["progress"]
        self.assertFalse(progress["halted"])
        self.assertEqual(progress["repair_rounds"], rounds)
        self.assertEqual(self._release("--decision", "D-012", "--section", section), 1)   # 没在刹车就不解

    def test_field_values_are_checked(self):
        self.assertEqual(self._check(unmet().replace("**已修轮次**：3", "**已修轮次**：0")), 1)
        self.assertEqual(self._check(tool_gap(count="9 / 3")), 1)
        self.assertEqual(self._check(tool_gap(gate="plan.coverage / PLAN.REQUIREMENT_UNOWNED", rounds="0")), 1)
        self.assertEqual(self._check(tool_gap(gate="plan.coverage / PLAN.REQUIREMENT_UNOWNED", rounds="2")), 0)
        self.assertEqual(self._check(tool_gap(output="`spec/decision-ledger.md`")), 1)
        self.assertIn("ledger / 放行汇总本身", self._summary())

    def test_alternative_field_and_heading_forms_are_parsed(self):
        body = tool_gap().replace("### D-010", "#### D-010").replace("**类型**：", "**类型：** ")
        self.assertEqual(self._check(body), 0)
        self.assertIn("| D-010 |", self._summary())

    def test_sub_heading_inside_entry_keeps_fields(self):
        body = tool_gap().replace("- **证据**：", "#### 证据与说明\n- **证据**：")
        self.assertEqual(self._check(body), 0)

    def test_prose_mentioning_a_release_type_is_not_flagged(self):
        body = "### D-030 普通决策\n- **类型**：具体决策（不是阶段不可判定）\n- **选定**：A\n"
        self.assertEqual(self._check(body), 0)

    def test_numbered_list_entry_is_parsed(self):
        # 1018 三审 中3：编号列表写法的放行条目照常解析核对
        body = "\n".join(f"{i}. {line[2:]}" if line.startswith("- ") else line
                         for i, line in enumerate(tool_gap().splitlines(), 1))
        self.assertEqual(self._check(body), 0)
        self.assertIn("| D-010 |", self._summary())

    def test_inline_type_mention_is_reported_not_dropped(self):
        body = "### D-031 某闸放行\n- **类目**：C5；类型：工具缺口\n- **门禁**：closure.wiring\n"
        self.assertEqual(self._check(body), 1)
        self.assertIn("D-031", self._summary())

    def test_unparseable_release_entries_are_reported_not_skipped(self):
        body = "### D-020 某闸放行\n- 类型 = 工具缺口\n- 门禁 = closure.wiring\n"
        self.assertEqual(self._check(body), 1)
        index = HEAD.replace("|---|---|---|---|---|\n", "|---|---|---|---|---|\n| D-021 | 未达标放行 | x | approved | default-policy |\n")
        (self.project / "spec/decision-ledger.md").write_text(index, encoding="utf-8")
        self.assertEqual(gate_ledger.main(["check", "--project-root", str(self.project)]), 1)


class HardRuleCountedPerFinding(_Base):
    """1019 审核 M5 / 复审 #5：hard 规则的工具缺口按发现编号点名覆盖，同一条 FAIL 跨文件只算一次，
    分析出错不能被未达标放行整体带过。"""

    def _setup(self, findings, files=("ledger.json",)):
        out = self.project / "spec/out"
        (self.project / "entry/src/main/ets/startup").mkdir(parents=True, exist_ok=True)
        (self.project / "entry/src/main/ets/startup/NetworkStartupTask.ets").write_text(
            "export default class NetworkStartupTask extends StartupTask {\n"
            "  async init(): Promise<void> { UserRepository.configure(new NetworkClient()) }\n}\n", encoding="utf-8")
        (self.android / "app/src/App.kt").write_text("package x\nclass NetworkStartupTask : Initializer<Unit>\n",
                                                     encoding="utf-8")
        for name in files:
            (out / name).write_text(json.dumps({"summary": {"FAIL": len(findings), "WARN": 0}, "findings": findings,
                                                "errors": []}), encoding="utf-8")

    @staticmethod
    def _finding(t, f):
        return {"subtype": "ledger-unassembled-dependency", "severity_at_scope": "FAIL", "type": t,
                "p_id": f"unassembled:{t}", "file": f, "line": 1}

    def _gap(self, did, count, names):
        return tool_gap(did=did, gate="closure.ledger / ledger-unassembled-dependency", count=count,
                        output="`spec/out/ledger.json`",
                        evidence="`entry/src/main/ets/startup/NetworkStartupTask.ets:2` `NetworkStartupTask`；"
                                 "`app/src/App.kt:2` `NetworkStartupTask`").replace(
            "只认字面 XxxPage() 调用", f"StartupTask.init 由框架调用，检测器不认（{names}）")

    def _fv1(self, output="`spec/out/ledger.json`"):
        return unmet(did="D-031", gate="execute.fv1-final").replace("`spec/out/wiring.json`", output)

    def test_gap_covers_only_the_findings_it_names(self):
        self._setup([self._finding("NetworkClient", "a.ets"), self._finding("ApiClient", "b.ets")])
        self.assertEqual(self._check(self._gap("D-030", "1 / 2", "NetworkClient") + self._fv1()), 1)
        self.assertIn("ledger-unassembled-dependency×1", self._summary())
        self.assertIn("ApiClient", self._summary())
        # 自报「2 / 2」但只点名一条：照样拒（复审 G2）
        self.assertEqual(self._check(self._gap("D-030", "2 / 2", "NetworkClient") + self._fv1()), 1)
        self.assertEqual(self._check(self._gap("D-030", "2 / 2", "NetworkClient、ApiClient") + self._fv1()), 0)

    def test_same_finding_in_two_outputs_counts_once(self):
        # 复审 G6：FV-1 引用两轮迭代的 ledger JSON，同一条不能数成 2
        self._setup([self._finding("NetworkClient", "a.ets")], files=("ledger-iter1.json", "ledger-iter2.json"))
        body = self._gap("D-030", "1 / 1", "NetworkClient").replace("`spec/out/ledger.json`",
                                                                  "`spec/out/ledger-iter1.json`") + \
            self._fv1("`spec/out/ledger-iter1.json`；`spec/out/ledger-iter2.json`")
        self.assertEqual(self._check(body), 0)

    def test_analysis_error_cannot_be_released_in_bulk(self):
        # 复审 G5：分析一崩就没有 hard 结论了，不能靠未达标放行整体带过
        out = self.project / "spec/out"
        (out / "ledger.json").write_text(json.dumps({"summary": {"FAIL": 1, "WARN": 0}, "findings": [
            {"subtype": "ledger-assembly-analysis-error", "severity_at_scope": "FAIL", "p_id": "assembly-analysis",
             "file": "", "line": 0}], "errors": ["boom"]}), encoding="utf-8")
        self.assertEqual(self._check(self._fv1()), 1)
        self.assertIn("ledger-assembly-analysis-error", self._summary())

if __name__ == "__main__":
    unittest.main()
