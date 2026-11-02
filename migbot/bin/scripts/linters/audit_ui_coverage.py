#!/usr/bin/env python3
"""Linter: UI 覆盖率审计

检查所有 UI 文件是否都有对应的 spec
"""
from __future__ import annotations

import os
import json
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "findings"))
from i2h_findings import make, replace_section


def audit_ui_coverage(project_root: str) -> list[dict]:
    """审计 UI 覆盖率"""
    findings = []

    # 读取 project-info.json
    project_info_path = os.path.join(project_root, "spec/.i2h/project-info.json")
    if not os.path.exists(project_info_path):
        findings.append(make(
            "IOS.MISSING_REQUIRED_FILE",
            "spec",
            "project-info.json",
            "无法进行覆盖率审计：缺少项目信息"
        ))
        return findings

    with open(project_info_path) as f:
        project_info = json.load(f)

    swiftui_views = project_info.get("swiftui_views", [])
    uikit_vcs = project_info.get("uikit_vcs", [])

    total_ui_files = len(swiftui_views) + len(uikit_vcs)

    # 检查 ui/ 目录
    ui_dir = os.path.join(project_root, "spec/baseline/ui")
    if not os.path.exists(ui_dir):
        findings.append(make(
            "IOS.MISSING_REQUIRED_FILE",
            "spec",
            "baseline/ui/",
            "UI spec 目录不存在"
        ))
        return findings

    spec_files = list(Path(ui_dir).glob("page_*.md"))

    # 计算覆盖率
    coverage = len(spec_files) / total_ui_files if total_ui_files > 0 else 0

    if coverage < 0.95:
        findings.append(make(
            "IOS.UI_COVERAGE_LOW",
            "spec",
            "ui-coverage",
            f"UI 覆盖率只有 {coverage*100:.1f}% (< 95%)",
            severity="warn",
            fix_hint="为缺失的 UI 文件生成 spec"
        ))

    # 检查重复的 View 名称
    view_names = set()
    duplicates = set()

    for spec_file in spec_files:
        name = spec_file.stem.split("_", 2)[-1] if "_" in spec_file.stem else spec_file.stem
        if name in view_names:
            duplicates.add(name)
        view_names.add(name)

    for dup in duplicates:
        findings.append(make(
            "IOS.DUPLICATE_VIEW_NAME",
            "spec",
            dup,
            f"重复的 View 名称: {dup}"
        ))

    return findings


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: audit_ui_coverage.py <project_root>")
        sys.exit(1)

    project_root = sys.argv[1]
    findings = audit_ui_coverage(project_root)

    replace_section(
        project_root,
        "spec/ui-coverage",
        findings,
        after_repair=False
    )

    if any(f.get("severity") == "blocking" for f in findings):
        print(f"❌ UI coverage audit failed: {len(findings)} issues")
        sys.exit(2)
    else:
        print(f"✅ UI coverage audit passed")
        sys.exit(0)
