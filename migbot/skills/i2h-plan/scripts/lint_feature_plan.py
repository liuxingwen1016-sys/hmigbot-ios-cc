#!/usr/bin/env python3
"""
i2h-plan Feature Plan Linter

检查 feature-plan.md、base-plan.md 和 slices/*.md 的格式和内容正确性。

Usage:
    python3 lint_feature_plan.py <project_root>

Exit codes:
    0 - 所有校验通过
    1 - 有校验失败
"""

import sys
import os
import json
import re
from pathlib import Path
from typing import List, Dict, Optional, Set
from dataclasses import dataclass, field


@dataclass
class ValidationError:
    """校验错误"""
    level: str  # ERROR, WARNING
    category: str  # 错误类别
    message: str
    file: Optional[str] = None
    line: Optional[int] = None
    suggestion: Optional[str] = None


class FeaturePlanLinter:
    """Feature Plan 格式和内容校验器"""

    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.spec_dir = self.project_root / "spec" / "baseline"
        self.plans_dir = self.spec_dir / "plans"
        self.feature_plan_path = self.plans_dir / "feature-plan.md"
        self.base_plan_path = self.plans_dir / "base-plan.md"
        self.slices_dir = self.plans_dir / "slices"
        self.errors: List[ValidationError] = []
        self.warnings: List[ValidationError] = []

    def run(self) -> bool:
        """运行所有校验"""
        print("🔍 检查 feature-plan.md 和相关文件...\n")

        # 1. 文件存在性
        if not self._check_files_exist():
            self._print_results()
            return False

        # 2. feature-plan.md 格式校验
        self._check_feature_plan_format()

        # 3. base-plan.md 校验
        self._check_base_plan()

        # 4. slices/*.md 校验
        self._check_slices()

        # 5. 索引与文件一致性
        self._check_index_file_consistency()

        # 6. FV 任务校验
        self._check_fv_tasks()

        # 7. iOS immersive/safe-area binding follows source-derived delivery
        # metadata.  Keep this check conditional so older Android/hand-authored
        # plans without a schema-2 inventory retain compatibility.
        self._check_immersive_binding()

        # 8. 输出结果
        self._print_results()

        return len(self.errors) == 0

    def _check_files_exist(self) -> bool:
        """检查必需文件是否存在"""
        missing = []

        if not self.feature_plan_path.exists():
            missing.append("feature-plan.md")
        if not self.base_plan_path.exists():
            missing.append("base-plan.md")
        if not self.slices_dir.exists():
            missing.append("slices/ 目录")

        if missing:
            print("❌ 缺少必需文件:")
            for f in missing:
                print(f"   - {f}")
            return False

        return True

    def _check_feature_plan_format(self):
        """检查 feature-plan.md 格式"""
        content = self.feature_plan_path.read_text()
        lines = content.splitlines()

        # 1. 检查 plan_format: indexed-v1
        if 'plan_format: indexed-v1' not in content:
            self._add_error(
                'format',
                "缺少 plan_format: indexed-v1 标记",
                file='feature-plan.md',
                suggestion="在 Context 段添加 plan_format: indexed-v1"
            )

        # 2. 检查 Base 层 stub
        has_base_stub = False
        base_detail_correct = False

        for i, line in enumerate(lines, 1):
            if re.match(r'^##\s+Base\s+层', line):
                has_base_stub = True

                # 检查后续几行是否有 detail: plans/base-plan.md
                for j in range(i, min(i + 5, len(lines))):
                    if 'detail: plans/base-plan.md' in lines[j]:
                        base_detail_correct = True
                        break
                    # 如果有展开的任务行，报错
                    if re.match(r'^\s*-\s+Base-\d+:', lines[j]):
                        self._add_error(
                            'format',
                            "Base 层不应展开任务行",
                            file='feature-plan.md',
                            line=j + 1,
                            suggestion="Base 层任务应在 base-plan.md 中，索引只保留 stub"
                        )
                break

        if not has_base_stub:
            self._add_error(
                'structure',
                "缺少 Base 层 stub",
                file='feature-plan.md',
                suggestion="添加 ## Base 层 stub，指向 base-plan.md"
            )

        if has_base_stub and not base_detail_correct:
            self._add_error(
                'format',
                "Base 层 stub 缺少 detail: plans/base-plan.md",
                file='feature-plan.md',
                suggestion="添加 detail: plans/base-plan.md 指针"
            )

        # 3. 检查 Slice 索引按 Group 分节
        has_group_section = any(re.match(r'^##\s+Group\s+\d+', line) for line in lines)
        if not has_group_section:
            self._add_warning(
                'format',
                "未找到 Group 分节",
                file='feature-plan.md',
                suggestion="Slice 应按 parallel_group 以 ## Group N 分节"
            )

        # 4. 检查 group-closer 插入点
        group_nums = set()
        for line in lines:
            match = re.match(r'^##\s+Group\s+(\d+)', line)
            if match:
                group_nums.add(int(match.group(1)))

        for group_num in group_nums:
            # 检查是否有对应的 group-closer
            closer_pattern = f'> group-closer @ G{group_num}'
            if closer_pattern not in content:
                self._add_error(
                    'format',
                    f"Group {group_num} 缺少 group-closer 插入点",
                    file='feature-plan.md',
                    suggestion=f"在 Group {group_num} 末尾添加：> group-closer @ G{group_num}"
                )

        # 5. 检查 Slice 头部字段
        slice_pattern = re.compile(r'^##\s+Slice\s+\d+:', re.MULTILINE)
        slice_matches = list(slice_pattern.finditer(content))

        for match in slice_matches:
            slice_start = match.end()
            slice_end = content.find('\n## ', slice_start)
            if slice_end == -1:
                slice_end = len(content)

            slice_content = content[slice_start:slice_end]

            # 检查必填字段
            required_fields = ['parallel_group', 'complexity', 'depends_on', 'detail']
            for field in required_fields:
                if f'{field}:' not in slice_content:
                    self._add_error(
                        'fields',
                        f"Slice 缺少必填字段 {field}",
                        file='feature-plan.md',
                        suggestion=f"添加 {field}: 字段"
                    )

            # 检查 detail 指向的文件是否存在
            detail_match = re.search(r'detail:\s*(plans/slices/[^\s]+)', slice_content)
            if detail_match:
                detail_path = self.spec_dir / detail_match.group(1)
                if not detail_path.exists():
                    self._add_error(
                        'reference',
                        f"detail 指向的文件不存在: {detail_match.group(1)}",
                        file='feature-plan.md',
                        suggestion="确保 slice 文件已生成"
                    )

        # 6. 检查是否有依赖 ASCII 树
        if '```' in content and any(c in line for line in lines for c in ['├', '└', '│']):
            self._add_error(
                'format',
                "索引不应包含依赖 ASCII 树",
                file='feature-plan.md',
                suggestion="依赖关系应由 depends_on 字段表达"
            )

    def _check_base_plan(self):
        """检查 base-plan.md"""
        if not self.base_plan_path.exists():
            return

        content = self.base_plan_path.read_text()
        lines = content.splitlines()

        # 1. 检查是否是只读态（无 checkbox）
        for i, line in enumerate(lines, 1):
            if re.match(r'^\s*-\s+\[\s*\]\s+Base-', line):
                self._add_error(
                    'readonly',
                    "base-plan.md 不应包含 checkbox",
                    file='base-plan.md',
                    line=i,
                    suggestion="Base 层任务应为只读态，移除 - [ ]"
                )

        # 2. 检查是否有 evidence 槽
        if 'evidence:' in content:
            self._add_error(
                'readonly',
                "base-plan.md 不应包含 evidence 槽",
                file='base-plan.md',
                suggestion="Base 层任务应为只读态，移除 evidence 字段"
            )

        # 3. 检查 Base 任务是否有 parallel_group（Base-0 除外）
        base_tasks = re.findall(r'^\s*-\s+Base-(\d+):', '\n'.join(lines), re.MULTILINE)
        for task_num in base_tasks:
            if task_num == '0':
                continue  # Base-0 不需要 parallel_group

            # 查找该任务的 parallel_group
            task_pattern = f'Base-{task_num}:'
            task_start = None
            for i, line in enumerate(lines):
                if task_pattern in line:
                    task_start = i
                    break

            if task_start is not None:
                # 检查接下来几行是否有 parallel_group
                has_group = False
                for j in range(task_start, min(task_start + 10, len(lines))):
                    if 'parallel_group:' in lines[j]:
                        has_group = True
                        break
                    # 遇到下一个任务则停止
                    if j > task_start and re.match(r'^\s*-\s+Base-\d+:', lines[j]):
                        break

                if not has_group:
                    self._add_error(
                        'fields',
                        f"Base-{task_num} 缺少 parallel_group 字段",
                        file='base-plan.md',
                        line=task_start + 1,
                        suggestion=f"添加 parallel_group: N"
                    )

        # 4. 检查 iOS 特定 Base 任务是否完整（8 个）
        expected_tasks = set(range(8))  # Base-0 到 Base-7
        actual_tasks = set(int(num) for num in base_tasks)

        missing_tasks = expected_tasks - actual_tasks
        if missing_tasks:
            self._add_warning(
                'completeness',
                f"可能缺少 Base 任务: {', '.join(f'Base-{n}' for n in sorted(missing_tasks))}",
                file='base-plan.md',
                suggestion="iOS 项目通常需要 Base-0 到 Base-7 共 8 个任务"
            )

    def _check_slices(self):
        """检查 slices/*.md"""
        if not self.slices_dir.exists():
            return

        slice_files = list(self.slices_dir.glob("slice-*.md"))

        if not slice_files:
            self._add_warning(
                'completeness',
                "slices/ 目录为空",
                suggestion="至少应有一个 slice 文件"
            )
            return

        for slice_file in slice_files:
            self._check_single_slice(slice_file)

    def _check_single_slice(self, slice_file: Path):
        """检查单个 slice 文件"""
        content = slice_file.read_text()
        lines = content.splitlines()
        file_name = slice_file.name

        # 1. 三铁律 ①：调度表非详案（行数启发式）
        line_count = len(lines)
        if line_count > 200:
            self._add_warning(
                'verbosity',
                f"行数过多 ({line_count} 行)",
                file=file_name,
                suggestion="疑似复制 spec 正文，应只保留名字级 scope + 指针引用"
            )

        # 2. 三铁律 ②：只读态（无 checkbox、evidence、状态字段）
        for i, line in enumerate(lines, 1):
            if re.match(r'^\s*-\s+\[\s*\]', line):
                self._add_error(
                    'readonly',
                    "slice 文件不应包含 checkbox",
                    file=file_name,
                    line=i,
                    suggestion="slice 文件应为只读态，移除 - [ ]"
                )

        if 'evidence:' in content:
            self._add_error(
                'readonly',
                "slice 文件不应包含 evidence 槽",
                file=file_name,
                suggestion="完成性由 verify_slice_wiring + 组 brief 记录"
            )

        if re.search(r'\bstatus\s*:', content):
            self._add_error(
                'readonly',
                "slice 文件不应包含 status 字段",
                file=file_name,
                suggestion="状态由外部 brief 记录，slice 不持有状态"
            )

        # 3. 三铁律 ③：不持有占位
        if re.search(r'\bP-S\d+-\d+', content):
            # 检查是否在 resolve_by 中引用（允许）
            resolve_by_refs = re.findall(r'resolve_by:.*?(P-S\d+-\d+)', content)
            all_p_ids = set(re.findall(r'P-S\d+-\d+', content))
            inline_p_ids = all_p_ids - set(resolve_by_refs)

            if inline_p_ids:
                self._add_error(
                    'placeholder',
                    f"slice 文件不应持有占位内容，发现: {', '.join(list(inline_p_ids)[:3])}",
                    file=file_name,
                    suggestion="占位应直写 spec/placeholder-registry.md"
                )

        # 4. 检查必填字段
        required_sections = [
            'ios_source_anchors_ref',
            'integration_points_ref',
            'wires'
        ]

        for section in required_sections:
            if section not in content:
                # integration_points_ref 可选（当 feature spec 无对接点段时）
                if section == 'integration_points_ref':
                    continue
                self._add_warning(
                    'completeness',
                    f"缺少 {section} 段",
                    file=file_name,
                    suggestion=f"添加 {section} 段，即使为空也应显式标注"
                )

        # 5. 检查 wires 结构
        if 'wires:' in content:
            # 简单检查是否有结构化内容
            wires_start = content.find('wires:')
            wires_end = content.find('\n\n', wires_start)
            if wires_end == -1:
                wires_end = len(content)

            wires_section = content[wires_start:wires_end]

            # 检查是否有 page 字段
            if '- page:' not in wires_section and 'wires: []' not in content:
                self._add_warning(
                    'format',
                    "wires 段格式可能不正确",
                    file=file_name,
                    suggestion="wires 应包含结构化的 page/viewmodel 或 page/slot/embed 条目"
                )

        # 6. 检查 cross_slice_edits 与 wires 的双登问题
        if 'cross_slice_edits:' in content and 'wires:' in content:
            # 提取 wires 中的 embed slot
            embed_slots = re.findall(r'slot:\s*(\w+)', content)

            # 提取 cross_slice_edits 中的 handler
            cross_handlers = re.findall(r'handler:\s*(\w+)', content)

            # 检查是否有重复
            overlap = set(embed_slots) & set(cross_handlers)
            if overlap:
                self._add_error(
                    'duplication',
                    f"wires embed 和 cross_slice_edits 双登: {', '.join(overlap)}",
                    file=file_name,
                    suggestion="槽位填充只登 wires embed 条，不在 cross_slice_edits 重复"
                )

        # 7. 检查 Step 行格式
        step_pattern = re.compile(r'^\s*-\s+Step\s+3[abcde]:', re.MULTILINE)
        steps = step_pattern.findall(content)

        if not steps:
            self._add_warning(
                'completeness',
                "未找到 Step 3a-3e 任务行",
                file=file_name,
                suggestion="slice 应包含 Step 3a（UI）、3b（ViewModel）、3c（数据层）、3d/3e（接线）"
            )

        # 8. 检查是否复述了验收契约
        if 'acceptance:' in content or 'AC:' in content:
            self._add_warning(
                'verbosity',
                "Step 行可能复述了验收契约",
                file=file_name,
                suggestion="验收契约权威在 i2h-execute，slice 不应复述"
            )

    def _check_index_file_consistency(self):
        """检查索引与实际文件的一致性"""
        if not self.feature_plan_path.exists() or not self.slices_dir.exists():
            return

        content = self.feature_plan_path.read_text()

        # 从索引提取 detail 指针
        indexed_slices = set()
        for match in re.finditer(r'detail:\s*plans/slices/(slice-\d+-F\d{3})\.md', content):
            indexed_slices.add(match.group(1))

        # 从实际文件列表提取
        actual_slices = set()
        for slice_file in self.slices_dir.glob("slice-*.md"):
            actual_slices.add(slice_file.stem)

        # 对比
        missing_files = indexed_slices - actual_slices
        extra_files = actual_slices - indexed_slices

        if missing_files:
            self._add_error(
                'consistency',
                f"索引有但文件缺失: {', '.join(sorted(missing_files))}",
                file='feature-plan.md',
                suggestion="生成对应的 slice 文件或从索引移除"
            )

        if extra_files:
            self._add_error(
                'consistency',
                f"文件有但索引缺失: {', '.join(sorted(extra_files))}",
                file='feature-plan.md',
                suggestion="在索引中添加对应的 Slice 条目"
            )

    def _check_fv_tasks(self):
        """检查 Final Verification 任务"""
        if not self.feature_plan_path.exists():
            return

        content = self.feature_plan_path.read_text()

        # 1. 检查是否有 Final Verification 段
        if '## Final Verification' not in content:
            self._add_error(
                'completeness',
                "缺少 Final Verification 段",
                file='feature-plan.md',
                suggestion="在 Slice 索引之后添加 ## Final Verification 段"
            )
            return

        # 2. 检查 FV-1 和 FV-2
        has_fv1 = 'FV-1:' in content or 'FV-1 ' in content
        has_fv2 = 'FV-2:' in content or 'FV-2 ' in content

        if not has_fv1:
            self._add_error(
                'completeness',
                "缺少 FV-1: Final Structural Closure",
                file='feature-plan.md',
                suggestion="添加 FV-1 任务（arkts-structural-closure）"
            )

        if not has_fv2:
            self._add_error(
                'completeness',
                "缺少 FV-2: 终态全量编译",
                file='feature-plan.md',
                suggestion="添加 FV-2 任务（hmos-builder）"
            )

        # 3. 检查 FV 顺序（FV-1 必须在 FV-2 前）
        if has_fv1 and has_fv2:
            fv1_pos = content.find('FV-1')
            fv2_pos = content.find('FV-2')

            if fv1_pos > fv2_pos:
                self._add_error(
                    'order',
                    "FV 任务顺序错误：FV-2 在 FV-1 之前",
                    file='feature-plan.md',
                    suggestion="FV-1 必须在 FV-2 之前（FV-1 会改码，FV-2 兜底编译）"
                )

        # 4. 检查 FV-1 是否指定了 arkts-structural-closure
        if has_fv1:
            fv1_section = content[content.find('FV-1'):content.find('FV-2') if has_fv2 else len(content)]
            if 'arkts-structural-closure' not in fv1_section:
                self._add_error(
                    'skills',
                    "FV-1 缺少 arkts-structural-closure skill",
                    file='feature-plan.md',
                    suggestion="添加 suggested_skills: [arkts-structural-closure]"
                )

        # 5. 检查 FV-2 是否指定了 hmos-builder
        if has_fv2:
            fv2_section = content[content.find('FV-2'):]
            if 'hmos-builder' not in fv2_section:
                self._add_error(
                    'agents',
                    "FV-2 缺少 hmos-builder agent",
                    file='feature-plan.md',
                    suggestion="添加 suggested_agents: [hmos-builder]"
                )

    def _check_immersive_binding(self):
        """Require the immersive skill and receipt gate for source evidence."""
        candidates = (
            self.project_root / "spec/baseline/ui-delivery-approved.json",
            self.project_root / "spec/baseline/plans/stage1-ui-delivery.json",
            self.project_root / "spec/baseline/plans/ui-delivery-approved.json",
        )
        inventory_path = next((path for path in candidates if path.is_file()), None)
        if inventory_path is None:
            return
        try:
            payload = json.loads(inventory_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return
        units = payload.get("units", []) if isinstance(payload, dict) else []
        required = [
            str(unit.get("unit_id"))
            for unit in units
            if isinstance(unit, dict) and unit.get("needs_immersive_safearea") is True
        ]
        if not required:
            return
        content = self.feature_plan_path.read_text(encoding="utf-8")
        if "arkts-immersive-safearea" not in content:
            self._add_error(
                "skills",
                "iOS delivery 含 needs_immersive_safearea，但 plan 未绑定 arkts-immersive-safearea",
                file="feature-plan.md",
                suggestion="在相关 Slice/FV-1 中添加 suggested_skills: [arkts-immersive-safearea]",
            )
        if "immersive_safearea_gate" not in content and "immersive-safearea-gate" not in content:
            self._add_error(
                "gates",
                "iOS immersive 页缺少 execute immersive-safearea receipt gate",
                file="feature-plan.md",
                suggestion="加入 immersive_safearea_gate.py，并将 spec/execution/immersive-safearea-gate.json 作为 Stage 5 前置产物",
            )

    def _add_error(self, category: str, message: str, file: Optional[str] = None,
                   line: Optional[int] = None, suggestion: Optional[str] = None):
        """添加错误"""
        self.errors.append(ValidationError(
            level='ERROR',
            category=category,
            message=message,
            file=file,
            line=line,
            suggestion=suggestion
        ))

    def _add_warning(self, category: str, message: str, file: Optional[str] = None,
                    line: Optional[int] = None, suggestion: Optional[str] = None):
        """添加警告"""
        self.warnings.append(ValidationError(
            level='WARNING',
            category=category,
            message=message,
            file=file,
            line=line,
            suggestion=suggestion
        ))

    def _print_results(self):
        """打印校验结果"""
        print("\n" + "=" * 80)

        if self.errors:
            print("\n❌ 错误:")
            for i, err in enumerate(self.errors, 1):
                file_info = f" [{err.file}" if err.file else ""
                line_info = f":{err.line}" if err.line else ""
                close_bracket = "]" if err.file else ""
                location = f"{file_info}{line_info}{close_bracket}"

                print(f"\n{i}. [{err.category}] {err.message}{location}")
                if err.suggestion:
                    print(f"   💡 建议: {err.suggestion}")

        if self.warnings:
            print("\n⚠️  警告:")
            for i, warn in enumerate(self.warnings, 1):
                file_info = f" [{warn.file}" if warn.file else ""
                line_info = f":{warn.line}" if warn.line else ""
                close_bracket = "]" if warn.file else ""
                location = f"{file_info}{line_info}{close_bracket}"

                print(f"\n{i}. [{warn.category}] {warn.message}{location}")
                if warn.suggestion:
                    print(f"   💡 建议: {warn.suggestion}")

        print("\n" + "=" * 80)

        if not self.errors and not self.warnings:
            print("\n✅ feature-plan.md 及相关文件格式正确，所有校验通过！")
        elif not self.errors:
            print(f"\n⚠️  发现 {len(self.warnings)} 个警告，建议修复")
        else:
            print(f"\n❌ 发现 {len(self.errors)} 个错误，{len(self.warnings)} 个警告")
            print("   请修复错误后重新运行")


def main():
    if len(sys.argv) != 2:
        print("Usage: python3 lint_feature_plan.py <project_root>")
        sys.exit(1)

    project_root = sys.argv[1]

    if not os.path.isdir(project_root):
        print(f"❌ 错误: 目录不存在: {project_root}")
        sys.exit(1)

    linter = FeaturePlanLinter(project_root)
    success = linter.run()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
