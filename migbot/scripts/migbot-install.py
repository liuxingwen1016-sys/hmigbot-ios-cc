#!/usr/bin/env python3
"""migbot iOS 版本安装脚本 - 完整版

关键：
1. 只复制 i2h-* 命令和相关 skills
2. 创建 .claude 目录并复制 commands 和 skills
3. 支持重复执行，保留用户配置
4. 自动清理旧的 a2h 文件
5. 智能过滤 skills：iOS 特定 + arkts 通用 + 工具类
"""
from __future__ import annotations

import os
import sys
import json
import shutil
import argparse
import hashlib
import subprocess
import tempfile
from pathlib import Path


# ============ Skills 过滤配置 ============
# 需要安装的 skills（iOS 特定 + 通用工具）
INSTALL_SKILLS = {
    # iOS 核心流水线
    'i2h-spec', 'i2h-plan', 'i2h-execute', 'i2h-verify', 'i2h-retrospect',

    # iOS 特定 skills
    'ios-ui-graph-builder', 'ios-ui-graph-query', 'swiftui-to-arkui',
    'ios-api-inventory', 'ios-fact-tree', 'ios_fast_traverse',
    'ios2hmos_resources_convert',

    # 通用工具 skills
    'app-relationship-tree', 'commit', 'dfr-fmea-general',
    'grill-with-docs', 'hmos_fix_build_errors', 'hmos-env-doctor',
    'harmonyos-ui-test', 'claude-session-stats', 'skill-checker',
    'toolkit-fact-indexer', 'mod-design', 'prd-generator',
    'rq-parse', 'rq-clarify', 'rq-codebase', 'tdd-enforcer',
}

# ArkTS skills 前缀（默认全部安装）
ARKTS_SKILLS_PREFIX = 'arkts-'

# 排除的 ArkTS skills（Android 特定）
EXCLUDE_ARKTS_SKILLS = {'arkts-ad'}

EXECUTE_SKILL = 'i2h-execute'
UI_GATE_ENTRIES = {
    'capability_gate.py': ('--project-root', '--output-json'),
    'ui_stage1_gate.py': ('--project-root', '--output-json'),
    'ui_delivery_gate.py': ('--project-root', '--output-json'),
    'ui_dispatch.py': ('prepare', 'complete', 'reuse-metadata'),
    'stage1_acceptance.py': ('--project-root', '--kind', '--build-receipt'),
    'stage1_visual_scope.py': ('--project-root', '--out'),
    'stage1_visual_report.py': ('--scope', 'assemble'),
    'ui_relationships.py': ('--comparison-id', '--harmony-tree'),
}
UI_GATE_FILES = {
    *UI_GATE_ENTRIES,
    '_launcher.py',
    'ui_delivery_inputs.py',
    'lib/__init__.py',
    'lib/ios_stage1_scope.py',
    'lib/ios_stage1_acceptance.py',
    'lib/ios_stage1_progress.py',
    'lib/ios_stage1_summary.py',
    'lib/ios_stage1_visual_gate.py',
    'lib/ios_ui_delivery_gate.py',
    'lib/ios_ui_dispatch.py',
    'lib/ios_ui_relationships.py',
    'lib/stage1_contract.py',
    'lib/stage1_reachability.py',
    'lib/stage1_visual_scope.py',
    'lib/stage1_visual_report.py',
    'lib/stage1_visual_acceptance.py',
    'lib/stage1_wiring_checks.py',
    'lib/ui_stage1_gate.py',
    'lib/ui_delivery_inputs_ios.py',
}


