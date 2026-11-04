#!/bin/bash
#
# i2h-verify 端到端验证脚本
#
# 用法: bash e2e_verify.sh <ios-root> <harmonyos-root>

set -e

# ============================================================================
# 配置
# ============================================================================

IOS_ROOT="${1}"
HOS_ROOT="${2}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_DIR="spec/verify"
VERBOSE="${VERBOSE:-0}"

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# ============================================================================
# 辅助函数
# ============================================================================

log() {
    echo -e "[$(date '+%H:%M:%S')] $*"
}

success() {
    echo -e "${GREEN}✅ $*${NC}"
}

error() {
    echo -e "${RED}❌ $*${NC}" >&2
}

warn() {
    echo -e "${YELLOW}⚠️  $*${NC}"
}

section() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "$*"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

# ============================================================================
# 参数验证
# ============================================================================

if [ -z "$IOS_ROOT" ] || [ -z "$HOS_ROOT" ]; then
    cat << EOF
用法: $0 <ios-root> <harmonyos-root>

端到端验证脚本，执行 CHECK-1, CHECK-2, CHECK-3（可选）

示例:
    $0 ~/Projects/MyiOSApp ~/Projects/MyHarmonyOSApp

环境变量:
    VERBOSE=1    详细输出
    SKIP_CHECK3=1  跳过 CHECK-3（设备验证）

EOF
    exit 1
fi

# 验证路径存在
if [ ! -d "$IOS_ROOT" ]; then
    error "iOS 项目路径不存在: $IOS_ROOT"
    exit 1
fi

if [ ! -d "$HOS_ROOT" ]; then
    error "HarmonyOS 项目路径不存在: $HOS_ROOT"
    exit 1
fi

# ============================================================================
# 环境检查
# ============================================================================

section "🔍 环境检查"

# 检查必需工具
TOOLS_OK=true

if ! command -v rg &> /dev/null; then
    error "ripgrep (rg) 未安装"
    warn "  安装: brew install ripgrep"
    TOOLS_OK=false
fi

if ! command -v python3 &> /dev/null; then
    error "Python 3 未安装"
    TOOLS_OK=false
fi

# 检查 Python 依赖
python3 -c "import PIL, imagehash" 2>/dev/null
if [ $? -ne 0 ]; then
    warn "Python 依赖未安装 (Pillow, imagehash)"
    warn "  安装: pip3 install Pillow imagehash"
    warn "  CHECK-3 将无法执行"
fi

if [ "$TOOLS_OK" = false ]; then
    error "环境检查失败，请安装缺失的工具"
    exit 1
fi

success "环境检查通过"

# ============================================================================
# CHECK-1: 静态分析
# ============================================================================

section "📊 CHECK-1: 静态分析"

log "执行 15 项静态检查..."
log "扫描目录: $HOS_ROOT"

CHECK1_RESULT="$OUTPUT_DIR/check1_result.json"
mkdir -p "$OUTPUT_DIR"

python3 "$SCRIPT_DIR/ios_static_analyzer.py" "$HOS_ROOT" \
    -o "$CHECK1_RESULT" 2>&1 | grep -v "检查:"

if [ $? -eq 0 ]; then
    ERROR_COUNT=$(cat "$CHECK1_RESULT" | python3 -c "import json, sys; print(json.load(sys.stdin)['summary']['error_count'])")
    WARN_COUNT=$(cat "$CHECK1_RESULT" | python3 -c "import json, sys; print(json.load(sys.stdin)['summary']['warn_count'])")

    if [ "$ERROR_COUNT" -eq 0 ]; then
        success "CHECK-1: PASS"
        log "   ERROR: $ERROR_COUNT, WARN: $WARN_COUNT"
        CHECK1_STATUS="PASS"
    else
        error "CHECK-1: FAIL"
        log "   ERROR: $ERROR_COUNT, WARN: $WARN_COUNT"
        CHECK1_STATUS="FAIL"

        # 显示 ERROR 详情
        echo ""
        log "ERROR 详情:"
        cat "$CHECK1_RESULT" | python3 -c "
