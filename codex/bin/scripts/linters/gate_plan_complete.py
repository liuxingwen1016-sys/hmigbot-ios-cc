#!/usr/bin/env python3
"""Gate: Plan 完成门禁

检查 Plan 阶段的所有产出物是否完整
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "findings"))
from i2h_findings import iter_findings, load, make, replace_section, section_exit_code


def gate_plan_complete(project_root: str) -> list[dict]:
    """Plan 完成门禁"""
    findings = []

    # 检查必需产出物
    required_file_alternatives = [
        (("spec/baseline/plans/ui-plan.json", "spec/baseline/plans/ui-plan.md"), "UI Plan"),
        (("spec/baseline/plans/feature-plan.json", "spec/baseline/plans/feature-plan.md"), "Feature Plan"),
        (("spec/baseline/plans/execution-summary.md", "spec/baseline/plans/gate-output.md"), "执行摘要"),
    ]

    for candidates, desc in required_file_alternatives:
        if not any(os.path.exists(os.path.join(project_root, path)) for path in candidates):
            findings.append(make(
                "GATE.PLAN_INCOMPLETE",
                "plan",
                candidates[0],
                f"缺少必需产出物: {desc}"
            ))

    # A malformed findings section must never be treated as an empty queue.
    # Accept both the current list form and the legacy key->finding dict.
    queue = load(project_root)
    for section, payload in queue.get("sections", {}).items():
        if not isinstance(payload, dict):
            findings.append(make("GATE.FINDINGS_INVALID", "plan", section, "findings section 不是对象"))
            continue
        raw = payload.get("findings", [])
        normalized = iter_findings(raw)
        if raw and not normalized:
            findings.append(make("GATE.FINDINGS_INVALID", "plan", section, "findings 必须是列表或 finding 字典"))
        for item in normalized:
            if item.get("severity") == "blocking" and not item.get("decision_ref") and section.startswith("plan/"):
                findings.append(make(
                    "GATE.PLAN_BLOCKING_FINDING",
                    "plan",
                    str(item.get("finding_key") or item.get("subject") or section),
                    str(item.get("detail") or "存在未释放的 blocking finding"),
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
