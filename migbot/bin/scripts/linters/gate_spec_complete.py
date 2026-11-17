#!/usr/bin/env python3
"""Gate: Spec 完成门禁

检查 Spec 阶段的所有产出物是否完整
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "findings"))
from i2h_findings import make, replace_section, section_exit_code


GRAPHEME = re.compile(r"字素(?:簇)?|grapheme", re.I)
CODE_POINT = re.compile(r"\bArray\s*\.\s*from\s*\([^()\n]+\)\s*\.\s*"
                        r"(?:length\b|slice\s*\(\s*0\s*,[^()\n]+\)\s*\.\s*join\s*\()")
NEGATIVE_EXAMPLE = re.compile(r"不得|不能|不可|不要|禁止|并非|而非|反例|错误示例|不正确|"
                              r"\b(?:avoid|incorrect|do not|not equivalent)\b", re.I)


def grapheme_mapping_finding(root: Path, feature: Path) -> dict | None:
    """Flag explicit equivalence claims pairing Swift graphemes with code point operations."""
    text = feature.read_text(encoding="utf-8")
    if "String.count" not in text or not GRAPHEME.search(text):
        return None
    matches = []
    for line_number, line in enumerate(text.splitlines(), 1):
        if not CODE_POINT.search(line) or NEGATIVE_EXAMPLE.search(line):
            continue
        if GRAPHEME.search(line) or re.search(r"(?:与|和)\s*iOS\s*一致|equivalent to Swift", line, re.I):
            matches.append(line_number)
    if not matches:
        return None
    relative = feature.relative_to(root).as_posix()
    return make("SPEC.SWIFT_GRAPHEME_MAPPING", "spec", relative,
                "Swift 字素计数/截断被映射为 Unicode 码点操作，涉及行 " + ", ".join(map(str, matches)),
                subject_ref=f"{relative}:{matches[0]}",
                fix_hint="保留 Swift String.count 与 prefix 的字素簇边界，并补组合重音、ZWJ 表情和旗帜例。")


def gate_spec_complete(project_root: str) -> list[dict]:
    """Spec 完成门禁"""
    findings = []

    # 检查必需产出物
    required_files = [
        ("spec/baseline/ui-manifest.md", "UI 清单"),
        ("spec/baseline/feature-index.md", "功能索引"),
    ]

    for file_path, desc in required_files:
        full_path = os.path.join(project_root, file_path)
        if not os.path.exists(full_path):
            findings.append(make(
                "GATE.SPEC_INCOMPLETE",
                "spec",
                file_path,
                f"缺少必需产出物: {desc}"
            ))

    # 检查 UI 页面 spec
    ui_dir = os.path.join(project_root, "spec/baseline/ui")
    if os.path.exists(ui_dir):
        page_specs = list(Path(ui_dir).glob("page_*.md"))
        if len(page_specs) == 0:
            findings.append(make(
                "GATE.SPEC_INCOMPLETE",
                "spec",
                "baseline/ui/",
                "没有生成任何页面 spec"
            ))
    else:
        findings.append(make(
            "GATE.SPEC_INCOMPLETE",
            "spec",
            "baseline/ui/",
            "UI spec 目录不存在"
        ))

    # 检查功能 spec
    features_dir = os.path.join(project_root, "spec/baseline/features")
    if os.path.exists(features_dir):
        feature_specs = sorted(Path(features_dir).glob("feat_*.md"))
        if len(feature_specs) == 0:
            findings.append(make(
                "GATE.SPEC_INCOMPLETE",
                "spec",
                "baseline/features/",
                "没有生成任何功能 spec",
                severity="warn"
            ))
        for feature in feature_specs:
            if finding := grapheme_mapping_finding(Path(project_root), feature):
                findings.append(finding)

    return findings


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_root")
    parser.add_argument("--report-only", action="store_true", help="report current findings without updating the ledger")
    args = parser.parse_args()
    project_root = args.project_root
    findings = gate_spec_complete(project_root)
    if args.report_only:
        blocked = any(row["severity"] == "blocking" for row in findings)
        print(json.dumps({"status": "BLOCKED" if blocked else "PASS", "findings": findings}, ensure_ascii=False))
        sys.exit(2 if blocked else 0)

    replace_section(
        project_root,
        "spec/gate-complete",
        findings,
        after_repair=False
    )

    exit_code = section_exit_code(project_root, "spec/gate-complete")

    if exit_code == 0:
        print("✅ Spec complete gate: PASS")
    elif exit_code == 2:
        print("⚠️  Spec complete gate: IN PROGRESS")
    else:
        print("❌ Spec complete gate: HALT")

    sys.exit(exit_code)