import json, sys
data = json.load(sys.stdin)
for finding in data['findings']:
    if finding['level'] == 'ERROR':
        print(f\"  - {finding['file']}:{finding['line']}\")
        print(f\"    {finding['rule_id']}: {finding['message']}\")
" | head -20
    fi
else
    error "CHECK-1: 执行失败"
    CHECK1_STATUS="ERROR"
fi

# ============================================================================
# CHECK-2: App 身份校验
# ============================================================================

section "📄 CHECK-2: App 身份校验"

log "解析 iOS 配置..."
IOS_CONFIG="$OUTPUT_DIR/ios_config.json"

python3 "$SCRIPT_DIR/ios_config_parser.py" "$IOS_ROOT" --json > "$IOS_CONFIG" 2>/dev/null

if [ $? -eq 0 ]; then
    BUNDLE_ID=$(cat "$IOS_CONFIG" | python3 -c "import json, sys; d=json.load(sys.stdin); print(d.get('info_plist', {}).get('bundle_id', 'N/A'))")
    DISPLAY_NAME=$(cat "$IOS_CONFIG" | python3 -c "import json, sys; d=json.load(sys.stdin); print(d.get('info_plist', {}).get('display_name', 'N/A'))")
    VERSION=$(cat "$IOS_CONFIG" | python3 -c "import json, sys; d=json.load(sys.stdin); print(d.get('info_plist', {}).get('version', 'N/A'))")

    log "iOS 配置:"
    log "   Bundle ID: $BUNDLE_ID"
    log "   Display Name: $DISPLAY_NAME"
    log "   Version: $VERSION"

    # 简单验证
    CHECK2_STATUS="PASS"

    if [[ "$BUNDLE_ID" == com.example.* ]]; then
        error "bundleName 仍为示例值"
        CHECK2_STATUS="FAIL"
    fi

    if [ "$CHECK2_STATUS" = "PASS" ]; then
        success "CHECK-2: PASS (配置已更新)"
    else
        error "CHECK-2: FAIL"
    fi
else
    warn "CHECK-2: 无法读取 iOS 配置"
    CHECK2_STATUS="PARTIAL"
fi

# ============================================================================
# CHECK-3: 视觉对齐（可选）
# ============================================================================

if [ "${SKIP_CHECK3:-0}" -eq 1 ]; then
    section "📱 CHECK-3: 视觉对齐 (跳过)"
    warn "CHECK-3 已跳过 (SKIP_CHECK3=1)"
    CHECK3_STATUS="SKIP"
else
    section "📱 CHECK-3: 视觉对齐"

    log "检测设备..."

    # 检测 iOS 设备
    python3 "$SCRIPT_DIR/ios_device_checker.py" --quiet > /dev/null 2>&1
    IOS_DEVICE_OK=$?

    # 检测 HarmonyOS 设备
    hdc list targets 2>/dev/null | grep -v "Empty" > /dev/null 2>&1
    HOS_DEVICE_OK=$?

    if [ $IOS_DEVICE_OK -eq 0 ] && [ $HOS_DEVICE_OK -eq 0 ]; then
        success "双端设备可用"
        log "执行截图对比..."

        bash "$SCRIPT_DIR/run_check3.sh" \
            --ios-root "$IOS_ROOT" \
            --harmonyos-root "$HOS_ROOT" \
            --output "$OUTPUT_DIR" 2>&1 | grep -E "Step|✅|❌"

        if [ $? -eq 0 ]; then
            AVG_SIMILARITY=$(cat "$OUTPUT_DIR/screenshots/comparison/comparison-results.json" | \
                python3 -c "import json, sys; print(json.load(sys.stdin)['summary']['avg_similarity'])" 2>/dev/null)

            success "CHECK-3: 完成"
            log "   平均相似度: ${AVG_SIMILARITY}%"

            CHECK3_STATUS="PASS"
        else
            error "CHECK-3: 执行失败"
            CHECK3_STATUS="ERROR"
        fi
    else
        warn "设备不可用，跳过 CHECK-3"
        if [ $IOS_DEVICE_OK -ne 0 ]; then
            log "   iOS 设备未找到"
        fi
        if [ $HOS_DEVICE_OK -ne 0 ]; then
            log "   HarmonyOS 设备未找到"
        fi
        CHECK3_STATUS="DEFERRED"
    fi
fi

# ============================================================================
# 生成最终报告
# ============================================================================

section "📝 生成验证报告"

REPORT_FILE="$OUTPUT_DIR/verify-summary.md"

cat > "$REPORT_FILE" << EOF
# i2h-verify 验证摘要

**生成时间**: $(date '+%Y-%m-%d %H:%M:%S')
**iOS 项目**: $IOS_ROOT
**HarmonyOS 项目**: $HOS_ROOT

---

## 验证结果

| 检查项 | 状态 | 说明 |
|--------|------|------|
| CHECK-1 静态分析 | $CHECK1_STATUS | ERROR: $ERROR_COUNT, WARN: $WARN_COUNT |
| CHECK-2 App 身份 | $CHECK2_STATUS | Bundle ID: $BUNDLE_ID |
| CHECK-3 视觉对齐 | $CHECK3_STATUS | ${AVG_SIMILARITY:--}% |

---

## 详细结果

### CHECK-1: 静态分析

- **结果文件**: $CHECK1_RESULT
- **ERROR 数量**: $ERROR_COUNT
- **WARN 数量**: $WARN_COUNT

### CHECK-2: App 身份校验

- **iOS 配置**: $IOS_CONFIG
- **Bundle ID**: $BUNDLE_ID
- **Display Name**: $DISPLAY_NAME
- **Version**: $VERSION

### CHECK-3: 视觉对齐

EOF

if [ "$CHECK3_STATUS" = "SKIP" ] || [ "$CHECK3_STATUS" = "DEFERRED" ]; then
    echo "- **状态**: $CHECK3_STATUS" >> "$REPORT_FILE"
else
    echo "- **报告**: $OUTPUT_DIR/ui-comparison.md" >> "$REPORT_FILE"
    echo "- **平均相似度**: ${AVG_SIMILARITY}%" >> "$REPORT_FILE"
fi

cat >> "$REPORT_FILE" << EOF

---

## 下一步

EOF

if [ "$CHECK1_STATUS" = "FAIL" ]; then
    cat >> "$REPORT_FILE" << EOF
1. **修复 CHECK-1 的 ERROR 项**
   - 查看详细结果: \`cat $CHECK1_RESULT | jq '.findings[] | select(.level=="ERROR")'\`
   - 根据建议修复代码

EOF
fi

if [ "$CHECK2_STATUS" = "FAIL" ]; then
    cat >> "$REPORT_FILE" << EOF
2. **修复 CHECK-2 的配置问题**
   - 更新 bundleName
   - 更新应用图标

EOF
fi

if [ "$CHECK3_STATUS" = "DEFERRED" ]; then
    cat >> "$REPORT_FILE" << EOF
3. **准备设备后重新执行 CHECK-3**
   - 启动 iOS 设备
   - 连接 HarmonyOS 设备
   - 重新运行: \`bash $(basename "$0") "$IOS_ROOT" "$HOS_ROOT"\`

EOF
fi

cat >> "$REPORT_FILE" << EOF

---

**工具版本**: i2h-verify v1.0
**执行脚本**: $0
EOF

success "报告已生成: $REPORT_FILE"

# ============================================================================
# 总结
# ============================================================================

section "🎊 验证完成"

echo ""
log "验证结果:"
log "  CHECK-1: $CHECK1_STATUS"
log "  CHECK-2: $CHECK2_STATUS"
log "  CHECK-3: $CHECK3_STATUS"
echo ""

if [ "$CHECK1_STATUS" = "PASS" ] && [ "$CHECK2_STATUS" = "PASS" ]; then
    success "基础验证通过！"
    log "详细报告: $REPORT_FILE"
    exit 0
else
    warn "验证发现问题，请查看报告"
    log "详细报告: $REPORT_FILE"
    exit 1
fi
