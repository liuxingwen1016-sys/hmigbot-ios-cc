#!/usr/bin/env python3
"""Linter: UI Plan 验证

检查 UI Plan 是否完整和合理
"""
from __future__ import annotations

import os
import json
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "findings"))
from i2h_findings import make, replace_section


def lint_ui_plan(project_root: str) -> list[dict]:
    """验证 UI Plan"""
    findings = []

    # 检查 ui-plan.json
    plan_file = os.path.join(project_root, "spec/baseline/plans/ui-plan.json")
    if not os.path.exists(plan_file):
        findings.append(make(
            "PLAN.MISSING_FILE",
            "plan",
            "ui-plan.json",
            "UI Plan 文件不存在"
        ))
        return findings

    # 读取并验证
    try:
        with open(plan_file) as f:
            plan = json.load(f)
    except json.JSONDecodeError:
        findings.append(make(
            "PLAN.INVALID_FORMAT",
            "plan",
            "ui-plan.json",
            "UI Plan 格式无效"
        ))
        return findings

    # 验证必需字段
    required_fields = ["version", "total_pages", "total_batches", "batches"]
    for field in required_fields:
        if field not in plan:
            findings.append(make(
                "PLAN.MISSING_FIELD",
                "plan",
                f"ui-plan.json:{field}",
                f"缺少必需字段: {field}"
            ))

    # 验证批次
    if "batches" in plan:
        batches = plan["batches"]

        # 检查批次数量
        if len(batches) != plan.get("total_batches", 0):
            findings.append(make(
                "PLAN.BATCH_COUNT_MISMATCH",
                "plan",
                "ui-plan.json",
                f"批次数量不匹配: 声称 {plan.get('total_batches')}，实际 {len(batches)}",
                severity="warn"
            ))

        # 检查页面总数
        total_pages_in_batches = sum(len(b.get("pages", [])) for b in batches)
        if total_pages_in_batches != plan.get("total_pages", 0):
            findings.append(make(
                "PLAN.PAGE_COUNT_MISMATCH",
                "plan",
                "ui-plan.json",
                f"页面数量不匹配: 声称 {plan.get('total_pages')}，实际 {total_pages_in_batches}"
            ))

        # 检查批次大小是否合理
        for i, batch in enumerate(batches):
            pages = batch.get("pages", [])
            if len(pages) > 30:
                findings.append(make(
                    "PLAN.BATCH_TOO_LARGE",
                    "plan",
                    f"batch_{i}",
                    f"批次过大: {len(pages)} 个页面 (建议 < 30)",
                    severity="warn"
                ))

            # 检查必需字段
            if "batch_id" not in batch:
                findings.append(make(
                    "PLAN.MISSING_BATCH_ID",
                    "plan",
                    f"batch_{i}",
                    "批次缺少 batch_id"
                ))

    return findings


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: lint_ui_plan.py <project_root>")
        sys.exit(1)

    project_root = sys.argv[1]
    findings = lint_ui_plan(project_root)

    replace_section(
        project_root,
        "plan/ui-plan",
        findings,
        after_repair=False
    )

    if any(f.get("severity") == "blocking" for f in findings):
        print(f"❌ UI plan validation failed: {len(findings)} issues")
        sys.exit(2)
    else:
        print(f"✅ UI plan validation passed")
        sys.exit(0)
