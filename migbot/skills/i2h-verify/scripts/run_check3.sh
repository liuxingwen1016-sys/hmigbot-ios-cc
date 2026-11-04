#!/bin/bash
#
# CHECK-3 视觉对齐主集成脚本
#
# 功能：
#   1. 检测 iOS 和 HarmonyOS 设备
#   2. 采集双端截图
#   3. 对比相似度
#   4. 生成详细报告
#
# 使用：
#   bash run_check3.sh --ios-root <path> --harmonyos-root <path> --output <dir>

set -e  # 遇到错误立即退出

# ============================================================================
# 配置和参数
# ============================================================================

IOS_ROOT=""
HARMONYOS_ROOT=""
OUTPUT_DIR="spec/verify"
IOS_DEVICE=""
HOS_DEVICE=""
VERBOSE=0

# 脚本目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ============================================================================
# 辅助函数
# ============================================================================

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

error() {
    echo "[ERROR] $*" >&2
    exit 1
}

verbose() {
    if [ "$VERBOSE" -eq 1 ]; then
        echo "[VERBOSE] $*"
    fi
}

usage() {
    cat << EOF
使用方法: $0 [OPTIONS]

CHECK-3 视觉对齐主集成脚本

选项:
    --ios-root PATH          iOS 项目根目录
    --harmonyos-root PATH    HarmonyOS 项目根目录
    --output DIR             输出目录 (默认: spec/verify)
    --ios-device UDID        指定 iOS 设备 UDID (可选)
    --hos-device ID          指定 HarmonyOS 设备 ID (可选)
    -v, --verbose            详细输出
    -h, --help               显示帮助

示例:
    $0 --ios-root /path/to/ios --harmonyos-root /path/to/harmonyos
    $0 --ios-root ~/ios-app --harmonyos-root ~/hos-app --verbose

EOF
    exit 0
}

# ============================================================================
# 参数解析
# ============================================================================

while [[ $# -gt 0 ]]; do
    case $1 in
        --ios-root)
            IOS_ROOT="$2"
            shift 2
            ;;
        --harmonyos-root)
            HARMONYOS_ROOT="$2"
            shift 2
            ;;
        --output)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --ios-device)
            IOS_DEVICE="$2"
            shift 2
            ;;
        --hos-device)
            HOS_DEVICE="$2"
            shift 2
            ;;
        -v|--verbose)
            VERBOSE=1
            shift
            ;;
        -h|--help)
            usage
            ;;
        *)
            error "未知参数: $1"
            ;;
    esac
done

# 验证必需参数
if [ -z "$IOS_ROOT" ]; then
    error "必须指定 --ios-root"
fi

if [ -z "$HARMONYOS_ROOT" ]; then
    error "必须指定 --harmonyos-root"
fi

# ============================================================================
# Step 1: 检测设备
# ============================================================================

log "🔍 Step 1: 检测设备可用性"

# 检测 iOS 设备
if [ -z "$IOS_DEVICE" ]; then
    log "   检测 iOS 设备..."
    IOS_DEVICE=$(python3 "$SCRIPT_DIR/ios_device_checker.py" --quiet 2>/dev/null || true)

    if [ -z "$IOS_DEVICE" ]; then
        log "   ❌ 未找到可用的 iOS 设备"
        log "   恢复条件:"
        log "      1. 启动 iOS 模拟器"
        log "      2. 或连接 iOS 真机并安装 libimobiledevice"

        # 生成 DEFERRED 报告
        mkdir -p "$OUTPUT_DIR"
        cat > "$OUTPUT_DIR/ui-comparison.md" << 'EOFR'
# UI 对比验证报告

## 执行状态
❌ DEFERRED - iOS 设备不可用

## 原因
未找到可用的 iOS 设备（模拟器或真机）

## 恢复条件
1. 启动 iOS 模拟器 (Xcode > Open Developer Tool > Simulator)
2. 或连接 iOS 真机并安装 libimobiledevice:
   ```bash
   brew install libimobiledevice
   ```

## CHECK-3 判定
- **状态**: DEFERRED
- **原因**: iOS 设备不可用

EOFR
        exit 1
    fi

    log "   ✅ iOS 设备: $IOS_DEVICE"
else
    log "   使用指定的 iOS 设备: $IOS_DEVICE"
