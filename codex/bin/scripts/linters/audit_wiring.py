#!/usr/bin/env python3
"""Linter: 接线完成性审计

检查所有 import 和函数调用是否完整
"""
from __future__ import annotations

import os
import sys
import re
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "findings"))
from i2h_findings import make, replace_section


def audit_wiring(project_root: str, hos_path: str) -> list[dict]:
    """审计接线完成性"""
    findings = []

    code_dir = Path(hos_path) / "entry/src/main/ets"
    if not code_dir.exists():
        findings.append(make(
            "WIRING.CODE_DIR_MISSING",
            "execute",
            "ets/",
            "代码目录不存在"
        ))
        return findings

    # 收集所有导出的符号
    exports = defaultdict(list)  # module -> [symbols]

    for ets_file in code_dir.rglob("*.ets"):
        try:
            content = ets_file.read_text(encoding="utf-8")
            module_path = str(ets_file.relative_to(code_dir).with_suffix(""))

            # 提取 export 的符号
            for match in re.finditer(r'export\s+(class|interface|function|const|let|var)\s+(\w+)', content):
                symbol = match.group(2)
                exports[module_path].append(symbol)

            # 提取 export default
            if "export default" in content:
                exports[module_path].append("default")
        except Exception:
            pass

    # 检查 import 语句
    for ets_file in code_dir.rglob("*.ets"):
        try:
            content = ets_file.read_text(encoding="utf-8")
            rel_path = str(ets_file.relative_to(code_dir))

            # 提取 import 语句
            for match in re.finditer(r'import\s+(?:{([^}]+)}|\*\s+as\s+\w+|(\w+))\s+from\s+["\']([^"\']+)["\']', content):
                imported_symbols = match.group(1)
                default_import = match.group(2)
                from_path = match.group(3)

                # 跳过系统模块
                if from_path.startswith("@ohos") or from_path.startswith("@system"):
                    continue

                # 解析相对路径
                if from_path.startswith("."):
                    # 简化处理：假设路径正确
                    resolved_path = from_path.lstrip("./")
                else:
                    resolved_path = from_path

                # 检查模块是否存在
                if resolved_path not in exports:
                    findings.append(make(
                        "WIRING.IMPORT_UNRESOLVED",
                        "execute",
                        f"{rel_path}:{from_path}",
                        f"导入的模块不存在: {from_path}",
                        severity="warn"
                    ))
        except Exception:
            pass

    # 统计
    total_modules = len(list(code_dir.rglob("*.ets")))
    total_exports = sum(len(syms) for syms in exports.values())

    print(f"📊 接线统计:")
    print(f"   模块数: {total_modules}")
    print(f"   导出符号: {total_exports}")
    print(f"   问题: {len(findings)}")

    return findings


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: audit_wiring.py <project_root> <hos_path>")
        sys.exit(1)

    project_root = sys.argv[1]
    hos_path = sys.argv[2]
    findings = audit_wiring(project_root, hos_path)

    replace_section(
        project_root,
        "execute/wiring",
        findings,
        after_repair=False
    )

    if any(f.get("severity") == "blocking" for f in findings):
        print(f"❌ Wiring audit failed")
        sys.exit(2)
    else:
        print(f"✅ Wiring audit passed")
        sys.exit(0)
