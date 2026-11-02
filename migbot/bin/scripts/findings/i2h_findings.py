#!/usr/bin/env python3
"""iOS→HarmonyOS findings 机制 - 完整移植自 a2h

一个文件 `spec/.i2h/open-findings.json` 保存整个流水线的所有开放 findings。
每个 linter 只拥有自己的 section，不会相互干扰。

核心原则：
1. findings 只能由 linter 重跑确认关闭，不能由 Agent 声称"已修复"
2. 循环控制计数 REPAIR ROUNDS，而不是 linter 运行次数
3. 进度基于整个 blocking 集合，而不是单个 finding
4. decision_ref 的 finding 不再算作 blocking

移植自: a2h-spec/scripts/_a2h_findings.py
"""
from __future__ import annotations

import json
import hashlib
import os
from typing import Any

FINDINGS_REL = "spec/.i2h/open-findings.json"
LOOP_LIMIT = 3          # per-finding: repair rounds before `escalate`
HALT_LIMIT = 3          # per-section: consecutive no-progress repair rounds before halt
MAX_REPAIR_ROUNDS = 10  # per-section: absolute cap even with slow progress
STAGES = ("spec", "plan", "execute", "verify")
SEVERITIES = ("blocking", "warn")


def finding_key(rule: str, subject: str) -> str:
    """稳定的身份标识：同样的规则 + 同样的主题 → 同样的 key"""
    digest = hashlib.sha256(f"{rule}\x00{subject}".encode("utf-8")).hexdigest()
    return f"FK-{digest[:16]}"


def make(
    rule: str,
    owner_stage: str,
    subject: str,
    detail: str,
    *,
    severity: str = "blocking",
    subject_ref: str | None = None,
    fix_hint: str | None = None,
    options: list[str] | None = None,
) -> dict[str, Any]:
    """构建一个 finding。owner_stage 是必须处理它的阶段。"""
    if owner_stage not in STAGES:
        raise ValueError(f"unknown owner_stage: {owner_stage}")
    if severity not in SEVERITIES:
        raise ValueError(f"unknown severity: {severity}")
    return {
        "finding_key": finding_key(rule, subject),
        "rule": rule,
        "owner_stage": owner_stage,
        "severity": severity,
        "subject": subject,
        "subject_ref": subject_ref,
        "detail": detail,
        "fix_hint": fix_hint,
        "options": options,
        "occurrences": 1,
        "escalate": False,
        "decision_ref": None,
    }


def path_for(project_root: str) -> str:
    return os.path.join(project_root, FINDINGS_REL)


def load(project_root: str) -> dict[str, Any]:
    """加载 open-findings.json"""
    path = path_for(project_root)
    if not os.path.isfile(path):
        return {"version": 1, "sections": {}}
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        # 损坏的队列不能静默显示为空 - 那会被理解为"没有问题要修"
        # 将其作为工具问题显示
        return {
            "version": 1,
            "sections": {
                "_tooling": {
                    "findings": [
                        make(
                            "TOOLING.FINDINGS_UNREADABLE",
                            "spec",
                            FINDINGS_REL,
                            "open-findings.json exists but could not be parsed",
                            fix_hint="delete the file and re-run the stage linters",
                        )
                    ]
                }
            },
        }
    data.setdefault("version", 1)
    data.setdefault("sections", {})
    return data


def save(project_root: str, data: dict[str, Any]) -> None:
    """保存 open-findings.json"""
    path = path_for(project_root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)


def is_open_blocking(item: dict[str, Any]) -> bool:
    """Blocking 且尚未被决策记录释放"""
    return item.get("severity") == "blocking" and not item.get("decision_ref")


def _blocking_digest(items: list[dict[str, Any]]) -> tuple[str, int]:
    """计算 blocking 集合的摘要"""
    keys = sorted(
        item["finding_key"] for item in items
        if is_open_blocking(item) and item.get("finding_key")
    )
    digest = hashlib.sha256("\n".join(keys).encode("utf-8")).hexdigest()[:16]
    return digest, len(keys)


def _stage_of_section(section: str) -> str:
    """从 section 名称推断 stage"""
    prefix = section.split("/", 1)[0]
    return prefix if prefix in STAGES else "spec"


