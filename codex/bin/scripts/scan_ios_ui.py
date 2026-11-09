#!/usr/bin/env python3
"""扫描 iOS 项目 UI 结构，生成 manifest.json

功能：
1. 解析 Xcode 项目文件 (.xcodeproj/project.pbxproj)
2. 扫描所有 Storyboard 文件
3. 扫描所有 Swift 源文件
4. 识别 SwiftUI 和 UIKit 视图
5. 生成完整的 UI 清单

输出：manifest.json
{
  "project_name": "MyApp",
  "project_type": "swiftui|uikit|mixed",
  "screens": [
    {
      "name": "HomeView",
      "type": "swiftui|uikit",
      "file": "path/to/file.swift",
      "view_controller": "HomeViewController",
      "storyboard": "Main.storyboard"
    }
  ],
  "storyboards": ["Main.storyboard", "LaunchScreen.storyboard"],
  "swift_files": ["HomeView.swift", "ProfileView.swift"],
  "resources": {
    "assets": ["Assets.xcassets"],
    "images": [...],
    "localizations": [...]
  }
}
"""

import sys
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Any, Optional


def parse_xcodeproj(project_path: Path) -> tuple[List[str], List[str]]:
    """解析 Xcode 项目文件

    Returns:
        (swift_files, storyboard_files)

    TODO: 完整实现需要解析 .pbxproj 格式
    目前返回通过文件系统扫描的结果
    """
    print(f"解析 Xcode 项目: {project_path}")

    # 简化实现：直接扫描目录
    project_root = project_path.parent
    swift_files = list(project_root.rglob("*.swift"))
    storyboards = list(project_root.rglob("*.storyboard"))

    print(f"  发现 {len(swift_files)} 个 Swift 文件")
    print(f"  发现 {len(storyboards)} 个 Storyboard 文件")

    return [str(f) for f in swift_files], [str(f) for f in storyboards]


def detect_project_type(swift_files: List[str]) -> str:
    """检测项目类型：SwiftUI、UIKit 或混合

    简单启发式：
    - 如果有 @main 和 SwiftUI import -> SwiftUI
    - 如果有 UIViewController -> UIKit
    - 两者都有 -> mixed
    """
    has_swiftui = False
    has_uikit = False

    for swift_file in swift_files[:20]:  # 采样前20个文件
        try:
            with open(swift_file, 'r', encoding='utf-8') as f:
                content = f.read()
                if 'import SwiftUI' in content or 'View' in content and 'body' in content:
                    has_swiftui = True
                if 'UIViewController' in content or 'UIView' in content:
                    has_uikit = True
        except Exception as e:
            print(f"  警告：无法读取 {swift_file}: {e}")

    if has_swiftui and has_uikit:
        return "mixed"
    elif has_swiftui:
        return "swiftui"
    elif has_uikit:
        return "uikit"
    else:
        return "unknown"


def scan_storyboards(storyboard_files: List[str]) -> List[Dict[str, Any]]:
    """扫描所有 Storyboard 文件

    Returns:
        List of screen info extracted from storyboards

    TODO: 完整实现需要解析 Storyboard XML 结构
    """
    screens = []

    for storyboard in storyboard_files:
        try:
            tree = ET.parse(storyboard)
            root = tree.getroot()

            # 查找所有 ViewController 场景
            # Storyboard XML 结构：<document><scenes><scene><objects><viewController>
            for vc in root.findall(".//viewController"):
                vc_id = vc.get('id', 'unknown')
                custom_class = vc.get('customClass', None)

                if custom_class:
                    screens.append({
                        "name": custom_class,
                        "type": "uikit",
                        "storyboard": storyboard,
                        "storyboard_id": vc_id
                    })
        except Exception as e:
            print(f"  警告：无法解析 Storyboard {storyboard}: {e}")

    return screens


def scan_swift_files(swift_files: List[str]) -> List[Dict[str, Any]]:
    """扫描 Swift 源文件，识别视图和视图控制器

    Returns:
        List of screen info extracted from Swift files

    TODO: 完整实现需要 Swift AST 解析
    目前使用简单的文本匹配
    """
    screens = []

    for swift_file in swift_files:
        try:
            with open(swift_file, 'r', encoding='utf-8') as f:
                content = f.read()
                lines = content.split('\n')

                # 检测 SwiftUI View
                if 'import SwiftUI' in content:
                    for line in lines:
                        if 'struct' in line and ': View' in line:
                            # 提取结构名称
                            parts = line.split()
                            if 'struct' in parts:
                                idx = parts.index('struct')
                                if idx + 1 < len(parts):
                                    view_name = parts[idx + 1].split(':')[0]
                                    screens.append({
                                        "name": view_name,
                                        "type": "swiftui",
                                        "file": swift_file
                                    })

                # 检测 UIKit ViewController
                if 'UIViewController' in content:
                    for line in lines:
                        if 'class' in line and 'UIViewController' in line:
                            parts = line.split()
                            if 'class' in parts:
                                idx = parts.index('class')
                                if idx + 1 < len(parts):
                                    vc_name = parts[idx + 1].split(':')[0]
                                    screens.append({
                                        "name": vc_name,
                                        "type": "uikit",
                                        "file": swift_file
                                    })
        except Exception as e:
            print(f"  警告：无法读取 {swift_file}: {e}")

    return screens


