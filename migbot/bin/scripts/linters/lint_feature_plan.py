#!/usr/bin/env python3
"""Linter: Feature Plan 验证

检查 Feature Plan 是否完整和合理
"""
from __future__ import annotations

import os
import json
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "findings"))
from i2h_findings import make, replace_section


def lint_feature_plan(project_root: str) -> list[dict]:
    """验证 Feature Plan"""
    findings = []

    plan_file = os.path.join(project_root, "spec/baseline/plans/feature-plan.json")
    if not os.path.exists(plan_file):
        findings.append(make(
            "PLAN.MISSING_FILE",
            "plan",
            "feature-plan.json",
            "Feature Plan 文件不存在"
        ))
        return findings

    try:
        with open(plan_file) as f:
            plan = json.load(f)
    except json.JSONDecodeError:
        findings.append(make(
            "PLAN.INVALID_FORMAT",
            "plan",
            "feature-plan.json",
            "Feature Plan 格式无效"
        ))
        return findings

    # 验证依赖关系
    if "execution_order" in plan:
        all_features = {}
        for group in plan["execution_order"]:
            for feature in group.get("features", []):
                fid = feature.get("feature_id")
                if fid:
                    all_features[fid] = feature

        # 检查依赖是否存在
        for fid, feature in all_features.items():
            for dep in feature.get("dependencies", []):
                if dep not in all_features:
                    findings.append(make(
                        "PLAN.MISSING_DEPENDENCY",
                        "plan",
                        fid,
                        f"依赖的功能不存在: {dep}"
                    ))

        # 检查循环依赖
        if has_circular_dependency(all_features):
            findings.append(make(
                "PLAN.CIRCULAR_DEPENDENCY",
                "plan",
                "feature-plan.json",
                "检测到循环依赖"
            ))

    return findings


def has_circular_dependency(features: dict) -> bool:
    """检测循环依赖"""
    visited = set()
    rec_stack = set()

    def visit(fid: str) -> bool:
        if fid in rec_stack:
            return True
        if fid in visited:
            return False

        visited.add(fid)
        rec_stack.add(fid)

        for dep in features.get(fid, {}).get("dependencies", []):
            if visit(dep):
                return True

        rec_stack.remove(fid)
        return False

    for fid in features:
        if visit(fid):
            return True

    return False


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: lint_feature_plan.py <project_root>")
        sys.exit(1)

    project_root = sys.argv[1]
    findings = lint_feature_plan(project_root)

    replace_section(
        project_root,
        "plan/feature-plan",
        findings,
        after_repair=False
    )

    if any(f.get("severity") == "blocking" for f in findings):
        print(f"❌ Feature plan validation failed")
        sys.exit(2)
    else:
        print(f"✅ Feature plan validation passed")
        sys.exit(0)
