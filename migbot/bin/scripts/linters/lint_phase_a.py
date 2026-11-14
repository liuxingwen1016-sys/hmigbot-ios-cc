#!/usr/bin/env python3
"""Linter: Phase A 数据准备验证

检查 Phase A 的产出物是否完整和有效
"""
from __future__ import annotations

import os
import json
import sys
from pathlib import Path

# 添加 findings 模块到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "findings"))
from i2h_findings import make, replace_section


def lint_phase_a(project_root: str) -> list[dict]:
    """验证 Phase A 产出"""
    findings = []

    # Try native project-skeleton.json first, fall back to legacy project-info.json
    skeleton_path = os.path.join(project_root, "spec/.i2h/project-skeleton.json")
    legacy_path = os.path.join(project_root, "spec/.i2h/project-info.json")

    project_info_path = None
    if os.path.exists(skeleton_path):
        project_info_path = skeleton_path
    elif os.path.exists(legacy_path):
        project_info_path = legacy_path

    if not project_info_path:
        findings.append(make(
            "IOS.MISSING_REQUIRED_FILE",
            "spec",
            "project-skeleton.json or project-info.json",
            "Phase A 未生成项目信息文件",
            fix_hint="重新运行 Phase A Step A1"
        ))
    else:
        # 验证内容
        try:
            with open(project_info_path) as f:
                data = json.load(f)

            if "swift_files" not in data:
                findings.append(make(
                    "IOS.INVALID_PROJECT_STRUCTURE",
                    "spec",
                    os.path.basename(project_info_path),
                    "缺少 swift_files 字段"
                ))

            if "swiftui_views" not in data:
                findings.append(make(
                    "IOS.INVALID_PROJECT_STRUCTURE",
                    "spec",
                    os.path.basename(project_info_path),
                    "缺少 swiftui_views 字段"
                ))
        except json.JSONDecodeError:
            findings.append(make(
                "IOS.INVALID_PROJECT_STRUCTURE",
                "spec",
                os.path.basename(project_info_path),
                "文件格式无效"
            ))

    # 检查 views/ 目录
    views_dir = os.path.join(project_root, "spec/.i2h/views")
    if os.path.exists(views_dir):
        view_files = list(Path(views_dir).glob("*.json"))
        if len(view_files) == 0:
            findings.append(make(
                "IOS.VIEW_PARSE_ERROR",
                "spec",
                "views/",
                "没有成功解析任何 SwiftUI View",
                severity="warn"
            ))

    return findings


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: lint_phase_a.py <project_root>")
        sys.exit(1)

    project_root = sys.argv[1]
    findings = lint_phase_a(project_root)

    # 报告到 findings
    replace_section(
        project_root,
        "spec/phase-a",
        findings,
        after_repair=False  # 首次检查
    )

    if findings:
        print(f"⚠️  Found {len(findings)} issues in Phase A")
        sys.exit(2)
    else:
        print("✅ Phase A validation passed")
        sys.exit(0)
