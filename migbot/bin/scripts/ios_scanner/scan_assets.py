#!/usr/bin/env python3
"""资源详细扫描器

扫描 iOS 资源文件的详细信息
"""
from __future__ import annotations

import os
import json
from pathlib import Path
import argparse
from PIL import Image


def scan_assets_detailed(assets_path: str, output_path: str) -> dict:
    """详细扫描 Assets.xcassets"""
    results = {
        "images": [],
        "colors": [],
        "data": [],
        "total_size_bytes": 0
    }

    assets_dir = Path(assets_path)
    if not assets_dir.exists():
        return results

    # 扫描 imagesets
    for imageset in assets_dir.rglob("*.imageset"):
        name = imageset.stem

        # 读取 Contents.json
        contents_file = imageset / "Contents.json"
        image_info = {
            "name": name,
            "path": str(imageset.relative_to(assets_dir.parent)),
            "files": [],
            "sizes": {}
        }

        if contents_file.exists():
            with open(contents_file) as f:
                contents = json.load(f)

            # 收集图片文件
            for img_item in contents.get("images", []):
                filename = img_item.get("filename")
                if filename:
                    img_path = imageset / filename
                    if img_path.exists():
                        image_info["files"].append(filename)

                        # 获取图片尺寸
                        try:
                            with Image.open(img_path) as img:
                                scale = img_item.get("scale", "1x")
                                image_info["sizes"][scale] = {
                                    "width": img.width,
                                    "height": img.height,
                                    "size_bytes": img_path.stat().st_size
                                }
                                results["total_size_bytes"] += img_path.stat().st_size
                        except Exception:
                            pass

        results["images"].append(image_info)

    # 扫描 colorsets
    for colorset in assets_dir.rglob("*.colorset"):
        name = colorset.stem
        contents_file = colorset / "Contents.json"

        color_info = {
            "name": name,
            "path": str(colorset.relative_to(assets_dir.parent)),
            "values": {}
        }

        if contents_file.exists():
            with open(contents_file) as f:
                contents = json.load(f)

            for color_item in contents.get("colors", []):
                appearance = color_item.get("appearances", [{}])[0].get("value", "light")
                color = color_item.get("color", {})
                components = color.get("components", {})

                if components:
                    r = int(float(components.get("red", "0")) * 255)
                    g = int(float(components.get("green", "0")) * 255)
                    b = int(float(components.get("blue", "0")) * 255)
                    a = float(components.get("alpha", "1"))

                    color_info["values"][appearance] = {
                        "hex": f"#{r:02X}{g:02X}{b:02X}",
                        "rgba": f"rgba({r},{g},{b},{a})"
                    }

        results["colors"].append(color_info)

    # 保存结果
    if output_path:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(results, f, indent=2)

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scan iOS assets in detail")
    parser.add_argument("assets_path", help="Path to Assets.xcassets")
    parser.add_argument("--output", help="Output JSON file")

    args = parser.parse_args()

    results = scan_assets_detailed(args.assets_path, args.output)

    print(f"✅ Scanned assets:")
    print(f"   Images: {len(results['images'])}")
    print(f"   Colors: {len(results['colors'])}")
    print(f"   Total size: {results['total_size_bytes'] / 1024:.1f} KB")

    if args.output:
        print(f"   Output: {args.output}")
