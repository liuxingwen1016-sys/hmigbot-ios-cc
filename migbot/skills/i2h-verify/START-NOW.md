# 🚀 立即使用指南

**目标**: 在你的真实 iOS→HarmonyOS 项目上运行 i2h-verify

---

## ⚡ 最快方式（3分钟）

### Step 1: 克隆/更新代码

```bash
cd ~/Codes/ios2harmony/hmigbot-ios
git pull
```

### Step 2: 安装依赖

```bash
# macOS
brew install ripgrep libimobiledevice

# Python 包
pip3 install Pillow imagehash
```

### Step 3: 运行验证

```bash
cd migbot/skills/i2h-verify

# 替换为你的实际路径
bash scripts/e2e_verify.sh \
    /path/to/your/ios/project \
    /path/to/your/harmonyos/project
```

**就这么简单！** 🎉

---

## 📋 验证结果

脚本会自动：

1. ✅ **CHECK-1**: 静态分析（15项检查）
2. ✅ **CHECK-2**: App身份校验
3. ✅ **CHECK-3**: 视觉对齐（如果设备可用）

生成报告：`spec/verify/verify-summary.md`

---

## 🎯 典型输出

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 CHECK-1: 静态分析
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[12:34:56] 执行 15 项静态检查...
✅ CHECK-1: PASS
   ERROR: 0, WARN: 3

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📄 CHECK-2: App 身份校验
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[12:34:58] iOS 配置:
   Bundle ID: com.mycompany.myapp
   Display Name: MyApp
   Version: 1.0.0
✅ CHECK-2: PASS (配置已更新)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎊 验证完成
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
验证结果:
  CHECK-1: PASS
  CHECK-2: PASS
  CHECK-3: DEFERRED

✅ 基础验证通过！
详细报告: spec/verify/verify-summary.md
```

---

## 🔧 分项验证

如果你只想运行特定检查：

### 仅 CHECK-1（静态分析）

```bash
cd migbot/skills/i2h-verify

python3 scripts/ios_static_analyzer.py \
    /path/to/harmonyos/project
```

**1分钟完成**，立即看到结果。

### 仅 CHECK-2（配置检查）

```bash
python3 scripts/ios_config_parser.py \
    /path/to/ios/project
```

### 仅 CHECK-3（截图对比）

```bash
# 前提：设备已连接
bash scripts/run_check3.sh \
    --ios-root /path/to/ios \
    --harmonyos-root /path/to/harmonyos
```

---

## 📊 查看详细结果

```bash
# 验证摘要
cat spec/verify/verify-summary.md

# CHECK-1 详细结果
cat spec/verify/check1_result.json | jq '.findings[] | select(.level=="ERROR")'

# CHECK-3 UI 对比
cat spec/verify/ui-comparison.md

# 查看截图
open spec/verify/screenshots/ios/
open spec/verify/screenshots/harmonyos/
```

---

## 💡 常见场景

### 场景 1: 快速检查是否有 ERROR

```bash
cd migbot/skills/i2h-verify

python3 scripts/ios_static_analyzer.py \
    /path/to/harmonyos/project \
    -o /tmp/result.json

# 查看 ERROR 数量
cat /tmp/result.json | jq '.summary.error_count'

# 如果是 0，说明没有 ERROR ✅
```

### 场景 2: 持续集成（CI）

```bash
#!/bin/bash
# 在 CI 中使用

cd /path/to/hmigbot-ios/migbot/skills/i2h-verify

python3 scripts/ios_static_analyzer.py "$WORKSPACE/harmonyos"

if [ $? -eq 0 ]; then
    echo "✅ 静态分析通过"
    exit 0
else
    echo "❌ 静态分析失败"
    exit 1
fi
```

### 场景 3: 本地开发验证

```bash
# 添加到你的 .bashrc 或 .zshrc
alias verify-ios='cd ~/hmigbot-ios/migbot/skills/i2h-verify && python3 scripts/ios_static_analyzer.py'

# 使用
verify-ios /path/to/project
```

---

## 🎯 试点建议

### 第一次运行

1. **选择一个小项目**（1-3个页面）
2. **运行端到端验证**
3. **修复发现的 ERROR**
4. **重新验证直到 PASS**

### 时间估算

- 小项目（1-3页面）: 5-10分钟
- 中项目（5-10页面）: 15-30分钟
- 大项目（10+页面）: 30-60分钟

### 预期结果

**第一次运行可能会发现**:
- 2-5个 ERROR（常见：DispatchQueue、UserDefaults）
- 5-10个 WARN（建议项）
- 配置问题（bundleName、图标）

**修复后**:
- ERROR: 0
- WARN: 可保留
- 配置: 已更新

---

## 🔍 故障排除

### 问题：找不到 rg 命令

```bash
brew install ripgrep
```

### 问题：Python 包未安装

```bash
pip3 install Pillow imagehash
```

### 问题：设备未检测到

```bash
# iOS 模拟器
open -a Simulator

# iOS 真机
brew install libimobiledevice
idevice_id -l

# HarmonyOS
hdc list targets
```

### 问题：权限错误

```bash
chmod +x scripts/*.sh
```

---

## 📞 获取帮助

### 查看脚本帮助

```bash
python3 scripts/ios_static_analyzer.py --help
python3 scripts/ios_device_checker.py --help
bash scripts/run_check3.sh --help
```

### 详细文档

- [QUICKSTART.md](QUICKSTART.md) - 快速入门
- [scripts/README.md](scripts/README.md) - 脚本文档
- [references/](references/) - 检查规则详解

---

## ✅ 准备就绪！

你现在可以：

1. ✅ 在任何 iOS→HarmonyOS 项目上运行验证
2. ✅ 5分钟内获得验证结果
3. ✅ 根据报告修复问题
4. ✅ 持续验证确保质量

**立即开始**:

```bash
cd ~/Codes/ios2harmony/hmigbot-ios/migbot/skills/i2h-verify

bash scripts/e2e_verify.sh \
    YOUR_IOS_PROJECT_PATH \
    YOUR_HARMONYOS_PROJECT_PATH
```

---

**版本**: v1.0  
**最后更新**: 2024-11-04 01:15  
**状态**: ✅ 生产就绪

🚀 **祝验证顺利！**
