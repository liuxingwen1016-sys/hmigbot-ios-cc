#!/usr/bin/env bash
# sync-skills-from-core.sh — 把 ArkTs-Core 的 dist 产物同步进 migbot 的 skills/
#
# 用法:
#   scripts/sync-skills-from-core.sh [ArkTs-Core 仓路径]
#   scripts/sync-skills-from-core.sh --dry-run [路径]     # 只看会改什么，不落盘
#
# ArkTs-Core 路径可省略，改用环境变量或 git 配置（推荐，设一次即可）：
#   git config migbot.coreRoot /path/to/ArkTs-Core
# 详见 scripts/lib/resolve-core.sh。
#
# 前提：先在 ArkTs-Core 侧完成构建
#   cd <core>/build/script-compression && python3 scripts/run.py --no-build --no-verify
#
# 为什么需要这个脚本，而不是直接 cp -r：
#
#   1. 【绝不能 --delete】migbot 有 16 个上游没有的 skill（claude-session-stats、
#      migbot-increment-* ×6、rq-* ×3、arkts-webview-manager、mod-design、
#      prd-generator、tdd-enforcer、dfr-fmea-general、harmonyos-ui-test）。
#      带 --delete 的同步会把它们全部删光。
#
#   2. 【排除清单】上游有但 migbot 不分发的 skill，见下方 EXCLUDES。
#
#   3. 打点 / 构建护栏 / frontmatter 引号已于 ArkTs-Core 的 be05517 内置到源仓，
#      dist 产物自带，同步后无需再手工补回。若某天这些内容又消失，说明上游被
#      整版覆盖过——用 --dry-run 比对后按 docs/skills-telemetry-instrumentation.md
#      §5 checklist 重新应用，并回推上游。

set -euo pipefail

MIGBOT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

DRY_RUN=0
ALLOW_PARTIAL_PLATFORM="${ALLOW_PARTIAL_PLATFORM:-0}"
while :; do
  case "${1:-}" in
    --dry-run)                 DRY_RUN=1; shift ;;
    --allow-partial-platform)  ALLOW_PARTIAL_PLATFORM=1; shift ;;
    *) break ;;
  esac
done

source "$MIGBOT_ROOT/scripts/lib/resolve-core.sh"
CORE="$(resolve_core "${1:-}")" || exit 1
SRC="$CORE/dist/pkg/arkts-skills/skills"
DST="$MIGBOT_ROOT/skills"

# 上游有、migbot 不分发的条目
EXCLUDES=(
  'arkts-architecture-refactor'   # 独立架构重构 skill，migbot 不纳入分发
  'README.md'                     # 上游的 skill 索引，与 migbot 无关
  'mig-arch'                      # 多模块架构分析，v1.2.2 已下线
  'a2h-arch-scaffold'             # 多模块骨架生成，v1.2.2 已下线
)

[ -d "$SRC" ] || { echo "ERROR: dist 产物不存在: $SRC"; echo "  请先在 ArkTs-Core 侧构建（见本文件头部注释）"; exit 1; }

# ---------------------------------------------------------------------------
# 前置闸门：残缺的 dist 会造成两类实际损坏，必须在覆盖前拦住。
# 二者都真实发生过——一次 run.py --no-build 在缺少 _artifacts 的仓里组装出
# 残缺产物，覆盖后把 31 个已编译 stub 换回了明文源码。
# ---------------------------------------------------------------------------

# 闸门 1：平台完整性。不带 --delete 的覆盖只会更新 dist 里有的平台，
# migbot 侧其余平台的二进制原地保留 => 同一 skill 两个平台跑不同版本。
missing_platforms=()
for plat in $(find "$DST" -type d -name '*-*' -path '*/scripts/bin/*' -maxdepth 5 2>/dev/null \
              | sed 's|.*/scripts/bin/||' | cut -d/ -f1 | sort -u); do
  find "$SRC" -type d -path "*/scripts/bin/$plat" -print -quit 2>/dev/null | grep -q . \
    || missing_platforms+=("$plat")
