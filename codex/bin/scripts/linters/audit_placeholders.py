#!/usr/bin/env python3
"""Linter: 占位符审计

审计所有占位符的使用情况
"""
from __future__ import annotations

import os
import json
import sys
import re
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "findings"))
from i2h_findings import make, replace_section


# 占位符 kind 分类
PLACEHOLDER_KINDS = {
    "thirdparty-sdk": "第三方 SDK 未迁移",
    "complex-logic": "复杂逻辑待实现",
    "data-layer-migration": "数据层迁移中",
    "runtime-api": "运行时 API 待适配",
    "performance-optimization": "性能优化待做",
    "ui-polish": "UI 细节待打磨",
    "optional-feature": "可选功能",
}


def audit_placeholders(project_root: str, hos_path: str) -> list[dict]:
    """审计占位符"""
    findings = []

    # 读取占位符注册表
    registry_file = os.path.join(project_root, "spec/execute/placeholder-registry.json")
    registered = {}

    if os.path.exists(registry_file):
        with open(registry_file) as f:
            registry = json.load(f)
            registered = {p["id"]: p for p in registry.get("placeholders", [])}

    # 扫描代码中的占位符
    code_dir = Path(hos_path) / "entry/src/main/ets"
    found_placeholders = []

    for ets_file in code_dir.rglob("*.ets"):
        try:
            content = ets_file.read_text(encoding="utf-8")

            # 匹配 PLACEHOLDER 注释
            for match in re.finditer(r'//\s*PLACEHOLDER:\s*(\S+)', content):
                placeholder_id = match.group(1)
                found_placeholders.append({
                    "id": placeholder_id,
                    "file": str(ets_file.relative_to(code_dir)),
                })
        except Exception:
            pass

    # 检查未注册的占位符
    for ph in found_placeholders:
        if ph["id"] not in registered:
            findings.append(make(
                "PLACEHOLDER.UNREGISTERED",
                "execute",
                ph["id"],
                f"占位符未在注册表中: {ph['file']}",
                fix_hint="在 placeholder-registry.json 中注册"
            ))

    # 检查注册但未使用的占位符
    found_ids = {ph["id"] for ph in found_placeholders}
    for ph_id in registered:
        if ph_id not in found_ids:
            findings.append(make(
                "PLACEHOLDER.UNUSED",
                "execute",
                ph_id,
                "占位符已注册但未在代码中使用",
                severity="warn"
            ))

    # 统计占位符类型
    kind_stats = {}
    for ph_id, ph_data in registered.items():
        kind = ph_data.get("kind", "unknown")
        kind_stats[kind] = kind_stats.get(kind, 0) + 1

    # 生成统计报告
    if registered:
        print(f"📊 占位符统计:")
        print(f"   总数: {len(registered)}")
        print(f"   使用中: {len(found_ids)}")
        for kind, count in kind_stats.items():
            desc = PLACEHOLDER_KINDS.get(kind, kind)
            print(f"   {desc}: {count}")

    return findings


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: audit_placeholders.py <project_root> <hos_path>")
        sys.exit(1)

    project_root = sys.argv[1]
    hos_path = sys.argv[2]
    findings = audit_placeholders(project_root, hos_path)

    replace_section(
        project_root,
        "execute/placeholders",
        findings,
        after_repair=False
    )

    if any(f.get("severity") == "blocking" for f in findings):
        print(f"❌ Placeholder audit failed")
        sys.exit(2)
    else:
        print(f"✅ Placeholder audit passed")
        sys.exit(0)
