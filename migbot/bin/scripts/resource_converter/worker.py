#!/usr/bin/env python3
"""资源转换器 - 后台 Worker

转换 iOS 资源到 HarmonyOS 格式
"""
from __future__ import annotations

import os
import json
import shutil
import re
from pathlib import Path
import argparse


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".pdf", ".svg", ".webp", ".gif"}


def _component(value: object, default: float = 0.0) -> float:
    """Decode Xcode color components (0..1, 0..255, or hex strings)."""
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        raw = str(value or "").strip()
        if raw.startswith("#"):
            return int(raw[1:3], 16) / 255.0
        try:
            number = float(raw)
        except ValueError:
            return default
    return max(0.0, min(1.0, number / 255.0 if number > 1 else number))


def _hex_color(components: dict) -> str:
    channels = [_component(components.get(channel, 0.0)) for channel in ("red", "green", "blue")]
    return "#" + "".join(f"{round(channel * 255):02X}" for channel in channels)


def _strings_file(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    # Handles escaped quotes and values containing '='. Comments are ignored.
    pattern = re.compile(r'"((?:\\.|[^"\\])*)"\s*=\s*"((?:\\.|[^"\\])*)"\s*;')
    def decode(value: str) -> str:
        try:
            return json.loads('"' + value + '"')
        except json.JSONDecodeError:
            return value.replace(r'\"', '"').replace(r'\\', '\\')
    return {decode(key): decode(value) for key, value in pattern.findall(text)}


def convert_assets(ios_path: str, output_path: str) -> dict:
    """转换 Assets.xcassets"""
    results = {
        "images": [],
        "colors": [],
        "data": []
    }

    assets_dir = Path(ios_path) / "Assets.xcassets"
    asset_roots = [assets_dir] if assets_dir.is_dir() else sorted(Path(ios_path).rglob("*.xcassets"))
    if not asset_roots:
        return results

    media_dir = Path(output_path) / "base" / "media"
    media_dir.mkdir(parents=True, exist_ok=True)

    # Convert every declared image variant, including PDF/SVG/vector assets.
    # Xcode often reuses the same filename in separate image sets, so avoid
    # silent overwrites by making the destination deterministic.
    used_names: set[str] = set()
    imagesets = [imageset for root in asset_roots for imageset in sorted(root.rglob("*.imageset"))]
    for imageset in imagesets:
        name = imageset.stem
        contents_file = imageset / "Contents.json"
        try:
            contents = json.loads(contents_file.read_text(encoding="utf-8")) if contents_file.is_file() else {}
        except json.JSONDecodeError:
            contents = {}
        declared = [item.get("filename") for item in contents.get("images", []) if isinstance(item, dict)]
        candidates = [imageset / filename for filename in declared if filename]
        if not candidates:
            candidates = [path for path in sorted(imageset.iterdir()) if path.suffix.lower() in IMAGE_SUFFIXES]
        for index, img in enumerate(candidates):
            if not img.is_file() or img.suffix.lower() not in IMAGE_SUFFIXES:
                continue
            filename = img.name
            if filename in used_names:
                filename = f"{name}_{index}{img.suffix.lower()}"
            used_names.add(filename)
            dest = media_dir / filename
            shutil.copy2(img, dest)
            results["images"].append({"asset": name, "source": str(img), "output": str(dest.relative_to(output_path))})

    # 转换颜色资源
    element_dir = Path(output_path) / "base" / "element"
    element_dir.mkdir(parents=True, exist_ok=True)

    colors = {}
    colorsets = [colorset for root in asset_roots for colorset in sorted(root.rglob("*.colorset"))]
    for colorset in colorsets:
        name = colorset.stem

        # 读取 Contents.json
        contents_file = colorset / "Contents.json"
        if contents_file.exists():
            with open(contents_file) as f:
                contents = json.load(f)

            variants = []
            for item in contents.get("colors", []):
                color = item.get("color", {})
                components = color.get("components", {})
                if components:
                    value = _hex_color(components)
                    appearances = item.get("appearances", [])
                    variant = {"value": value, "appearances": appearances}
                    variants.append(variant)
                    if not appearances:
                        colors[name] = value
                    elif any(a.get("value") == "luminosity" and a.get("appearance") == "luminosity-dark" for a in appearances):
                        if not isinstance(colors.get(name), dict):
                            colors[name] = {"light": colors.get(name, value)}
                        colors[name]["dark"] = value
                    else:
                        if not isinstance(colors.get(name), dict):
                            colors[name] = {"light": colors.get(name, value)}
                        colors[name]["light"] = value
            if variants:
                if isinstance(colors.get(name), dict):
                    colors[name].setdefault("light", colors[name].get("light", variants[0]["value"]))
                    colors[name]["variants"] = variants
                results["colors"].append({"name": name, "variants": variants})

    # 生成 color.json
    if colors:
        color_file = element_dir / "color.json"
        with open(color_file, "w") as f:
            json.dump({"color": [{"name": name, "value": value} for name, value in colors.items()]}, f, indent=2)

    return results


def convert_strings(ios_path: str, output_path: str) -> dict:
    """转换本地化字符串"""
    results = {"strings": [], "localizations": {}}

    element_dir = Path(output_path) / "base" / "element"
    element_dir.mkdir(parents=True, exist_ok=True)

    # 查找 Localizable.strings
    strings_files = list(Path(ios_path).rglob("Localizable.strings"))

    if not strings_files:
        return results

    # Merge all locales deterministically.  The base resource keeps the
    # default language while the report preserves every locale for later
    # qualifier-specific emission.
    strings = {}
    for strings_file in sorted(strings_files):
        locale = next((part[:-6] for part in strings_file.parts if part.endswith(".lproj")), "base")
        parsed = _strings_file(strings_file)
        results["localizations"][locale] = sorted(parsed)
        if locale in {"base", "Base"} or not strings:
            strings.update(parsed)
        for key in parsed:
            if key not in results["strings"]:
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
