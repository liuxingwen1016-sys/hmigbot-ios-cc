#!/usr/bin/env python3
"""
SwiftUI 简化解析器 (基于正则表达式)

这是一个轻量级的 SwiftUI 解析器，不依赖 SourceKitten
可以处理 80% 的标准 SwiftUI 代码

对于复杂情况，后续可以升级到使用 SourceKitten
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field


@dataclass
class SwiftUIProperty:
    """SwiftUI 属性"""
    name: str
    type: str
    wrapper: Optional[str] = None
    default_value: Optional[str] = None
    is_private: bool = False


@dataclass
class SwiftUIViewInfo:
    """SwiftUI View 信息"""
    name: str
    properties: List[SwiftUIProperty] = field(default_factory=list)
    body_source: str = ""
    methods: List[Dict[str, str]] = field(default_factory=list)


class SimpleSwiftUIParser:
    """简化的 SwiftUI 解析器（基于正则表达式）"""

    # 正则表达式模式
    STRUCT_PATTERN = r'struct\s+(\w+)\s*:\s*View\s*\{'
    PROPERTY_PATTERN = r'(@\w+)?\s*(private|public|internal)?\s*var\s+(\w+)\s*:\s*([^\s=]+)(?:\s*=\s*([^\n]+))?'
    BODY_PATTERN = r'var\s+body\s*:\s*some\s+View\s*\{(.*?)\n\s*\}'

    def __init__(self):
        """初始化解析器"""
        print("✅ Simple SwiftUI Parser initialized (regex-based)")

    def parse_file(self, swift_file: Path) -> Optional[SwiftUIViewInfo]:
        """
        解析 Swift 文件

        Args:
            swift_file: Swift 文件路径

        Returns:
            SwiftUIViewInfo 或 None（如果不是 SwiftUI View）
        """
        if not swift_file.exists():
            raise FileNotFoundError(f"Swift file not found: {swift_file}")

        content = swift_file.read_text(encoding='utf-8')

        # 检查是否是 SwiftUI 文件
        if 'import SwiftUI' not in content:
            return None

        # 提取 struct 名称
        struct_match = re.search(self.STRUCT_PATTERN, content)
        if not struct_match:
            return None

        struct_name = struct_match.group(1)

        # 提取 struct 内容
        struct_start = struct_match.end()
        struct_content = self._extract_struct_content(content, struct_start)

        # 解析属性
        properties = self._parse_properties(struct_content)

        # 解析 body
        body_source = self._parse_body(struct_content)

        return SwiftUIViewInfo(
            name=struct_name,
            properties=properties,
            body_source=body_source
        )

    def _extract_struct_content(self, content: str, start_pos: int) -> str:
        """提取 struct 的完整内容（匹配大括号）"""
        depth = 1
        pos = start_pos

        while pos < len(content) and depth > 0:
            if content[pos] == '{':
                depth += 1
            elif content[pos] == '}':
                depth -= 1
            pos += 1

        return content[start_pos:pos-1]

    def _parse_properties(self, struct_content: str) -> List[SwiftUIProperty]:
        """解析属性"""
        properties = []

        # 查找所有属性声明
        for match in re.finditer(self.PROPERTY_PATTERN, struct_content):
            wrapper = match.group(1)  # @State, @Binding, etc.
            access = match.group(2)   # private, public, etc.
            name = match.group(3)
            type_name = match.group(4)
            default_value = match.group(5)

            # 跳过 body（body 是计算属性）
            if name == 'body':
                continue

            # 清理类型名称
            type_name = type_name.strip()
            if default_value:
                default_value = default_value.strip()

            prop = SwiftUIProperty(
                name=name,
                type=type_name,
                wrapper=wrapper,
                default_value=default_value,
                is_private=(access == 'private')
            )
            properties.append(prop)

        return properties

    def _parse_body(self, struct_content: str) -> str:
        """解析 body 内容"""
        # 查找 body 的开始位置
        body_match = re.search(r'var\s+body\s*:\s*some\s+View\s*\{', struct_content)
        if not body_match:
            return ""

        # 从 body 开始位置提取内容
        body_start = body_match.end()
        body_content = self._extract_body_content(struct_content, body_start)

        return body_content.strip()

    def _extract_body_content(self, content: str, start_pos: int) -> str:
        """提取 body 的完整内容（匹配大括号）"""
        depth = 1
        pos = start_pos

        while pos < len(content) and depth > 0:
            if content[pos] == '{':
                depth += 1
            elif content[pos] == '}':
                depth -= 1
            pos += 1

        return content[start_pos:pos-1]


def main():
    """测试函数"""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python simple_parser.py <swift_file>")
        sys.exit(1)

    swift_file = Path(sys.argv[1])

    # 解析
    parser = SimpleSwiftUIParser()
    print(f"📄 Parsing: {swift_file}")

    view_info = parser.parse_file(swift_file)

    if view_info:
        print(f"\n✅ Found SwiftUI View: {view_info.name}")
        print(f"\n📋 Properties ({len(view_info.properties)}):")
        for prop in view_info.properties:
            wrapper_str = f"{prop.wrapper} " if prop.wrapper else ""
            access_str = "private " if prop.is_private else ""
            default_str = f" = {prop.default_value}" if prop.default_value else ""
            print(f"  {wrapper_str}{access_str}var {prop.name}: {prop.type}{default_str}")

        print(f"\n🏗️ Body:")
        print(f"  {view_info.body_source[:300]}...")
    else:
        print("❌ Not a SwiftUI View file")


if __name__ == "__main__":
    main()
