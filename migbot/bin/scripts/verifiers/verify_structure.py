#!/usr/bin/env python3
"""Verifier: 结构验证

验证鸿蒙项目结构是否完整
"""
from __future__ import annotations

import os
import sys
import json
from pathlib import Path


def verify_structure(hos_path: str) -> dict:
    """验证鸿蒙项目结构"""
    results = {
        "passed": True,
        "checks": [],
        "errors": [],
        "warnings": []
    }

    # 检查必需目录
    required_dirs = [
        "entry/src/main/ets",
        "entry/src/main/ets/pages",
        "entry/src/main/resources",
    ]

    for dir_path in required_dirs:
        full_path = os.path.join(hos_path, dir_path)
        check = {
            "name": f"目录存在: {dir_path}",
            "passed": os.path.isdir(full_path)
        }
        results["checks"].append(check)

        if not check["passed"]:
            results["passed"] = False
            results["errors"].append(f"缺少目录: {dir_path}")

    # 检查必需文件
    required_files = [
        "entry/src/main/module.json5",
        "entry/src/main/resources/base/profile/main_pages.json",
        "oh-package.json5",
    ]

    for file_path in required_files:
        full_path = os.path.join(hos_path, file_path)
        check = {
            "name": f"文件存在: {file_path}",
            "passed": os.path.isfile(full_path)
        }
        results["checks"].append(check)

        if not check["passed"]:
            results["passed"] = False
            results["errors"].append(f"缺少文件: {file_path}")

    # 检查页面文件
    pages_dir = os.path.join(hos_path, "entry/src/main/ets/pages")
    if os.path.exists(pages_dir):
        page_files = list(Path(pages_dir).glob("*.ets"))
        check = {
            "name": f"页面文件数量",
            "passed": len(page_files) > 0,
            "count": len(page_files)
        }
        results["checks"].append(check)

        if not check["passed"]:
            results["warnings"].append("没有页面文件")

    return results


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: verify_structure.py <hos_path>")
        sys.exit(1)

    hos_path = sys.argv[1]
    results = verify_structure(hos_path)

    print("📊 结构验证结果:")
    print(f"   状态: {'✅ 通过' if results['passed'] else '❌ 失败'}")
    print(f"   检查项: {len(results['checks'])}")
    print(f"   错误: {len(results['errors'])}")
    print(f"   警告: {len(results['warnings'])}")

    if results['errors']:
        print("\n错误详情:")
        for error in results['errors']:
            print(f"   ❌ {error}")

    if results['warnings']:
        print("\n警告:")
        for warning in results['warnings']:
            print(f"   ⚠️  {warning}")

    # 保存报告
    report_path = os.path.join(os.path.dirname(hos_path), "spec/verify/structure-report.json")
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\n报告已保存: {report_path}")

    sys.exit(0 if results['passed'] else 1)