fi

# 检测 HarmonyOS 设备
if [ -z "$HOS_DEVICE" ]; then
    log "   检测 HarmonyOS 设备..."
    HOS_DEVICE=$(hdc list targets 2>/dev/null | grep -v "Empty" | head -1 || true)

    if [ -z "$HOS_DEVICE" ]; then
        log "   ❌ 未找到可用的 HarmonyOS 设备"

        # 生成 DEFERRED 报告
        mkdir -p "$OUTPUT_DIR"
        cat > "$OUTPUT_DIR/ui-comparison.md" << 'EOFR'
# UI 对比验证报告

## 执行状态
❌ DEFERRED - HarmonyOS 设备不可用

## 原因
未找到可用的 HarmonyOS 设备

## 恢复条件
1. 连接 HarmonyOS 设备或启动模拟器
2. 确保 hdc 命令可用

## CHECK-3 判定
- **状态**: DEFERRED
- **原因**: HarmonyOS 设备不可用

EOFR
        exit 1
    fi

    log "   ✅ HarmonyOS 设备: $HOS_DEVICE"
else
    log "   使用指定的 HarmonyOS 设备: $HOS_DEVICE"
fi

# ============================================================================
# Step 2: 准备目录
# ============================================================================

log "📁 Step 2: 准备截图目录"

IOS_SCREENSHOT_DIR="$OUTPUT_DIR/screenshots/ios"
HOS_SCREENSHOT_DIR="$OUTPUT_DIR/screenshots/harmonyos"
COMPARISON_DIR="$OUTPUT_DIR/screenshots/comparison"

mkdir -p "$IOS_SCREENSHOT_DIR"
mkdir -p "$HOS_SCREENSHOT_DIR"
mkdir -p "$COMPARISON_DIR"

log "   ✅ 目录已创建"

# ============================================================================
# Step 3: 读取页面列表
# ============================================================================

log "📋 Step 3: 读取页面列表"

PAGE_LIST_FILE="$OUTPUT_DIR/.page-list.txt"

# 从 ui-manifest.md 提取页面
if [ -f "spec/baseline/ui-manifest.md" ]; then
    verbose "   从 ui-manifest.md 提取页面"
    grep -E "^##\s+\w+(View|Page)" spec/baseline/ui-manifest.md | \
        sed -E 's/^##\s+([A-Za-z0-9_]+).*/\1/' > "$PAGE_LIST_FILE" || true
fi

# 扩展：从 gate-release 添加页面
if [ -f "spec/gate-release/verify-focus.json" ]; then
    verbose "   从 gate-release 扩展验证范围"
    python3 -c "
import json
import sys
try:
    with open('spec/gate-release/verify-focus.json') as f:
        data = json.load(f)
    for item in data.get('items', []):
        for page in item.get('pages', []):
            print(page)
except:
    pass
" >> "$PAGE_LIST_FILE" 2>/dev/null || true
fi

# 去重
if [ -f "$PAGE_LIST_FILE" ]; then
    sort -u "$PAGE_LIST_FILE" -o "$PAGE_LIST_FILE"
    PAGE_COUNT=$(wc -l < "$PAGE_LIST_FILE" | tr -d ' ')
    log "   ✅ 待验证页面: $PAGE_COUNT 个"
else
    error "未找到页面列表"
fi

# ============================================================================
# Step 4: iOS 端截图
# ============================================================================

log "📱 Step 4: iOS 端截图采集"

IOS_SUCCESS=0
IOS_FAILED=0

while IFS= read -r page; do
    [ -z "$page" ] && continue

    verbose "   截图: $page"

    # 检测设备类型
    if echo "$IOS_DEVICE" | grep -q "^[A-F0-9-]\{36\}$"; then
        # 模拟器 UDID（36位UUID）
        xcrun simctl io "$IOS_DEVICE" screenshot "$IOS_SCREENSHOT_DIR/${page}.png" 2>/dev/null
    else
        # 真机
        idevicescreenshot -u "$IOS_DEVICE" "$IOS_SCREENSHOT_DIR/${page}.png" 2>/dev/null
    fi

    if [ -f "$IOS_SCREENSHOT_DIR/${page}.png" ]; then
        verbose "      ✅ 成功"
        IOS_SUCCESS=$((IOS_SUCCESS + 1))
    else
        verbose "      ⚠️  失败"
        IOS_FAILED=$((IOS_FAILED + 1))
    fi

    sleep 0.5
