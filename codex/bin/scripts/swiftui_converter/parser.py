#!/usr/bin/env python3
"""
SwiftUI AST Parser using SourceKitten

功能:
- 使用 SourceKitten 解析 Swift 文件
- 提取 SwiftUI View 结构
- 识别属性包装器 (@State, @Binding, etc.)
- 解析 body 视图树

依赖:
- SourceKitten (brew install sourcekitten)
"""

import subprocess
import json
from pathlib import Path
from typing import Dict, List, Optional, Any


class SwiftUIParser:
    """SwiftUI AST 解析器"""

    def __init__(self):
        """初始化解析器，检查 SourceKitten 是否可用"""
        try:
            result = subprocess.run(
                ["sourcekitten", "version"],
                capture_output=True,
                check=True,
                text=True
            )
            print(f"✅ SourceKitten version: {result.stdout.strip()}")
        except FileNotFoundError:
            raise RuntimeError(
                "❌ SourceKitten not found. Install: brew install sourcekitten"
            )
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"❌ SourceKitten error: {e}")

    def parse_file(self, swift_file: Path) -> Dict[str, Any]:
        """
        解析 Swift 文件获取 AST

        Args:
            swift_file: Swift 文件路径

        Returns:
            AST 字典

        Raises:
            RuntimeError: 解析失败
        """
        if not swift_file.exists():
            raise FileNotFoundError(f"Swift file not found: {swift_file}")

        try:
            result = subprocess.run(
                ["sourcekitten", "structure", "--file", str(swift_file)],
                capture_output=True,
                text=True,
                check=True
            )
            return json.loads(result.stdout)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to parse {swift_file}: {e.stderr}")
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Invalid JSON from SourceKitten: {e}")

    def extract_view_struct(self, ast: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        从 AST 提取 SwiftUI View 结构

        Returns:
            {
                "name": "ContentView",
                "properties": [...],
                "body": {...}
            }
            或 None（如果不是 SwiftUI View）
        """
        # 遍历顶层结构
        for item in ast.get("key.substructure", []):
            if item.get("key.kind") == "source.lang.swift.decl.struct":
                # 检查是否 conforms to View
                if self._conforms_to_view(item):
                    return self._parse_view_struct(item)

        return None

    def _conforms_to_view(self, struct_ast: Dict[str, Any]) -> bool:
        """检查 struct 是否遵循 View 协议"""
        inherited = struct_ast.get("key.inheritedtypes", [])
        for inherited_type in inherited:
            type_name = inherited_type.get("key.name", "")
            if "View" in type_name:
                return True
        return False

    def _parse_view_struct(self, struct_ast: Dict[str, Any]) -> Dict[str, Any]:
        """解析 View struct 的详细信息"""
        view_info = {
            "name": struct_ast.get("key.name", "UnknownView"),
            "properties": [],
            "body": None,
            "methods": []
        }

        # 提取属性和方法
        for sub in struct_ast.get("key.substructure", []):
            kind = sub.get("key.kind", "")

            if kind == "source.lang.swift.decl.var.instance":
                # 实例属性
                prop = self._parse_property(sub)
                if prop:
                    view_info["properties"].append(prop)

            elif kind == "source.lang.swift.decl.var.computed":
                # 计算属性（body 是计算属性）
                prop_name = sub.get("key.name", "")
                if prop_name == "body":
                    view_info["body"] = self._parse_body(sub)

            elif kind == "source.lang.swift.decl.function.method.instance":
                # 实例方法
                method = self._parse_method(sub)
                if method:
                    view_info["methods"].append(method)

        return view_info

    def _parse_property(self, prop_ast: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        解析属性

        Returns:
            {
                "name": "count",
                "type": "Int",
                "wrapper": "@State",
                "is_private": True
            }
        """
        prop_name = prop_ast.get("key.name", "")
        if not prop_name or prop_name.startswith("_"):  # 跳过编译器生成的属性
            return None

        # 提取类型
        type_name = prop_ast.get("key.typename", "")

        # 检测属性包装器 (@State, @Binding 等)
        wrapper = None
        attributes = prop_ast.get("key.attributes", [])
        for attr in attributes:
            attr_name = attr.get("key.attribute", "")
            if attr_name.startswith("source.decl.attribute."):
                # 提取 @State, @Binding 等
                wrapper_name = attr_name.replace("source.decl.attribute.", "")
                if wrapper_name:
                    wrapper = f"@{wrapper_name.capitalize()}"

        # 检测访问级别
        accessibility = prop_ast.get("key.accessibility", "")
        is_private = "private" in accessibility

        return {
            "name": prop_name,
            "type": type_name,
            "wrapper": wrapper,
            "is_private": is_private
        }

    def _parse_body(self, body_ast: Dict[str, Any]) -> Dict[str, Any]:
        """
        解析 body 的视图树

        注意: SourceKitten 不会解析 body 内部的 SwiftUI DSL 结构
        我们只能获取 body 的源码范围，后续需要额外解析
        """
        offset = body_ast.get("key.bodyoffset")
        length = body_ast.get("key.bodylength")

        return {
            "offset": offset,
            "length": length,
            "needs_source_parsing": True  # 标记需要读取源码进一步解析
        }

    def _parse_method(self, method_ast: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """解析方法"""
        method_name = method_ast.get("key.name", "")
        if not method_name:
            return None

        return {
            "name": method_name,
            "offset": method_ast.get("key.bodyoffset"),
            "length": method_ast.get("key.bodylength")
        }

    def extract_body_source(self, swift_file: Path, offset: int, length: int) -> str:
        """
        从源文件提取 body 的源码

        Args:
            swift_file: Swift 文件路径
            offset: body 起始位置
            length: body 长度

        Returns:
            body 源码字符串
        """
        content = swift_file.read_text(encoding='utf-8')
        return content[offset:offset + length]


def main():
    """测试函数"""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python parser.py <swift_file>")
        sys.exit(1)

    swift_file = Path(sys.argv[1])

    # 解析
    parser = SwiftUIParser()
    print(f"📄 Parsing: {swift_file}")

    ast = parser.parse_file(swift_file)
    print(f"✅ AST parsed, top-level items: {len(ast.get('key.substructure', []))}")

    view_info = parser.extract_view_struct(ast)

    if view_info:
        print(f"\n✅ Found SwiftUI View: {view_info['name']}")
        print(f"   Properties: {len(view_info['properties'])}")
        for prop in view_info['properties']:
            wrapper_str = f"{prop['wrapper']} " if prop['wrapper'] else ""
            print(f"     - {wrapper_str}{prop['name']}: {prop['type']}")

        if view_info['body']:
            body = view_info['body']
            print(f"\n   Body: offset={body['offset']}, length={body['length']}")

            # 提取 body 源码
            body_source = parser.extract_body_source(
                swift_file,
                body['offset'],
                body['length']
            )
            print(f"   Body source:\n{body_source[:200]}...")
    else:
        print("❌ Not a SwiftUI View file")


if __name__ == "__main__":
    main()
