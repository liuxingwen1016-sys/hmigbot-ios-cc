#!/usr/bin/env python3
"""提取 iOS 资源文件（Assets.xcassets + Localizable.strings）

功能：
1. 解析 Assets.xcassets 目录结构
2. 提取图片资源清单
3. 提取颜色资源
4. 解析本地化字符串文件
5. 生成资源映射 JSON

输出：resources.json
{
  "images": [
    {
      "name": "icon_home",
      "path": "Assets.xcassets/icon_home.imageset",
      "files": ["icon_home@1x.png", "icon_home@2x.png", "icon_home@3x.png"],
      "idiom": "universal"
    }
  ],
  "colors": [
    {
      "name": "primaryColor",
      "components": {"red": 0.2, "green": 0.4, "blue": 0.8}
    }
  ],
  "localizations": {
    "en": {...},
    "zh-Hans": {...}
  }
}

注意：
- Assets.xcassets 使用 JSON 配置文件（Contents.json）
- Localizable.strings 是键值对格式
- 需要处理多语言、多设备适配
"""

import sys
import json
import re
from pathlib import Path
from typing import Dict, List, Any, Optional


def parse_assets_catalog(assets_path: Path) -> Dict[str, Any]:
    """解析 Assets.xcassets 目录

    结构：
    Assets.xcassets/
      AppIcon.appiconset/
        Contents.json
        icon-1024.png
      icon_home.imageset/
        Contents.json
        icon_home@1x.png
        icon_home@2x.png
        icon_home@3x.png
      Colors/
        primaryColor.colorset/
          Contents.json

    TODO: 完整实现需要解析所有资源类型
    """
    print(f"解析 Assets Catalog: {assets_path.name}")

    if not assets_path.exists():
        print(f"  错误：路径不存在")
        return {"images": [], "colors": [], "app_icons": []}

    images = []
    colors = []
    app_icons = []

    # 1. 扫描 imagesets
    print("  扫描图片资源...")
    for imageset in assets_path.rglob("*.imageset"):
        image_info = parse_imageset(imageset)
        if image_info:
            images.append(image_info)

    print(f"    发现 {len(images)} 个图片资源")

    # 2. 扫描 colorsets
    print("  扫描颜色资源...")
    for colorset in assets_path.rglob("*.colorset"):
        color_info = parse_colorset(colorset)
        if color_info:
            colors.append(color_info)

    print(f"    发现 {len(colors)} 个颜色资源")

    # 3. 扫描 appiconsets
    print("  扫描应用图标...")
    for appiconset in assets_path.rglob("*.appiconset"):
        icon_info = parse_appiconset(appiconset)
        if icon_info:
            app_icons.append(icon_info)

    print(f"    发现 {len(app_icons)} 个应用图标集")

    return {
        "images": images,
        "colors": colors,
        "app_icons": app_icons
    }


def parse_imageset(imageset_path: Path) -> Optional[Dict[str, Any]]:
    """解析单个 imageset

    Contents.json 示例：
    {
      "images" : [
        {
          "filename" : "icon_home@1x.png",
          "idiom" : "universal",
          "scale" : "1x"
        },
        {
          "filename" : "icon_home@2x.png",
          "idiom" : "universal",
          "scale" : "2x"
        },
        {
          "filename" : "icon_home@3x.png",
          "idiom" : "universal",
          "scale" : "3x"
        }
      ]
    }

    TODO: 完整实现
    """
    contents_json = imageset_path / "Contents.json"

    if not contents_json.exists():
        return None

    try:
        with open(contents_json, 'r', encoding='utf-8') as f:
            data = json.load(f)

        image_name = imageset_path.name.replace('.imageset', '')
        files = []

        for img in data.get('images', []):
            if img.get('filename'):
                files.append({
                    "filename": img['filename'],
                    "scale": img.get('scale', '1x'),
                    "idiom": img.get('idiom', 'universal')
                })

        return {
            "name": image_name,
            "path": str(imageset_path),
            "files": files
        }

    except Exception as e:
        print(f"    警告：解析 {imageset_path.name} 失败 - {e}")
        return None


def parse_colorset(colorset_path: Path) -> Optional[Dict[str, Any]]:
    """解析单个 colorset

    Contents.json 示例：
    {
      "colors" : [
        {
          "color" : {
            "color-space" : "srgb",
            "components" : {
              "red" : "0.200",
              "green" : "0.400",
              "blue" : "0.800",
              "alpha" : "1.000"
            }
          },
          "idiom" : "universal"
        }
      ]
    }

    TODO: 完整实现，支持暗黑模式等
    """
    contents_json = colorset_path / "Contents.json"

    if not contents_json.exists():
        return None

    try:
        with open(contents_json, 'r', encoding='utf-8') as f:
            data = json.load(f)

        color_name = colorset_path.name.replace('.colorset', '')
        colors = data.get('colors', [])

        if colors:
            color_data = colors[0].get('color', {})
            components = color_data.get('components', {})

            return {
                "name": color_name,
                "path": str(colorset_path),
                "components": components,
                "color_space": color_data.get('color-space', 'srgb')
            }

    except Exception as e:
        print(f"    警告：解析 {colorset_path.name} 失败 - {e}")
        return None


