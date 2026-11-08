#!/usr/bin/env python3
"""
i2h-plan UI Plan Linter

检查 ui-plan.md 的格式和内容正确性。

Usage:
    python3 lint_ui_plan.py <project_root>

Exit codes:
    0 - 所有校验通过
    1 - 有校验失败
"""

import sys
import os
import re
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field


@dataclass
class UIPageEntry:
    """UI 页面条目"""
    seq: str  # 序号（如 "0001"）
    name: str  # 页面名称
    source: str  # iOS 来源
    owning_slice: str  # 归属 F-ID
    line_number: int  # 行号
    has_low_confidence: bool = False  # 是否标记 low confidence


@dataclass
class BatchInfo:
    """批次信息"""
    batch_id: int
    pages: List[UIPageEntry]
    has_checkpoint: bool = False


@dataclass
class ValidationError:
    """校验错误"""
    level: str  # ERROR, WARNING
    message: str
    line: Optional[int] = None
    suggestion: Optional[str] = None


class UIPlannLinter:
    """UI Plan 格式和内容校验器"""

    F_ID_PATTERN = re.compile(r'^F\d{3}$')
    SEQ_PATTERN = re.compile(r'^\d{4}$')

    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.spec_dir = self.project_root / "spec" / "baseline"
        self.ui_plan_path = self.spec_dir / "plans" / "ui-plan.md"
        self.ui_manifest_path = self.spec_dir / "ui-manifest.md"
        self.errors: List[ValidationError] = []
        self.warnings: List[ValidationError] = []
        self.feature_priorities: Dict[str, str] = self._load_feature_priorities()

    def run(self) -> bool:
        """运行所有校验"""
        print("🔍 检查 ui-plan.md...\n")

        # 1. 文件存在性
        if not self._check_file_exists():
            return False

        # 2. 解析文件
        content = self.ui_plan_path.read_text()
        batches = self._parse_ui_plan(content)

        if not batches:
            self._add_error("无法解析批次信息", suggestion="检查文件格式是否正确")
            self._print_results()
            return False

        # 3. 格式校验
        self._check_format(content, batches)

        # 4. 字段校验
        self._check_fields(batches)

        # 5. 批次校验
        self._check_batches(batches)

        # 6. 与 ui-manifest 交叉校验
        self._check_against_manifest(batches)

        # 7. Summary 校验
        self._check_summary(content, batches)

        # 8. 输出结果
        self._print_results()

        return len(self.errors) == 0

    def _check_file_exists(self) -> bool:
        """检查文件是否存在"""
        if not self.ui_plan_path.exists():
            print(f"❌ 错误: ui-plan.md 不存在")
            print(f"   预期路径: {self.ui_plan_path.relative_to(self.project_root)}")
            return False
        return True

    def _parse_ui_plan(self, content: str) -> List[BatchInfo]:
        """解析 ui-plan.md"""
        batches = []
        current_batch = None
        lines = content.splitlines()

        for i, line in enumerate(lines, 1):
            # 匹配 Batch 标题
            batch_match = re.match(r'^##\s+Batch\s+(\d+)', line, re.IGNORECASE)
            if batch_match:
                if current_batch:
                    batches.append(current_batch)
                current_batch = BatchInfo(
                    batch_id=int(batch_match.group(1)),
                    pages=[]
                )
                continue

            # 匹配结算检查点
            if current_batch and '结算检查点' in line:
                current_batch.has_checkpoint = True
                continue

            # 匹配表格行（页面条目）
            if current_batch and line.startswith('|') and not line.startswith('|---'):
                parts = [p.strip() for p in line.split('|')[1:-1]]
                if len(parts) >= 4 and parts[0] and self.SEQ_PATTERN.match(parts[0]):
                    page = UIPageEntry(
                        seq=parts[0],
                        name=parts[1].replace('⚠️low', '').strip(),
                        source=parts[2] if len(parts) > 2 else '',
                        owning_slice=parts[3] if len(parts) > 3 else '',
                        line_number=i,
                        has_low_confidence='⚠️low' in parts[1]
                    )
                    current_batch.pages.append(page)

        if current_batch:
            batches.append(current_batch)

        return batches

    def _check_format(self, content: str, batches: List[BatchInfo]):
        """检查文件格式"""
        lines = content.splitlines()

        # 1. 检查是否有 Context 段
        has_context = any('## Context' in line for line in lines)
        if not has_context:
            self._add_error("缺少 Context 段", suggestion="添加 ## Context 段")

        # 2. 检查是否是 Markdown 表格格式（而非 JSON）
        if '{' in content and '"pages"' in content:
            self._add_error(
                "检测到 JSON 格式",
                suggestion="应该使用 Markdown 表格格式，参考 templates/ui-plan-template.md"
            )

        # 3. 检查表格头部
        for batch in batches:
            # 查找该 batch 的表格头
            batch_line_start = None
            for i, line in enumerate(lines):
                if f'Batch {batch.batch_id}' in line:
                    batch_line_start = i
                    break

            if batch_line_start:
                # 检查后续是否有正确的表格头
                header_found = False
                for line in lines[batch_line_start:batch_line_start + 10]:
                    if '序号' in line and '页面' in line and 'owning_slice' in line:
                        header_found = True
                        # 检查是否有不应该存在的列
                        if 'confidence' in line.lower():
                            self._add_error(
                                f"Batch {batch.batch_id}: 表格不应有 confidence 列",
                                suggestion="confidence:low 应在页面名后标 ⚠️low，不单独成列"
                            )
                        break

                if not header_found:
                    self._add_error(
                        f"Batch {batch.batch_id}: 缺少表格头部或格式错误",
                        suggestion="表格头应包含：序号 | 页面 | iOS 来源 | owning_slice"
                    )

        # 4. 检查是否有 Summary 段
        has_summary = any('## Summary' in line for line in lines)
        if not has_summary:
            self._add_error("缺少 Summary 段", suggestion="添加 ## Summary 段统计信息")

    def _check_fields(self, batches: List[BatchInfo]):
        """检查字段正确性"""
        for batch in batches:
            for page in batch.pages:
                # 1. 序号格式（4 位数字）
                if not self.SEQ_PATTERN.match(page.seq):
                    self._add_error(
                        f"序号格式错误: {page.seq}",
                        line=page.line_number,
                        suggestion="序号应为 4 位数字，如 0001"
                    )

                # 2. 页面名称非空
                if not page.name:
                    self._add_error(
                        f"页面名称为空 (序号 {page.seq})",
                        line=page.line_number
                    )

                # 3. iOS 来源非空
                if not page.source:
                    self._add_error(
                        f"iOS 来源为空 (序号 {page.seq})",
                        line=page.line_number
                    )

                # 4. owning_slice 格式（必须是裸 F-ID）
                if not page.owning_slice:
                    self._add_error(
                        f"owning_slice 为空 (序号 {page.seq})",
                        line=page.line_number
                    )
                elif not self.F_ID_PATTERN.match(page.owning_slice):
                    self._add_error(
                        f"owning_slice 格式错误: {page.owning_slice} (序号 {page.seq})",
                        line=page.line_number,
                        suggestion=f"应为裸 F-ID 格式（如 F001），而非 '{page.owning_slice}'"
                    )

                # 5. low confidence 标记格式
                if page.has_low_confidence:
                    if '⚠️low' not in page.name:
                        self._add_warning(
                            f"页面 {page.seq} 可能缺少 ⚠️low 标记",
                            line=page.line_number
                        )

    def _check_batches(self, batches: List[BatchInfo]):
        """检查批次分配"""
        # 1. 检查批次编号连续性
        batch_ids = [b.batch_id for b in batches]
        expected_ids = list(range(1, len(batches) + 1))
        if batch_ids != expected_ids:
            self._add_error(
                f"批次编号不连续: {batch_ids}",
                suggestion=f"应为连续编号: {expected_ids}"
            )

        # 2. 检查 size-1 批次
        for batch in batches:
            if len(batch.pages) == 1:
                self._add_error(
                    f"Batch {batch.batch_id} 只有 1 个页面（size-1 批次）",
                    suggestion="应并入前一批次末尾"
                )

        # 3. 检查每个批次是否有结算检查点
        for batch in batches:
            if not batch.has_checkpoint:
                self._add_error(
                    f"Batch {batch.batch_id} 缺少结算检查点",
                    suggestion="在批次末尾添加：结算检查点: Batch N 完成后..."
                )

        # 4. 检查序号连续性
        all_seqs = []
        for batch in batches:
            all_seqs.extend([int(p.seq) for p in batch.pages])

        all_seqs.sort()
        for i in range(len(all_seqs) - 1):
            if all_seqs[i + 1] != all_seqs[i] + 1:
                self._add_warning(
                    f"序号不连续: {all_seqs[i]:04d} → {all_seqs[i+1]:04d}",
                    suggestion="页面序号应连续递增"
                )

    def _check_against_manifest(self, batches: List[BatchInfo]):
        """与 ui-manifest.md 交叉校验"""
        if not self.ui_manifest_path.exists():
            self._add_warning("ui-manifest.md 不存在，跳过交叉校验")
            return

        # 从 manifest 提取页面
        manifest_pages = self._parse_ui_manifest()

        # 从 plan 提取页面
        plan_pages = set()
        for batch in batches:
            plan_pages.update(p.seq for p in batch.pages)

        # 检查覆盖率
        manifest_active = {seq for seq, data in manifest_pages.items()
                          if data.get('status') != 'skipped'}

        missing_in_plan = manifest_active - plan_pages
        extra_in_plan = plan_pages - set(manifest_pages.keys())

        if missing_in_plan:
            self._add_error(
                f"ui-plan 缺少 {len(missing_in_plan)} 个页面",
                suggestion=f"缺失序号: {', '.join(sorted(missing_in_plan)[:5])}"
            )

        if extra_in_plan:
            self._add_warning(
                f"ui-plan 包含 {len(extra_in_plan)} 个 manifest 中不存在的页面",
                suggestion=f"额外序号: {', '.join(sorted(extra_in_plan)[:5])}"
            )

    def _check_summary(self, content: str, batches: List[BatchInfo]):
        """检查 Summary 段的统计正确性"""
        lines = content.splitlines()

        # 提取 Summary 段
        summary_start = None
        for i, line in enumerate(lines):
            if '## Summary' in line:
                summary_start = i
                break

        if not summary_start:
            return  # 已在 _check_format 中报错

        summary_lines = lines[summary_start:summary_start + 20]
        summary_text = '\n'.join(summary_lines)

        # 计算实际统计
        total_pages = sum(len(b.pages) for b in batches)
        p0_pages = sum(1 for b in batches for p in b.pages
                      if self._get_priority(p.owning_slice) == 'P0')
        p1_pages = sum(1 for b in batches for p in b.pages
                      if self._get_priority(p.owning_slice) == 'P1')
        low_conf_pages = sum(1 for b in batches for p in b.pages
                            if p.has_low_confidence)

        # 检查总页面数
        total_match = re.search(r'(\d+)\s*个?页面', summary_text)
        if total_match:
            stated_total = int(total_match.group(1))
            if stated_total != total_pages:
                self._add_error(
                    f"Summary 总页面数不匹配: 声明 {stated_total}，实际 {total_pages}",
                    suggestion="更新 Summary 统计"
                )

        # 检查 P0/P1 统计
        p0_match = re.search(r'P0.*?(\d+)', summary_text)
        if p0_match and int(p0_match.group(1)) != p0_pages:
            self._add_warning(
                f"Summary P0 页面数可能不匹配: 声明 {p0_match.group(1)}，实际 {p0_pages}"
            )

        # 检查 low confidence 统计
        if low_conf_pages > 0:
            if 'Low confidence' not in summary_text:
                self._add_warning(
                    f"有 {low_conf_pages} 个 low confidence 页面但 Summary 未提及",
                    suggestion="添加 ⚠️ Low confidence: N pages"
                )

    def _parse_ui_manifest(self) -> Dict[str, Dict]:
        """解析 ui-manifest.md"""
        pages = {}
        if not self.ui_manifest_path.exists():
            return pages

        content = self.ui_manifest_path.read_text()
        lines = content.splitlines()

        for line in lines:
            # 只读取屏幕级页面表中的 canonical ID。不要从生成日期、source-index
            # 映射表或普通说明文字中提取裸四位数字。
            seq_match = re.search(r'\bpage_(\d{4})_[A-Za-z_]\w*\b', line)
            if seq_match:
                seq = seq_match.group(1)
                pages[seq] = {}

                # 检查 status
                if 'skipped' in line.lower():
                    pages[seq]['status'] = 'skipped'

        return pages

    def _load_feature_priorities(self) -> Dict[str, str]:
        """读取 feature-index.md 中的真实优先级，避免把所有页面都算成 P0。"""
        path = self.spec_dir / "feature-index.md"
        if not path.exists():
            return {}
        priorities: Dict[str, str] = {}
        current: Optional[str] = None
        for line in path.read_text().splitlines():
            match = re.match(r'^###\s+(F\d{3})\b', line)
            if match:
                current = match.group(1)
                continue
            if current:
                priority = re.search(r'\b(P[0-3])\b', line)
                if priority and ('优先级' in line or 'priority' in line.lower()):
                    priorities[current] = priority.group(1)
        return priorities

    def _get_priority(self, f_id: str) -> str:
        """获取功能优先级（简化实现）"""
        return self.feature_priorities.get(f_id, 'P1')

    def _add_error(self, message: str, line: Optional[int] = None,
                   suggestion: Optional[str] = None):
        """添加错误"""
        self.errors.append(ValidationError(
            level='ERROR',
            message=message,
            line=line,
            suggestion=suggestion
        ))

    def _add_warning(self, message: str, line: Optional[int] = None,
                    suggestion: Optional[str] = None):
        """添加警告"""
        self.warnings.append(ValidationError(
            level='WARNING',
            message=message,
            line=line,
            suggestion=suggestion
        ))

    def _print_results(self):
        """打印校验结果"""
        print("\n" + "=" * 80)

        if self.errors:
            print("\n❌ 错误:")
            for i, err in enumerate(self.errors, 1):
                line_info = f" (行 {err.line})" if err.line else ""
                print(f"\n{i}. {err.message}{line_info}")
                if err.suggestion:
                    print(f"   💡 建议: {err.suggestion}")

        if self.warnings:
            print("\n⚠️  警告:")
            for i, warn in enumerate(self.warnings, 1):
                line_info = f" (行 {warn.line})" if warn.line else ""
                print(f"\n{i}. {warn.message}{line_info}")
                if warn.suggestion:
                    print(f"   💡 建议: {warn.suggestion}")

        print("\n" + "=" * 80)

        if not self.errors and not self.warnings:
            print("\n✅ ui-plan.md 格式正确，所有校验通过！")
        elif not self.errors:
            print(f"\n⚠️  发现 {len(self.warnings)} 个警告，建议修复")
        else:
            print(f"\n❌ 发现 {len(self.errors)} 个错误，{len(self.warnings)} 个警告")
            print("   请修复错误后重新运行")


def main():
    if len(sys.argv) != 2:
        print("Usage: python3 lint_ui_plan.py <project_root>")
        sys.exit(1)

    project_root = sys.argv[1]

    if not os.path.isdir(project_root):
        print(f"❌ 错误: 目录不存在: {project_root}")
        sys.exit(1)

    linter = UIPlannLinter(project_root)
    success = linter.run()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
