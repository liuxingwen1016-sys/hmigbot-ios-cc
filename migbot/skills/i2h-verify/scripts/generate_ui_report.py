#!/usr/bin/env python3
"""
UI 对比报告生成工具

根据对比结果生成详细的 Markdown 报告
"""
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict


class UIReportGenerator:
    """UI 报告生成器"""

    def __init__(self, results_file: str, output_file: str):
        self.results_file = Path(results_file)
        self.output_file = Path(output_file)
        self.results = None

    def load_results(self) -> bool:
        """加载对比结果"""
        try:
            with open(self.results_file, encoding='utf-8') as f:
                self.results = json.load(f)
            return True
        except Exception as e:
            print(f"错误: 无法加载结果文件: {e}", file=sys.stderr)
            return False

    def generate_report(self) -> str:
        """生成 Markdown 报告"""
        if not self.results:
            return "# 错误\n\n无法加载对比结果"

        data = self.results
        summary = data.get("summary", {})
        comparisons = data.get("comparisons", [])

        # 开始生成报告
        report = f"""# UI 对比验证报告

生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## 执行状态
✅ 已完成 - 双端自动截图对比

## 总体统计

- 对比页面数: {summary.get('total', 0)}
- 高度匹配 (≥95%): {summary.get('matched', 0)} 页
- 良好 (85-95%): {summary.get('similar', 0)} 页
- 差异较大 (<85%): {summary.get('different', 0)} 页
- HarmonyOS 缺失: {summary.get('missing_harmonyos', 0)} 页
- 平均相似度: {summary.get('avg_similarity', 0):.1f}%
"""

        # 计算匹配率
        total = summary.get('total', 0)
        matched = summary.get('matched', 0)
        if total > 0:
            match_rate = matched / total * 100
            report += f"- 匹配率: {match_rate:.1f}%\n"

        report += "\n## 分页对比结果\n\n"

        # 按相似度排序
        sorted_comparisons = sorted(
            comparisons,
            key=lambda x: x.get('similarity', 0),
            reverse=True
        )

        for comp in sorted_comparisons:
            page = comp.get('page', 'Unknown')
            similarity = comp.get('similarity', 0)
            status = comp.get('status', 'unknown')
            ios_path = comp.get('ios_path', '')
            hos_path = comp.get('harmonyos_path', '')

            report += f"### {page}\n"

            # 状态图标
            if status == 'match':
                icon = "✅"
                level = "高度匹配"
            elif status == 'similar':
                icon = "⚠️"
                level = "良好"
            elif status == 'different':
                icon = "❌"
                level = "差异较大"
            elif status == 'missing_harmonyos':
                icon = "❓"
                level = "HarmonyOS 截图缺失"
            else:
                icon = "❌"
                level = "对比出错"

            report += f"{icon} **相似度: {similarity:.1f}%** ({level})\n\n"

            # 详细信息
            report += f"- iOS: `{ios_path}`\n"
            report += f"- HarmonyOS: `{hos_path}`\n"

            if status == 'missing_harmonyos':
                report += "\n**问题**: HarmonyOS 截图缺失\n\n"
                report += "**可能原因**:\n"
                report += "- 页面可能未实现\n"
                report += "- 页面无法访问\n"
                report += "- 截图失败\n\n"
                report += "**建议**: 检查页面是否已正确迁移\n\n"
            elif status == 'error':
                error_msg = comp.get('error', '未知错误')
                report += f"\n**错误**: {error_msg}\n\n"
            else:
                distance = comp.get('distance', 0)
                report += f"- 汉明距离: {distance}\n\n"

                # 差异分析
                if similarity >= 95:
                    report += "**分析**: UI 高度一致，无明显差异\n\n"
                elif similarity >= 85:
                    report += "**差异分析**: 轻微差异，可能是字体、间距等细节问题\n\n"
                    report += "**建议**: \n"
                    report += "- 检查字体大小和间距设置\n"
                    report += "- 确认颜色值完全一致\n"
                    report += "- 调整布局细节\n\n"
                else:
                    report += "**差异分析**: 差异较大，需要重点关注\n\n"
                    report += "**建议**:\n"
                    report += "- 检查页面布局结构是否一致\n"
                    report += "- 确认所有元素都已正确渲染\n"
                    report += "- 对比具体差异点并逐项修复\n\n"

            report += "---\n\n"

        # 总体评估
        avg = summary.get('avg_similarity', 0)
        report += "## 总体评估\n\n"

        if avg >= 95:
            report += f"""✅ **优秀** - UI 高度一致

平均相似度达到 {avg:.1f}%，说明 HarmonyOS 版本的 UI 还原度非常高。

**下一步**: 可以继续其他验证项（CHECK-4 单元测试等）
"""
        elif avg >= 85:
            report += f"""⚠️  **良好** - 有轻微差异

平均相似度 {avg:.1f}%，整体还原度良好，但存在一些细节差异需要优化。

**建议**:
- 检查字体大小和间距
- 确认颜色值完全一致
- 调整布局细节

**下一步**: 可以选择：
1. 接受当前结果，继续 CHECK-4
2. 优化 UI 差异后重新验证
"""
        else:
            report += f"""❌ **需改进** - 差异较大

平均相似度仅 {avg:.1f}%，需要重点关注 UI 一致性。

**优先改进页面**:
"""
            for comp in sorted_comparisons:
                if comp.get('similarity', 0) < 85:
                    report += f"- **{comp.get('page', 'Unknown')}**: {comp.get('similarity', 0):.1f}%\n"

            report += "\n**下一步**: 建议优化 UI 差异后再继续后续验证\n"

        # CHECK-3 判定
        report += "\n## CHECK-3 判定\n\n"

        if avg >= 95:
            report += "- **状态**: PASS\n"
            report += f"- **平均相似度**: {avg:.1f}%\n"
            report += "- **结论**: UI 验证通过\n"
        elif avg >= 85:
            report += "- **状态**: FAIL-visual（建议项）\n"
            report += f"- **平均相似度**: {avg:.1f}%\n"
            report += "- **结论**: 存在轻微视觉差异，不影响功能\n"
        else:
            report += "- **状态**: FAIL-functional\n"
            report += f"- **平均相似度**: {avg:.1f}%\n"
            report += "- **结论**: 差异较大，需要修复\n"

        if summary.get('missing_harmonyos', 0) > 0:
            report += f"\n⚠️  **警告**: 有 {summary.get('missing_harmonyos', 0)} 个页面缺少 HarmonyOS 截图\n"

        # 证据
        report += "\n## 截图证据\n\n"
        report += f"- **iOS 截图**: `{data.get('ios_dir', '')}`\n"
        report += f"- **HarmonyOS 截图**: `{data.get('harmonyos_dir', '')}`\n"
        report += f"- **对比结果**: `{self.results_file}`\n"

        report += "\n---\n\n"
        report += f"**报告版本**: v1.0  \n"
        report += f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  \n"

        return report

    def save_report(self, report: str) -> bool:
        """保存报告"""
        try:
            # 确保输出目录存在
            self.output_file.parent.mkdir(parents=True, exist_ok=True)

            with open(self.output_file, 'w', encoding='utf-8') as f:
                f.write(report)
            return True
        except Exception as e:
            print(f"错误: 无法保存报告: {e}", file=sys.stderr)
            return False

    def generate(self) -> bool:
        """生成并保存报告"""
        if not self.load_results():
            return False

        report = self.generate_report()

        if not self.save_report(report):
            return False

        return True


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description='UI 对比报告生成工具')
    parser.add_argument('results_file', help='对比结果 JSON 文件')
    parser.add_argument('output_file', help='输出报告文件路径')
    parser.add_argument('--print', action='store_true', help='打印报告到控制台')

    args = parser.parse_args()

    generator = UIReportGenerator(args.results_file, args.output_file)

    if not generator.load_results():
        sys.exit(1)

    report = generator.generate_report()

    if args.print:
        print(report)

    if generator.save_report(report):
        print(f"✅ 报告已生成: {args.output_file}")

        # 打印摘要
        summary = generator.results.get("summary", {})
        avg = summary.get("avg_similarity", 0)
        print(f"   总体相似度: {avg:.1f}%")
        print(f"   匹配页面: {summary.get('matched', 0)}/{summary.get('total', 0)}")

        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == '__main__':
    main()
