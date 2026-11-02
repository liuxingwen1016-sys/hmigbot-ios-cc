#!/usr/bin/env python3
"""功能分析器

分析 iOS 代码结构，识别功能模块
"""
from __future__ import annotations

import os
import json
import re
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import List
import argparse


@dataclass
class FeatureModule:
    """功能模块"""
    id: str
    name: str
    directory: str
    files: List[str] = field(default_factory=list)
    complexity: str = "medium"  # low, medium, high
    technologies: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)


def analyze_features(ios_path: str, output_path: str) -> dict:
    """分析功能模块"""
    ios_root = Path(ios_path)
    features = []

    # 预定义的功能模块模式
    feature_patterns = {
        "Data": "数据管理",
        "Services": "系统服务",
        "Navigation": "导航",
        "Network": "网络",
        "Storage": "存储",
        "Auth": "认证",
        "UI": "UI组件",
    }

    feature_id_counter = 1

    # 扫描目录结构
    for pattern_dir, pattern_name in feature_patterns.items():
        candidates = list(ios_root.rglob(pattern_dir))

        for candidate in candidates:
            if not candidate.is_dir():
                continue

            # 收集该目录下的 Swift 文件
            swift_files = list(candidate.rglob("*.swift"))
            if not swift_files:
                continue

            feature = FeatureModule(
                id=f"F{feature_id_counter:03d}",
                name=pattern_name,
                directory=str(candidate.relative_to(ios_root)),
                files=[str(f.relative_to(ios_root)) for f in swift_files]
            )

            # 分析技术栈
            for swift_file in swift_files:
                try:
                    content = swift_file.read_text(encoding="utf-8")

                    # 检测技术
                    if "import SwiftData" in content:
                        if "SwiftData" not in feature.technologies:
                            feature.technologies.append("SwiftData")

                    if "import CoreData" in content:
                        if "CoreData" not in feature.technologies:
                            feature.technologies.append("CoreData")

                    if "@AppStorage" in content:
                        if "AppStorage" not in feature.technologies:
                            feature.technologies.append("AppStorage")

                    if "URLSession" in content:
                        if "URLSession" not in feature.technologies:
                            feature.technologies.append("URLSession")

                    if "import Combine" in content:
                        if "Combine" not in feature.technologies:
                            feature.technologies.append("Combine")

                except Exception:
                    pass

            # 评估复杂度
            total_lines = sum(
                len(f.read_text(encoding="utf-8").splitlines())
                for f in swift_files
            )

            if total_lines < 100:
                feature.complexity = "low"
            elif total_lines > 500:
                feature.complexity = "high"
            else:
                feature.complexity = "medium"

            features.append(feature)
            feature_id_counter += 1

    # 生成结果
    result = {
        "total_features": len(features),
        "features": [asdict(f) for f in features]
    }

    # 保存
    if output_path:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze iOS features")
    parser.add_argument("ios_path", help="Path to iOS project")
    parser.add_argument("--output", help="Output JSON file")

    args = parser.parse_args()

    result = analyze_features(args.ios_path, args.output)

    print(f"✅ Analyzed features:")
    print(f"   Total: {result['total_features']}")

    for feature in result["features"]:
        print(f"   {feature['id']}: {feature['name']} ({feature['complexity']})")
        if feature['technologies']:
            print(f"      Technologies: {', '.join(feature['technologies'])}")

    if args.output:
        print(f"   Output: {args.output}")