done < "$PAGE_LIST_FILE"

log "   ✅ iOS 截图完成: 成功 $IOS_SUCCESS, 失败 $IOS_FAILED"

# ============================================================================
# Step 5: HarmonyOS 端截图
# ============================================================================

log "📱 Step 5: HarmonyOS 端截图采集"

# 查找并安装 HAP
HAP_FILE=$(find "$HARMONYOS_ROOT" -name "*.hap" -type f | head -1)
if [ -n "$HAP_FILE" ]; then
    log "   安装应用: $(basename "$HAP_FILE")"
    hdc -t "$HOS_DEVICE" install "$HAP_FILE" 2>&1 | grep -v "warning" || true
fi

# 获取 bundle name
HOS_BUNDLE=$(python3 -c "
import json
import sys
try:
    with open('$HARMONYOS_ROOT/AppScope/app.json5') as f:
        content = f.read()
        # 简单处理 JSON5
        lines = [l for l in content.split('\n') if not l.strip().startswith('//')]
        data = json.loads('\n'.join(lines))
        print(data.get('app', {}).get('bundleName', ''))
except:
    pass
" 2>/dev/null)

if [ -n "$HOS_BUNDLE" ]; then
    log "   启动应用: $HOS_BUNDLE"
    hdc -t "$HOS_DEVICE" shell aa start -a EntryAbility -b "$HOS_BUNDLE" 2>/dev/null || true
    sleep 2
fi

HOS_SUCCESS=0
HOS_FAILED=0

while IFS= read -r page; do
    [ -z "$page" ] && continue

    verbose "   截图: $page"

    # HarmonyOS 截图
    hdc -t "$HOS_DEVICE" shell snapshot_display -f "/data/local/tmp/${page}.png" 2>/dev/null || true
    hdc -t "$HOS_DEVICE" file recv "/data/local/tmp/${page}.png" "$HOS_SCREENSHOT_DIR/${page}.png" 2>/dev/null || true

    if [ -f "$HOS_SCREENSHOT_DIR/${page}.png" ]; then
        verbose "      ✅ 成功"
        HOS_SUCCESS=$((HOS_SUCCESS + 1))
    else
        verbose "      ⚠️  失败"
        HOS_FAILED=$((HOS_FAILED + 1))
    fi

    sleep 0.5
done < "$PAGE_LIST_FILE"

log "   ✅ HarmonyOS 截图完成: 成功 $HOS_SUCCESS, 失败 $HOS_FAILED"

# ============================================================================
# Step 6: 执行对比
# ============================================================================

log "🔍 Step 6: 执行相似度对比"

python3 "$SCRIPT_DIR/compare_screenshots.py" \
    "$IOS_SCREENSHOT_DIR" \
    "$HOS_SCREENSHOT_DIR" \
    --json \
    --output "$COMPARISON_DIR/comparison-results.json"

COMPARE_EXIT_CODE=$?

log "   ✅ 对比完成"

# ============================================================================
# Step 7: 生成报告
# ============================================================================

log "📝 Step 7: 生成详细报告"

python3 "$SCRIPT_DIR/generate_ui_report.py" \
    "$COMPARISON_DIR/comparison-results.json" \
    "$OUTPUT_DIR/ui-comparison.md"

log "   ✅ 报告已生成: $OUTPUT_DIR/ui-comparison.md"

# ============================================================================
# Step 8: 状态判定
# ============================================================================

log "✅ Step 8: CHECK-3 状态判定"

# 读取平均相似度
AVG_SIMILARITY=$(python3 -c "
import json
with open('$COMPARISON_DIR/comparison-results.json') as f:
    data = json.load(f)
    print(data.get('summary', {}).get('avg_similarity', 0))
" 2>/dev/null)

log "   平均相似度: ${AVG_SIMILARITY}%"

if [ "$COMPARE_EXIT_CODE" -eq 0 ]; then
    log "   ✅ CHECK-3 判定: PASS (平均相似度 ≥ 85%)"
    exit 0
else
    log "   ❌ CHECK-3 判定: FAIL (平均相似度 < 85%)"
    exit 1
fi
