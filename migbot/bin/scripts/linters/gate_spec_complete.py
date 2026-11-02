#!/usr/bin/env python3
"""Gate: Spec 完成门禁

检查 Spec 阶段的所有产出物是否完整
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "findings"))
from i2h_findings import make, replace_section, section_exit_code


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
        feature_specs = list(Path(features_dir).glob("feat_*.md"))
        if len(feature_specs) == 0:
            findings.append(make(
                "GATE.SPEC_INCOMPLETE",
                "spec",
                "baseline/features/",
                "没有生成任何功能 spec",
                severity="warn"
            ))

    return findings


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: gate_spec_complete.py <project_root>")
        sys.exit(1)

    project_root = sys.argv[1]
    findings = gate_spec_complete(project_root)

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
