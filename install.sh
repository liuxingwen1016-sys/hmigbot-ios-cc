#!/bin/bash
set -e

# install.sh - migbot iOS 安装脚本

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_PATH=""
IOS_PATH=""

# 解析参数
while [[ $# -gt 0 ]]; do
  case $1 in
    --project)
      PROJECT_PATH="$2"
      shift 2
      ;;
    --ios)
      IOS_PATH="$2"
      shift 2
      ;;
    *)
      echo "Unknown option: $1"
      exit 1
      ;;
  esac
done

if [ -z "$PROJECT_PATH" ]; then
  echo "Usage: ./install.sh --project <harmonyos-project-path> [--ios <ios-project-path>]"
  exit 1
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  iOS → HarmonyOS 迁移工具安装"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "HarmonyOS 项目: $PROJECT_PATH"
if [ -n "$IOS_PATH" ]; then
  echo "iOS 项目: $IOS_PATH"
fi
echo ""

# 检查 Python
if ! command -v python3 &> /dev/null; then
  echo "❌ 错误: 未找到 python3"
  exit 1
fi

# 运行安装脚本
if [ -n "$IOS_PATH" ]; then
  python3 "$SCRIPT_DIR/migbot/scripts/migbot-install.py" --project "$PROJECT_PATH" --ios "$IOS_PATH"
else
  python3 "$SCRIPT_DIR/migbot/scripts/migbot-install.py" --project "$PROJECT_PATH"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  安装完成！"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "下一步:"
echo "  1. cd $PROJECT_PATH"
echo "  2. 在 Claude Code 中运行 /i2h-init"
echo "  3. 运行 /i2h-run 开始迁移"
echo ""
