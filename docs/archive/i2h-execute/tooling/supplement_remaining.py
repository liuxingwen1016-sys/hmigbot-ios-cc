#!/usr/bin/env python3
"""
i2h-execute 批量补充脚本

用途: 根据 Android 原版自动补充剩余的 references 文档和 scripts 脚本
"""

import os
import shutil
from pathlib import Path

# 路径配置
ANDROID_ROOT = Path("/Users/liuxingwen/Codes/ios2harmony/hmigbot-1.8.0")
IOS_ROOT = Path("/Users/liuxingwen/Codes/ios2harmony/hmigbot-ios")

ANDROID_REFS = ANDROID_ROOT / "migbot/skills/a2h-execute/references"
IOS_REFS = IOS_ROOT / "migbot/skills/i2h-execute/references"

ANDROID_SCRIPTS = ANDROID_ROOT / "migbot/skills/a2h-execute/scripts"
IOS_SCRIPTS = IOS_ROOT / "migbot/skills/i2h-execute/scripts"

# 需要补充的文档
REFS_TO_SUPPLEMENT = [
    "data-prep.md",
    "layout-fidelity.md",
    "resource-facts-handoff.md",
    "stage1-gate-policy.md",
]

# 需要补充的可选文档
OPTIONAL_REFS = [
    "ui-delivery-contract.md",
    "ui-integration-1030.md",
    "phase-a-ondemand.md",
    "skill-binding-override.md",
]

# 需要实现的脚本
SCRIPTS_TO_IMPLEMENT = [
    "verify_slice_wiring.py",
    "lint_execute_coverage.py",
    "validate_runtime_snapshots.py",
    "layout_dims_gate.py",
    "build_writeback.py",
    "stage1_reachability.py",
]

def supplement_reference(filename: str):
    """补充单个 reference 文档"""
    android_file = ANDROID_REFS / filename
    ios_file = IOS_REFS / filename

    if not android_file.exists():
        print(f"⚠️  Android 原版不存在: {filename}")
        return

    if ios_file.exists() and ios_file.stat().st_size > 1000:
        print(f"⏭️  已存在且有内容: {filename}")
        return

    print(f"📄 补充: {filename}")

    # 读取 Android 原版
    content = android_file.read_text(encoding='utf-8')

    # 适配 iOS
    content = content.replace('Android', 'iOS')
    content = content.replace('android', 'ios')
    content = content.replace('a2h-execute', 'i2h-execute')
    content = content.replace('a2h-spec', 'i2h-spec')
    content = content.replace('a2h-plan', 'i2h-plan')
    content = content.replace('a2h-verify', 'i2h-verify')

    # 删除版本信息
    lines = content.split('\n')
    cleaned_lines = []
    skip_next = 0
    for line in lines:
        if skip_next > 0:
            skip_next -= 1
            continue
        if '版本' in line or '更新时间' in line or '适用' in line:
            skip_next = 2
            continue
        if line.strip() == '---' and len(cleaned_lines) > 0 and cleaned_lines[-1].strip() == '':
            # 可能是版本信息前的分隔符
            continue
        cleaned_lines.append(line)

    content = '\n'.join(cleaned_lines)

    # 写入
    ios_file.write_text(content, encoding='utf-8')
    print(f"✅ 完成: {filename}")

def supplement_script(filename: str):
    """补充单个 script"""
    android_file = ANDROID_SCRIPTS / filename
    ios_file = IOS_SCRIPTS / filename

    if not android_file.exists():
        print(f"⚠️  Android 原版不存在: {filename}")
        return

    if ios_file.exists() and ios_file.stat().st_size > 1000:
        print(f"⏭️  已存在且有内容: {filename}")
        return

    print(f"🔧 补充: {filename}")

    # 读取 Android 原版
    content = android_file.read_text(encoding='utf-8')

    # 适配 iOS
    content = content.replace('Android', 'iOS')
    content = content.replace('android', 'ios')
    content = content.replace('a2h-execute', 'i2h-execute')
    content = content.replace('a2h-spec', 'i2h-spec')
    content = content.replace('a2h-plan', 'i2h-plan')

    # 写入
    ios_file.write_text(content, encoding='utf-8')
    ios_file.chmod(0o755)
    print(f"✅ 完成: {filename}")

def main():
    print("=" * 60)
    print("i2h-execute 批量补充工具")
    print("=" * 60)

    # 补充 references
    print("\n📂 补充 References 文档:")
    for ref in REFS_TO_SUPPLEMENT:
        supplement_reference(ref)

    print("\n📂 补充可选 References:")
    for ref in OPTIONAL_REFS:
        supplement_reference(ref)

    # 补充 scripts
    print("\n🔧 补充 Scripts:")
    for script in SCRIPTS_TO_IMPLEMENT:
        supplement_script(script)

    print("\n" + "=" * 60)
    print("✅ 批量补充完成！")
    print("=" * 60)
    print("\n⚠️  注意:")
    print("  1. 自动补充的内容可能需要手动调整")
    print("  2. 请检查 iOS 特定的差异")
    print("  3. 测试所有补充的脚本")
    print("\n下一步:")
    print("  git add .")
    print("  git commit -m 'feat: 批量补充 references 和 scripts'")
    print("  git push origin main")

if __name__ == '__main__':
    main()
