#!/usr/bin/env python3
"""
iOS 静态分析工具

执行 15 项静态分析检查（6 通用 + 9 iOS 特有）
"""
import subprocess
import re
import json
import sys
from pathlib import Path
from typing import List, Dict, Tuple, Optional


# 检查规则定义
STATIC_CHECKS = [
    # 通用检查（6 项）
    {
        'id': 'COMMON.ANY_TYPE',
        'pattern': r'\bany\b',
        'level': 'ERROR',
        'message': '使用 any 类型，ArkTS 强类型要求不允许',
        'context_check': lambda line: 'any' in line and ':' in line
    },
    {
        'id': 'COMMON.OLD_OHOS_IMPORT',
        'pattern': r'@ohos\.',
        'level': 'WARN',
        'message': '使用旧的 @ohos.* 导入，建议迁移到新 API',
        'context_check': lambda line: 'import' in line or 'from' in line
    },
    {
        'id': 'COMMON.SQL_CONCAT',
        'pattern': r'(SELECT|INSERT|UPDATE|DELETE|WHERE).*\+.*["\']',
        'level': 'ERROR',
        'message': 'SQL 拼接，存在 SQL 注入风险',
        'context_check': lambda line: any(kw in line.upper() for kw in ['SELECT', 'INSERT', 'UPDATE', 'DELETE'])
    },
    {
        'id': 'COMMON.AS_ASSERTION',
        'pattern': r'\bas\s+\w+',
        'level': 'WARN',
        'message': '使用 as 类型断言，存在类型安全风险',
        'context_check': lambda line: ' as ' in line
    },
    {
        'id': 'COMMON.EVAL_CALL',
        'pattern': r'\beval\s*\(',
        'level': 'ERROR',
        'message': '使用 eval()，存在动态执行风险',
        'context_check': lambda line: 'eval(' in line
    },
    {
        'id': 'COMMON.ABOUT_TO_APPEAR_ROUTE',
        'pattern': r'aboutToAppear.*pathInfo',
        'level': 'ERROR',
        'message': '在 aboutToAppear 中获取路由参数，生命周期错误',
        'context_check': lambda line: 'aboutToAppear' in line or 'pathInfo' in line
    },

    # iOS 特有检查（9 项）
    {
        'id': 'IOS.FORCE_UNWRAP',
        'pattern': r'\w+!\.',
        'level': 'WARN',
        'message': '使用强制解包 !，可能导致运行时崩溃',
        'context_check': lambda line: '!.' in line or '!' in line
    },
    {
        'id': 'IOS.ESCAPING_CLOSURE',
        'pattern': r'@escaping',
        'level': 'WARN',
        'message': 'Swift 闭包逃逸标记，ArkTS 不需要',
        'context_check': lambda line: '@escaping' in line
    },
    {
        'id': 'IOS.WEAK_UNOWNED',
        'pattern': r'\b(weak|unowned)\b',
        'level': 'WARN',
        'message': 'Swift 内存管理关键字，ArkTS 自动管理',
        'context_check': lambda line: 'weak' in line or 'unowned' in line
    },
    {
        'id': 'IOS.OBJC_INTEROP',
        'pattern': r'@objc',
        'level': 'WARN',
        'message': 'Swift/OC 互操作标记，迁移遗留',
        'context_check': lambda line: '@objc' in line
    },
    {
        'id': 'IOS.AVAILABLE_CHECK',
        'pattern': r'(#available|@available)',
        'level': 'WARN',
        'message': 'iOS 版本检查，HarmonyOS 不适用',
        'context_check': lambda line: 'available' in line
    },
    {
        'id': 'IOS.DISPATCH_QUEUE',
        'pattern': r'DispatchQueue',
        'level': 'ERROR',
        'message': 'GCD 调度队列，必须改为 TaskPool/Worker',
        'context_check': lambda line: 'DispatchQueue' in line
    },
    {
        'id': 'IOS.NOTIFICATION_CENTER',
        'pattern': r'NotificationCenter',
        'level': 'WARN',
        'message': 'iOS 通知中心，需要改为 Emitter',
        'context_check': lambda line: 'NotificationCenter' in line
    },
    {
        'id': 'IOS.USER_DEFAULTS',
        'pattern': r'UserDefaults',
        'level': 'ERROR',
        'message': 'iOS 本地存储，必须改为 Preferences',
        'context_check': lambda line: 'UserDefaults' in line
    },
    {
        'id': 'IOS.UI_FRAMEWORK',
        'pattern': r'import\s+(UIKit|SwiftUI)',
        'level': 'ERROR',
        'message': 'iOS UI 框架，迁移未完成',
        'context_check': lambda line: 'import' in line and ('UIKit' in line or 'SwiftUI' in line)
    }
]


