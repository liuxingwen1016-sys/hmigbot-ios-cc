#!/usr/bin/env python3
"""
模板映射器 - SwiftUI to ArkTS

基于映射规则将 SwiftUI 代码转换为 ArkTS
"""

import json
import re
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass


@dataclass
class ConversionResult:
    """转换结果"""
    success: bool
    arkts_code: str = ""
    auto_converted_percent: float = 0.0
    warnings: List[str] = None
    todos: List[str] = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []
        if self.todos is None:
            self.todos = []


class TemplateMapper:
    """SwiftUI → ArkTS 模板映射器"""

    def __init__(self, mappings_file: Path):
        """
        初始化映射器

        Args:
            mappings_file: 映射规则 JSON 文件
        """
        with open(mappings_file, 'r', encoding='utf-8') as f:
            self.mappings = json.load(f)

        print(f"✅ Loaded mappings: {len(self.mappings['views'])} views, "
              f"{len(self.mappings['modifiers'])} modifiers")

    def convert_simple_body(self, body_source: str) -> ConversionResult:
        """
        转换简单的 body 内容（基于模板）

        这是 90% 自动转换的核心

        Args:
            body_source: SwiftUI body 源码

        Returns:
            ConversionResult
        """
        warnings = []
        todos = []

        # 1. 转换 View 组件
        arkts_code = self._convert_views(body_source, warnings, todos)

        # 2. 转换修饰符
        arkts_code = self._convert_modifiers(arkts_code, warnings)

        # 3. 转换颜色
        arkts_code = self._convert_colors(arkts_code)

        # 4. 转换字符串插值
        arkts_code = self._convert_string_interpolation(arkts_code)

        # 5. 计算自动转换率
        auto_percent = self._calculate_auto_percent(arkts_code, todos)

        return ConversionResult(
            success=True,
            arkts_code=arkts_code,
            auto_converted_percent=auto_percent,
            warnings=warnings,
            todos=todos
        )

    def _convert_views(self, source: str, warnings: List[str], todos: List[str]) -> str:
        """转换 View 组件"""
        result = source

        for swiftui_view, mapping in self.mappings['views'].items():
            arkui_view = mapping['arkui']

            # 简单替换 View 名称
            # VStack → Column
            pattern = r'\b' + swiftui_view + r'\b'
            result = re.sub(pattern, arkui_view, result)

            # 处理复杂映射
            if mapping.get('complexity', 0) >= 2:
                todos.append(f"Review {swiftui_view} → {arkui_view} conversion")

        return result

    def _convert_modifiers(self, source: str, warnings: List[str]) -> str:
        """转换修饰符"""
        result = source

        for swiftui_mod, arkui_mod in self.mappings['modifiers'].items():
            if isinstance(arkui_mod, list):
                # 一对多映射（例如 .font(.title) → [.fontSize(), .fontWeight()]）
                # 这里简化处理，只用第一个
                warnings.append(f"Modifier {swiftui_mod} expanded to multiple modifiers")
                arkui_mod = arkui_mod[0]

            # 转义特殊字符
            pattern = re.escape(swiftui_mod)
            result = re.sub(pattern, arkui_mod, result)

        return result

    def _convert_colors(self, source: str) -> str:
        """转换颜色"""
        result = source

        for swiftui_color, arkui_color in self.mappings['colors'].items():
            pattern = r'Color' + re.escape(swiftui_color)
            result = re.sub(pattern, arkui_color, result)

        return result

    def _convert_string_interpolation(self, source: str) -> str:
        """
        转换字符串插值
        SwiftUI: "Count: \\(count)"
        ArkTS:   `Count: ${this.count}`
        """
        # 查找所有字符串插值（修复正则表达式）
        pattern = r'"([^"]*?)\\\(([^)]+)\)([^"]*?)"'

        def replace_interpolation(match):
            before = match.group(1)
            var_name = match.group(2).strip()
            after = match.group(3)

            # 添加 this. 前缀（如果是属性引用）
            if not var_name.startswith('this.') and not any(c in var_name for c in ['.', '(', '[']):
                var_name = f'this.{var_name}'

            return f'`{before}${{{var_name}}}{after}`'

        result = re.sub(pattern, replace_interpolation, source)

        return result

    def _calculate_auto_percent(self, code: str, todos: List[str]) -> float:
        """计算自动转换百分比"""
        if not code:
            return 0.0

        # 简单估算：TODO 越多，自动转换率越低
        total_lines = len(code.split('\n'))
        todo_lines = len(todos)

        if total_lines == 0:
            return 0.0

        auto_percent = max(0, (total_lines - todo_lines) / total_lines * 100)
        return auto_percent


def main():
    """测试函数"""
    mappings_file = Path(__file__).parent.parent.parent.parent / "mappings" / "swiftui-to-arkui.json"

    mapper = TemplateMapper(mappings_file)

    # 测试用例
    swiftui_body = '''
        VStack(spacing: 20) {
            Text("Count: \\(count)")
                .font(.title)
                .foregroundColor(.blue)

            Button("Increment") {
                count += 1
            }
            .padding()
            .background(Color.green)
        }
    '''

    print("\n📝 Converting SwiftUI body:")
    print(swiftui_body)

    result = mapper.convert_simple_body(swiftui_body)

    print(f"\n✅ Conversion result:")
    print(f"   Auto-converted: {result.auto_converted_percent:.1f}%")
    print(f"   Warnings: {len(result.warnings)}")
    print(f"   TODOs: {len(result.todos)}")

    print(f"\n🎯 ArkTS code:")
    print(result.arkts_code)

    if result.todos:
        print(f"\n📋 TODOs:")
        for todo in result.todos:
            print(f"   - {todo}")


if __name__ == "__main__":
    main()
