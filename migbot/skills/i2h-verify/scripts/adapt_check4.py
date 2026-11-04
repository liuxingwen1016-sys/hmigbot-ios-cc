#!/usr/bin/env python3
"""
CHECK-4 参数适配脚本

将 iOS 项目参数适配为 arkts-ut-verifier 可接受的格式
"""
import json
import sys
from pathlib import Path
from typing import Dict


class Check4Adapter:
    """CHECK-4 参数适配器"""

    def __init__(self, ios_root: str, harmonyos_root: str):
        self.ios_root = Path(ios_root)
        self.harmonyos_root = Path(harmonyos_root)

    def adapt_params(self, mode: str = 'verify_fix') -> Dict:
        """
        适配参数为 arkts-ut-verifier 格式

        Args:
            mode: 验证模式 (verify_fix / verify_only)

        Returns:
            适配后的参数字典
        """
        params = {
            # iOS 源码路径（映射到 android_source_root）
            'ios_source_root': str(self.ios_root),
            'android_source_root': str(self.ios_root),  # 兼容旧参数名

            # HarmonyOS 工程路径
            'harmonyos_root': str(self.harmonyos_root),
            'arkts_root': str(self.harmonyos_root),  # 兼容旧参数名

            # 模式
            'mode': mode,

            # 跳过 Android Oracle 采集
            'skip_oracle': True,

            # 测试框架
            'test_framework': 'xctest',

            # 输出目录
            'out': str(self.harmonyos_root / 'spec/verify/ut'),

            # 环境变量设置
            'env': {
                'UT_ANDROID_ORACLE': 'off',
                'IOS_MODE': 'true'
            }
        }

        return params

    def generate_call_script(self, mode: str = 'verify_fix', output_file: str = None) -> str:
        """
        生成 arkts-ut-verifier 调用脚本

        Args:
            mode: 验证模式
            output_file: 输出脚本文件路径

        Returns:
            脚本内容
        """
        params = self.adapt_params(mode)

        script = f"""#!/bin/bash
#
# CHECK-4 单元测试调用脚本
# 自动生成 - 请勿手动编辑
#

set -e

# 设置环境变量
export UT_ANDROID_ORACLE=off
export IOS_MODE=true

# 调用 arkts-ut-verifier
echo "🧪 开始 CHECK-4 单元测试验证..."

# 检查 arkts-ut-verifier 是否可用
if ! command -v arkts-ut-verifier &> /dev/null; then
    echo "❌ 错误: arkts-ut-verifier 未安装或不在 PATH 中"
    exit 1
fi

# 执行验证
arkts-ut-verifier \\
    --ios-source-root "{params['ios_source_root']}" \\
    --harmonyos-root "{params['harmonyos_root']}" \\
    --mode {params['mode']} \\
    --skip-oracle \\
    --test-framework xctest \\
    --out "{params['out']}"

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ CHECK-4 单元测试验证完成"
else
    echo "❌ CHECK-4 单元测试验证失败"
fi

exit $EXIT_CODE
"""

        if output_file:
            with open(output_file, 'w') as f:
                f.write(script)
            import os
            os.chmod(output_file, 0o755)

        return script

    def check_ios_tests(self) -> Dict:
        """
        检查 iOS 测试文件

        Returns:
            测试文件信息
        """
        test_info = {
            'unit_tests': [],
            'ui_tests': [],
            'total': 0
        }

        # 查找单元测试
        for test_dir in self.ios_root.rglob('*Tests'):
            if test_dir.is_dir() and 'UI' not in test_dir.name:
                test_files = list(test_dir.glob('*.swift'))
                test_info['unit_tests'].extend([str(f) for f in test_files])

        # 查找 UI 测试
        for test_dir in self.ios_root.rglob('*UITests'):
            if test_dir.is_dir():
                test_files = list(test_dir.glob('*.swift'))
                test_info['ui_tests'].extend([str(f) for f in test_files])

        test_info['total'] = len(test_info['unit_tests']) + len(test_info['ui_tests'])

        return test_info

    def generate_summary(self) -> str:
        """生成适配摘要"""
        params = self.adapt_params()
        test_info = self.check_ios_tests()

        summary = f"""# CHECK-4 参数适配摘要

## iOS 项目信息

- **iOS 源码路径**: {params['ios_source_root']}
- **测试文件总数**: {test_info['total']}
  - 单元测试: {len(test_info['unit_tests'])}
  - UI 测试: {len(test_info['ui_tests'])}

## HarmonyOS 项目信息

- **工程路径**: {params['harmonyos_root']}
- **输出目录**: {params['out']}

## 适配配置

- **测试框架**: XCTest
- **验证模式**: {params['mode']}
- **跳过 Oracle**: {params['skip_oracle']}

## 环境变量

```bash
export UT_ANDROID_ORACLE=off
export IOS_MODE=true
```

## 调用方式

### 方式 1: 使用生成的脚本

```bash
bash scripts/run_check4.sh
```

### 方式 2: 直接调用（如果 arkts-ut-verifier 支持）

```bash
arkts-ut-verifier \\
    --ios-source-root {params['ios_source_root']} \\
    --harmonyos-root {params['harmonyos_root']} \\
    --mode {params['mode']} \\
    --skip-oracle \\
    --test-framework xctest
```

## 限制说明

由于跳过 Android Oracle 采集，存在以下限制：

1. **测试用例需要手动编写或基于 Spec**
   - 不自动从 iOS 源码生成测试
   - 依赖 Spec 的验收标准

2. **以 Spec 为准（而非 iOS 实际行为）**
   - 功能预期来自 Spec
   - 需要确保 Spec 准确反映需求

3. **XCTest 框架识别**
   - 需要识别 XCTest 测试语法
   - 映射到 ArkTS 测试框架

## 状态判定

根据 `spec/verify/ut/ut-report.md` 判定：

- **PASS**: 全范围实际 GREEN，无未验证设计点
- **FAIL**: 有实际 RED、ERROR 或最终 FAIL
- **PARTIAL**: CONVERGED、缺证据或尚未复测

---

**生成时间**: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""

        return summary


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description='CHECK-4 参数适配脚本')
    parser.add_argument('ios_root', help='iOS 项目根目录')
    parser.add_argument('harmonyos_root', help='HarmonyOS 项目根目录')
    parser.add_argument('--mode', default='verify_fix',
                       choices=['verify_fix', 'verify_only'],
                       help='验证模式 (默认: verify_fix)')
    parser.add_argument('--generate-script', metavar='FILE',
                       help='生成调用脚本到指定文件')
    parser.add_argument('--check-tests', action='store_true',
                       help='检查 iOS 测试文件')
    parser.add_argument('--summary', action='store_true',
                       help='生成适配摘要')
    parser.add_argument('--json', action='store_true',
                       help='JSON 格式输出')

    args = parser.parse_args()

    adapter = Check4Adapter(args.ios_root, args.harmonyos_root)

    if args.check_tests:
        test_info = adapter.check_ios_tests()
        if args.json:
            print(json.dumps(test_info, indent=2, ensure_ascii=False))
        else:
            print(f"iOS 测试文件统计:")
            print(f"  单元测试: {len(test_info['unit_tests'])}")
            print(f"  UI 测试: {len(test_info['ui_tests'])}")
            print(f"  总计: {test_info['total']}")

    elif args.generate_script:
        script = adapter.generate_call_script(args.mode, args.generate_script)
        print(f"✅ 脚本已生成: {args.generate_script}")

    elif args.summary:
        summary = adapter.generate_summary()
        print(summary)

    else:
        # 默认：输出适配参数
        params = adapter.adapt_params(args.mode)
        if args.json:
            print(json.dumps(params, indent=2, ensure_ascii=False))
        else:
            print("CHECK-4 适配参数:")
            for key, value in params.items():
                if key != 'env':
                    print(f"  {key}: {value}")
            print("\n环境变量:")
            for key, value in params.get('env', {}).items():
                print(f"  {key}={value}")


if __name__ == '__main__':
    main()