class IOSStaticAnalyzer:
    """iOS 静态分析器"""

    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.findings = []

    def is_comment_or_string(self, line: str, match_pos: int) -> bool:
        """判断匹配位置是否在注释或字符串中"""
        # 检查是否在注释中
        if '//' in line:
            comment_pos = line.find('//')
            if match_pos >= comment_pos:
                return True

        if '/*' in line or '*/' in line:
            return True

        # 简单检查是否在字符串中（不完美但足够）
        before_match = line[:match_pos]
        single_quotes = before_match.count("'")
        double_quotes = before_match.count('"')

        # 如果引号数量为奇数，可能在字符串中
        if single_quotes % 2 == 1 or double_quotes % 2 == 1:
            return True

        return False

    def search_pattern(self, pattern: str) -> List[Tuple[str, int, str]]:
        """使用 rg 搜索模式"""
        try:
            # 使用 rg 搜索
            result = subprocess.run(
                ['rg', '-n', '--no-heading', '-g', '*.ets', pattern, str(self.project_root)],
                capture_output=True,
                text=True,
                timeout=30
            )

            matches = []
            for line in result.stdout.strip().split('\n'):
                if not line:
                    continue

                # 解析 rg 输出：文件:行号:内容
                parts = line.split(':', 2)
                if len(parts) >= 3:
                    file_path = parts[0]
                    line_num = int(parts[1])
                    content = parts[2]
                    matches.append((file_path, line_num, content))

            return matches

        except subprocess.TimeoutExpired:
            print(f"搜索超时: {pattern}", file=sys.stderr)
            return []
        except Exception as e:
            print(f"搜索失败: {pattern}, {e}", file=sys.stderr)
            return []

    def verify_match(self, check: Dict, file_path: str, line_num: int, content: str) -> bool:
        """验证匹配是否为真实违规"""
        # 检查是否在注释或字符串中
        pattern = check['pattern']
        match = re.search(pattern, content)
        if match:
            match_pos = match.start()
            if self.is_comment_or_string(content, match_pos):
                return False

        # 使用自定义的上下文检查
        if 'context_check' in check:
            return check['context_check'](content)

        return True

    def analyze_check(self, check: Dict) -> List[Dict]:
        """执行单个检查"""
        matches = self.search_pattern(check['pattern'])
        findings = []

        for file_path, line_num, content in matches:
            # 验证匹配
            if not self.verify_match(check, file_path, line_num, content):
                continue

            # 记录违规
            findings.append({
                'rule_id': check['id'],
                'file': file_path,
                'line': line_num,
                'level': check['level'],
                'message': check['message'],
                'snippet': content.strip()
            })

        return findings

    def analyze_all(self) -> Dict:
        """执行所有检查"""
        results = {
            'project_root': str(self.project_root),
            'total_checks': len(STATIC_CHECKS),
            'checks': [],
            'findings': [],
            'summary': {
                'error_count': 0,
                'warn_count': 0,
                'total_violations': 0
            }
        }

        print(f"🔍 开始静态分析: {self.project_root}")
        print(f"   检查规则: {len(STATIC_CHECKS)} 项")
        print()

        for check in STATIC_CHECKS:
            print(f"   检查: {check['id']}...", end=' ')
            findings = self.analyze_check(check)

            check_result = {
                'rule_id': check['id'],
                'level': check['level'],
                'pattern': check['pattern'],
                'message': check['message'],
                'violations': len(findings)
            }

            results['checks'].append(check_result)
            results['findings'].extend(findings)

            if findings:
                print(f"❌ {len(findings)} 个违规")
            else:
                print(f"✅ 通过")

        # 统计
        results['summary']['total_violations'] = len(results['findings'])
        results['summary']['error_count'] = len([f for f in results['findings'] if f['level'] == 'ERROR'])
        results['summary']['warn_count'] = len([f for f in results['findings'] if f['level'] == 'WARN'])

        return results

    def print_summary(self, results: Dict):
        """打印分析摘要"""
        print("\n" + "=" * 60)
        print("静态分析结果")
        print("=" * 60)

        summary = results['summary']
        print(f"\n📊 总体统计:")
        print(f"  检查规则:   {results['total_checks']} 项")
        print(f"  总违规数:   {summary['total_violations']} 个")
        print(f"  ERROR:      {summary['error_count']} 个")
        print(f"  WARN:       {summary['warn_count']} 个")

        # 按级别分组
        errors = [f for f in results['findings'] if f['level'] == 'ERROR']
        warns = [f for f in results['findings'] if f['level'] == 'WARN']

        # ERROR 详情
        if errors:
            print(f"\n❌ ERROR 详情 ({len(errors)} 个):")
            for i, finding in enumerate(errors[:10], 1):  # 只显示前 10 个
                print(f"\n  {i}. {finding['rule_id']}")
                print(f"     文件: {finding['file']}:{finding['line']}")
                print(f"     问题: {finding['message']}")
                print(f"     代码: {finding['snippet']}")

            if len(errors) > 10:
                print(f"\n  ... 还有 {len(errors) - 10} 个 ERROR")

        # WARN 摘要
        if warns:
            print(f"\n⚠️  WARN 摘要 ({len(warns)} 个):")
            # 按规则分组
            warn_by_rule = {}
            for warn in warns:
                rule_id = warn['rule_id']
                if rule_id not in warn_by_rule:
                    warn_by_rule[rule_id] = []
                warn_by_rule[rule_id].append(warn)

            for rule_id, rule_warns in warn_by_rule.items():
                print(f"  - {rule_id}: {len(rule_warns)} 个")
                # 显示第一个示例
                first = rule_warns[0]
                print(f"    示例: {first['file']}:{first['line']}")

        # 判定
        print("\n" + "=" * 60)
        if summary['error_count'] == 0:
            print("✅ CHECK-1 判定: PASS (ERROR 为 0)")
        else:
            print(f"❌ CHECK-1 判定: FAIL (有 {summary['error_count']} 个 ERROR)")
        print("=" * 60)


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description='iOS 静态分析工具')
    parser.add_argument('project_root', help='项目根目录')
    parser.add_argument('--json', action='store_true', help='输出 JSON 格式')
    parser.add_argument('--output', '-o', help='输出文件路径')
    parser.add_argument('--verbose', '-v', action='store_true', help='详细输出')

    args = parser.parse_args()

    # 检查 rg 是否可用
    try:
        subprocess.run(['which', 'rg'], capture_output=True, check=True)
    except subprocess.CalledProcessError:
        print("错误: 需要安装 ripgrep (rg)", file=sys.stderr)
        print("安装: brew install ripgrep", file=sys.stderr)
        sys.exit(1)

    # 执行分析
    analyzer = IOSStaticAnalyzer(args.project_root)
    results = analyzer.analyze_all()

    # 输出结果
    if args.json:
        output = json.dumps(results, indent=2, ensure_ascii=False)
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(output)
            print(f"✅ 结果已保存到: {args.output}")
        else:
            print(output)
    else:
        analyzer.print_summary(results)

        if args.output:
            # 生成文本报告
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write("# 静态分析报告\n\n")
                f.write(f"项目: {results['project_root']}\n\n")
                f.write(f"## 总体统计\n\n")
                f.write(f"- 检查规则: {results['total_checks']} 项\n")
                f.write(f"- 总违规数: {results['summary']['total_violations']} 个\n")
                f.write(f"- ERROR: {results['summary']['error_count']} 个\n")
                f.write(f"- WARN: {results['summary']['warn_count']} 个\n\n")

                for finding in results['findings']:
                    f.write(f"## {finding['level']}: {finding['rule_id']}\n\n")
                    f.write(f"- 文件: {finding['file']}:{finding['line']}\n")
                    f.write(f"- 问题: {finding['message']}\n")
                    f.write(f"- 代码: `{finding['snippet']}`\n\n")

            print(f"✅ 报告已保存到: {args.output}")

    # 返回状态码
    sys.exit(0 if results['summary']['error_count'] == 0 else 1)


if __name__ == '__main__':
    main()
