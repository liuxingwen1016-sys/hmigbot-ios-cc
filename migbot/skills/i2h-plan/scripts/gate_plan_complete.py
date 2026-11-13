#!/usr/bin/env python3
"""
i2h-plan Completion Gate

在 i2h-plan 完成时只读校验产物与质量门禁。完成标记由阶段收口写入。

Usage:
    python3 gate_plan_complete.py <project_root>

Exit codes:
    0 - 门禁通过，可以进入 i2h-execute
    1 - 门禁失败，需要修复问题
"""

import sys
import os
import json
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass


@dataclass
class GateCheck:
    """门禁检查项"""
    name: str
    passed: bool
    message: str
    blocking: bool = True


class PlanCompletionGate:
    """Plan 完成门禁检查器"""

    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.spec_dir = self.project_root / "spec" / "baseline"
        self.plans_dir = self.spec_dir / "plans"
        self.checks: List[GateCheck] = []

    def run(self) -> bool:
        """运行所有门禁检查"""
        print("🚪 i2h-plan 完成门禁检查\n")
        print("=" * 80)

        # 1. 必需文件存在性
        self._check_required_files()

        # 2. 产物完整性
        self._check_completeness()

        # 3. 覆盖率指标
        self._check_coverage_metrics()

        # 4. Blocking findings
        self._check_blocking_findings()

        # 5. grill #2 完成性
        self._check_grill2_completion()

        # 6. 输出结果
        self._print_results()

        # 判断是否通过
        blocking_failures = [c for c in self.checks if not c.passed and c.blocking]
        return len(blocking_failures) == 0

    def _check_required_files(self):
        """检查必需文件是否存在"""
        required_files = [
            ('ui-plan.md', self.plans_dir / 'ui-plan.md'),
            ('feature-plan.md', self.plans_dir / 'feature-plan.md'),
            ('base-plan.md', self.plans_dir / 'base-plan.md'),
            ('coverage-matrix.md', self.plans_dir / 'coverage-matrix.md'),
        ]

        all_exist = True
        missing = []

        for name, path in required_files:
            if path.exists():
                self.checks.append(GateCheck(
                    name=f"✅ {name} 存在",
                    passed=True,
                    message=str(path.relative_to(self.project_root))
                ))
            else:
                all_exist = False
                missing.append(name)
                self.checks.append(GateCheck(
                    name=f"❌ {name} 缺失",
                    passed=False,
                    message=f"文件不存在: {path.relative_to(self.project_root)}",
                    blocking=True
                ))

        # 检查 slices/ 目录
        slices_dir = self.plans_dir / 'slices'
        if slices_dir.exists():
            slice_files = list(slices_dir.glob('slice-*.md'))
            self.checks.append(GateCheck(
                name=f"✅ slices/ 目录包含 {len(slice_files)} 个文件",
                passed=True,
                message=f"找到 {len(slice_files)} 个 slice 文件"
            ))
        else:
            self.checks.append(GateCheck(
                name="❌ slices/ 目录缺失",
                passed=False,
                message="slices/ 目录不存在",
                blocking=True
            ))

    def _check_completeness(self):
        """检查产物完整性"""
        # 1. 检查 feature-plan.md 是否包含 indexed-v1 标记
        feature_plan_path = self.plans_dir / 'feature-plan.md'
        if feature_plan_path.exists():
            content = feature_plan_path.read_text()

            if 'plan_format: indexed-v1' in content:
                self.checks.append(GateCheck(
                    name="✅ feature-plan.md 使用 indexed-v1 格式",
                    passed=True,
                    message="检测到 plan_format: indexed-v1"
                ))
            else:
                self.checks.append(GateCheck(
                    name="❌ feature-plan.md 缺少 indexed-v1 标记",
                    passed=False,
                    message="未找到 plan_format: indexed-v1",
                    blocking=True
                ))

            # 检查 FV 任务
            has_fv1 = 'FV-1' in content
            has_fv2 = 'FV-2' in content

            if has_fv1 and has_fv2:
                self.checks.append(GateCheck(
                    name="✅ Final Verification 任务完整",
                    passed=True,
                    message="包含 FV-1 和 FV-2"
                ))
            else:
                missing_fv = []
                if not has_fv1:
                    missing_fv.append('FV-1')
                if not has_fv2:
                    missing_fv.append('FV-2')

                self.checks.append(GateCheck(
                    name="❌ Final Verification 任务不完整",
                    passed=False,
                    message=f"缺少: {', '.join(missing_fv)}",
                    blocking=True
                ))

        # 2. 检查 base-plan.md 是否是只读态
        base_plan_path = self.plans_dir / 'base-plan.md'
        if base_plan_path.exists():
            content = base_plan_path.read_text()

            has_checkbox = '- [ ]' in content
            has_evidence = 'evidence:' in content

            if not has_checkbox and not has_evidence:
                self.checks.append(GateCheck(
                    name="✅ base-plan.md 是只读态",
                    passed=True,
                    message="无 checkbox 和 evidence 槽"
                ))
            else:
                issues = []
                if has_checkbox:
                    issues.append('包含 checkbox')
                if has_evidence:
                    issues.append('包含 evidence 槽')

                self.checks.append(GateCheck(
                    name="⚠️  base-plan.md 不是纯只读态",
                    passed=False,
                    message=', '.join(issues),
                    blocking=False
                ))

    def _check_coverage_metrics(self):
        """检查覆盖率指标"""
        coverage_path = self.plans_dir / 'coverage-matrix.md'

        if not coverage_path.exists():
            self.checks.append(GateCheck(
                name="❌ 无法检查覆盖率指标",
                passed=False,
                message="coverage-matrix.md 不存在",
                blocking=True
            ))
            return

        content = coverage_path.read_text()

        # 解析覆盖率指标
        metrics = {
            'P0 功能覆盖率': self._extract_metric(content, r'P0.*?(\d+)/(\d+)\s*\((\d+)%\)'),
            'P1 功能覆盖率': self._extract_metric(content, r'P1.*?(\d+)/(\d+)\s*\((\d+)%\)'),
            'UI 页面覆盖率': self._extract_metric(content, r'UI.*?(\d+)/(\d+)\s*\((\d+)%\)'),
        }

        # 检查 P0 功能覆盖率 = 100%
        if metrics['P0 功能覆盖率']:
            actual, total, percentage = metrics['P0 功能覆盖率']
            if percentage == 100:
                self.checks.append(GateCheck(
                    name="✅ P0 功能覆盖率 = 100%",
                    passed=True,
                    message=f"{actual}/{total} (100%)"
                ))
            else:
                self.checks.append(GateCheck(
                    name="❌ P0 功能覆盖率不足 100%",
                    passed=False,
                    message=f"当前: {actual}/{total} ({percentage}%)",
                    blocking=True
                ))

        # 检查 P1 功能覆盖率 ≥ 80%
        if metrics['P1 功能覆盖率']:
            actual, total, percentage = metrics['P1 功能覆盖率']
            if percentage >= 80:
                self.checks.append(GateCheck(
                    name="✅ P1 功能覆盖率 ≥ 80%",
                    passed=True,
                    message=f"{actual}/{total} ({percentage}%)"
                ))
            else:
                self.checks.append(GateCheck(
                    name="⚠️  P1 功能覆盖率不足 80%",
                    passed=False,
                    message=f"当前: {actual}/{total} ({percentage}%)",
                    blocking=False
                ))

        # 检查 UI 页面覆盖率 = 100%
        if metrics['UI 页面覆盖率']:
            actual, total, percentage = metrics['UI 页面覆盖率']
            if percentage == 100:
                self.checks.append(GateCheck(
                    name="✅ UI 页面覆盖率 = 100%",
                    passed=True,
                    message=f"{actual}/{total} (100%)"
                ))
            else:
                self.checks.append(GateCheck(
                    name="❌ UI 页面覆盖率不足 100%",
                    passed=False,
                    message=f"当前: {actual}/{total} ({percentage}%)",
                    blocking=True
                ))

        # 检查 Placeholder 白名单率
        if 'Placeholder trigger 白名单率: 100%' in content or 'Placeholder.*?100%.*?✓' in content:
            self.checks.append(GateCheck(
                name="✅ Placeholder trigger 白名单率 = 100%",
                passed=True,
                message="所有 placeholder trigger 符合白名单"
            ))
        elif 'Placeholder' in content:
            self.checks.append(GateCheck(
                name="⚠️  Placeholder trigger 白名单率可能不足",
                passed=False,
                message="请检查 coverage-matrix.md 中的 Placeholder 校验结果",
                blocking=False
            ))

    def _check_blocking_findings(self):
        """检查是否有 blocking findings"""
        findings_path = self.spec_dir.parent / '.i2h' / 'open-findings.json'

        if not findings_path.exists():
            self.checks.append(GateCheck(
                name="✅ 无 open findings",
                passed=True,
                message="open-findings.json 不存在（无遗留问题）"
            ))
            return

        try:
            with open(findings_path) as f:
                findings = json.load(f)

            # Both the legacy contract (a top-level list) and the indexed
            # contract (sections keyed by ledger name) are emitted by the
            # pipeline.  Normalize them before applying the plan gate so a
            # newer execute section cannot crash the plan checker.
            normalized_findings = []
            if isinstance(findings, list):
                normalized_findings = [item for item in findings if isinstance(item, dict)]
            elif isinstance(findings, dict):
                direct = findings.get('findings')
                if isinstance(direct, list):
                    normalized_findings.extend(item for item in direct if isinstance(item, dict))
                sections = findings.get('sections')
                if isinstance(sections, dict):
                    for section in sections.values():
                        if not isinstance(section, dict):
                            continue
                        items = section.get('findings')
                        if isinstance(items, list):
                            normalized_findings.extend(item for item in items if isinstance(item, dict))

            # 筛选 blocking + 属于 plan 阶段的 findings
            plan_blocking = [
                f for f in normalized_findings
                if f.get('severity') == 'blocking'
                and f.get('owner_stage') in ['plan', 'spec']
                and not f.get('decision_ref')
            ]

            if not plan_blocking:
                self.checks.append(GateCheck(
                    name="✅ 无 blocking findings",
                    passed=True,
                    message=f"总 findings: {len(normalized_findings)}，无阻断级别"
                ))
            else:
                self.checks.append(GateCheck(
                    name="❌ 存在 blocking findings",
                    passed=False,
                    message=f"{len(plan_blocking)} 个阻断级别的 findings 未解决",
                    blocking=True
                ))

        except (json.JSONDecodeError, KeyError) as e:
            self.checks.append(GateCheck(
                name="⚠️  无法解析 open-findings.json",
                passed=False,
                message=str(e),
                blocking=False
            ))

    def _check_grill2_completion(self):
        """检查 grill #2 是否完成"""
        ledger_path = self.spec_dir.parent / 'decision-ledger.md'

        if not ledger_path.exists():
            self.checks.append(GateCheck(
                name="⚠️  decision-ledger.md 不存在",
                passed=False,
                message="无法确认 grill #2 是否完成",
                blocking=False
            ))
            return

        content = ledger_path.read_text()

        # 检查是否有新增的 D 编号（grill #2 产出）
        # 简单检测：是否包含 grill #2 相关内容
        has_grill2 = 'grill #2' in content.lower() or 'Grill #2' in content

        if has_grill2:
            # 统计 D 编号数量
            d_numbers = len([line for line in content.splitlines() if line.strip().startswith('- D-')])

            self.checks.append(GateCheck(
                name="✅ grill #2 已完成",
                passed=True,
                message=f"decision-ledger.md 包含 {d_numbers} 条决策"
            ))
        else:
            self.checks.append(GateCheck(
                name="⚠️  grill #2 可能未完成",
                passed=False,
                message="decision-ledger.md 中未找到 grill #2 相关内容",
                blocking=False
            ))

    def _extract_metric(self, content: str, pattern: str) -> Optional[tuple]:
        """从 coverage-matrix.md 提取指标"""
        import re
        match = re.search(pattern, content)
        if match:
            actual = int(match.group(1))
            total = int(match.group(2))
            percentage = int(match.group(3))
            return (actual, total, percentage)
        return None

    def _print_results(self):
        """打印门禁检查结果"""
        print("\n📋 门禁检查结果:\n")

        for check in self.checks:
            icon = "✅" if check.passed else ("❌" if check.blocking else "⚠️ ")
            print(f"{icon} {check.name}")
            if check.message:
                print(f"   {check.message}")
            print()

        print("=" * 80)

        # 统计
        passed = sum(1 for c in self.checks if c.passed)
        failed = sum(1 for c in self.checks if not c.passed)
        blocking = sum(1 for c in self.checks if not c.passed and c.blocking)
        warnings = sum(1 for c in self.checks if not c.passed and not c.blocking)

        print(f"\n统计: {passed} 通过, {failed} 失败 (阻断: {blocking}, 警告: {warnings})")

        if blocking > 0:
            print("\n🔴 门禁失败: 存在阻断级别的问题，请修复后重试")
            print("   i2h-plan 未完成，无法进入 i2h-execute")
            return False
        elif warnings > 0:
            print("\n⚠️  门禁通过（有警告）: 存在非阻断问题，建议修复")
            print("   可以进入 i2h-execute，但建议先解决警告")
            return True
        else:
            print("\n🎉 门禁通过: 所有检查通过，可以进入 i2h-execute！")
            return True


def main():
    if len(sys.argv) != 2:
        print("Usage: python3 gate_plan_complete.py <project_root>")
        sys.exit(1)

    project_root = sys.argv[1]

    if not os.path.isdir(project_root):
        print(f"❌ 错误: 目录不存在: {project_root}")
        sys.exit(1)

    gate = PlanCompletionGate(project_root)
    success = gate.run()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
