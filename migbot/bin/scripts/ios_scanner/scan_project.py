#!/usr/bin/env python3
"""iOS 项目扫描器 - 用于 i2h-spec Phase A

扫描 iOS 项目，提取：
- Xcode 项目信息
- Swift 文件清单
- SwiftUI View 列表
- UIKit ViewController 列表
- 资源文件
"""
from __future__ import annotations

import os
import json
import re
from pathlib import Path
from typing import Any
from dataclasses import dataclass, field, asdict


@dataclass
class ProjectInfo:
    """iOS 项目信息"""
    project_path: str
    project_name: str
    has_xcodeproj: bool
    has_xcworkspace: bool
    has_package_swift: bool
    swift_files: list[str] = field(default_factory=list)
    swiftui_views: list[str] = field(default_factory=list)
    uikit_vcs: list[str] = field(default_factory=list)
    assets: list[str] = field(default_factory=list)
    storyboards: list[str] = field(default_factory=list)
    total_lines: int = 0


def scan_ios_project(ios_path: str, output_path: str | None = None) -> ProjectInfo:
    """扫描 iOS 项目"""
    ios_root = Path(ios_path)

    if not ios_root.exists():
        raise FileNotFoundError(f"iOS project not found: {ios_path}")

    info = ProjectInfo(
        project_path=str(ios_root),
        project_name=ios_root.name,
        has_xcodeproj=bool(list(ios_root.glob("*.xcodeproj"))),
        has_xcworkspace=bool(list(ios_root.glob("*.xcworkspace"))),
        has_package_swift=(ios_root / "Package.swift").exists(),
    )

    # 扫描所有 Swift 文件
    swift_files = list(ios_root.rglob("*.swift"))

    # 过滤掉测试文件
    swift_files = [
        f for f in swift_files
        if "Tests" not in f.parts and "Test" not in f.name
    ]

    info.swift_files = [str(f.relative_to(ios_root)) for f in swift_files]

    # 统计总行数
    total_lines = 0
    for f in swift_files:
        try:
            total_lines += len(f.read_text(encoding="utf-8").splitlines())
        except Exception:
            pass
    info.total_lines = total_lines

    # 识别 SwiftUI Views 和 UIKit VCs
    for f in swift_files:
        try:
            content = f.read_text(encoding="utf-8")
            rel_path = str(f.relative_to(ios_root))

            # SwiftUI View
            if "import SwiftUI" in content and ": View" in content:
                info.swiftui_views.append(rel_path)

            # UIKit ViewController
            elif "import UIKit" in content and "ViewController" in content:
                info.uikit_vcs.append(rel_path)
        except Exception:
            pass

    # 扫描资源
    assets_dirs = list(ios_root.rglob("*.xcassets"))
    info.assets = [str(d.relative_to(ios_root)) for d in assets_dirs]

    # 扫描 Storyboard
    storyboards = list(ios_root.rglob("*.storyboard")) + list(ios_root.rglob("*.xib"))
    info.storyboards = [str(f.relative_to(ios_root)) for f in storyboards]

    # 保存结果
    if output_path:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(asdict(info), f, indent=2, ensure_ascii=False)

    return info


if __name__ == "__main__":
    import sys
    import argparse

    parser = argparse.ArgumentParser(description="Scan iOS project")
    parser.add_argument("ios_path", help="Path to iOS project")
    parser.add_argument("--output", help="Output JSON file")

    args = parser.parse_args()

    info = scan_ios_project(args.ios_path, args.output)

    print(f"✅ Scanned iOS project: {info.project_name}")
    print(f"   Swift files: {len(info.swift_files)}")
    print(f"   SwiftUI Views: {len(info.swiftui_views)}")
    print(f"   UIKit VCs: {len(info.uikit_vcs)}")
    print(f"   Total lines: {info.total_lines}")

    if args.output:
        print(f"   Output: {args.output}")