def replace_section(
    project_root: str,
    section: str,
    findings: list[dict[str, Any]],
    *,
    context: dict[str, Any] | None = None,
    after_repair: bool = False,
) -> dict[str, Any]:
    """重写一个 section；只在 after_repair 时推进循环计数器。

    普通状态检查 (after_repair=False) 会刷新 finding 列表，但不计数。
    """
    data = load(project_root)
    prior_section = data["sections"].get(section, {})
    prior = {
        item["finding_key"]: item
        for item in prior_section.get("findings", [])
        if isinstance(item, dict) and item.get("finding_key")
    }

    carried = []
    for item in findings:
        was = prior.get(item["finding_key"])
        if was:
            base = int(was.get("occurrences", 1))
            item["occurrences"] = base + 1 if after_repair else base
            item["decision_ref"] = was.get("decision_ref")
        item["escalate"] = item["occurrences"] >= LOOP_LIMIT
        carried.append(item)

    digest, blocking_count = _blocking_digest(carried)
    prior_progress = prior_section.get("progress", {}) if isinstance(prior_section.get("progress"), dict) else {}
    repair_rounds = int(prior_progress.get("repair_rounds", 0))
    no_progress = int(prior_progress.get("no_progress_rounds", 0))
    halted = bool(prior_progress.get("halted", False))
    decision_ref = prior_progress.get("decision_ref")

    if blocking_count == 0:
        # 干净的 section：循环收敛了；所有刹车自动释放
        no_progress, halted = 0, False
    elif after_repair and "blocking_count" in prior_progress:
        repair_rounds += 1
        if blocking_count < int(prior_progress.get("blocking_count", 0)):
            no_progress = 0
        else:
            # 同样的集合，或者变异但没有缩小 - 都算作卡住
            no_progress += 1
        halted = halted or no_progress >= HALT_LIMIT or repair_rounds >= MAX_REPAIR_ROUNDS

    if halted and blocking_count:
        stage = _stage_of_section(section)
        stall = make(
            "LOOP.NOT_CONVERGING", stage, section,
            f"Section halted: {blocking_count} blocking findings after "
            f"{repair_rounds} repair rounds ({no_progress} no-progress rounds)",
            fix_hint="Record a decision to release these findings or fix them manually",
        )
        if not any(f.get("rule") == "LOOP.NOT_CONVERGING" for f in carried):
            carried.append(stall)

    progress = {
        "repair_rounds": repair_rounds,
        "no_progress_rounds": no_progress,
        "blocking_digest": digest,
        "blocking_count": blocking_count,
        "halted": halted,
        "decision_ref": decision_ref,
    }

    data["sections"][section] = {
        "findings": carried,
        "progress": progress,
        "context": context or {},
    }

    save(project_root, data)
    return data


def section_exit_code(project_root: str, section: str) -> int:
    """返回 section 的退出码。

    0: 没有 blocking findings
    2: 有 blocking findings，但在进展中
    3: halted (LOOP.NOT_CONVERGING)
    """
    data = load(project_root)
    sec = data["sections"].get(section, {})
    findings = sec.get("findings", [])
    blocking = [f for f in findings if is_open_blocking(f)]

    if not blocking:
        return 0

    progress = sec.get("progress", {})
    if progress.get("halted"):
        return 3

    return 2


def has_upstream_blockers(project_root: str, stage: str) -> bool:
    """检查是否有上游阶段的 blocking findings。"""
    data = load(project_root)
    stage_order = {s: i for i, s in enumerate(STAGES)}
    current_idx = stage_order.get(stage, 999)

    for section, sec_data in data["sections"].items():
        sec_stage = _stage_of_section(section)
        if stage_order.get(sec_stage, 999) < current_idx:
            findings = sec_data.get("findings", [])
            if any(is_open_blocking(f) for f in findings):
                return True
    return False


def release(project_root: str, finding_keys: list[str], decision_ref: str) -> None:
    """释放指定的 findings（通过决策记录）。"""
    data = load(project_root)
    for section, sec_data in data["sections"].items():
        findings = sec_data.get("findings", [])
        for item in findings:
            if item.get("finding_key") in finding_keys:
                item["decision_ref"] = decision_ref
    save(project_root, data)


def clear_halt(project_root: str, section: str, decision_ref: str) -> None:
    """清除 halt 状态（通过人工决策）。"""
    data = load(project_root)
    if section in data["sections"]:
        progress = data["sections"][section].get("progress", {})
        progress["halted"] = False
        progress["decision_ref"] = decision_ref
        progress["no_progress_rounds"] = 0
    save(project_root, data)


if __name__ == "__main__":
    # 测试
    import tempfile
    import shutil

    tmpdir = tempfile.mkdtemp()
    try:
        # 测试基本流程
        f1 = make("IOS.VIEW_PARSE_ERROR", "spec", "HomeView.swift",
                  "Failed to parse SwiftUI View")
        replace_section(tmpdir, "spec/ui-scan", [f1])

        code = section_exit_code(tmpdir, "spec/ui-scan")
        print(f"Exit code: {code} (expected 2)")

        # 测试修复后
        replace_section(tmpdir, "spec/ui-scan", [], after_repair=True)
        code = section_exit_code(tmpdir, "spec/ui-scan")
        print(f"Exit code after fix: {code} (expected 0)")

        print("✅ Findings mechanism test passed")
    finally:
        shutil.rmtree(tmpdir)
