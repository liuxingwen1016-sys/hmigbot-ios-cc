# i2h-verify Scripts

i2h-verify 的辅助脚本工具集

---

## 📋 脚本清单

| 脚本 | 功能 | 优先级 |
|------|------|--------|
| ios_device_checker.py | iOS 设备检测 | ⭐⭐⭐⭐⭐ |
| ios_config_parser.py | iOS 配置解析 | ⭐⭐⭐⭐⭐ |
| ios_static_analyzer.py | iOS 静态分析 | ⭐⭐⭐⭐⭐ |
| compare_screenshots.py | 截图相似度对比 | ⭐⭐⭐⭐⭐ |
| generate_ui_report.py | UI 对比报告生成 | ⭐⭐⭐⭐⭐ |

---

## 🚀 使用方法

### 1. ios_device_checker.py

**功能**: 检测 iOS 模拟器和真机设备

**用法**:
```bash
# 检测所有设备（默认输出）
python3 ios_device_checker.py

# JSON 输出
python3 ios_device_checker.py --json

# 静默模式（只输出 UDID）
python3 ios_device_checker.py --quiet

# 指定设备类型
python3 ios_device_checker.py --type simulator
python3 ios_device_checker.py --type physical
```

**依赖**:
- xcrun (macOS 自带，用于模拟器)
- libimobiledevice (可选，用于真机)
  ```bash
  brew install libimobiledevice
  ```

---

### 2. ios_config_parser.py

**功能**: 解析 iOS Info.plist 和 Assets.xcassets

**用法**:
```bash
# 解析所有配置
python3 ios_config_parser.py /path/to/ios/project

# 只解析 Info.plist
python3 ios_config_parser.py /path/to/ios/project --plist-only

# 只解析 AppIcon
python3 ios_config_parser.py /path/to/ios/project --icon-only

# JSON 输出
python3 ios_config_parser.py /path/to/ios/project --json
```

**依赖**:
- Python 标准库 (plistlib, json)
- 支持 XML 和 Binary plist 格式

---

### 3. ios_static_analyzer.py

**功能**: 执行 15 项静态分析检查

**用法**:
```bash
# 分析项目
python3 ios_static_analyzer.py /path/to/harmonyos/project

# JSON 输出
python3 ios_static_analyzer.py /path/to/harmonyos/project --json

# 保存结果
python3 ios_static_analyzer.py /path/to/harmonyos/project -o result.json

# 详细输出
python3 ios_static_analyzer.py /path/to/harmonyos/project -v
```

**检查规则**:
- 6 项通用检查（any 类型、SQL 拼接、eval 等）
- 9 项 iOS 特有检查（强制解包、DispatchQueue、UserDefaults 等）

**依赖**:
- ripgrep (rg)
  ```bash
  brew install ripgrep
  ```

---

### 4. compare_screenshots.py

**功能**: 对比 iOS 和 HarmonyOS 截图相似度

**用法**:
```bash
# 对比截图
python3 compare_screenshots.py ios_screenshots/ harmonyos_screenshots/

# JSON 输出
python3 compare_screenshots.py ios_screenshots/ harmonyos_screenshots/ --json

# 保存结果
python3 compare_screenshots.py ios_screenshots/ harmonyos_screenshots/ -o result.json

# 自定义哈希大小
python3 compare_screenshots.py ios_screenshots/ harmonyos_screenshots/ --hash-size 32
```

**算法**:
- 感知哈希 (Perceptual Hash)
- 汉明距离计算
- 相似度阈值：≥95% 高度匹配，≥85% 良好，<85% 差异较大

**依赖**:
- Pillow
- imagehash
  ```bash
  pip3 install Pillow imagehash
  ```

---

### 5. generate_ui_report.py

**功能**: 根据对比结果生成详细的 Markdown 报告

**用法**:
```bash
# 生成报告
python3 generate_ui_report.py comparison_results.json ui_comparison.md

# 打印报告到控制台
python3 generate_ui_report.py comparison_results.json ui_comparison.md --print
```

**输出**:
- 总体统计
- 分页对比结果
- 差异分析
- 修复建议
- CHECK-3 判定

---

## 🔄 完整工作流

### CHECK-1: 静态分析

```bash
# 执行静态分析
python3 ios_static_analyzer.py /path/to/harmonyos/project -o check1_result.json

# 查看结果
cat check1_result.json | jq '.summary'
```

### CHECK-2: App 身份校验

```bash
# 解析 iOS 配置
python3 ios_config_parser.py /path/to/ios/project --json > ios_config.json

# 对比 HarmonyOS 配置（在主程序中实现）
```

### CHECK-3: 视觉对比

```bash
# 1. 检测设备
python3 ios_device_checker.py

# 2. 截图（使用 Shell 脚本）
# iOS: xcrun simctl io <device> screenshot <file>
# HarmonyOS: hdc shell snapshot_display -f <path>

# 3. 对比截图
python3 compare_screenshots.py \
    spec/verify/screenshots/ios \
    spec/verify/screenshots/harmonyos \
    -o comparison_results.json

# 4. 生成报告
python3 generate_ui_report.py \
    comparison_results.json \
    spec/verify/ui_comparison.md
```

---

## 📦 依赖安装

### macOS

```bash
# 安装 Homebrew 工具
brew install ripgrep libimobiledevice

# 安装 Python 包
pip3 install Pillow imagehash
```

### 验证安装

```bash
# 检查 rg
which rg

# 检查 xcrun
which xcrun

# 检查 idevice (可选)
which idevice_id

# 检查 Python 包
python3 -c "import PIL, imagehash; print('OK')"
```

---

## 🧪 测试

每个脚本都可以独立测试：

```bash
# 测试设备检测
python3 ios_device_checker.py --json

# 测试配置解析（需要 iOS 项目）
python3 ios_config_parser.py /path/to/ios/project

# 测试静态分析（需要 HarmonyOS 项目）
python3 ios_static_analyzer.py /path/to/harmonyos/project

# 测试截图对比（需要截图目录）
python3 compare_screenshots.py test_ios/ test_harmonyos/
```

---

## 📝 返回状态码

所有脚本都遵循标准返回码：

- `0`: 成功
- `1`: 失败或发现问题

可用于脚本自动化：

```bash
if python3 ios_static_analyzer.py /path/to/project; then
    echo "静态分析通过"
else
    echo "静态分析失败"
fi
```

---

## 🔍 调试

使用 `-v` 或 `--verbose` 选项获取详细输出：

```bash
python3 ios_static_analyzer.py /path/to/project -v
```

使用 `--json` 选项输出机器可读格式：

```bash
python3 ios_device_checker.py --json | jq .
```

---

## 📚 参考文档

- [static-and-identity.md](../references/static-and-identity.md) - CHECK-1/2 规则
- [device-verification.md](../references/device-verification.md) - CHECK-3 实现
- [ios-specific-checks.md](../references/ios-specific-checks.md) - iOS 特有检查

---

**版本**: v1.0  
**创建时间**: 2024-11-04  
**状态**: ✅ 所有脚本已完成