def stage_execute_skill(source: Path, target: Path) -> None:
    """Verify a project-local copy before replacing the installed skill."""
    scripts = source / 'scripts'

    def exclude(directory, names):
        ignored = {'__pycache__'}
        if Path(directory) == scripts:
            ignored.add('bin')  # obsolete shared Android Nuitka distribution
        return ignored.intersection(names)

    shutil.copytree(source, target, ignore=exclude)
    staged = target / 'scripts'
    manifest = json.loads((staged / 'ui-delivery-runtime.json').read_text(encoding='utf-8'))
    checksums = manifest.get('sha256') if isinstance(manifest, dict) else None
    if not isinstance(checksums, dict) or manifest.get('schema_version') != 1 or set(checksums) != UI_GATE_FILES:
        raise ValueError('invalid UI delivery runtime manifest')
    for name, expected in checksums.items():
        if hashlib.sha256((staged / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f'UI delivery runtime checksum mismatch: {name}')
    for entry, expected_help in UI_GATE_ENTRIES.items():
        result = subprocess.run(
            [sys.executable, '-E', '-B', '-X', 'utf8', str(staged / entry), '--help'],
            cwd=target, capture_output=True, text=True, encoding='utf-8', timeout=20,
        )
        if result.returncode or any(flag not in result.stdout for flag in expected_help):
            raise ValueError(f'UI delivery runtime preflight failed for {entry}: {result.stderr.strip()}')
    with tempfile.TemporaryDirectory(dir=target.parent) as temporary:
        for kind in ('summary', 'next'):
            result = subprocess.run(
                [sys.executable, '-E', '-B', '-X', 'utf8', str(staged / 'stage1_acceptance.py'),
                 '--project-root', temporary, '--kind', kind],
                cwd=target, capture_output=True, text=True, encoding='utf-8', timeout=20,
            )
            try:
                report = json.loads(result.stdout)
            except json.JSONDecodeError as exc:
                raise ValueError(f'UI Stage-1 {kind} runtime preflight failed: {result.stderr.strip()}') from exc
            if (result.returncode != 2 or not isinstance(report, dict)
                    or report.get('policy_gate') != f'execute.stage1-{kind}'
                    or report.get('status') != 'BLOCKED' or report.get('stage1_complete') is not False):
                raise ValueError(f'UI Stage-1 {kind} runtime preflight must report an incomplete project')


def replace_execute_skill(staged: Path, installed: Path) -> None:
    previous = staged.parent / 'previous-execute'
    if installed.exists() or installed.is_symlink():
        installed.replace(previous)
    try:
        staged.replace(installed)
    except OSError:
        if previous.exists() or previous.is_symlink():
            previous.replace(installed)
        raise


def should_install_skill(skill_name: str) -> bool:
    """判断是否应该安装该 skill

    规则：
    1. 在 INSTALL_SKILLS 白名单中 -> 安装
    2. 以 arkts- 开头且不在黑名单中 -> 安装
    3. 其他 -> 跳过
    """
    # 白名单匹配
    if skill_name in INSTALL_SKILLS:
        return True

    # arkts- 前缀匹配（排除黑名单）
    if skill_name.startswith(ARKTS_SKILLS_PREFIX):
        return skill_name not in EXCLUDE_ARKTS_SKILLS

    # 默认跳过
    return False


def install_migbot(project_path: str, ios_path: str = None, repo_root: str = None, language: str = None):
    """安装 migbot 到项目"""
    project_root = Path(project_path).resolve()

    if not project_root.exists():
        print(f"❌ 项目路径不存在: {project_path}")
        sys.exit(1)

    if repo_root is None:
        # 脚本所在的 hmigbot-ios 目录
        repo_root = Path(__file__).parent.parent.parent
    else:
        repo_root = Path(repo_root).expanduser().resolve()

    with tempfile.TemporaryDirectory(prefix='.i2h-package-', dir=project_root) as stage:
        checked_skill = Path(stage) / EXECUTE_SKILL
        try:
            stage_execute_skill(repo_root / 'migbot' / 'skills' / EXECUTE_SKILL, checked_skill)
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            print(f'package_error: {exc}', file=sys.stderr)
            sys.exit(3)
        _install_project(project_root, ios_path, repo_root, language, checked_skill)


def _install_project(project_root, ios_path, repo_root, language, checked_skill):
    # 检测是否是升级安装
    is_upgrade = (project_root / ".migbot" / "config.json").exists()
    skills_src = repo_root / "migbot" / "skills"
    owned_skill_names = {
        path.name for path in skills_src.iterdir()
        if path.is_dir() and should_install_skill(path.name)
    } if skills_src.is_dir() else set()

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

        # 只清理本插件以前安装的 skills；保留用户自己放入 .claude/skills
        # 的目录。旧版没有清单时，再兼容清理明确的 Android 前缀。
        skills_dir = claude_dir / "skills"
        if skills_dir.exists():
            for skill in skills_dir.iterdir():
                if skill.name != EXECUTE_SKILL and skill.is_dir() and (skill.name in owned_skill_names
                                       or skill.name.startswith(("a2h-", "android-"))):
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
    skills_dst = claude_dir / "skills"
    skills_dst.mkdir(exist_ok=True)

    if skills_src.exists():
        if is_upgrade:
            print("📋 更新 skills...")
        else:
            print("📋 复制 skills...")

        copied_count = 0
        skipped_count = 0
        for skill_dir in skills_src.iterdir():
            if skill_dir.is_dir():
                # 使用过滤函数判断是否安装
                if should_install_skill(skill_dir.name):
                    dst = skills_dst / skill_dir.name
                    if skill_dir.name == EXECUTE_SKILL:
                        replace_execute_skill(checked_skill, dst)
                    else:
                        if dst.exists():
                            shutil.rmtree(dst)
                        shutil.copytree(skill_dir, dst)
                    copied_count += 1
                    if not is_upgrade:
                        print(f"   ✅ {skill_dir.name}")
                else:
                    skipped_count += 1

        if copied_count > 0:
            print(f"   复制了 {copied_count} 个 skills（跳过 {skipped_count} 个不相关 skills）")

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

    # Claude Code commands call these stable project-local entry points. Keep
    # them as ordinary executable files (rather than relying on a shell alias
    # or CLAUDE_PLUGIN_ROOT), so both plugin installs and install.sh installs
    # behave identically. i2h is the local fact/stage runtime; i2h-tool is the
    # iOS-specific path/build helper.
    runtime_src = repo_root / "migbot" / "bin"
    for runtime_name in ("i2h", "i2h-tool", "i2h-bootstrap"):
        source = runtime_src / runtime_name
        target = bin_dir / runtime_name
        if source.is_file():
            shutil.copy2(source, target)
            target.chmod(target.stat().st_mode | 0o111)

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
            "language": language if language in {"zh", "en"} else "zh",
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
    all_skills = [d for d in (claude_dir / "skills").iterdir() if d.is_dir()]
    i2h_skills = [d for d in all_skills if d.name.startswith("i2h-")]
    ios_skills = [d for d in all_skills if d.name.startswith("ios")]
    arkts_skills = [d for d in all_skills if d.name.startswith("arkts-")]
    print(f"   .claude/commands/: {len(i2h_commands)} 个 i2h 命令")
    print(f"   .claude/skills/: {len(all_skills)} 个 skills")
    print(f"      - i2h 流水线: {len(i2h_skills)} 个")
    print(f"      - iOS 特定: {len(ios_skills)} 个")
    print(f"      - ArkTS 通用: {len(arkts_skills)} 个")
    print(f"      - 其他工具: {len(all_skills) - len(i2h_skills) - len(ios_skills) - len(arkts_skills)} 个")
    print(f"   .migbot/bin/scripts/: {len(list((bin_dir / 'scripts').rglob('*.py')))} 个脚本")
    runtime_status = all((bin_dir / name).is_file() and os.access(bin_dir / name, os.X_OK)
                         for name in ("i2h", "i2h-tool", "i2h-bootstrap"))
    print(f"   .migbot/bin/i2h + i2h-tool + i2h-bootstrap: {'就绪' if runtime_status else '缺失'}")

    if is_upgrade:
        print(f"""
✅ migbot 升级完成！

更新内容:
  ✅ 已清理旧的 a2h 文件
  ✅ .claude/commands/ (i2h 命令已更新)
  ✅ .claude/skills/ (i2h + iOS + arkts 通用 skills 已更新)
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
  ✅ .claude/skills/ ({len(all_skills)} 个 skills)
     - i2h 流水线: {len(i2h_skills)} 个
     - iOS 特定: {len(ios_skills)} 个
     - ArkTS 通用: {len(arkts_skills)} 个
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
    parser.add_argument("--lang", choices=("zh", "en"), help="Initial output language")

    args = parser.parse_args()

    install_migbot(args.project, args.ios, args.repo_root, args.lang)
