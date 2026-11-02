#!/usr/bin/env python3
"""资源转换器 - 后台 Worker

转换 iOS 资源到 HarmonyOS 格式
"""
from __future__ import annotations

import os
import json
import shutil
from pathlib import Path
import argparse


def convert_assets(ios_path: str, output_path: str) -> dict:
    """转换 Assets.xcassets"""
    results = {
        "images": [],
        "colors": [],
        "data": []
    }

    assets_dir = Path(ios_path) / "Assets.xcassets"
    if not assets_dir.exists():
        # 尝试查找其他位置
        candidates = list(Path(ios_path).rglob("*.xcassets"))
        if candidates:
            assets_dir = candidates[0]
        else:
            return results

    media_dir = Path(output_path) / "base" / "media"
    media_dir.mkdir(parents=True, exist_ok=True)

    # 转换图片资源
    for imageset in assets_dir.rglob("*.imageset"):
        name = imageset.stem

        # 查找图片文件
        for img in imageset.glob("*.png"):
            # 复制到 media/
            dest = media_dir / img.name
            shutil.copy2(img, dest)
            results["images"].append(str(dest.relative_to(output_path)))

        for img in imageset.glob("*.jpg"):
            dest = media_dir / img.name
            shutil.copy2(img, dest)
            results["images"].append(str(dest.relative_to(output_path)))

    # 转换颜色资源
    element_dir = Path(output_path) / "base" / "element"
    element_dir.mkdir(parents=True, exist_ok=True)

    colors = {}
    for colorset in assets_dir.rglob("*.colorset"):
        name = colorset.stem

        # 读取 Contents.json
        contents_file = colorset / "Contents.json"
        if contents_file.exists():
            with open(contents_file) as f:
                contents = json.load(f)

            # 提取颜色值
            for item in contents.get("colors", []):
                color = item.get("color", {})
                components = color.get("components", {})
                if components:
                    # 转换为 HEX
                    r = int(float(components.get("red", "0")) * 255)
                    g = int(float(components.get("green", "0")) * 255)
                    b = int(float(components.get("blue", "0")) * 255)
                    hex_color = f"#{r:02X}{g:02X}{b:02X}"
                    colors[name] = hex_color
                    results["colors"].append(name)

    # 生成 color.json
    if colors:
        color_file = element_dir / "color.json"
        with open(color_file, "w") as f:
            json.dump({"color": [
                {"name": name, "value": value}
                for name, value in colors.items()
            ]}, f, indent=2)

    return results


def convert_strings(ios_path: str, output_path: str) -> dict:
    """转换本地化字符串"""
    results = {"strings": []}

    element_dir = Path(output_path) / "base" / "element"
    element_dir.mkdir(parents=True, exist_ok=True)

    # 查找 Localizable.strings
    strings_files = list(Path(ios_path).rglob("Localizable.strings"))

    if not strings_files:
        return results

    # 读取第一个
    strings_file = strings_files[0]
    strings = {}

    with open(strings_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("//"):
                continue

            # 解析 "key" = "value";
            if "=" in line:
                key, value = line.split("=", 1)
                key = key.strip().strip('"')
                value = value.strip().rstrip(";").strip().strip('"')
                strings[key] = value
                results["strings"].append(key)

    # 生成 string.json
    if strings:
        string_file = element_dir / "string.json"
        with open(string_file, "w", encoding="utf-8") as f:
            json.dump({"string": [
                {"name": name, "value": value}
                for name, value in strings.items()
            ]}, f, indent=2, ensure_ascii=False)

    return results


def main():
    parser = argparse.ArgumentParser(description="Resource converter worker")
    parser.add_argument("--ios", required=True, help="iOS project path")
    parser.add_argument("--output", required=True, help="Output path")
    parser.add_argument("--daemon", action="store_true", help="Run as daemon")

    args = parser.parse_args()

    print(f"🔄 Converting resources from {args.ios}")

    # 转换资源
    assets_result = convert_assets(args.ios, args.output)
    strings_result = convert_strings(args.ios, args.output)

    # 汇总
    total_images = len(assets_result["images"])
    total_colors = len(assets_result["colors"])
    total_strings = len(strings_result["strings"])

    print(f"✅ Resource conversion complete:")
    print(f"   Images: {total_images}")
    print(f"   Colors: {total_colors}")
    print(f"   Strings: {total_strings}")

    # 保存报告
    report = {
        "images": total_images,
        "colors": total_colors,
        "strings": total_strings,
        "assets": assets_result,
        "strings_data": strings_result
    }

    report_file = Path(args.output).parent / "resource-conversion-report.json"
    with open(report_file, "w") as f:
        json.dump(report, f, indent=2)

    print(f"   Report: {report_file}")


if __name__ == "__main__":
    main()
