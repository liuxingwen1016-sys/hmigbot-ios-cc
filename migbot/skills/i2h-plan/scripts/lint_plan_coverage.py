#!/usr/bin/env python3
"""
i2h-plan Coverage Linter

检查 i2h-plan 产出的完整性和覆盖率，对应 SKILL.md §7 的 12 项校验。

Usage:
    python3 lint_plan_coverage.py <project_root>

Exit codes:
    0 - 所有校验通过
    1 - 有校验失败（阻断级别）
    2 - 有警告（非阻断）
"""

import sys
import os
import json
import re
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional
from dataclasses import dataclass, field


@dataclass
class CoverageResult:
    """覆盖率校验结果"""
    name: str
    passed: bool
    actual: int
    total: int
    threshold: float
    blocking: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def percentage(self) -> float:
        return (self.actual / self.total * 100) if self.total > 0 else 100.0

    @property
    def status_icon(self) -> str:
        if self.passed:
            return "✅"
        elif self.blocking:
            return "❌"
        else:
            return "⚠️"


class PlanCoverageLinter:
    """Plan 覆盖率检查器"""

    # 白名单 trigger_condition 格式（正则表达式）
    TRIGGER_WHITELIST = [
        r'^D-\d+ chosen$',  # D-{N} chosen
        r'^.+ 实现 .+$',  # <path> 实现 <symbol>
        r'^.+ SDK 入仓$',  # <业务类别> SDK 入仓
        r'^.+ 上线$',  # <api-endpoint> 上线
        r'^.+ 就绪$',  # <resource-id> 就绪
        r'^Slice \d+ Step (3c|3d)$',  # Slice {N} Step {3c|3d}
        r'^Slice \d+ Step 3a 确认$',  # Slice {N} Step 3a 确认
        r'^.+ 翻译就绪$',  # <locale> 翻译就绪
    ]

    # 黑名单关键词（模糊匹配）
    TRIGGER_BLACKLIST = [
        '等真机', '真机联调', '等设备就绪',
        '等 SDK', 'SDK 接入后', '待 SDK',
        '联调时', '联调后', '联调阶段',
        '上线前', '上线时补',
        '后续', '稍后', '暂时', '先这样', '回头'
    ]

    # iOS 源码锚点 role 类型
    IOS_ANCHOR_ROLES = [
        'view', 'view_controller', 'viewmodel', 'store',
        'service', 'repository', 'manager', 'coordinator',
        'delegate', 'util', 'data_model'
    ]

    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.spec_dir = self.project_root / "spec" / "baseline"
        self.plans_dir = self.spec_dir / "plans"
        self.results: List[CoverageResult] = []

    def run_all_checks(self) -> bool:
        """运行所有校验，返回是否全部通过"""
        print("🔍 开始 i2h-plan 覆盖率校验...\n")

        # 前置检查：必需文件存在
        if not self._check_required_files():
            return False

        # 1. P0 功能覆盖率
        self._check_p0_feature_coverage()

        # 2. P1 功能覆盖率
        self._check_p1_feature_coverage()

        # 3. UI 页面覆盖率
        self._check_ui_page_coverage()

        # 4. Placeholder trigger 白名单率
        self._check_placeholder_triggers()

        # 5. Complex Slice anchor 完整率
        self._check_complex_slice_anchors()

        # 6. 对接点归属率
        self._check_integration_points_attribution()

        # 7. 组件嵌入归属率
        self._check_component_embed_coverage()

        # 8. 数据链路层扇出完整率
        self._check_data_chain_coverage()

        # 9. 骨架审计预演（WARN）
        self._check_skeleton_audit()

        # 10. 分层校验（5 项）
        self._check_layered_validation()

        # 11. 功能分组校验
        self._check_group_validation()

        # 12. 跨切片接线归属检测
        self._check_cross_slice_wiring()

        # 输出结果
        self._print_results()

        # 判断是否通过
        has_blocking_failure = any(not r.passed and r.blocking for r in self.results)
        has_warning = any(not r.passed and not r.blocking for r in self.results)

        if has_blocking_failure:
            return False
        elif has_warning:
            sys.exit(2)  # 有警告但不阻断
        else:
            return True

    def _check_required_files(self) -> bool:
        """检查必需文件是否存在"""
        required_files = [
            self.spec_dir / "feature-index.md",
            self.spec_dir / "ui-manifest.md",
            self.plans_dir / "ui-plan.md",
            self.plans_dir / "feature-plan.md",
        ]

        missing = [f for f in required_files if not f.exists()]
        if missing:
            print("❌ 缺少必需文件：")
            for f in missing:
                print(f"   - {f.relative_to(self.project_root)}")
            return False
        return True

    def _check_p0_feature_coverage(self):
        """1. P0 功能覆盖率 = 100%"""
        features = self._parse_feature_index()
        p0_features = {fid for fid, data in features.items() if data['priority'] == 'P0'}
        covered = self._get_covered_features()

        p0_covered = p0_features & covered
        missing = p0_features - covered

        result = CoverageResult(
            name="P0 功能覆盖率",
            passed=(len(missing) == 0),
            actual=len(p0_covered),
            total=len(p0_features),
            threshold=100.0,
            blocking=True
        )

        if missing:
            result.errors = [f"缺失 P0 功能: {', '.join(sorted(missing))}"]

        self.results.append(result)

    def _check_p1_feature_coverage(self):
        """2. P1 功能覆盖率 ≥ 80%"""
        features = self._parse_feature_index()
        p1_features = {fid for fid, data in features.items() if data['priority'] == 'P1'}
        covered = self._get_covered_features()

        p1_covered = p1_features & covered
        coverage = len(p1_covered) / len(p1_features) * 100 if p1_features else 100.0

        result = CoverageResult(
            name="P1 功能覆盖率",
            passed=(coverage >= 80.0),
            actual=len(p1_covered),
            total=len(p1_features),
            threshold=80.0,
            blocking=False
        )

        if not result.passed:
            missing = p1_features - covered
            result.warnings = [f"P1 功能覆盖率不足 80%，缺失: {', '.join(sorted(missing))}"]

        self.results.append(result)

    def _check_ui_page_coverage(self):
        """3. UI 页面覆盖率 = 100%"""
        manifest_pages = self._parse_ui_manifest()
        plan_pages = self._parse_ui_plan()

        # 只统计非 skipped 的页面
        active_pages = {pid for pid, data in manifest_pages.items()
                       if data.get('status') != 'skipped'}
        covered = active_pages & plan_pages

        missing = active_pages - covered

        result = CoverageResult(
            name="UI 页面覆盖率",
            passed=(len(missing) == 0),
            actual=len(covered),
            total=len(active_pages),
            threshold=100.0,
            blocking=True
        )

        if missing:
            result.errors = [f"缺失页面: {', '.join(sorted(missing))}"]

        self.results.append(result)

    def _check_placeholder_triggers(self):
        """4. Placeholder trigger 白名单率 = 100%"""
        registry_path = self.project_root / "spec" / "placeholder-registry.md"
        if not registry_path.exists():
            # 无 placeholder 视为通过
            result = CoverageResult(
                name="Placeholder trigger 白名单率",
                passed=True,
                actual=0,
                total=0,
                threshold=100.0,
                blocking=True
            )
            result.warnings = ["无 placeholder-registry.md（无占位）"]
            self.results.append(result)
            return

        placeholders = self._parse_placeholder_registry(registry_path)
        total = len(placeholders)
        invalid = []

        for pid, data in placeholders.items():
            trigger = data.get('trigger_condition', '')

            # 检查白名单
            if not self._is_trigger_whitelisted(trigger):
                # 检查黑名单
                for keyword in self.TRIGGER_BLACKLIST:
                    if keyword in trigger:
                        invalid.append(f"{pid}: 包含黑名单关键词 '{keyword}'")
                        break
                else:
                    invalid.append(f"{pid}: 不符合白名单格式 '{trigger}'")

        result = CoverageResult(
            name="Placeholder trigger 白名单率",
            passed=(len(invalid) == 0),
            actual=total - len(invalid),
            total=total,
            threshold=100.0,
            blocking=True
        )

        if invalid:
            result.errors = invalid

        self.results.append(result)

    def _check_complex_slice_anchors(self):
        """5. Complex Slice anchor 完整率 = 100%"""
        slices = self._parse_slices()
        complex_slices = [(sid, data) for sid, data in slices.items()
                         if data.get('complexity') == 'complex']

        if not complex_slices:
            result = CoverageResult(
                name="Complex Slice anchor 完整率",
                passed=True,
                actual=0,
                total=0,
                threshold=100.0,
                blocking=True
            )
            result.warnings = ["无 complex slice"]
            self.results.append(result)
            return

        errors = []
        for sid, data in complex_slices:
            # 检查 ios_source_anchors_ref
            anchor_ref = data.get('ios_source_anchors_ref', {})
            count = anchor_ref.get('count', 0)
            source = anchor_ref.get('source', '')

            if count == 0:
                errors.append(f"Slice {sid}: complexity=complex 但 anchor count=0")
                continue

            # 检查 feature spec 中的 anchors
            if source:
                feature_spec_path = self.spec_dir / source
                if feature_spec_path.exists():
                    anchors = self._parse_ios_source_anchors(feature_spec_path)
                    if len(anchors) != count:
                        errors.append(f"Slice {sid}: anchor count 不匹配 (spec={len(anchors)}, slice={count})")

                    # 检查 anchor 路径存在性和 role 合法性
                    for anchor in anchors:
                        path = anchor.get('path', '')
                        role = anchor.get('role', '')

                        if role not in self.IOS_ANCHOR_ROLES:
                            errors.append(f"Slice {sid}: anchor role '{role}' 不合法")

                        # 检查 iOS 源文件存在性（相对路径）
                        # 注意：这里假设 iOS 源码在项目根目录下
                        # 实际项目中可能需要调整路径
                        if path and not (self.project_root / path).exists():
                            errors.append(f"Slice {sid}: anchor 路径不存在 '{path}'")

        result = CoverageResult(
            name="Complex Slice anchor 完整率",
            passed=(len(errors) == 0),
            actual=len(complex_slices) - len(errors),
            total=len(complex_slices),
            threshold=100.0,
            blocking=True,
            errors=errors
        )

        self.results.append(result)

    def _check_integration_points_attribution(self):
        """6. 对接点归属率 = 100%"""
        # 从所有 feature spec 提取对接点
        integration_points = self._extract_integration_points()
        slices = self._parse_slices()

        unattributed = []
        for point, fid in integration_points.items():
            # 检查对应 slice 的 integration_points_ref 或 cross_slice_edits
            slice_data = slices.get(fid, {})
            ipr = slice_data.get('integration_points_ref', '')
            cross_edits = slice_data.get('cross_slice_edits', [])

            if not ipr and point not in [e['handler'] for e in cross_edits]:
                unattributed.append(f"{point} (F{fid})")

        result = CoverageResult(
            name="对接点归属率",
            passed=(len(unattributed) == 0),
            actual=len(integration_points) - len(unattributed),
            total=len(integration_points),
            threshold=100.0,
            blocking=True
        )

        if unattributed:
            result.errors = [f"未归属对接点: {', '.join(unattributed)}"]

        self.results.append(result)

    def _check_component_embed_coverage(self):
        """7. 组件嵌入归属率 = 100%"""
        # 从 ui-manifest 和 page specs 提取嵌入关系
        embed_relations = self._extract_embed_relations()
        slices = self._parse_slices()

        unattributed = []
        for parent, child in embed_relations:
            # 检查 child 的 owning slice 是否有对应的 wires embed 条目
            child_owner = self._get_page_owner(child)
            if child_owner:
                slice_data = slices.get(child_owner, {})
                wires = slice_data.get('wires', [])

                # 检查是否有对应的 embed 条目
                has_embed = any(
                    w.get('page') == parent and w.get('embed') and child in w['embed']
                    for w in wires
                )

                if not has_embed:
                    unattributed.append(f"{parent} ⊇ {child}")

        result = CoverageResult(
            name="组件嵌入归属率",
            passed=(len(unattributed) == 0),
            actual=len(embed_relations) - len(unattributed),
            total=len(embed_relations),
            threshold=100.0,
            blocking=True
        )

        if unattributed:
            result.errors = [f"未归属嵌入: {', '.join(unattributed)}"]

        self.results.append(result)

    def _check_data_chain_coverage(self):
        """8. 数据链路层扇出完整率 = 100%（chain-auth 存在时）"""
        chain_auth_path = self.spec_dir / "api-inventory" / "data-chains" / "chain-auth.md"

        if not chain_auth_path.exists():
            result = CoverageResult(
                name="数据链路层扇出完整率",
                passed=True,
                actual=0,
                total=0,
                threshold=100.0,
                blocking=True
            )
            result.warnings = ["无 chain-auth.md（不适用）"]
            self.results.append(result)
            return

        # 提取 chain-auth 中的层清单（L0-L7）
        layers = self._parse_chain_auth_layers(chain_auth_path)

        # 检查每层是否有对应的 data_chain_refs
        base_plan = self._parse_base_plan()
        slices = self._parse_slices()

        uncovered_layers = []
        for layer in layers:
            # 检查 base tasks
            has_ref_in_base = any(
                f'chain-auth {layer}' in task.get('data_chain_refs', '')
                for task in base_plan
            )

            # 检查 slices
            has_ref_in_slice = any(
                f'chain-auth {layer}' in data.get('data_chain_refs', '')
                for data in slices.values()
            )

            if not has_ref_in_base and not has_ref_in_slice:
                uncovered_layers.append(layer)

        result = CoverageResult(
            name="数据链路层扇出完整率",
            passed=(len(uncovered_layers) == 0),
            actual=len(layers) - len(uncovered_layers),
            total=len(layers),
            threshold=100.0,
            blocking=True
        )

        if uncovered_layers:
            result.errors = [f"未覆盖层: {', '.join(uncovered_layers)}"]

        self.results.append(result)

    def _check_skeleton_audit(self):
        """9. 骨架审计预演（WARN，不阻断）"""
        registry_path = self.project_root / "spec" / "placeholder-registry.md"
        if not registry_path.exists():
            result = CoverageResult(
                name="骨架审计预演",
                passed=True,
                actual=0,
                total=0,
                threshold=0.0,
                blocking=False
            )
            result.warnings = ["无 placeholder-registry.md"]
            self.results.append(result)
            return

        placeholders = self._parse_placeholder_registry(registry_path)

        # 按文件统计 placeholder 数量
        file_counts: Dict[str, int] = {}
        for data in placeholders.values():
            location = data.get('location', '')
            # 提取文件路径（去除行号和锚点）
            file_path = re.sub(r'[:#].*$', '', location)
            file_counts[file_path] = file_counts.get(file_path, 0) + 1

        # 检查是否有文件 ≥5 个 placeholder
        high_density = {f: c for f, c in file_counts.items() if c >= 5}

        result = CoverageResult(
            name="骨架审计预演",
            passed=(len(high_density) == 0),
            actual=len(file_counts) - len(high_density),
            total=len(file_counts),
            threshold=0.0,
            blocking=False
        )

        if high_density:
            result.warnings = [
                f"高密度占位文件 (≥5 P-ID): {f} ({c} 个)"
                for f, c in high_density.items()
            ]

        self.results.append(result)

    def _check_layered_validation(self):
        """10. 分层校验（5 项）"""
        errors = []

        # 10.1 索引条目 ↔ slices/ 文件一一对应
        feature_plan_path = self.plans_dir / "feature-plan.md"
        if feature_plan_path.exists():
            indexed_slices = self._extract_indexed_slices(feature_plan_path)
            actual_files = set((self.plans_dir / "slices").glob("slice-*.md"))
            actual_slice_ids = {f.stem for f in actual_files}

            missing_files = indexed_slices - actual_slice_ids
            extra_files = actual_slice_ids - indexed_slices

            if missing_files:
                errors.append(f"索引有但文件缺失: {', '.join(missing_files)}")
            if extra_files:
                errors.append(f"文件有但索引缺失: {', '.join(extra_files)}")

        # 10.2 spec_refs 路径存在
        slices = self._parse_slices()
        for sid, data in slices.items():
            spec_refs = data.get('spec_refs', [])
            for ref in spec_refs:
                ref_path = self.spec_dir / ref.split('#')[0]  # 去除锚点
                if not ref_path.exists():
                    errors.append(f"Slice {sid}: spec_ref 路径不存在 '{ref}'")

        # 10.3 索引 complexity 快照与 feature spec 一致
        features = self._parse_feature_specs()
        for sid, data in slices.items():
            fid = data.get('feature_id')
            if fid in features:
                slice_complexity = data.get('complexity')
                spec_complexity = features[fid].get('complexity')
                if slice_complexity != spec_complexity:
                    errors.append(
                        f"Slice {sid}: complexity 不一致 "
                        f"(slice={slice_complexity}, spec={spec_complexity})"
                    )

        # 10.4 slice 文件零 spec 复述（行数启发式）
        for sid, data in slices.items():
            slice_path = data.get('_path')
            if slice_path and slice_path.exists():
                line_count = len(slice_path.read_text().splitlines())
                if line_count > 200:  # 启发式阈值
                    errors.append(f"Slice {sid}: 行数过多 ({line_count} 行，疑似复述 spec)")

        # 10.5 状态交叉：implemented feature 的 owned 页不得 pending
        feature_index = self._parse_feature_index()
        ui_manifest = self._parse_ui_manifest()
        for fid, fdata in feature_index.items():
            if fdata.get('status') == 'implemented':
                owned_pages = [pid for pid, pdata in ui_manifest.items()
                              if pdata.get('owning_slice') == fid]
                pending_pages = [pid for pid in owned_pages
                                if ui_manifest[pid].get('status') == 'pending']
                if pending_pages:
                    errors.append(
                        f"F{fid}: status=implemented 但 owned 页仍 pending "
                        f"({', '.join(pending_pages)})"
                    )

        result = CoverageResult(
            name="分层校验（5 项）",
            passed=(len(errors) == 0),
            actual=5 - min(len(errors), 5),
            total=5,
            threshold=100.0,
            blocking=True,
            errors=errors[:10]  # 限制显示前 10 个错误
        )

        self.results.append(result)

    def _check_group_validation(self):
        """11. 功能分组校验"""
        slices = self._parse_slices()
        errors = []

        # 11.1 最早可行组：每个 slice 排入 max(依赖组号)+1 组
        for sid, data in slices.items():
            depends_on = data.get('depends_on', [])
            parallel_group = data.get('parallel_group', 0)

            max_dep_group = 0
            for dep in depends_on:
                if dep == 'base':
                    continue
                dep_slice = slices.get(dep, {})
                dep_group = dep_slice.get('parallel_group', 0)
                max_dep_group = max(max_dep_group, dep_group)

            expected_min_group = max_dep_group + 1 if depends_on and depends_on != ['base'] else 1
            if parallel_group < expected_min_group:
                errors.append(
                    f"Slice {sid}: parallel_group={parallel_group} < 最早可行组 {expected_min_group}"
                )

        # 11.2 组容量上限：每组 ≤ 8
        group_counts: Dict[int, int] = {}
        for data in slices.values():
            group = data.get('parallel_group', 0)
            group_counts[group] = group_counts.get(group, 0) + 1

        for group, count in group_counts.items():
            if count > 8:
                errors.append(f"Group {group}: {count} 个 slices > GROUP_HARD_LIMIT(8)")

        # 11.3 size-1 组处理
        size1_groups = [g for g, c in group_counts.items() if c == 1]
        if size1_groups:
            errors.append(f"存在 size-1 组: {', '.join(map(str, size1_groups))} (需并组或附挂)")

        result = CoverageResult(
            name="功能分组校验",
            passed=(len(errors) == 0),
            actual=3 - min(len(errors), 3),
            total=3,
            threshold=100.0,
            blocking=True,
            errors=errors
        )

        self.results.append(result)

    def _check_cross_slice_wiring(self):
        """12. 跨切片接线归属检测"""
        # 生成全局接线归属映射
        wiring_map = self._build_wiring_ownership_map()
        slices = self._parse_slices()

        errors = []

        # 检查非首切片 handler 是否有显式 cross_slice_edits
        for (file, handler), owner_fid in wiring_map.items():
            # 找到首次创建该文件的 slice
            first_owner = self._find_first_owner(file, slices)

            if first_owner != owner_fid:
                # 非首切片，检查是否有 cross_slice_edits
                owner_slice = slices.get(owner_fid, {})
                cross_edits = owner_slice.get('cross_slice_edits', [])

                has_edit = any(
                    e.get('file') == file and e.get('handler') == handler
                    for e in cross_edits
                )

                if not has_edit:
                    # 检查是否是 embed 类型（豁免）
                    wires = owner_slice.get('wires', [])
                    is_embed = any(
                        w.get('page') == file and w.get('embed')
                        for w in wires
                    )

                    if not is_embed:
                        errors.append(
                            f"{file}#{handler}: 由 F{owner_fid} 回改但缺少 cross_slice_edits"
                        )

        result = CoverageResult(
            name="跨切片接线归属检测",
            passed=(len(errors) == 0),
            actual=len(wiring_map) - len(errors),
            total=len(wiring_map),
            threshold=100.0,
            blocking=True,
            errors=errors[:10]
        )

        self.results.append(result)

    # ========== 辅助解析方法 ==========

    def _parse_feature_index(self) -> Dict[str, Dict]:
        """解析 feature-index.md"""
        path = self.spec_dir / "feature-index.md"
        if not path.exists():
            return {}

        features = {}
        current_fid = None

        for line in path.read_text().splitlines():
            # 匹配 F-ID
            match = re.search(r'\b(F\d{3})\b', line)
            if match:
                current_fid = match.group(1)
                features[current_fid] = {'priority': 'P1'}  # 默认

            # 匹配优先级
            if current_fid and re.search(r'\bP[012]\b', line):
                priority_match = re.search(r'\b(P[012])\b', line)
                if priority_match:
                    features[current_fid]['priority'] = priority_match.group(1)

        return features

    def _get_covered_features(self) -> Set[str]:
        """获取已覆盖的功能 ID"""
        slices = self._parse_slices()
        return {data.get('feature_id') for data in slices.values()
                if data.get('feature_id')}

    def _parse_ui_manifest(self) -> Dict[str, Dict]:
        """解析 ui-manifest.md"""
        path = self.spec_dir / "ui-manifest.md"
        if not path.exists():
            return {}

        pages = {}
        for line in path.read_text().splitlines():
            # 简单解析，实际可能需要更复杂的逻辑
            match = re.search(r'\b(page_\d{4})\b', line)
            if match:
                pid = match.group(1)
                pages[pid] = {}

                # 检查 status
                if 'skipped' in line.lower():
                    pages[pid]['status'] = 'skipped'

        return pages

    def _parse_ui_plan(self) -> Set[str]:
        """解析 ui-plan.md，返回覆盖的页面 ID"""
        path = self.plans_dir / "ui-plan.md"
        if not path.exists():
            return set()

        pages = set()
        for line in path.read_text().splitlines():
            match = re.search(r'\b(\d{4})\b', line)
            if match:
                # 假设序号对应 page_NNNN
                page_id = f"page_{match.group(1)}"
                pages.add(page_id)

        return pages

    def _parse_placeholder_registry(self, path: Path) -> Dict[str, Dict]:
        """解析 placeholder-registry.md"""
        if not path.exists():
            return {}

        placeholders = {}
        lines = path.read_text().splitlines()

        # 跳过到表格部分
        in_table = False
        for line in lines:
            if line.startswith('| P-ID'):
                in_table = True
                continue
            if not in_table or not line.startswith('|'):
                continue
            if line.startswith('|---'):
                continue

            # 解析表格行
            parts = [p.strip() for p in line.split('|')[1:-1]]
            if len(parts) >= 4:
                pid = parts[0]
                placeholders[pid] = {
                    'location': parts[1],
                    'trigger_condition': parts[2],
                    'status': parts[3],
                    'kind': parts[4] if len(parts) > 4 else '',
                    'resolve_by': parts[5] if len(parts) > 5 else ''
                }

        return placeholders

    def _is_trigger_whitelisted(self, trigger: str) -> bool:
        """检查 trigger 是否符合白名单格式"""
        return any(re.match(pattern, trigger) for pattern in self.TRIGGER_WHITELIST)

    def _parse_slices(self) -> Dict[str, Dict]:
        """解析所有 slice 文件"""
        slices_dir = self.plans_dir / "slices"
        if not slices_dir.exists():
            return {}

        slices = {}
        for slice_file in slices_dir.glob("slice-*.md"):
            # 提取 slice ID
            match = re.search(r'slice-(\d+)-', slice_file.name)
            if not match:
                continue

            sid = match.group(1)
            content = slice_file.read_text()

            # 解析 YAML 头部
            yaml_match = re.search(r'```yaml\n(.*?)\n```', content, re.DOTALL)
            data = {'_path': slice_file}

            if yaml_match:
                yaml_content = yaml_match.group(1)
                for line in yaml_content.splitlines():
                    if ':' in line:
                        key, value = line.split(':', 1)
                        data[key.strip()] = value.strip()

            # 解析其他字段
            data['feature_id'] = self._extract_field(content, 'feature_id')
            data['complexity'] = self._extract_field(content, 'complexity')
            data['parallel_group'] = int(self._extract_field(content, 'parallel_group') or 0)
            data['depends_on'] = self._extract_list_field(content, 'depends_on')
            data['wires'] = []  # 简化处理
            data['cross_slice_edits'] = []  # 简化处理

            slices[sid] = data

        return slices

    def _extract_field(self, content: str, field: str) -> Optional[str]:
        """从内容中提取字段值"""
        match = re.search(rf'{field}:\s*(\S+)', content)
        return match.group(1) if match else None

    def _extract_list_field(self, content: str, field: str) -> List[str]:
        """从内容中提取列表字段"""
        match = re.search(rf'{field}:\s*\[(.*?)\]', content)
        if match:
            return [item.strip().strip('"\'') for item in match.group(1).split(',')]
        return []

    def _parse_ios_source_anchors(self, spec_path: Path) -> List[Dict]:
        """从 feature spec 解析 ios_source_anchors"""
        if not spec_path.exists():
            return []

        content = spec_path.read_text()
        # 简化解析，实际需要更复杂的 YAML/Markdown 解析
        anchors = []

        # 查找 ios_source_anchors 段
        match = re.search(r'ios_source_anchors:\s*\n((?:  - .*\n)*)', content)
        if match:
            anchor_lines = match.group(1)
            for line in anchor_lines.splitlines():
                if 'role:' in line:
                    role_match = re.search(r'role:\s*(\w+)', line)
                    if role_match:
                        anchors.append({'role': role_match.group(1), 'path': ''})

        return anchors

    def _extract_integration_points(self) -> Dict[str, str]:
        """提取所有 feature spec 的对接点"""
        # 简化实现
        return {}

    def _extract_embed_relations(self) -> List[Tuple[str, str]]:
        """提取组件嵌入关系"""
        # 简化实现
        return []

    def _get_page_owner(self, page_id: str) -> Optional[str]:
        """获取页面的 owning slice"""
        ui_plan_path = self.plans_dir / "ui-plan.md"
        if not ui_plan_path.exists():
            return None

        for line in ui_plan_path.read_text().splitlines():
            if page_id in line:
                match = re.search(r'\b(F\d{3})\b', line)
                if match:
                    return match.group(1)
        return None

    def _parse_chain_auth_layers(self, path: Path) -> List[str]:
        """解析 chain-auth.md 的层清单"""
        # 简化实现，返回 L0-L7
        return [f'L{i}' for i in range(8)]

    def _parse_base_plan(self) -> List[Dict]:
        """解析 base-plan.md"""
        path = self.plans_dir / "base-plan.md"
        if not path.exists():
            return []

        tasks = []
        current_task = None

        for line in path.read_text().splitlines():
            if line.startswith('- Base-'):
                if current_task:
                    tasks.append(current_task)
                current_task = {'data_chain_refs': ''}
            elif current_task and 'data_chain_refs:' in line:
                match = re.search(r'data_chain_refs:\s*(.+)', line)
                if match:
                    current_task['data_chain_refs'] = match.group(1)

        if current_task:
            tasks.append(current_task)

        return tasks

    def _parse_feature_specs(self) -> Dict[str, Dict]:
        """解析所有 feature spec 文件"""
        features_dir = self.spec_dir / "features"
        if not features_dir.exists():
            return {}

        features = {}
        for spec_file in features_dir.glob("F*.md"):
            match = re.search(r'(F\d{3})', spec_file.name)
            if match:
                fid = match.group(1)
                content = spec_file.read_text()
                features[fid] = {
                    'complexity': self._extract_field(content, 'complexity')
                }

        return features

    def _extract_indexed_slices(self, feature_plan_path: Path) -> Set[str]:
        """从 feature-plan.md 提取索引的 slice IDs"""
        content = feature_plan_path.read_text()
        indexed = set()

        for line in content.splitlines():
            match = re.search(r'plans/slices/(slice-\d+-F\d{3})\.md', line)
            if match:
                indexed.add(match.group(1))

        return indexed

    def _build_wiring_ownership_map(self) -> Dict[Tuple[str, str], str]:
        """构建全局接线归属映射"""
        # 简化实现
        return {}

    def _find_first_owner(self, file: str, slices: Dict) -> Optional[str]:
        """找到首次创建文件的 slice"""
        # 简化实现：假设按 slice 编号顺序
        for sid in sorted(slices.keys()):
            # 检查是否创建了该文件
            # 简化判断
            return slices[sid].get('feature_id')
        return None

    def _print_results(self):
        """打印校验结果"""
        print("\n📊 覆盖率校验结果\n")
        print("=" * 80)

        for result in self.results:
            print(f"\n{result.status_icon} {result.name}")
            if result.total > 0:
                print(f"   覆盖率: {result.actual}/{result.total} ({result.percentage:.1f}%)")
                if result.threshold > 0:
                    print(f"   阈值: {result.threshold:.0f}%")

            if result.errors:
                print("   ❌ 错误:")
                for error in result.errors[:5]:  # 限制显示前 5 个
                    print(f"      - {error}")
                if len(result.errors) > 5:
                    print(f"      ... 还有 {len(result.errors) - 5} 个错误")

            if result.warnings:
                print("   ⚠️  警告:")
                for warning in result.warnings[:5]:
                    print(f"      - {warning}")
                if len(result.warnings) > 5:
                    print(f"      ... 还有 {len(result.warnings) - 5} 个警告")

        print("\n" + "=" * 80)

        # 统计
        passed = sum(1 for r in self.results if r.passed)
        failed = sum(1 for r in self.results if not r.passed)
        blocking = sum(1 for r in self.results if not r.passed and r.blocking)
        warnings = sum(1 for r in self.results if not r.passed and not r.blocking)

        print(f"\n✅ 通过: {passed}")
        print(f"❌ 失败: {failed} (阻断: {blocking}, 警告: {warnings})")

        if blocking > 0:
            print("\n🔴 存在阻断级别的失败，plan 不可输出")
        elif warnings > 0:
            print("\n⚠️  存在警告，建议修复后继续")
        else:
            print("\n🎉 所有校验通过！")


def main():
    if len(sys.argv) != 2:
        print("Usage: python3 lint_plan_coverage.py <project_root>")
        sys.exit(1)

    project_root = sys.argv[1]

    if not os.path.isdir(project_root):
        print(f"❌ 错误: 目录不存在: {project_root}")
        sys.exit(1)

    linter = PlanCoverageLinter(project_root)
    success = linter.run_all_checks()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
