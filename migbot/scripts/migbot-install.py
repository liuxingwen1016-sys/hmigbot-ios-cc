#!/usr/bin/env python3
"""migbot iOS 版本安装脚本 - 完整版

关键：
1. 只复制 i2h-* 命令和 skills
2. 创建 .claude 目录并复制 commands 和 skills
3. 支持重复执行，保留用户配置
4. 自动清理旧的 a2h 文件
"""
from __future__ import annotations

import os
import sys
import json
import shutil
import argparse
from pathlib import Path


def install_migbot(project_path: str, ios_path: str = None, repo_root: str = None):
    """安装 migbot 到项目"""
    project_root = Path(project_path).resolve()

    if not project_root.exists():
        print(f"❌ 项目路径不存在: {project_path}")
        sys.exit(1)

    if repo_root is None:
        # 脚本所在的 hmigbot-ios 目录
        repo_root = Path(__file__).parent.parent.parent

    # 检测是否是升级安装
    is_upgrade = (project_root / ".migbot" / "config.json").exists()

    if is_upgrade:
        print(f"🔄 升级 migbot: {project_root}")
    else:
        print(f"📦 安装 migbot 到: {project_root}")

    print(f"📦 源仓库: {repo_root}")

    # ============ 核心：创建 .claude 目录 ============
    claude_dir = project_root / ".claude"
    claude_dir.mkdir(exist_ok=True)

    if not is_upgrade:
        print(f"✅ 创建 .claude 目录: {claude_dir}")

    # ============ 清理旧的 a2h 和其他无关文件 ============
    if is_upgrade and claude_dir.exists():
        print("🧹 清理旧文件...")

        # 清理 commands 中的 a2h 和 migbot 命令
        commands_dir = claude_dir / "commands"
        if commands_dir.exists():
            for cmd in commands_dir.glob("a2h-*.md"):
                cmd.unlink()
            for cmd in commands_dir.glob("migbot-*.md"):
                cmd.unlink()

        # 清理 skills 中的非 i2h skills
        skills_dir = claude_dir / "skills"
        if skills_dir.exists():
            for skill in skills_dir.iterdir():
                if skill.is_dir() and not skill.name.startswith("i2h-"):
                    shutil.rmtree(skill)

        print("   ✅ 已清理旧文件")

    # ============ 1. 复制 commands 到 .claude/commands/ ============
    commands_src = repo_root / "migbot" / "commands"
    commands_dst = claude_dir / "commands"
    commands_dst.mkdir(exist_ok=True)

    if commands_src.exists():
        if is_upgrade:
            print("📋 更新 commands...")
        else:
            print("📋 复制 commands...")

        copied_count = 0
        for cmd_file in commands_src.glob("i2h-*.md"):
            shutil.copy2(cmd_file, commands_dst / cmd_file.name)
            copied_count += 1
            if not is_upgrade:
                print(f"   ✅ {cmd_file.name}")

        if copied_count > 0:
            print(f"   复制了 {copied_count} 个 i2h 命令")

    # ============ 2. 复制 skills 到 .claude/skills/ ============
    skills_src = repo_root / "migbot" / "skills"
    skills_dst = claude_dir / "skills"
    skills_dst.mkdir(exist_ok=True)

    if skills_src.exists():
        if is_upgrade:
            print("📋 更新 skills...")
        else:
            print("📋 复制 skills...")

        copied_count = 0
        for skill_dir in skills_src.iterdir():
            if skill_dir.is_dir() and skill_dir.name.startswith("i2h-"):
                dst = skills_dst / skill_dir.name
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.copytree(skill_dir, dst)
                copied_count += 1
                if not is_upgrade:
                    print(f"   ✅ {skill_dir.name}")

        if copied_count > 0:
            print(f"   复制了 {copied_count} 个 i2h skills")

    # ============ 3. 创建 .migbot 目录（运行时数据）============
    migbot_dir = project_root / ".migbot"
    migbot_dir.mkdir(exist_ok=True)

    # 创建 bin 目录
    bin_dir = migbot_dir / "bin"
    bin_dir.mkdir(exist_ok=True)

    # 复制脚本
    scripts_src = repo_root / "migbot" / "bin" / "scripts"
    if scripts_src.exists():
        if is_upgrade:
            print("📋 更新脚本...")
        else:
            print("📋 复制脚本...")
        shutil.copytree(scripts_src, bin_dir / "scripts", dirs_exist_ok=True)

    # 复制映射文件
    mappings_src = repo_root / "migbot" / "mappings"
    if mappings_src.exists():
        mappings_dst = migbot_dir / "mappings"
        mappings_dst.mkdir(exist_ok=True)
        for mapping_file in mappings_src.glob("*.json"):
            shutil.copy2(mapping_file, mappings_dst / mapping_file.name)

    # ============ 4. 处理配置文件（保留用户配置）============
    config_file = migbot_dir / "config.json"

    if config_file.exists():
        # 读取现有配置，保留用户设置
        print("✅ 保留现有配置")
        with open(config_file, "r") as f:
            existing_config = json.load(f)

        # 只更新版本号（如果需要）
        if "version" not in existing_config:
            existing_config["version"] = "1.0.0"
            with open(config_file, "w") as f:
                json.dump(existing_config, f, indent=2)
            print("   ✅ 已更新版本号")
    else:
        # 首次安装，创建新配置
        config = {
            "version": "1.0.0",
            "language": "zh",
            "ios": ios_path or "../ios-app",
            "harmonyos": ".",
            "xcode": "",
            "xcrun": "",
            "simctl": "",
            "deveco": "",
            "hvigorw": "",
            "hdc": "",
            "app_name": "",
            "confirmed": False
        }

        with open(config_file, "w") as f:
            json.dump(config, f, indent=2)
        print(f"✅ 配置文件已创建: {config_file}")

    # 创建 spec 目录结构
    spec_dir = project_root / "spec"
    spec_dir.mkdir(exist_ok=True)
    (spec_dir / ".i2h").mkdir(exist_ok=True)
    (spec_dir / "baseline").mkdir(exist_ok=True)
    (spec_dir / "baseline" / "ui").mkdir(exist_ok=True)
    (spec_dir / "baseline" / "features").mkdir(exist_ok=True)
    (spec_dir / "baseline" / "plans").mkdir(exist_ok=True)

    if not is_upgrade:
        print("✅ 目录结构已创建")

    # 验证安装
    print("\n📊 安装验证:")
    i2h_commands = list((claude_dir / "commands").glob("i2h-*.md"))
    i2h_skills = [d for d in (claude_dir / "skills").iterdir() if d.is_dir() and d.name.startswith("i2h-")]
    print(f"   .claude/commands/: {len(i2h_commands)} 个 i2h 命令")
    print(f"   .claude/skills/: {len(i2h_skills)} 个 i2h skills")
    print(f"   .migbot/bin/scripts/: {len(list((bin_dir / 'scripts').rglob('*.py')))} 个脚本")

    if is_upgrade:
        print(f"""
✅ migbot 升级完成！

更新内容:
  ✅ 已清理旧的 a2h 文件
  ✅ .claude/commands/ (i2h 命令已更新)
  ✅ .claude/skills/ (i2h skills 已更新)
  ✅ .migbot/bin/scripts/ (脚本已更新)
  ✅ 用户配置已保留

可用命令:
  /i2h-init   - 初始化配置（统一探测，一次确认）
  /i2h-run    - 运行完整迁移流水线

配置文件: {config_file}
""")
    else:
        print(f"""
✅ migbot 安装完成！

安装清单:
  ✅ .claude/commands/ ({len(i2h_commands)} 个 i2h 命令)
  ✅ .claude/skills/ ({len(i2h_skills)} 个 i2h skills)
  ✅ .migbot/bin/scripts/ (所有脚本)
  ✅ .migbot/config.json (配置)
  ✅ spec/ (目录结构)

可用命令:
  /i2h-init   - 初始化配置（统一探测，一次确认）
  /i2h-run    - 运行完整迁移流水线

下一步:
1. 在 Claude Code 中打开项目: {project_root}
2. 运行 /i2h-init 确认配置
3. 运行 /i2h-run 开始迁移

配置文件: {config_file}
""")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Install migbot iOS to HarmonyOS project")
    parser.add_argument("--project", required=True, help="HarmonyOS project path")
    parser.add_argument("--ios", help="iOS project path (optional)")
    parser.add_argument("--repo-root", help="Repository root (auto-detected)")

    args = parser.parse_args()

    install_migbot(args.project, args.ios, args.repo_root)
