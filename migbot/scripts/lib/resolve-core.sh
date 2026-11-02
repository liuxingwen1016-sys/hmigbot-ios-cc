#!/usr/bin/env bash
# resolve-core.sh — 定位本机的 ArkTs-Core 仓库路径（供 scripts/ 下的脚本 source）
#
# ArkTs-Core 的位置因人而异，不能写死在仓库里。按以下优先级解析：
#
#   1. 命令行参数         scripts/xxx.sh /path/to/ArkTs-Core
#   2. 环境变量           export ARKTS_CORE_ROOT=/path/to/ArkTs-Core
#   3. git 本地配置       git config migbot.coreRoot /path/to/ArkTs-Core
#
# 推荐第 3 种：每人设置一次，之后调用脚本无需再带参数；该配置存在 .git/config
# 里，不随仓库分发，不会影响他人。
#
# 用法：
#   source "$(dirname "${BASH_SOURCE[0]}")/lib/resolve-core.sh"
#   CORE="$(resolve_core "${1:-}")" || exit 1

resolve_core() {
  local from_arg="${1:-}"
  local candidate=""

  if [ -n "$from_arg" ]; then
    candidate="$from_arg"
  elif [ -n "${ARKTS_CORE_ROOT:-}" ]; then
    candidate="$ARKTS_CORE_ROOT"
  else
    candidate="$(git config --get migbot.coreRoot 2>/dev/null || true)"
  fi

  if [ -z "$candidate" ]; then
    cat >&2 <<'EOF'
ERROR: 未指定 ArkTs-Core 仓库路径。

  该路径因人而异，未写死在仓库中。三种指定方式（任选其一）：

    1. 直接传参
         scripts/<脚本名>.sh /path/to/ArkTs-Core

    2. 环境变量
         export ARKTS_CORE_ROOT=/path/to/ArkTs-Core

    3. git 本地配置（推荐，设一次即可，不随仓库分发）
         git config migbot.coreRoot /path/to/ArkTs-Core
EOF
    return 1
  fi

  # 规范成绝对路径
  candidate="$(cd "$candidate" 2>/dev/null && pwd)" || {
    echo "ERROR: 路径不存在: ${from_arg:-${ARKTS_CORE_ROOT:-$(git config --get migbot.coreRoot 2>/dev/null)}}" >&2
    return 1
  }

  # 校验确实是 ArkTs-Core 仓（而非随便一个目录）
  if [ ! -d "$candidate/arkts-skills/skills" ]; then
    echo "ERROR: 不像是 ArkTs-Core 仓库（缺 arkts-skills/skills/）: $candidate" >&2
    return 1
  fi

  echo "$candidate"
}
