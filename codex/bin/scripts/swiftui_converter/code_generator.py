#!/usr/bin/env python3
"""
ArkTS 代码生成器

功能:
- 生成完整的 @Component 结构
- 处理属性装饰器（@State, @Link 等）
- 生成 build() 方法
- 添加导入语句
- 格式化输出
"""

from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from pathlib import Path


@dataclass
class ArkTSProperty:
    """ArkTS 属性"""
    name: str
    type: str
    decorator: Optional[str] = None  # @State, @Link, etc.
    default_value: Optional[str] = None
    is_private: bool = False


@dataclass
class ArkTSComponent:
    """ArkTS 组件结构"""
    name: str
    properties: List[ArkTSProperty]
    build_body: str
    is_entry: bool = False
    imports: List[str] = None

    def __post_init__(self):
        if self.imports is None:
            self.imports = []


class ArkTSCodeGenerator:
    """ArkTS 代码生成器"""

    def __init__(self, indent: str = "  "):
        """
        初始化生成器

        Args:
            indent: 缩进字符串（默认2空格）
        """
        self.indent = indent
        self.current_level = 0

    def generate(self, component: ArkTSComponent) -> str:
        """
        生成完整的 ArkTS 代码

        Args:
            component: ArkTS 组件结构

        Returns:
            完整的 ArkTS 源码
        """
        lines = []

        # 1. 导入语句（如果需要）
        if component.imports:
            for imp in component.imports:
                lines.append(imp)
            lines.append("")  # 空行

        # 2. @Entry 装饰器（如果是入口组件）
        if component.is_entry:
            lines.append("@Entry")

        # 3. @Component 装饰器
        lines.append("@Component")

        # 4. struct 定义
        lines.append(f"struct {component.name} {{")
        self.current_level += 1

        # 5. 属性声明
        if component.properties:
            for prop in component.properties:
                lines.append(self._generate_property(prop))
            lines.append("")  # 属性后空行

        # 6. build 方法
        lines.extend(self._generate_build_method(component.build_body))

        # 7. 结束
        self.current_level -= 1
        lines.append("}")

        return "\n".join(lines)

    def _generate_property(self, prop: ArkTSProperty) -> str:
        """
        生成属性声明

        Examples:
            @State count: number = 0
            @Link message: string
            private name: string = "hello"
        """
        parts = []

        # 装饰器
        if prop.decorator:
            parts.append(f"{self.indent * self.current_level}{prop.decorator}")

        # 访问修饰符 + 名称: 类型
        line_parts = []
        if prop.is_private and not prop.decorator:  # @State 等不需要 private
            line_parts.append("private")

        line_parts.append(f"{prop.name}: {prop.type}")

        # 默认值
        if prop.default_value:
            line_parts.append(f"= {prop.default_value}")

        if prop.decorator:
            # 装饰器单独一行
            parts.append(f"{self.indent * self.current_level}{' '.join(line_parts)}")
            return "\n".join(parts)
        else:
            return f"{self.indent * self.current_level}{' '.join(line_parts)}"

    def _generate_build_method(self, build_body: str) -> List[str]:
        """
        生成 build 方法

        Args:
            build_body: build 方法的 body 内容

        Returns:
            代码行列表
        """
        lines = []

        # build() {
        lines.append(f"{self.indent * self.current_level}build() {{")
        self.current_level += 1

        # body 内容（缩进处理）
        body_lines = build_body.strip().split('\n')
        for line in body_lines:
            if line.strip():  # 跳过空行
                lines.append(f"{self.indent * self.current_level}{line.strip()}")
            else:
                lines.append("")

        # }
        self.current_level -= 1
        lines.append(f"{self.indent * self.current_level}}}")

        return lines

    def generate_from_swiftui(self,
                              view_name: str,
                              properties: List[Dict[str, Any]],
                              body_source: str,
                              is_entry: bool = False) -> str:
        """
        从 SwiftUI 信息生成 ArkTS 代码

        Args:
            view_name: View 名称
            properties: 属性列表（从 SwiftUI 解析）
            body_source: body 源码（已转换为 ArkTS）
            is_entry: 是否是入口组件

        Returns:
            完整的 ArkTS 代码
        """
        # 转换属性
        arkts_properties = []
        for prop in properties:
            arkts_prop = ArkTSProperty(
                name=prop['name'],
                type=self._convert_type(prop.get('type', 'any')),
                decorator=self._convert_wrapper(prop.get('wrapper')),
                default_value=prop.get('default_value'),
                is_private=prop.get('is_private', False)
            )
            arkts_properties.append(arkts_prop)

        # 构建组件
        component = ArkTSComponent(
            name=view_name,
            properties=arkts_properties,
            build_body=body_source,
            is_entry=is_entry
        )

        return self.generate(component)

    def _convert_type(self, swift_type: str) -> str:
        """转换类型名称"""
        type_mapping = {
            'Int': 'number',
            'Double': 'number',
            'Float': 'number',
            'String': 'string',
            'Bool': 'boolean',
            'Array': 'Array',
            '[': 'Array',  # [String] → Array<string>
        }

        # 简单类型
        if swift_type in type_mapping:
            return type_mapping[swift_type]

        # 数组类型 [Type]
        if swift_type.startswith('[') and swift_type.endswith(']'):
            inner_type = swift_type[1:-1]
            converted_inner = self._convert_type(inner_type)
            return f'Array<{converted_inner}>'

        # 可选类型 Type?
        if swift_type.endswith('?'):
            inner_type = swift_type[:-1]
            converted_inner = self._convert_type(inner_type)
            return f'{converted_inner} | undefined'

        # 其他保持不变
        return swift_type

    def _convert_wrapper(self, swift_wrapper: Optional[str]) -> Optional[str]:
        """转换属性包装器"""
        if not swift_wrapper:
            return None

        wrapper_mapping = {
            '@State': '@State',
            '@Binding': '@Link',
            '@ObservedObject': '@ObjectLink',
            '@StateObject': '@Observed',
            '@EnvironmentObject': '@Consume',
        }

        return wrapper_mapping.get(swift_wrapper, swift_wrapper)


