#!/usr/bin/env python3
"""
Verify Slice Wiring

用途: 验证 Slice 接线完成性，检查 UI、ViewModel、数据层的连接
"""

import argparse
import json
import sys
import re
from pathlib import Path
from typing import Dict, List, Any

class SliceWiringVerifier:
    """Slice 接线验证器"""

    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.errors = []
        self.warnings = []

    def verify_slice(self, slice_id: str, slice_spec: str) -> Dict[str, Any]:
        """验证单个 Slice 的接线"""
        print(f"\n🔍 验证 Slice: {slice_id}")

        result = {
            'slice_id': slice_id,
            'status': 'PASS',
            'checks': {
                'ui_events': False,
                'viewmodel_state': False,
                'data_layer': False,
                'lifecycle': False
            },
            'errors': [],
            'warnings': []
        }

        # 读取 Slice spec
        spec_file = Path(slice_spec)
        if not spec_file.exists():
            result['status'] = 'FAIL'
            result['errors'].append(f"Slice spec 不存在: {slice_spec}")
            return result

        spec_content = spec_file.read_text(encoding='utf-8')

        # 提取涉及的文件
        files = self._extract_files_from_spec(spec_content)

        # 验证各个层面
        result['checks']['ui_events'] = self._verify_ui_events(files)
        result['checks']['viewmodel_state'] = self._verify_viewmodel_state(files)
        result['checks']['data_layer'] = self._verify_data_layer(files)
        result['checks']['lifecycle'] = self._verify_lifecycle(files)

        # 汇总结果
        if not all(result['checks'].values()):
            result['status'] = 'FAIL'
            for check_name, passed in result['checks'].items():
                if not passed:
                    result['errors'].append(f"{check_name} 验证失败")

        result['errors'].extend(self.errors)
        result['warnings'].extend(self.warnings)

        return result

    def _extract_files_from_spec(self, spec_content: str) -> Dict[str, Path]:
        """从 spec 中提取相关文件"""
        files = {
            'page': None,
            'viewmodel': None,
            'repository': None,
            'service': None
        }

        # 查找 Page 文件
        page_match = re.search(r'entry/src/main/ets/pages/(\w+)\.ets', spec_content)
        if page_match:
            files['page'] = self.project_root / f"entry/src/main/ets/pages/{page_match.group(1)}.ets"

        # 查找 ViewModel 文件
        vm_match = re.search(r'entry/src/main/ets/viewmodels/(\w+)\.ets', spec_content)
        if vm_match:
            files['viewmodel'] = self.project_root / f"entry/src/main/ets/viewmodels/{vm_match.group(1)}.ets"

        return files

    def _verify_ui_events(self, files: Dict[str, Path]) -> bool:
        """验证 UI 事件绑定"""
        if not files.get('page') or not files['page'].exists():
            self.errors.append("Page 文件不存在")
            return False

        page_content = files['page'].read_text(encoding='utf-8')

        # 检查是否有事件绑定
        event_patterns = [
            r'\.onClick\(',
            r'\.onTouch\(',
            r'\.onChange\(',
            r'\.onSubmit\(',
        ]

        has_events = any(re.search(pattern, page_content) for pattern in event_patterns)

        if not has_events:
            self.warnings.append("未发现 UI 事件绑定")
            return True  # 警告但不失败

        # 检查事件是否调用 ViewModel 方法
        if files.get('viewmodel'):
            vm_name = files['viewmodel'].stem
            vm_call_pattern = rf'this\.{vm_name}\.\w+\('

            if not re.search(vm_call_pattern, page_content):
                self.errors.append("UI 事件未调用 ViewModel 方法")
                return False

        return True

    def _verify_viewmodel_state(self, files: Dict[str, Path]) -> bool:
        """验证 ViewModel 状态管理"""
        if not files.get('viewmodel') or not files['viewmodel'].exists():
            self.errors.append("ViewModel 文件不存在")
            return False

        vm_content = files['viewmodel'].read_text(encoding='utf-8')

        # 检查是否使用 @Trace 装饰器
        if '@Trace' not in vm_content and '@Track' not in vm_content:
            self.warnings.append("ViewModel 未使用 @Trace/@Track 状态管理")

        # 检查是否有业务方法
        method_pattern = r'async \w+\([^)]*\): Promise<'
        if not re.search(method_pattern, vm_content):
            self.warnings.append("ViewModel 未发现异步业务方法")

        return True

    def _verify_data_layer(self, files: Dict[str, Path]) -> bool:
        """验证数据层接入"""
        if not files.get('viewmodel'):
            return True  # 如果没有 ViewModel，跳过检查

        vm_content = files['viewmodel'].read_text(encoding='utf-8')

        # 检查是否引入了 Service 或 Repository
        service_patterns = [
            r'from [\'"].*Service[\'"]',
            r'from [\'"].*Repository[\'"]',
            r': \w+Service',
            r': \w+Repository',
        ]

        has_data_layer = any(re.search(pattern, vm_content) for pattern in service_patterns)

        if not has_data_layer:
            self.warnings.append("ViewModel 未接入数据层（Service/Repository）")
            return True  # 警告但不失败

        return True

    def _verify_lifecycle(self, files: Dict[str, Path]) -> bool:
        """验证生命周期方法"""
        if not files.get('page'):
            return True

        page_content = files['page'].read_text(encoding='utf-8')

        # 检查常见生命周期方法
        lifecycle_methods = [
            'aboutToAppear',
            'onReady',
            'aboutToDisappear'
        ]

        found_lifecycle = [method for method in lifecycle_methods if method in page_content]

        if not found_lifecycle:
            self.warnings.append("Page 未实现生命周期方法")

        return True

def main():
    parser = argparse.ArgumentParser(description='验证 Slice 接线完成性')
    parser.add_argument('--project-root', required=True, help='项目根目录')
    parser.add_argument('--slice-id', required=True, help='Slice ID')
    parser.add_argument('--slice-spec', required=True, help='Slice spec 文件路径')
    parser.add_argument('--output-json', help='输出 JSON 结果文件')

    args = parser.parse_args()

    print("=" * 60)
    print("🔍 Slice Wiring Verifier")
    print("=" * 60)
    print(f"Project Root: {args.project_root}")
    print(f"Slice ID: {args.slice_id}")
    print(f"Slice Spec: {args.slice_spec}")
    print("=" * 60)

    verifier = SliceWiringVerifier(args.project_root)
    result = verifier.verify_slice(args.slice_id, args.slice_spec)

    # 输出结果
    if args.output_json:
        output_file = Path(args.output_json)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(json.dumps(result, indent=2, ensure_ascii=False))
        print(f"\n📄 结果已保存: {args.output_json}")

    # 打印摘要
    print("\n" + "=" * 60)
    print("📊 验证结果:")
    print("=" * 60)
    print(f"  Slice ID: {result['slice_id']}")
    print(f"  状态: {result['status']}")
    print(f"\n  检查项:")
    for check_name, passed in result['checks'].items():
        status = "✅" if passed else "❌"
        print(f"    {status} {check_name}")

    if result['errors']:
        print(f"\n  ❌ 错误 ({len(result['errors'])} 个):")
        for error in result['errors']:
            print(f"    - {error}")

    if result['warnings']:
        print(f"\n  ⚠️  警告 ({len(result['warnings'])} 个):")
        for warning in result['warnings']:
            print(f"    - {warning}")

    print("=" * 60)

    # 返回状态码
    if result['status'] == 'PASS':
        print("✅ 验证通过")
        return 0
    else:
        print("❌ 验证失败")
        return 1

if __name__ == '__main__':
    sys.exit(main())
