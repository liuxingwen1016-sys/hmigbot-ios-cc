#!/usr/bin/env bash
# gen-core-manifest.sh — 重新生成 .githooks/core-skills.manifest
#
# 用法: scripts/gen-core-manifest.sh [ArkTs-Core 路径] [上游分支名]
#
# 路径可省略，改用环境变量或 git 配置（推荐）：
#   git config migbot.coreRoot /path/to/ArkTs-Core
# 详见 scripts/lib/resolve-core.sh。
#
# 何时需要重新生成：上游新增 / 删除了 skill，或 migbot 调整了分发范围。
# 清单决定 pre-commit hook 对哪些 skill 提示「需回推上游」。

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$REPO_ROOT/scripts/lib/resolve-core.sh"
CORE="$(resolve_core "${1:-}")" || exit 1
BRANCH="${2:-}"

SRC="$CORE/arkts-skills/skills"

[ -z "$BRANCH" ] && BRANCH="$(git -C "$CORE" branch --show-current 2>/dev/null || echo '未知')"

MANIFEST="$REPO_ROOT/.githooks/core-skills.manifest"
mkdir -p "$(dirname "$MANIFEST")"

shared="$(comm -12 \
  <(ls "$SRC" | grep -v '^README.md$' | sort) \
  <(ls "$REPO_ROOT/skills" | sort))"

{
  echo "# core-skills.manifest — 来自 ArkTs-Core 的 skill 清单（migbot 与上游共享）"
  echo "#"
  echo "# 这些 skill 的真相源是 ArkTs-Core，migbot 通过 dist 产物同步而来。"
  echo "# 在 migbot 侧改动它们 => 必须回推 ArkTs-Core 的对应分支，否则下次整版"
  echo "# 同步会把改动覆盖掉（历史上已发生 3 次：v1.1.2 / v1.2.1 / v1.2.2）。"
  echo "#"
  echo "# 不在此清单中的 skill 为 migbot 独有，改动无需回推。"
  echo "#"
  echo "# 重新生成：scripts/gen-core-manifest.sh <ArkTs-Core 路径>"
  echo "# 生成于：$(date +%Y-%m-%d)，对应上游分支 $BRANCH"
  echo ""
  echo "$shared"
} > "$MANIFEST"

echo "已写入 $MANIFEST"
echo "  共享 skill: $(echo "$shared" | wc -l | tr -d ' ') 个（上游分支 ${BRANCH}）"
echo "  migbot-only: $(comm -13 <(ls "$SRC" | grep -v '^README.md$' | sort) <(ls "$REPO_ROOT/skills" | sort) | wc -l | tr -d ' ') 个（改动无需回推）"
