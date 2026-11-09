# i2h-verify 快速入门指南

**目标**: 5 分钟内开始验证你的 iOS→HarmonyOS 迁移项目

---

## 🚀 快速开始

### 前置条件

```bash
# 1. 安装依赖
brew install ripgrep libimobiledevice  # macOS
pip3 install Pillow imagehash          # Python 包

# 2. 验证安装
which rg xcrun hdc
python3 -c "import PIL, imagehash; print('OK')"
```

### 基本用法

```bash
# 进入项目目录
cd /path/to/hmigbot-ios/migbot/skills/i2h-verify

# 设置路径变量
export IOS_ROOT="/path/to/your/ios/project"
export HOS_ROOT="/path/to/your/harmonyos/project"
```

---

## ✅ CHECK-1: 静态分析（2分钟）

**一键执行**:

```bash
python3 scripts/ios_static_analyzer.py "$HOS_ROOT"
```

**查看结果**:
- 终端输出：ERROR 和 WARN 统计
- JSON 结果：`-o result.json`

**快速修复**:
- ERROR 必须修复
- WARN 建议修复

---

## ✅ CHECK-2: App 身份校验（1分钟）

**一键执行**:

```bash
# 1. 解析 iOS 配置
python3 scripts/ios_config_parser.py "$IOS_ROOT" --json > ios_config.json

# 2. 检查关键项
cat ios_config.json | jq '.info_plist | {bundle_id, display_name, version}'
```

**手动验证**:
对比 HarmonyOS `AppScope/app.json5`:
- bundleName 不是 `com.example.*`
- vendor 不是 `example`
- 版本号一致

---

## ✅ CHECK-3: 视觉对齐（5-10分钟）

**前提**:
- iOS 模拟器或真机正在运行
- HarmonyOS 设备已连接

**一键执行**:

```bash
bash scripts/run_check3.sh \
    --ios-root "$IOS_ROOT" \
    --harmonyos-root "$HOS_ROOT" \
    --output spec/verify
```

**查看结果**:

```bash
# 查看报告
cat spec/verify/ui-comparison.md

# 查看截图
open spec/verify/screenshots/ios/
open spec/verify/screenshots/harmonyos/
```

**快速诊断**:
- 平均相似度 ≥95%: ✅ PASS
- 平均相似度 85-95%: ⚠️ 轻微差异
- 平均相似度 <85%: ❌ 需要修复

---

## ⚡ 最小可用示例

**只验证静态分析**（最快）:

```bash
cd /path/to/hmigbot-ios/migbot/skills/i2h-verify

# 静态分析
python3 scripts/ios_static_analyzer.py \
    /path/to/harmonyos/project \
    -o check1_result.json

# 查看结果
cat check1_result.json | jq '.summary'
```

**完整验证**（包含截图对比）:

```bash
# 1. 检测设备
python3 scripts/ios_device_checker.py

# 2. 执行完整 CHECK-3
bash scripts/run_check3.sh \
    --ios-root /path/to/ios \
    --harmonyos-root /path/to/harmonyos \
    --verbose

# 3. 查看报告
cat spec/verify/ui-comparison.md
```

---

## 🎯 真实项目试点步骤

### Step 1: 准备（1分钟）

```bash
# 克隆或进入项目
cd ~/Codes/ios2harmony/hmigbot-ios

# 设置路径
export IOS_ROOT="你的iOS项目路径"
export HOS_ROOT="你的HarmonyOS项目路径"

# 验证路径
ls "$IOS_ROOT/Info.plist"
ls "$HOS_ROOT/AppScope/app.json5"
```

### Step 2: 快速检查（3分钟）

```bash
cd migbot/skills/i2h-verify

# 1. 静态分析
echo "🔍 执行静态分析..."
python3 scripts/ios_static_analyzer.py "$HOS_ROOT" -o /tmp/check1.json

# 2. 查看 ERROR 数量
ERROR_COUNT=$(cat /tmp/check1.json | jq '.summary.error_count')
echo "ERROR 数量: $ERROR_COUNT"

if [ "$ERROR_COUNT" -eq 0 ]; then
    echo "✅ CHECK-1 通过"
else
    echo "❌ CHECK-1 失败，需要修复 $ERROR_COUNT 个 ERROR"
    cat /tmp/check1.json | jq '.findings[] | select(.level=="ERROR")'
fi
```

### Step 3: 配置检查（1分钟）

