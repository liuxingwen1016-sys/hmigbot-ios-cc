#!/usr/bin/env python3
"""
gate-release 迁移放行项读取工具

读取并处理 i2h-spec 的门禁放行项
"""
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional


class GateReleaseReader:
    """门禁放行项读取器"""

    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.verify_focus_file = self.project_root / "spec/gate-release/verify-focus.json"
        self.open_findings_file = self.project_root / "spec/.i2h/open-findings.json"

    def read_verify_focus(self) -> Optional[Dict]:
        """读取验证焦点（迁移放行项）"""
        if not self.verify_focus_file.exists():
            return None

        try:
            with open(self.verify_focus_file, encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"警告: 无法读取 verify-focus.json: {e}", file=sys.stderr)
            return None

    def read_open_findings(self) -> Optional[Dict]:
        """读取开放问题"""
        if not self.open_findings_file.exists():
            return None

        try:
            with open(self.open_findings_file, encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"警告: 无法读取 open-findings.json: {e}", file=sys.stderr)
            return None

    def check_blocking_findings(self) -> bool:
        """检查是否有上游 blocking findings"""
        open_findings = self.read_open_findings()
        if not open_findings:
            return False

        findings = open_findings.get('findings', [])
        for finding in findings:
            if finding.get('severity') == 'blocking' and \
               finding.get('owner_stage') != 'verify':
                return True

        return False

    def get_verify_stage_findings(self) -> List[Dict]:
        """获取 verify 阶段负责的 findings"""
        open_findings = self.read_open_findings()
        if not open_findings:
            return []

        findings = open_findings.get('findings', [])
        return [f for f in findings if f.get('owner_stage') == 'verify']

    def expand_verification_scope(self, base_pages: List[str]) -> List[str]:
        """扩展验证范围（纳入放行项涉及的页面）"""
        verify_focus = self.read_verify_focus()
        if not verify_focus:
            return base_pages

        pages = set(base_pages)
        items = verify_focus.get('items', [])

        for item in items:
            item_pages = item.get('pages', [])
            pages.update(item_pages)

        return sorted(list(pages))

    def generate_verification_table(self, results: Dict) -> str:
        """生成迁移放行项核实表格"""
        verify_focus = self.read_verify_focus()
        if not verify_focus:
            return ""

        items = verify_focus.get('items', [])
        if not items:
            return ""

        # 生成表格
        table = """## 迁移放行项核实

来源 `spec/gate-release/verify-focus.json`；每条一行，不得省略。

| 决策 | 类型 | 门禁 | 核实问题 | 结论 | 证据 |
|---|---|---|---|---|---|
"""

        for item in items:
            decision_id = item.get('decision_id', 'N/A')
            item_type = item.get('type', 'unknown')
            gate = item.get('gate', 'N/A')
            question = item.get('verify_question', '')
            finding_ref = item.get('finding_ref', '')

            # 从 results 中查找对应页面的验证结果
            pages = item.get('pages', [])
            conclusion = self._determine_conclusion(pages, results)
            evidence = self._get_evidence(pages, results)

            # 类型映射
            type_map = {
                'tool_gap': '工具缺口',
                'unmet_release': '未达标放行',
                'stage_undecidable': '阶段不可判定'
            }
            item_type_cn = type_map.get(item_type, item_type)

            table += f"| {decision_id} | {item_type_cn} | {gate} | {question} | {conclusion} | {evidence} |\n"

        # 添加汇总
        total = len(items)
        verified_ok = len([i for i in items if self._determine_conclusion(i.get('pages', []), results) == '已核实正常'])
        confirmed_defect = len([i for i in items if self._determine_conclusion(i.get('pages', []), results) == '确认缺陷'])
        not_covered = len([i for i in items if self._determine_conclusion(i.get('pages', []), results) == '未覆盖'])

        table += f"""
**汇总**:
- 总放行项: {total}
- 已核实正常: {verified_ok}
- 确认缺陷: {confirmed_defect}
- 未覆盖: {not_covered}
"""

        return table

    def _determine_conclusion(self, pages: List[str], results: Dict) -> str:
        """判定结论"""
        if not pages:
            return '未覆盖'

        # 检查这些页面的验证结果
        comparisons = results.get('comparisons', [])

        page_results = {}
        for comp in comparisons:
            if comp['page'] in pages:
                page_results[comp['page']] = comp

        if not page_results:
            return '未覆盖'

        # 判定逻辑
        all_high_similarity = True
        has_missing = False
        has_low_similarity = False

        for page in pages:
            if page not in page_results:
                has_missing = True
                continue

            result = page_results[page]
            similarity = result.get('similarity', 0)
            status = result.get('status', 'unknown')

            if status == 'missing_harmonyos':
                has_missing = True
            elif similarity < 85:
                has_low_similarity = True
            elif similarity < 95:
                all_high_similarity = False

        if has_missing or has_low_similarity:
            return '确认缺陷'
        elif all_high_similarity:
            return '已核实正常'
        else:
            return '已核实正常'  # 轻微差异也算正常

    def _get_evidence(self, pages: List[str], results: Dict) -> str:
        """获取证据链接"""
        if not pages:
            return '-'

        # 引用 UI 对比报告
        return 'spec/verify/ui-comparison.md'

    def get_summary(self) -> Dict:
        """获取完整摘要"""
        verify_focus = self.read_verify_focus()
        open_findings = self.read_open_findings()

        summary = {
            'has_verify_focus': verify_focus is not None,
            'has_open_findings': open_findings is not None,
            'verify_focus_items': len(verify_focus.get('items', [])) if verify_focus else 0,
            'open_findings_count': len(open_findings.get('findings', [])) if open_findings else 0,
            'blocking_findings': self.check_blocking_findings(),
            'verify_stage_findings': len(self.get_verify_stage_findings())
        }

        return summary


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description='gate-release 迁移放行项读取工具')
    parser.add_argument('project_root', nargs='?', default='.',
                       help='项目根目录 (默认: 当前目录)')
    parser.add_argument('--check-blocking', action='store_true',
                       help='检查是否有上游 blocking findings')
    parser.add_argument('--expand-pages', metavar='PAGE',
                       nargs='*', help='扩展页面列表')
    parser.add_argument('--summary', action='store_true',
                       help='显示摘要信息')

    args = parser.parse_args()

    reader = GateReleaseReader(args.project_root)

    if args.check_blocking:
        has_blocking = reader.check_blocking_findings()
        if has_blocking:
            print("❌ 发现上游 blocking findings，拒绝开工", file=sys.stderr)
            sys.exit(1)
        else:
            print("✅ 无上游 blocking findings")
            sys.exit(0)

    elif args.expand_pages is not None:
        expanded = reader.expand_verification_scope(args.expand_pages)
        for page in expanded:
            print(page)

    elif args.summary:
        summary = reader.get_summary()
        print(json.dumps(summary, indent=2, ensure_ascii=False))

    else:
        # 默认：显示 verify-focus 内容
        verify_focus = reader.read_verify_focus()
        if verify_focus:
            print(json.dumps(verify_focus, indent=2, ensure_ascii=False))
        else:
            print("未找到 verify-focus.json", file=sys.stderr)
            sys.exit(1)


if __name__ == '__main__':
    main()
