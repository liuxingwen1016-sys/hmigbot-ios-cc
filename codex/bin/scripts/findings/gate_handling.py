#!/usr/bin/env python3
"""iOS→HarmonyOS gate-handling - 门禁失败处置规则

移植自 a2h-spec/references/gate-handling.md

门禁分类：
1. 精确类：工具可以机械判定（必须修过或记决策）
2. 推断类：需要人工判断（可以"未达标放行"）
3. 阶段不可判定：需要动态运行才能判定（推到 verify）
"""
from __future__ import annotations

import json
import os
from typing import Any
from datetime import datetime

DECISION_LEDGER = "spec/decision-ledger.md"


class GateFailureType:
    """门禁失败类型"""
    PRECISE = "precise"          # 精确类：必须修过
    INFERENCE = "inference"      # 推断类：可以放行
    RUNTIME_NEEDED = "runtime"   # 阶段不可判定


def classify_finding(rule: str) -> str:
    """分类 finding 规则"""
    # 精确类规则（机械判定，0 误报）
    PRECISE_RULES = {
        "IOS.VIEW_PARSE_ERROR",           # View 解析错误
        "IOS.INVALID_SWIFT_SYNTAX",       # Swift 语法错误
        "IOS.MISSING_REQUIRED_FILE",      # 缺少必需文件
        "IOS.DUPLICATE_VIEW_NAME",        # 重复的 View 名称
        "ARKTS.SYNTAX_ERROR",             # ArkTS 语法错误
        "ARKTS.IMPORT_MISSING",           # 缺少 import
        "COMPILE.BUILD_FAILURE",          # 编译失败
    }

    # 阶段不可判定（需要运行时）
    RUNTIME_RULES = {
        "UI.VISUAL_DIFFERENCE",           # UI 视觉差异
        "BEHAVIOR.RUNTIME_ERROR",         # 运行时错误
        "PERFORMANCE.SLOW_RENDER",        # 渲染性能
    }

    if rule in PRECISE_RULES:
        return GateFailureType.PRECISE
    elif rule in RUNTIME_RULES:
        return GateFailureType.RUNTIME_NEEDED
    else:
        return GateFailureType.INFERENCE


def record_decision(
    project_root: str,
    decision_id: str,
    category: str,
    finding_keys: list[str],
    rationale: str,
    *,
    tool_gap: str | None = None,
    fallback: str | None = None,
) -> None:
    """记录门禁放行决策

    三种放行记录：
    1. 工具缺口：工具不支持，人工实现
    2. 未达标放行：推断类，记账放行
    3. 阶段不可判定：推到 verify
    """
    ledger_path = os.path.join(project_root, DECISION_LEDGER)
    os.makedirs(os.path.dirname(ledger_path), exist_ok=True)

    # 创建或读取 ledger
    if os.path.exists(ledger_path):
        with open(ledger_path, "r", encoding="utf-8") as f:
            content = f.read()
    else:
        content = """# Decision Ledger

## 决策索引

| ID | 类型 | 审批来源 | 日期 |
|----|------|---------|------|

## 决策详情

"""

    # 添加索引
    index_line = f"| {decision_id} | {category} | default-policy | {datetime.now().strftime('%Y-%m-%d')} |\n"

    # 添加详情
    detail = f"""
### {decision_id}: {category}

**Finding Keys**: {', '.join(finding_keys)}

**理由**: {rationale}
"""

    if tool_gap:
        detail += f"\n**工具缺口**: {tool_gap}\n"

    if fallback:
        detail += f"\n**临时方案**: {fallback}\n"

    detail += f"\n**日期**: {datetime.now().isoformat()}\n"

    # 插入到适当位置
    if "## 决策详情" in content:
        parts = content.split("## 决策详情")
        # 在索引表后添加新行
        index_parts = parts[0].split("|----|")
        if len(index_parts) >= 2:
            index_parts[1] = index_parts[1] + index_line
            parts[0] = "|----|".join(index_parts)
        content = parts[0] + "## 决策详情" + detail + parts[1]
    else:
        content += detail

    with open(ledger_path, "w", encoding="utf-8") as f:
        f.write(content)


def handle_gate_failure(
    project_root: str,
    findings: list[dict[str, Any]],
    stage: str,
) -> tuple[list[str], list[str], list[str]]:
    """处理门禁失败

    Returns:
        (must_fix, can_release, to_verify)
        - must_fix: 必须修复的 (精确类)
        - can_release: 可以记账放行的 (推断类)
        - to_verify: 推到 verify 的 (阶段不可判定)
    """
    must_fix = []
    can_release = []
    to_verify = []

    for finding in findings:
        rule = finding.get("rule", "")
        fk = finding.get("finding_key", "")

        failure_type = classify_finding(rule)

        if failure_type == GateFailureType.PRECISE:
            must_fix.append(fk)
        elif failure_type == GateFailureType.RUNTIME_NEEDED:
            to_verify.append(fk)
        else:
            can_release.append(fk)

    return must_fix, can_release, to_verify


def auto_release_inference(
    project_root: str,
    finding_keys: list[str],
    rationale: str,
) -> str:
    """自动放行推断类 findings"""
    decision_id = f"D-{len(finding_keys):03d}"

    record_decision(
        project_root,
        decision_id,
        "未达标放行",
        finding_keys,
        rationale,
    )

    return decision_id


def defer_to_verify(
    project_root: str,
    finding_keys: list[str],
    reason: str,
) -> str:
    """推迟到 verify 阶段"""
    decision_id = f"V-{len(finding_keys):03d}"

    record_decision(
        project_root,
        decision_id,
        "阶段不可判定",
        finding_keys,
        f"推到 verify: {reason}",
    )

    return decision_id


if __name__ == "__main__":
    import tempfile
    import shutil

    tmpdir = tempfile.mkdtemp()
    try:
        # 测试分类
        print("Testing gate-handling...")

        # 精确类
        assert classify_finding("IOS.VIEW_PARSE_ERROR") == GateFailureType.PRECISE

        # 推断类
        assert classify_finding("IOS.COMPLEX_LOGIC") == GateFailureType.INFERENCE

        # 阶段不可判定
        assert classify_finding("UI.VISUAL_DIFFERENCE") == GateFailureType.RUNTIME_NEEDED

        # 测试决策记录
        record_decision(
            tmpdir,
            "D-001",
            "未达标放行",
            ["FK-abc123"],
            "UI 样式差异可接受",
        )

        ledger = os.path.join(tmpdir, DECISION_LEDGER)
        assert os.path.exists(ledger)

        with open(ledger) as f:
            content = f.read()
            assert "D-001" in content
            assert "未达标放行" in content

        print("✅ Gate-handling test passed")
    finally:
        shutil.rmtree(tmpdir)