```bash
# 解析 iOS 配置
python3 scripts/ios_config_parser.py "$IOS_ROOT" --json > /tmp/ios_config.json

# 显示关键信息
echo "iOS 配置:"
cat /tmp/ios_config.json | jq '.info_plist | {bundle_id, display_name, version}'

echo ""
echo "HarmonyOS 配置:"
cat "$HOS_ROOT/AppScope/app.json5" | grep -E "(bundleName|vendor|versionName)" | head -3
```

### Step 4: 视觉验证（可选，10分钟）

```bash
# 检测设备
python3 scripts/ios_device_checker.py

# 如果有设备，执行截图对比
bash scripts/run_check3.sh \
    --ios-root "$IOS_ROOT" \
    --harmonyos-root "$HOS_ROOT" \
    --verbose

# 查看结果
cat spec/verify/ui-comparison.md
```

---

## 📊 快速诊断脚本

保存为 `quick_verify.sh`:

```bash
#!/bin/bash
set -e

IOS_ROOT="${1:-$IOS_ROOT}"
HOS_ROOT="${2:-$HOS_ROOT}"

if [ -z "$IOS_ROOT" ] || [ -z "$HOS_ROOT" ]; then
    echo "用法: $0 <ios-root> <hos-root>"
    exit 1
fi

cd "$(dirname "$0")"

echo "═══════════════════════════════════════"
echo "i2h-verify 快速验证"
echo "═══════════════════════════════════════"
echo ""

# CHECK-1
echo "🔍 CHECK-1: 静态分析"
python3 scripts/ios_static_analyzer.py "$HOS_ROOT" -o /tmp/check1.json 2>/dev/null
ERROR_COUNT=$(cat /tmp/check1.json | jq -r '.summary.error_count')
WARN_COUNT=$(cat /tmp/check1.json | jq -r '.summary.warn_count')

if [ "$ERROR_COUNT" -eq 0 ]; then
    echo "   ✅ PASS (WARN: $WARN_COUNT)"
else
    echo "   ❌ FAIL (ERROR: $ERROR_COUNT, WARN: $WARN_COUNT)"
fi
echo ""

# CHECK-2
echo "📄 CHECK-2: App 身份"
python3 scripts/ios_config_parser.py "$IOS_ROOT" --json > /tmp/ios_config.json 2>/dev/null
if [ -f /tmp/ios_config.json ]; then
    BUNDLE_ID=$(cat /tmp/ios_config.json | jq -r '.info_plist.bundle_id // "N/A"')
    if [[ "$BUNDLE_ID" == com.example.* ]]; then
        echo "   ❌ bundleName 仍为示例值"
    else
        echo "   ✅ 配置已更新"
    fi
else
    echo "   ⚠️  无法读取配置"
fi
echo ""

# CHECK-3
echo "📱 CHECK-3: 设备检测"
python3 scripts/ios_device_checker.py --quiet > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo "   ✅ iOS 设备可用"
else
    echo "   ⚠️  iOS 设备不可用（可选）"
fi
echo ""

echo "═══════════════════════════════════════"
echo "快速验证完成"
echo "═══════════════════════════════════════"
```

使用：

```bash
chmod +x quick_verify.sh
./quick_verify.sh /path/to/ios /path/to/harmonyos
```

---

## 🔧 故障排除

### 问题 1: rg 命令未找到

```bash
brew install ripgrep
```

### 问题 2: PIL/imagehash 未安装

```bash
pip3 install Pillow imagehash
```

### 问题 3: iOS 设备未检测到

```bash
# 模拟器
xcrun simctl list devices | grep Booted

# 真机
brew install libimobiledevice
idevice_id -l
```

### 问题 4: HarmonyOS 设备未检测到

```bash
hdc list targets

# 如果是 Empty，检查：
# 1. 设备是否连接
# 2. hdc 是否在 PATH 中
```

---

## 📝 输出文件位置

```
spec/verify/
├── check1_result.json              # CHECK-1 结果
├── ios_config.json                 # iOS 配置
├── ui-comparison.md                # CHECK-3 报告
└── screenshots/
    ├── ios/                        # iOS 截图
    ├── harmonyos/                  # HarmonyOS 截图
    └── comparison/
        └── comparison-results.json # 对比结果
```

---

## ⚡ 一键验证（最快方式）

```bash
# 设置一次
export IOS_ROOT="/path/to/ios"
export HOS_ROOT="/path/to/harmonyos"

# 每次验证
cd /path/to/hmigbot-ios/migbot/skills/i2h-verify && \
python3 scripts/ios_static_analyzer.py "$HOS_ROOT" && \
echo "✅ 验证完成"
```

---

**版本**: v1.0  
**更新时间**: 2024-11-04  
**适用于**: i2h-verify Phase 1-4
