#!/usr/bin/env python3
"""解析 iOS UI 布局文件（Storyboard + SwiftUI）

功能：
1. 解析 Storyboard XML 结构
2. 提取视图层次结构
3. 提取约束信息（Auto Layout）
4. 解析 SwiftUI 视图（需要 AST 解析）
5. 生成布局描述 JSON

输出：layout.json
{
  "views": [
    {
      "id": "view_001",
      "type": "UILabel|Text",
      "properties": {...},
      "constraints": [...],
      "children": [...]
    }
  ]
}

注意：
- Storyboard 是 XML 格式，可以直接解析
- SwiftUI 需要 Swift AST 解析（复杂）
- 当前版本是骨架，完整实现需要 8-12 小时
"""

import sys
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Any, Optional


def parse_storyboard_xml(storyboard_path: Path) -> Dict[str, Any]:
    """解析 Storyboard XML 文件

    Storyboard 结构：
    <document>
      <scenes>
        <scene sceneID="xxx">
          <objects>
            <viewController id="xxx" customClass="XXXViewController">
              <view key="view">
                <subviews>
                  <label ... />
                  <button ... />
                </subviews>
                <constraints>
                  <constraint ... />
                </constraints>
              </view>
            </viewController>
          </objects>
        </scene>
      </scenes>
    </document>

    TODO: 完整实现
    """
    print(f"解析 Storyboard: {storyboard_path.name}")

    try:
        tree = ET.parse(storyboard_path)
        root = tree.getroot()

        scenes = []

        # 遍历所有场景
        for scene in root.findall(".//scene"):
            scene_id = scene.get('sceneID', 'unknown')

            # 查找 viewController
            view_controller = scene.find(".//viewController")
            if view_controller is None:
                continue

            vc_info = {
                "scene_id": scene_id,
                "id": view_controller.get('id'),
                "custom_class": view_controller.get('customClass'),
                "view": None
            }

            # 解析根视图
            root_view = view_controller.find(".//view[@key='view']")
            if root_view is not None:
                vc_info["view"] = parse_view_element(root_view)

            scenes.append(vc_info)

        return {
            "type": "storyboard",
            "source": str(storyboard_path),
            "scenes": scenes
        }

    except Exception as e:
        print(f"  错误：解析失败 - {e}")
        return {"type": "storyboard", "source": str(storyboard_path), "error": str(e)}


def parse_view_element(view_elem: ET.Element) -> Dict[str, Any]:
    """解析单个视图元素

    TODO: 完整实现需要处理：
    - 所有 UIKit 视图类型
    - 所有属性（frame, color, font, etc）
    - 约束解析
    - IBOutlet 连接
    - IBAction 连接
    """
    view_info = {
        "id": view_elem.get('id', 'unknown'),
        "tag": view_elem.tag,
        "properties": {},
        "subviews": [],
        "constraints": []
    }

    # 提取常见属性
    if view_elem.get('key'):
        view_info["key"] = view_elem.get('key')

    # 解析 frame
    rect = view_elem.find("rect")
    if rect is not None:
        view_info["properties"]["frame"] = {
            "x": rect.get('x'),
            "y": rect.get('y'),
            "width": rect.get('width'),
            "height": rect.get('height')
        }

    # 解析 color (backgroundColor)
    color = view_elem.find("color")
    if color is not None:
        view_info["properties"]["backgroundColor"] = {
            "key": color.get('key'),
            "red": color.get('red'),
            "green": color.get('green'),
            "blue": color.get('blue'),
            "alpha": color.get('alpha')
        }

    # 解析子视图
    subviews = view_elem.find("subviews")
    if subviews is not None:
        for subview in subviews:
            view_info["subviews"].append(parse_view_element(subview))

    # 解析约束
    constraints = view_elem.find("constraints")
    if constraints is not None:
        for constraint in constraints.findall("constraint"):
            view_info["constraints"].append({
                "firstItem": constraint.get('firstItem'),
                "firstAttribute": constraint.get('firstAttribute'),
                "secondItem": constraint.get('secondItem'),
                "secondAttribute": constraint.get('secondAttribute'),
                "constant": constraint.get('constant'),
                "multiplier": constraint.get('multiplier'),
                "relation": constraint.get('relation', 'equal')
            })

    return view_info


def parse_swiftui_file(swift_file: Path) -> Dict[str, Any]:
    """解析 SwiftUI 文件

    SwiftUI 示例：
    struct ContentView: View {
        var body: some View {
            VStack {
                Text("Hello")
                Button("Tap") { action() }
            }
        }
    }

    TODO: 完整实现需要：
    - Swift 语法解析器（AST）
    - SwiftUI 视图层次提取
    - 修饰符解析
    - 状态管理识别

    困难：
    - Swift AST 解析复杂
    - 需要处理泛型、闭包、属性包装器
    - 当前只能做简单的文本匹配

    建议：
    - 使用 SourceKit 或 SwiftSyntax（Swift 官方工具）
    - 或者使用正则表达式做简单提取
    """
    print(f"解析 SwiftUI 文件: {swift_file.name}")
    print("  [骨架版本] TODO: 实现 Swift AST 解析")

    try:
        with open(swift_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # 简单检测：是否是 SwiftUI View
        if 'import SwiftUI' not in content:
            return {"type": "swiftui", "source": str(swift_file), "is_view": False}

        # TODO: 实际的 AST 解析
        # 当前只返回骨架
        return {
            "type": "swiftui",
            "source": str(swift_file),
            "is_view": True,
            "note": "需要完整的 Swift AST 解析器才能提取视图层次"
        }

    except Exception as e:
        print(f"  错误：{e}")
        return {"type": "swiftui", "source": str(swift_file), "error": str(e)}


def main():
    if len(sys.argv) < 3:
        print("用法: parse_ios_layouts.py <input_file> <output_layout.json>")
        print()
        print("支持的输入文件类型:")
        print("  - .storyboard (XML 格式)")
        print("  - .swift (SwiftUI 文件，需要 AST 解析)")
        print()
        print("示例:")
        print("  python parse_ios_layouts.py Main.storyboard layout.json")
        print("  python parse_ios_layouts.py ContentView.swift layout.json")
        sys.exit(1)

    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])

    if not input_path.exists():
        print(f"错误：输入文件不存在: {input_path}")
        sys.exit(1)

    print(f"解析 iOS 布局文件: {input_path}")
    print()

    # 根据文件类型选择解析器
    if input_path.suffix == '.storyboard':
        layout_data = parse_storyboard_xml(input_path)
    elif input_path.suffix == '.swift':
        layout_data = parse_swiftui_file(input_path)
    else:
        print(f"错误：不支持的文件类型: {input_path.suffix}")
        print("支持的类型: .storyboard, .swift")
        sys.exit(1)

    # 写入输出
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(layout_data, f, indent=2, ensure_ascii=False)

    print()
    print(f"✅ 布局数据已生成: {output_path}")

    if layout_data.get('error'):
        print(f"⚠️  警告：解析过程中出现错误")
        sys.exit(1)


if __name__ == '__main__':
    main()