def scan_resources(project_root: Path) -> Dict[str, List[str]]:
    """扫描资源文件

    Returns:
        Dict with assets, images, localizations

    TODO: 完整实现需要解析 Assets.xcassets 结构
    """
    resources = {
        "assets": [],
        "images": [],
        "localizations": []
    }

    # 扫描 Assets.xcassets
    for assets_dir in project_root.rglob("*.xcassets"):
        resources["assets"].append(str(assets_dir))

        # 扫描 imageset
        for imageset in assets_dir.rglob("*.imageset"):
            image_name = imageset.name.replace('.imageset', '')
            resources["images"].append(image_name)

    # 扫描本地化文件
    for strings_file in project_root.rglob("*.strings"):
        resources["localizations"].append(str(strings_file))

    return resources


def main():
    if len(sys.argv) < 3:
        print("用法: scan_ios_ui.py <ios_project_root> <output_manifest.json>")
        print()
        print("示例:")
        print("  python scan_ios_ui.py ~/Projects/MyApp ./manifest.json")
        sys.exit(1)

    ios_root = Path(sys.argv[1])
    output_path = Path(sys.argv[2])

    if not ios_root.exists():
        print(f"错误：iOS 项目路径不存在: {ios_root}")
        sys.exit(1)

    print(f"扫描 iOS 项目: {ios_root}")
    print()

    # 1. 查找 .xcodeproj
    xcodeproj_list = list(ios_root.rglob("*.xcodeproj"))
    if not xcodeproj_list:
        print("错误：未找到 .xcodeproj 文件")
        sys.exit(1)

    xcodeproj = xcodeproj_list[0]
    print(f"✅ 找到 Xcode 项目: {xcodeproj.name}")

    # 2. 解析项目文件
    swift_files, storyboard_files = parse_xcodeproj(xcodeproj)

    # 3. 检测项目类型
    project_type = detect_project_type(swift_files)
    print(f"✅ 项目类型: {project_type}")
    print()

    # 4. 扫描 Storyboards
    print("扫描 Storyboards...")
    storyboard_screens = scan_storyboards(storyboard_files)
    print(f"  发现 {len(storyboard_screens)} 个 Storyboard 场景")

    # 5. 扫描 Swift 文件
    print("扫描 Swift 文件...")
    swift_screens = scan_swift_files(swift_files)
    print(f"  发现 {len(swift_screens)} 个视图/视图控制器")

    # 6. 扫描资源
    print("扫描资源文件...")
    resources = scan_resources(ios_root)
    print(f"  发现 {len(resources['assets'])} 个 Assets catalog")
    print(f"  发现 {len(resources['images'])} 个图片资源")
    print(f"  发现 {len(resources['localizations'])} 个本地化文件")

    # 7. 合并结果
    all_screens = storyboard_screens + swift_screens

    # 8. 生成 manifest
    manifest = {
        "project_name": xcodeproj.name.replace('.xcodeproj', ''),
        "project_type": project_type,
        "xcodeproj": str(xcodeproj),
        "screens": all_screens,
        "storyboards": storyboard_files,
        "swift_files": swift_files,
        "resources": resources,
        "statistics": {
            "total_screens": len(all_screens),
            "swiftui_screens": len([s for s in all_screens if s['type'] == 'swiftui']),
            "uikit_screens": len([s for s in all_screens if s['type'] == 'uikit']),
            "total_swift_files": len(swift_files),
            "total_storyboards": len(storyboard_files),
            "total_images": len(resources['images'])
        }
    }

    # 9. 写入文件
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    print()
    print(f"✅ Manifest 已生成: {output_path}")
    print()
    print("统计信息:")
    print(f"  总场景数: {manifest['statistics']['total_screens']}")
    print(f"  SwiftUI: {manifest['statistics']['swiftui_screens']}")
    print(f"  UIKit: {manifest['statistics']['uikit_screens']}")
    print(f"  Swift 文件: {manifest['statistics']['total_swift_files']}")
    print(f"  Storyboards: {manifest['statistics']['total_storyboards']}")
    print(f"  图片资源: {manifest['statistics']['total_images']}")


if __name__ == '__main__':
    main()