def main():
    """测试函数"""
    generator = ArkTSCodeGenerator()

    # 测试用例 1: 简单组件
    print("=" * 60)
    print("Test 1: Simple Component")
    print("=" * 60)

    simple_component = ArkTSComponent(
        name="ContentView",
        properties=[
            ArkTSProperty(
                name="count",
                type="number",
                decorator="@State",
                default_value="0"
            ),
            ArkTSProperty(
                name="message",
                type="string",
                decorator="@State",
                default_value='"Hello"'
            )
        ],
        build_body="""
Column({ space: 20 }) {
  Text(`Count: ${this.count}`)
    .fontSize(20)
    .fontWeight(FontWeight.Bold)
    .fontColor(Color.Blue)

  Text(this.message)

  Button("Increment")
    .onClick(() => {
      this.count += 1
    })
    .padding(10)
    .backgroundColor(Color.Green)
}
        """.strip(),
        is_entry=True
    )

    code = generator.generate(simple_component)
    print(code)

    # 测试用例 2: 从 SwiftUI 生成
    print("\n" + "=" * 60)
    print("Test 2: From SwiftUI Info")
    print("=" * 60)

    swiftui_properties = [
        {
            'name': 'isOn',
            'type': 'Bool',
            'wrapper': '@State',
            'default_value': 'false'
        },
        {
            'name': 'items',
            'type': '[String]',
            'wrapper': '@State',
            'default_value': '[]'
        }
    ]

    body = """
VStack {
  Toggle("Switch", isOn: $isOn)
  List(items) { item in
    Text(item)
  }
}
    """.strip()

    # 注意：这里的 body 应该已经被 template_mapper 转换过
    converted_body = """
Column() {
  Toggle({ isOn: $isOn })
  List() {
    ForEach(this.items, (item) => {
      Text(item)
    })
  }
}
    """.strip()

    code2 = generator.generate_from_swiftui(
        view_name="SettingsView",
        properties=swiftui_properties,
        body_source=converted_body,
        is_entry=False
    )

    print(code2)

    # 保存到文件（可选）
    output_file = Path("test_output.ets")
    output_file.write_text(code, encoding='utf-8')
    print(f"\n✅ Code saved to: {output_file}")


if __name__ == "__main__":
    main()