def parse_appiconset(appiconset_path: Path) -> Optional[Dict[str, Any]]:
    """解析应用图标集

    TODO: 完整实现
    """
    contents_json = appiconset_path / "Contents.json"

    if not contents_json.exists():
        return None

    try:
        with open(contents_json, 'r', encoding='utf-8') as f:
            data = json.load(f)

        icons = []
        for img in data.get('images', []):
            if img.get('filename'):
                icons.append({
                    "filename": img['filename'],
                    "size": img.get('size'),
                    "idiom": img.get('idiom'),
                    "scale": img.get('scale')
                })

        return {
            "name": appiconset_path.name.replace('.appiconset', ''),
            "path": str(appiconset_path),
            "icons": icons
        }

    except Exception as e:
        print(f"    警告：解析 {appiconset_path.name} 失败 - {e}")
        return None


def parse_localizable_strings(strings_file: Path) -> Dict[str, str]:
    """解析 Localizable.strings 文件

    格式：
    /* Comment */
    "key1" = "value1";
    "key2" = "value2";

    TODO: 完整实现需要处理：
    - 转义字符
    - 多行字符串
    - 注释
    - 编码问题
    """
    print(f"解析本地化文件: {strings_file.name}")

    strings = {}

    try:
        with open(strings_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # 简单正则匹配：
        # "key" = "value";
        pattern = r'"([^"]+)"\s*=\s*"([^"]+)";'
        matches = re.findall(pattern, content)

        for key, value in matches:
            strings[key] = value

        print(f"  发现 {len(strings)} 个本地化字符串")

    except Exception as e:
        print(f"  错误：{e}")

    return strings


def scan_localizations(project_root: Path) -> Dict[str, Dict[str, str]]:
    """扫描所有本地化文件

    结构：
    en.lproj/
      Localizable.strings
    zh-Hans.lproj/
      Localizable.strings

    TODO: 完整实现
    """
    print("扫描本地化文件...")

    localizations = {}

    for lproj in project_root.rglob("*.lproj"):
        language = lproj.name.replace('.lproj', '')
        print(f"  语言: {language}")

        strings_file = lproj / "Localizable.strings"
        if strings_file.exists():
            localizations[language] = parse_localizable_strings(strings_file)

    return localizations


def main():
    if len(sys.argv) < 3:
        print("用法: extract_ios_resources.py <ios_project_root> <output_resources.json>")
        print()
        print("功能:")
        print("  - 解析 Assets.xcassets（图片、颜色、图标）")
        print("  - 解析 Localizable.strings（多语言）")
        print()
        print("示例:")
        print("  python extract_ios_resources.py ~/Projects/MyApp ./resources.json")
        sys.exit(1)

    project_root = Path(sys.argv[1])
    output_path = Path(sys.argv[2])

    if not project_root.exists():
        print(f"错误：项目路径不存在: {project_root}")
        sys.exit(1)

    print(f"提取 iOS 资源: {project_root}")
    print()

    resources = {
        "assets": [],
        "localizations": {}
    }

    # 1. 扫描 Assets.xcassets
    assets_catalogs = list(project_root.rglob("*.xcassets"))
    print(f"发现 {len(assets_catalogs)} 个 Assets Catalog")
    print()

    for assets_path in assets_catalogs:
        catalog_data = parse_assets_catalog(assets_path)
        resources["assets"].append({
            "path": str(assets_path),
            "name": assets_path.name,
            "images": catalog_data["images"],
            "colors": catalog_data["colors"],
            "app_icons": catalog_data["app_icons"]
        })

    # 2. 扫描本地化文件
    print()
    resources["localizations"] = scan_localizations(project_root)

    # 3. 统计
    total_images = sum(len(a["images"]) for a in resources["assets"])
    total_colors = sum(len(a["colors"]) for a in resources["assets"])
    total_languages = len(resources["localizations"])

    print()
    print("统计信息:")
    print(f"  图片资源: {total_images}")
    print(f"  颜色资源: {total_colors}")
    print(f"  本地化语言: {total_languages}")

    # 4. 写入输出
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(resources, f, indent=2, ensure_ascii=False)

    print()
    print(f"✅ 资源清单已生成: {output_path}")


if __name__ == '__main__':
    main()
