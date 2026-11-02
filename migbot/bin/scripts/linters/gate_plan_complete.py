#!/usr/bin/env python3
"""Gate: Plan 完成门禁

检查 Plan 阶段的所有产出物是否完整
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "findings"))
from i2h_findings import make, replace_section, section_exit_code


def gate_plan_complete(project_root: str) -> list[dict]:
    """Plan 完成门禁"""
    findings = []

    # 检查必需产出物
    required_files = [
        ("spec/baseline/plans/ui-plan.json", "UI Plan"),
        ("spec/baseline/plans/feature-plan.json", "Feature Plan"),
        ("spec/baseline/plans/execution-summary.md", "执行摘要"),
    ]

    for file_path, desc in required_files:
        full_path = os.path.join(project_root, file_path)
        if not os.path.exists(full_path):
            findings.append(make(
                "GATE.PLAN_INCOMPLETE",
                "plan",
                file_path,
                f"缺少必需产出物: {desc}"
            ))

    return findings


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: gate_plan_complete.py <project_root>")
        sys.exit(1)

    project_root = sys.argv[1]
    findings = gate_plan_complete(project_root)

    replace_section(
        project_root,
        "plan/gate-complete",
        findings,
        after_repair=False
    )

    exit_code = section_exit_code(project_root, "plan/gate-complete")

    if exit_code == 0:
        print("✅ Plan complete gate: PASS")
    elif exit_code == 2:
        print("⚠️  Plan complete gate: IN PROGRESS")
    else:
        print("❌ Plan complete gate: HALT")

    sys.exit(exit_code)
