#!/usr/bin/env python3
"""safety_gate 回归（2026-09 AntennaPod：视觉修复引入 NAV_NESTED_DESTINATION / NAV_CONDITIONAL_ROOT，
fixer 之后没人复跑 verify_arkui_safety）。锁：新增/已解决/既有失败的分类、解析错误按文件计数、
WARN 只透传不阻断、基线不可变、修复次数上限、退出码，以及源码态跨 skill 调检查器的真实一跑。
夹具零 app 常量。"""
import json, os, sys
from pathlib import Path

import pytest

SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPTS)
import safety_gate as sg  # noqa: E402


def finding(id_, rule="HITTEST_BLOCK_INTERACTIVE", severity="FAIL", file="pages/A.ets"):
    return {"id": id_, "rule_id": rule, "severity": severity, "file": file, "line": 1, "symbol": "A", "reason": "r"}


def report(findings=(), errors=()):
    return {"findings": list(findings), "errors": list(errors),
            "summary": {"FAIL": sum(f["severity"] == "FAIL" for f in findings) + len(errors),
                        "WARN": sum(f["severity"] == "WARN" for f in findings)}}


def dump(tmp_path, name, data):
    p = tmp_path / name
    p.write_text(json.dumps(data), encoding="utf-8")
    return str(p)


def gate(tmp_path, cmd, rep, *extra):
    src = dump(tmp_path, f"in-{cmd}-{len(list(tmp_path.iterdir()))}.json", rep)
    return sg.main([cmd, "--project-root", str(tmp_path), "--dir", str(tmp_path / "out"),
                    "--prefix", "phase6-", "--from-json", src, *extra])


def test_classifies_new_resolved_existing():
    base = report([finding("A"), finding("B")])
    post = report([finding("B"), finding("C", rule="NAV_NESTED_DESTINATION")])
    d = sg.compute_delta(base, post)
    assert [f["id"] for f in d["new_failures"]] == ["C"]
    assert [f["id"] for f in d["resolved_failures"]] == ["A"]
    assert [f["id"] for f in d["existing_failures"]] == ["B"]
    assert d["passed"] is False


def test_existing_failures_do_not_block():
    base = report([finding("A")])
    d = sg.compute_delta(base, report([finding("A")]))
    assert d["passed"] and d["existing_failures"]


def test_new_warning_passes_through_without_blocking():
    w = finding("W", rule="HITTEST_BLOCK_CONDITIONAL_UNKNOWN", severity="WARN")
    d = sg.compute_delta(report(), report([w]))
    assert d["passed"] and [f["id"] for f in d["new_warnings"]] == ["W"]


def test_parser_errors_counted_per_file_not_by_message():
    base = report(errors=[{"file": "s/X.ets", "reason": "unbalanced delimiter near line 165"}])
    moved = report(errors=[{"file": "s/X.ets", "reason": "unbalanced delimiter near line 170"}])
    assert sg.compute_delta(base, moved)["passed"], "line drift of an existing parser error is not a regression"
    more = report(errors=[{"file": "s/X.ets", "reason": "a"}, {"file": "s/X.ets", "reason": "b"}])
    d = sg.compute_delta(base, more)
    assert not d["passed"] and d["new_failures"][0]["count_delta"] == 1
    d = sg.compute_delta(more, base)
    assert d["passed"] and d["resolved_failures"][0]["count_delta"] == -1


def test_postfix_exit_codes_and_files(tmp_path):
    assert gate(tmp_path, "baseline", report([finding("A")])) == 0
    assert gate(tmp_path, "postfix", report([finding("A"), finding("N")]), "--step", "attempt-0") == 1
    assert gate(tmp_path, "postfix", report([finding("A")]), "--step", "repair-1") == 0
    out = tmp_path / "out"
    for name in ("phase6-baseline.json", "phase6-postfix-attempt-0.json", "phase6-delta-attempt-0.json",
                 "phase6-postfix-repair-1.json", "phase6-delta-repair-1.json", "phase6-postfix.json", "phase6-delta.json"):
        assert (out / name).is_file(), name
    assert json.loads((out / "phase6-delta-attempt-0.json").read_text())["passed"] is False
    assert json.loads((out / "phase6-delta.json").read_text())["step"] == "repair-1"


def test_baseline_is_immutable(tmp_path):
    assert gate(tmp_path, "baseline", report()) == 0
    # a later baseline call (e.g. before a repair retry) must not absorb the regression
    assert gate(tmp_path, "baseline", report([finding("N")])) == 0
    assert gate(tmp_path, "postfix", report([finding("N")]), "--step", "repair-1") == 1


def test_repair_budget_and_missing_baseline(tmp_path):
    assert gate(tmp_path, "postfix", report(), "--step", "attempt-0") == 2   # no baseline
    assert gate(tmp_path, "baseline", report()) == 0
    assert gate(tmp_path, "postfix", report(), "--step", "repair-3") == 2    # over budget


def test_real_checker_run_cross_skill(tmp_path):
    """源码态：经 sibling_exec 真跑 arkts-structural-closure/verify_arkui_safety.py。"""
    page = tmp_path / "entry/src/main/ets/pages/A.ets"
    page.parent.mkdir(parents=True)
    clean = "@ComponentV2\nexport struct A {\n  build() {\n    Column() { Button('OK') }\n  }\n}\n"
    page.write_text(clean, encoding="utf-8")
    common = ["--project-root", str(tmp_path), "--dir", str(tmp_path / "out")]
    assert sg.main(["baseline", *common]) == 0
    page.write_text(clean.replace("Column() { Button('OK') }",
                                  "Column() { Button('OK') }.hitTestBehavior(HitTestMode.Block)"), encoding="utf-8")
    assert sg.main(["postfix", *common, "--step", "attempt-0"]) == 1
    d = json.loads((tmp_path / "out/delta.json").read_text())
    assert [f["rule_id"] for f in d["new_failures"]] == ["HITTEST_BLOCK_INTERACTIVE"]