done
if [ ${#missing_platforms[@]} -gt 0 ]; then
  if [ "${ALLOW_PARTIAL_PLATFORM:-0}" = "1" ]; then
    echo "WARN: dist 缺少平台 ${missing_platforms[*]}，已由 --allow-partial-platform 放行。"
    echo "  这些平台的二进制将停留在旧版本，与已更新平台不同步。"
    echo ""
  else
    echo "ERROR: dist 缺少平台: ${missing_platforms[*]}"
    echo "  dist 现有平台: $(find "$SRC" -type d -path '*/scripts/bin/*' -maxdepth 5 2>/dev/null | sed 's|.*/scripts/bin/||' | cut -d/ -f1 | sort -u | tr '\n' ' ')"
    echo ""
    echo "  覆盖只更新 dist 里有的平台，缺失平台的二进制会停留在旧版本，"
    echo "  导致同一 skill 在不同平台跑不同逻辑。"
    echo ""
    echo "  修复：在缺失平台的机器上跑 run.py --build-only，把该平台的"
    echo "        dist/_artifacts/<tag>/ 拷回本机，再 run.py --no-build 重新组装。"
    echo ""
    echo "  确知只发布单平台可加 --allow-partial-platform 跳过本闸门。"
    exit 1
  fi
fi

# 闸门 2：stub 退化。dist 里应是编译后的 launcher stub；若某文件在 migbot 侧
# 已是 stub、在 dist 里却是明文源码，说明该 skill 这次没编译进去。覆盖会泄露
# 源码，且与 migbot 侧残留的 _entry.bin 版本错配。
regressions=()
while IFS= read -r f; do
  rel="${f#$SRC/}"; tgt="$DST/$rel"
  [ -f "$tgt" ] || continue
  grep -q "AUTO-GENERATED launcher" "$f" 2>/dev/null && continue
  grep -q "AUTO-GENERATED launcher" "$tgt" 2>/dev/null && regressions+=("$rel")
done < <(find "$SRC" -path '*/scripts/*.py' -maxdepth 4 2>/dev/null)
if [ ${#regressions[@]} -gt 0 ]; then
  echo "ERROR: ${#regressions[@]} 个文件会从已编译 stub 退化为明文源码："
  printf '  %s\n' "${regressions[@]:0:10}"
  [ ${#regressions[@]} -gt 10 ] && echo "  ...（另 $(( ${#regressions[@]} - 10 )) 个）"
  echo ""
  echo "  这批 skill 本次未编译进 dist。覆盖会泄露源码，并与 migbot 侧残留的"
  echo "  _entry.bin 版本错配。请重新完整构建后再同步。"
  exit 1
fi

RSYNC_ARGS=(-a)
for e in "${EXCLUDES[@]}"; do RSYNC_ARGS+=(--exclude="$e"); done
# 注意：此处刻意不加 --delete，理由见文件头 §1
[ "$DRY_RUN" -eq 1 ] && RSYNC_ARGS+=(--dry-run -v)

echo "源:   $SRC"
echo "目标: $DST"
echo "排除: ${EXCLUDES[*]}"
[ "$DRY_RUN" -eq 1 ] && echo "模式: DRY-RUN（不落盘）"
echo ""

rsync "${RSYNC_ARGS[@]}" "$SRC/" "$DST/"

[ "$DRY_RUN" -eq 1 ] && { echo ""; echo "dry-run 结束，未改动任何文件。"; exit 0; }

# ---- 同步后自检：CI 的 8 条 telemetry 断言 ----
echo ""
echo "=== 同步后自检：打点断言（与 .github/workflows/publish.yml 一致）==="
fail=0
check() {
  if grep -qE "$2" "$DST/$1"; then echo "  ok: $3"; else echo "  MISSING: $3 ($1)"; fail=1; fi
}
check a2h-spec/SKILL.md       'metrics report-stage a2h-spec'       'spec: report-stage'
check a2h-plan/SKILL.md       'metrics report-stage a2h-plan'       'plan: report-stage'
check a2h-execute/SKILL.md    'metrics report-stage a2h-execute'    'execute: report-stage'
check a2h-verify/SKILL.md     'metrics report-verify'               'verify: report-verify'
check a2h-verify/SKILL.md     'metrics report-stage a2h-verify'     'verify: report-stage'
check a2h-retrospect/SKILL.md 'metrics report-stage a2h-retrospect' 'retrospect: report-stage'
check a2h-retrospect/SKILL.md 'metrics upload-retrospect'           'retrospect: upload-retrospect'
check a2h-retrospect/SKILL.md 'metrics upload-sessions'             'retrospect: upload-sessions'

# CI 不覆盖、只能自查的三项（v1.2.1 正是漏了 component-builder 这条）
echo ""
echo "=== 自检：CI 断言覆盖不到的护栏与引号 ==="
check a2h-spec/SKILL.md                'metrics verify-access'                     'spec: verify-access 门控'
check a2h-spec/SKILL.md                'metrics verify-consent'                    'spec: verify-consent 门控'
check a2h-execute/SKILL.md             '构建修复循环操作纪律'                        'execute: 构建循环纪律'
check hmos_fix_build_errors/SKILL.md   'Build-Fix Loop: Environmental Safeguards'  'hmos: 构建环境护栏'
check arkts-component-builder/SKILL.md 'Linter 共存规则'                            'component-builder: Linter 共存'
check arkts-component-builder/SKILL.md '共享组件资格判定'                            'component-builder: 共享组件资格'

echo ""
echo "=== 自检：frontmatter 可解析（引号丢失会让 skill 永不触发）==="
python3 - "$DST" <<'PY'
import pathlib, sys
try:
    import yaml
except ImportError:
    print("  SKIP: PyYAML 未安装"); sys.exit(0)
bad = []
for p in sorted(pathlib.Path(sys.argv[1]).glob("*/SKILL.md")):
    t = p.read_text(encoding="utf-8", errors="replace")
    if not t.startswith("---"):
        continue
    try:
        d = yaml.safe_load(t.split("---", 2)[1])
        if not isinstance(d, dict) or not d.get("name") or not d.get("description"):
            bad.append(p.parent.name)
    except Exception:
        bad.append(p.parent.name)
if bad:
    print("  FAILED: frontmatter 解析失败 / 元数据为空 —", ", ".join(bad))
    sys.exit(1)
print("  ok: 全部 skill 的 frontmatter 均可解析")
PY
py_status=$?

echo ""
if [ "$fail" -ne 0 ] || [ "$py_status" -ne 0 ]; then
  echo "同步完成，但自检未全过 —— 上游可能又被整版覆盖了。"
  echo "按 docs/skills-telemetry-instrumentation.md §5 checklist 补回，并把补丁回推 ArkTs-Core。"
  exit 1
fi
echo "同步完成，全部自检通过。"
