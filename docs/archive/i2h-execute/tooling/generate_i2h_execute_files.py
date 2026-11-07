#!/usr/bin/env python3
"""
i2h-execute 文件批量生成脚本

用途: 为剩余的 references 和 scripts 生成框架文件
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).parent
REFERENCES_DIR = BASE_DIR / "migbot/skills/i2h-execute/references"
SCRIPTS_DIR = BASE_DIR / "migbot/skills/i2h-execute/scripts"

# ============================================================================
# References 定义
# ============================================================================

REFERENCES = {
    # 已创建
    "agent-prompts/_common.md": "✅ 已创建",
    "agent-prompts/1-converter.md": "✅ 已创建",
    "agent-prompts/2-batch-closer.md": "✅ 已创建",
    "agent-prompts/3-worker.md": "✅ 已创建",
    "agent-prompts/4-slice-worker.md": "✅ 已创建",
    "agent-prompts/8-group-closer.md": "✅ 已创建",
    "build-loop.md": "✅ 已创建",
    "brief-schemas.md": "✅ 已创建",

    # 待创建（生成框架）
    "stage1-dispatch.md": "Stage 1 派发规则",
    "stage1-wiring.md": "Stage 1 接线规则",
    "entry-navigation-setup.md": "入口装配流程",
    "stage-0-resources.md": "资源校验规则",
    "runtime-snapshot-handoff.md": "运行时快照交接",
    "resource-facts-handoff.md": "资源事实交接",
    "execution-discipline.md": "执行纪律",
    "stage1-gate-policy.md": "Stage 1 门禁策略",
    "layout-fidelity.md": "布局保真规则",
    "data-prep.md": "数据准备规则",
}

# ============================================================================
# Scripts 定义
# ============================================================================

SCRIPTS = {
    # 核心工具 (P0)
    "apply_writeback.py": "应用 writeback manifest",
    "sweep_resources.py": "资源 sweep",
    "verify_slice_wiring.py": "验证 Slice 接线完成性",
    "lint_execute_coverage.py": "执行覆盖率检查",
    "validate_runtime_snapshots.py": "验证运行时快照",
    "layout_dims_gate.py": "布局尺寸门禁",
    "build_writeback.py": "构建 writeback manifest",

    # 其他工具 (P1)
    "stage1_reachability.py": "Stage 1 可达性检查",
    "stage1_visual_scope.py": "Stage 1 视觉范围",
    "stage1_visual_report.py": "Stage 1 视觉报告",
    "stage1_preview.py": "Stage 1 预览",
    "ui_stage1_gate.py": "UI Stage 1 门禁",
    "audit_interaction_candidates.py": "交互候选审查",

    # UI 相关 (P2)
    "ui_dispatch.py": "UI 派发",
    "ui_delivery_gate.py": "UI 交付门禁",
    "ui_delivery_scope.py": "UI 交付范围",
    "ui_delivery_inputs.py": "UI 交付输入",
    "ui_delivery_validation.py": "UI 交付验证",
    "ui_consumption.py": "UI 消费",
    "ui_isolation_audit.py": "UI 隔离审查",
    "ui_layout_lint.py": "UI 布局检查",
    "ui_relationships.py": "UI 关系",
}

# ============================================================================
# 模板
# ============================================================================

REFERENCE_TEMPLATE = """# {title}

**用途**: {description}
**加载时机**: {when_to_load}

---

## §1 概述

{overview}

---

## §2 规则

{rules}

---

## §3 示例

{examples}

---

## §4 常见问题

{faq}

---

**版本**: 1.0
**更新时间**: 2024-11-03
**适用**: i2h-execute
"""

SCRIPT_TEMPLATE = """#!/usr/bin/env python3
\"\"\"
{title}

用途: {description}
\"\"\"

import argparse
import json
import sys
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description='{description}')
    parser.add_argument('--project-root', required=True, help='项目根目录')

    # TODO: 添加其他参数

    args = parser.parse_args()

    print(f"执行 {title}...")
    print(f"项目根目录: {{args.project_root}}")

    # TODO: 实现具体逻辑

    print("✅ 完成")
    return 0

if __name__ == '__main__':
    sys.exit(main())
"""

# ============================================================================
# 生成函数
# ============================================================================

def generate_reference(name: str, description: str):
    """生成 reference 文件框架"""
    file_path = REFERENCES_DIR / name

    if file_path.exists():
        print(f"⏭️  跳过（已存在）: {name}")
        return

    file_path.parent.mkdir(parents=True, exist_ok=True)

    content = REFERENCE_TEMPLATE.format(
        title=name.replace('.md', '').replace('-', ' ').title(),
        description=description,
        when_to_load="待定义",
        overview="待补充",
        rules="待补充",
        examples="待补充",
        faq="待补充"
    )

    file_path.write_text(content)
    print(f"✅ 创建: {name}")

def generate_script(name: str, description: str):
    """生成 script 文件框架"""
    file_path = SCRIPTS_DIR / name

    if file_path.exists():
        print(f"⏭️  跳过（已存在）: {name}")
        return

    file_path.parent.mkdir(parents=True, exist_ok=True)

    content = SCRIPT_TEMPLATE.format(
        title=name.replace('.py', '').replace('_', ' ').title(),
        description=description
    )

    file_path.write_text(content)
    file_path.chmod(0o755)  # 添加可执行权限
    print(f"✅ 创建: {name}")

def generate_all():
    """生成所有文件"""
    print("=" * 60)
    print("开始生成 i2h-execute 文件框架")
    print("=" * 60)

    # 生成 References
    print("\n📂 生成 References:")
    for name, desc in REFERENCES.items():
        if desc.startswith("✅"):
            print(f"⏭️  跳过: {name} ({desc})")
        else:
            generate_reference(name, desc)

    # 生成 Scripts
    print("\n📂 生成 Scripts:")
    for name, desc in SCRIPTS.items():
        generate_script(name, desc)

    # 生成总结
    print("\n" + "=" * 60)
    print("生成完成！")
    print("=" * 60)

    references_created = len([d for d in REFERENCES.values() if not d.startswith("✅")])
    scripts_created = len(SCRIPTS)

    print(f"\n📊 统计:")
    print(f"  - References: {references_created} 个新建（共 {len(REFERENCES)} 个）")
    print(f"  - Scripts: {scripts_created} 个新建")
    print(f"  - 总计: {references_created + scripts_created} 个新文件")

    print(f"\n📍 位置:")
    print(f"  - References: {REFERENCES_DIR}")
    print(f"  - Scripts: {SCRIPTS_DIR}")

    print(f"\n⚠️  注意:")
    print(f"  这些是框架文件，需要根据 Android 原版补充具体内容。")
    print(f"  参考: hmigbot-1.8.0/migbot/skills/a2h-execute/")

if __name__ == '__main__':
    generate_all()
