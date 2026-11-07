---
name: i2h-verify
description: 验证迁移结果（Pipeline 第四步）：编译验证 + 结构验证 + API验证 + 可选的视觉/行为验证
tags: [pipeline, migration]
type: pipeline
domain: migration
---

# i2h-verify

Pipeline 第四步：验证迁移的完整性和正确性。

## 启动检查 — 待办 findings

读取 `spec/.i2h/open-findings.json`：

| 情况 | 行动 |
|---|---|
| 有 `owner_stage: verify` 的条目 | 先处理这些 |
| 有上游 blocking findings | 🔴 拒绝开工 |

## 1. 前置检查

检查 execute 产出物：
- [ ] `spec/migration-report.md` 存在
- [ ] `spec/execute/stage3-complete.txt` 存在

缺失 → 停止，提示先运行 `/i2h-execute`

## 2. 选择验证项

在开始任何检查前，确定执行范围：

**固定执行**:
- CHECK-1: 编译验证（必须）
- CHECK-2: 结构验证（必须）

**可选执行** (询问用户):
- CHECK-3: API 验证
- CHECK-4: UI 对比验证（需要真机）
- CHECK-5: 行为验证（需要真机）

## 3. CHECK-1: 编译验证

### Step 1.1: 清理旧构建

```bash
cd "$HOS_PATH"
./hvigorw clean
```

### Step 1.2: 完整编译

```bash
./hvigorw assembleHap --mode module -p module=entry@default --no-daemon 2>&1 | tee /tmp/i2h_compile.log
```

### Step 1.3: 分析编译结果

```python
def analyze_compile_log(log_path):
    """分析编译日志"""
    with open(log_path) as f:
        log = f.read()
    
    errors = []
    warnings = []
    
    # 提取错误
    for match in re.finditer(r'ERROR.*?(\w+\.ets):(\d+)', log):
        errors.append({
            'file': match.group(1),
            'line': int(match.group(2)),
        })
    
    # 提取警告
    for match in re.finditer(r'WARN.*?(\w+\.ets):(\d+)', log):
        warnings.append({
            'file': match.group(1),
            'line': int(match.group(2)),
        })
    
    return errors, warnings
```

### Step 1.4: 生成编译报告

生成 `spec/verify/compile-report.md`:

```markdown
# 编译验证报告

## 编译结果
状态: ✅ 成功 / ❌ 失败

## 编译统计
- 总文件数: 65
- 成功: 65
- 错误: 0
- 警告: 3

## 警告详情
1. HomeView.ets:42 - Unused variable 'temp'
2. DataStore.ets:123 - Deprecated API usage
3. Router.ets:56 - Type inference fallback

## 评估
- 可部署: ✅ 是
- 需要修复: 0 个错误
- 建议优化: 3 个警告
```

**Findings 报告**:
- 编译错误 → `COMPILE.BUILD_FAILURE` (blocking)
- 警告 → `COMPILE.WARNING` (warn)

## 4. CHECK-2: 结构验证

### Step 2.1: 验证目录结构

```bash
python3 .migbot/bin/scripts/verifiers/verify_structure.py "$HOS_PATH"
```

检查：
- [ ] entry/src/main/ets/ 结构完整
- [ ] pages/ 目录存在且有文件
- [ ] resources/ 目录结构正确
- [ ] module.json5 存在且有效

### Step 2.2: 验证文件完整性

对比 UI Plan 和实际文件：

```python
def verify_file_completeness(project_root):
    """验证文件完整性"""
    with open(f"{project_root}/spec/baseline/plans/ui-plan.json") as f:
        ui_plan = json.load(f)
    
    expected_files = set()
    for batch in ui_plan["batches"]:
        for page in batch["pages"]:
            expected_files.add(page["output"])
    
    hos_path = get_harmonyos_path(project_root)
    actual_files = set()
    for f in Path(f"{hos_path}/entry/src/main/ets/pages").glob("*.ets"):
        actual_files.add(f"pages/{f.name}")
    
    missing = expected_files - actual_files
    extra = actual_files - expected_files
    
    return missing, extra
```

### Step 2.3: 生成结构报告

生成 `spec/verify/structure-report.md`:

```markdown
# 结构验证报告

## 目录结构
✅ entry/src/main/ets/ 完整
✅ pages/ (11 个文件)
✅ components/ (5 个文件)
✅ models/ (3 个文件)
✅ services/ (4 个文件)
✅ utils/ (2 个文件)

## 文件完整性
预期文件: 11
实际文件: 11
状态: ✅ 完整

详细对比:
| iOS 文件 | HarmonyOS 文件 | 状态 |
|---------|---------------|------|
| HomeView.swift | HomeView.ets | ✅ |
| SettingsView.swift | SettingsView.ets | ✅ |
...

## 配置文件
✅ module.json5 有效
✅ main_pages.json 完整
✅ oh-package.json5 有效
```

## 5. CHECK-3: API 验证（可选）

如果用户选择：

### Step 3.1: 扫描 API 使用

```bash
cd "$HOS_PATH/entry/src/main/ets"
grep -r "import.*@ohos" . > /tmp/i2h_api_usage.txt
```

### Step 3.2: 验证 API 可用性

```python
def verify_api_availability(api_usage_file):
    """验证 API 可用性"""
    with open(api_usage_file) as f:
        lines = f.readlines()
    
    api_stats = {}
    deprecated = []
    
    for line in lines:
        if match := re.search(r'@ohos\.(\w+)', line):
            api = match.group(1)
            api_stats[api] = api_stats.get(api, 0) + 1
            
            # 检查是否已弃用
            if is_deprecated(api):
                deprecated.append(api)
    
    return api_stats, deprecated
```

### Step 3.3: 生成 API 报告

生成 `spec/verify/api-report.md`:

```markdown
# API 使用验证

## 常用 API
✅ @ohos.router (18 次)
✅ @ohos.data.preferences (5 次)
✅ @ohos.data.relationalStore (12 次)
✅ @ohos.notificationManager (3 次)

## API 覆盖
- 导航: ✅ 完整
- 数据存储: ✅ 完整
- 系统服务: ✅ 部分（缺少 OCR）

## 潜在问题
⚠️  使用了 1 个已弃用 API
   - @ohos.data.storage (建议替换为 preferences)

## 评估
总体: ✅ API 使用正确
```

## 6. CHECK-4: UI 对比验证

**执行条件**: 自动检测设备可用性

**设计原则**（参考 hmigbot arkts-visual-verify）:
- 完全自动化，不暂停，不问用户
- iOS 端截图作为 baseline
- HarmonyOS 端截图与 baseline 对比
- 批量处理所有页面
- 最后一次性生成完整报告

### Step 4.0: 设备可用性检测

在执行 UI 对比前，先检测双端设备是否可用：

```bash
# 读取配置
config_file=".migbot/config.json"
ios_bundle=$(python3 -c "import json; print(json.load(open('$config_file'))['ios_bundle_id'])" 2>/dev/null || echo "")
hos_bundle=$(python3 -c "import json; print(json.load(open('$config_file'))['harmonyos_bundle'])" 2>/dev/null || echo "")

# 读取工具路径（从 config.json，避免重复探测）
HDC=$(python3 -c "import json; print(json.load(open('$config_file')).get('hdc', 'hdc'))")
XCRUN=$(python3 -c "import json; print(json.load(open('$config_file')).get('xcrun', 'xcrun'))")

# 检测 iOS 设备/模拟器
ios_available=false
if $XCRUN simctl list devices | grep -q "Booted"; then
    echo "✅ iOS 模拟器已启动"
    ios_available=true
    ios_device=$($XCRUN simctl list devices | grep "Booted" | head -1 | sed -E 's/.*\(([^)]+)\).*/\1/')
elif command -v idevice_id &> /dev/null && idevice_id -l | grep -q "."; then
    echo "✅ iOS 真机已连接"
    ios_available=true
    ios_device="physical"
else
    echo "❌ iOS 设备不可用"
    echo "   提示: 启动 iOS 模拟器或连接 iPhone"
fi

# 检测 HarmonyOS 设备/模拟器
hos_available=false
if $HDC list targets | grep -v "Empty" | grep -q "."; then
    echo "✅ HarmonyOS 设备已连接"
    hos_available=true
    hos_device=$($HDC list targets | grep -v "Empty" | head -1)
else
    echo "❌ HarmonyOS 设备不可用"
    echo "   提示: 启动 HarmonyOS 模拟器或连接设备"
fi

# 判断是否可以执行
if [ "$ios_available" = false ] || [ "$hos_available" = false ]; then
    echo ""
    echo "⚠️  CHECK-4 状态: DEFERRED（原因：设备不可用）"
    echo ""
    echo "需要:"
    [ "$ios_available" = false ] && echo "  - iOS 设备/模拟器"
    [ "$hos_available" = false ] && echo "  - HarmonyOS 设备/模拟器"
    echo ""
    
    # 生成 DEFERRED 报告
    mkdir -p spec/verify
    cat > spec/verify/ui-comparison.md << 'EOF'
# UI 对比验证报告

## 执行状态
⏸️ DEFERRED - 设备不可用

## 原因
EOF
    [ "$ios_available" = false ] && echo "- iOS 设备/模拟器未连接" >> spec/verify/ui-comparison.md
    [ "$hos_available" = false ] && echo "- HarmonyOS 设备/模拟器未连接" >> spec/verify/ui-comparison.md
    
    cat >> spec/verify/ui-comparison.md << 'EOF'

## 解决方法

### 启动 iOS 模拟器
```bash
# 列出可用的模拟器
xcrun simctl list devices

# 启动指定的模拟器
xcrun simctl boot <device_id>

# 或使用 Xcode 启动
open -a Simulator
```

### 启动 HarmonyOS 模拟器
1. 打开 DevEco Studio
2. Tools → Device Manager
3. 启动一个模拟器

或使用命令行（如果已配置）:
```bash
# 检查设备
hdc list targets
```

### 重新运行验证
设备就绪后，重新运行:
```bash
/i2h-verify
```
EOF
    
    exit 0
fi

echo ""
echo "✅ 设备检测通过，开始 UI 对比验证"
echo ""
```

**如果设备不可用**: 
- 状态: DEFERRED
- 生成说明文档
- 退出 CHECK-4

**如果设备可用**: 继续执行自动化对比

### Step 4.1: 准备工作

```bash
# 创建截图目录
mkdir -p spec/verify/screenshots/ios
mkdir -p spec/verify/screenshots/harmonyos
mkdir -p spec/verify/screenshots/comparison

# 读取页面列表（从 spec 或配置）
pages=$(python3 -c "
import json
import os

# 尝试从不同来源获取页面列表
pages = []

# 1. 从 ui-manifest 读取
if os.path.exists('spec/baseline/ui-manifest.md'):
    with open('spec/baseline/ui-manifest.md', 'r') as f:
        content = f.read()
        # 简单提取页面名称（根据实际格式调整）
        import re
        pages = re.findall(r'##\s+(\w+View)', content)

# 2. 如果没有，使用默认页面列表
if not pages:
    pages = ['HomeView', 'SettingsView', 'ProfileView', 'AboutView']

print(','.join(pages))
" 2>/dev/null || echo "HomeView,SettingsView")

echo "📋 待对比页面: $pages"
echo ""
```

### Step 4.2: iOS 端截图（Baseline）

**完全自动化**，不需要手动操作：

```bash
echo "📱 iOS 端截图采集中..."

IFS=',' read -ra PAGE_ARRAY <<< "$pages"
ios_screenshots=""

for page in "${PAGE_ARRAY[@]}"; do
    echo "  截图: $page"
    
    # iOS 截图命令
    if [ "$ios_device" = "physical" ]; then
        # 真机截图（需要 libimobiledevice）
        idevicescreenshot spec/verify/screenshots/ios/${page}.png 2>/dev/null
    else
        # 模拟器截图
        $XCRUN simctl io $ios_device screenshot spec/verify/screenshots/ios/${page}.png 2>/dev/null
    fi
    
    if [ -f "spec/verify/screenshots/ios/${page}.png" ]; then
        echo "    ✅ iOS 截图成功"
        ios_screenshots="$ios_screenshots,$page"
    else
        echo "    ⚠️  iOS 截图失败（页面可能不可见）"
    fi
    
    # 小延迟，确保 UI 稳定
    sleep 1
done

echo ""
echo "✅ iOS 端截图完成"
echo ""
```

### Step 4.3: HarmonyOS 端截图

```bash
echo "📱 HarmonyOS 端截图采集中..."

# 确保应用已安装并启动
if [ -n "$hos_bundle" ]; then
    # 安装 HAP（如果需要）
    hap_file=$(find . -name "*.hap" -type f | head -1)
    if [ -n "$hap_file" ]; then
        echo "  安装应用: $hap_file"
        $HDC install "$hap_file" 2>/dev/null
    fi
    
    # 启动应用
    echo "  启动应用: $hos_bundle"
    $HDC shell aa start -a EntryAbility -b "$hos_bundle" 2>/dev/null
    sleep 2
fi

hos_screenshots=""

for page in "${PAGE_ARRAY[@]}"; do
    echo "  截图: $page"
    
    # HarmonyOS 截图
    $HDC shell snapshot_display -f /data/local/tmp/${page}.png 2>/dev/null
    $HDC file recv /data/local/tmp/${page}.png spec/verify/screenshots/harmonyos/${page}.png 2>/dev/null
    
    if [ -f "spec/verify/screenshots/harmonyos/${page}.png" ]; then
        echo "    ✅ HarmonyOS 截图成功"
        hos_screenshots="$hos_screenshots,$page"
    else
        echo "    ⚠️  HarmonyOS 截图失败"
    fi
    
    sleep 1
done

echo ""
echo "✅ HarmonyOS 端截图完成"
echo ""
```

### Step 4.4: 图像相似度对比

使用 Python 脚本计算相似度：

```python
# 创建对比脚本
cat > /tmp/compare_screenshots.py << 'SCRIPT'
#!/usr/bin/env python3
"""
iOS vs HarmonyOS 截图相似度对比
使用感知哈希算法计算相似度
"""

import sys
import os
import json
from pathlib import Path

try:
    from PIL import Image
    import imagehash
except ImportError:
    print("错误: 需要安装 PIL 和 imagehash")
    print("运行: pip3 install Pillow imagehash")
    sys.exit(1)

def calculate_similarity(img1_path, img2_path):
    """计算两张图片的相似度（百分比）"""
    try:
        img1 = Image.open(img1_path)
        img2 = Image.open(img2_path)
        
        # 计算感知哈希
        hash1 = imagehash.phash(img1)
        hash2 = imagehash.phash(img2)
        
        # 计算汉明距离
        distance = hash1 - hash2
        
        # 转换为相似度百分比（64位哈希）
        similarity = (64 - distance) / 64 * 100
        
        return {
            "similarity": round(similarity, 2),
            "distance": int(distance),
            "status": "match" if similarity >= 95 else "diff"
        }
    except Exception as e:
        return {
            "similarity": 0,
            "distance": 64,
            "status": "error",
            "error": str(e)
        }

def main():
    if len(sys.argv) < 3:
        print("用法: compare_screenshots.py <ios_dir> <hos_dir>")
        sys.exit(1)
    
    ios_dir = Path(sys.argv[1])
    hos_dir = Path(sys.argv[2])
    
    results = []
    
    # 遍历所有 iOS 截图
    for ios_img in ios_dir.glob("*.png"):
        page_name = ios_img.stem
        hos_img = hos_dir / ios_img.name
        
        if not hos_img.exists():
            results.append({
                "page": page_name,
                "status": "missing_hos",
                "similarity": 0
            })
            continue
        
        # 计算相似度
        result = calculate_similarity(str(ios_img), str(hos_img))
        result["page"] = page_name
        result["ios_path"] = str(ios_img)
        result["hos_path"] = str(hos_img)
        
        results.append(result)
    
    # 输出 JSON 结果
    print(json.dumps(results, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
SCRIPT

chmod +x /tmp/compare_screenshots.py

# 执行对比
echo "🔍 计算相似度中..."
comparison_results=$(python3 /tmp/compare_screenshots.py \
    spec/verify/screenshots/ios \
    spec/verify/screenshots/harmonyos)

echo "$comparison_results" > spec/verify/comparison-results.json
echo "✅ 对比完成"
echo ""
```

### Step 4.5: 生成详细报告

**一次性生成完整报告**，包含所有页面的对比结果：

```python
cat > /tmp/generate_ui_report.py << 'SCRIPT'
#!/usr/bin/env python3
"""生成 UI 对比验证报告"""

import json
import sys
from pathlib import Path
from datetime import datetime

def generate_report(results_file, output_file):
    with open(results_file) as f:
        results = json.load(f)
    
    # 计算统计数据
    total = len(results)
    matched = len([r for r in results if r.get('similarity', 0) >= 95])
    avg_similarity = sum(r.get('similarity', 0) for r in results) / total if total > 0 else 0
    
    # 生成 Markdown 报告
    report = f"""# UI 对比验证报告

生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## 执行状态
✅ 已完成 - 双端自动截图对比

## 总体统计

- 对比页面数: {total}
- 高度匹配 (≥95%): {matched} 页
- 平均相似度: {avg_similarity:.1f}%
- 匹配率: {matched}/{total} ({matched/total*100:.1f}%)

## 分页对比结果

"""
    
    # 按相似度排序
    results.sort(key=lambda x: x.get('similarity', 0), reverse=True)
    
    for result in results:
        page = result['page']
        similarity = result.get('similarity', 0)
        status = result.get('status', 'unknown')
        
        if status == 'missing_hos':
            report += f"""### {page}
❌ **HarmonyOS 截图缺失**
- iOS 截图: 存在
- HarmonyOS 截图: 不存在
- 问题: 页面可能未实现或无法访问

---

"""
        elif status == 'error':
            report += f"""### {page}
⚠️  **对比出错**
- 错误: {result.get('error', '未知错误')}

---

"""
        else:
            icon = "✅" if similarity >= 95 else "⚠️" if similarity >= 85 else "❌"
            report += f"""### {page}
{icon} **相似度: {similarity}%**

![iOS]({result['ios_path']})  
**iOS Baseline**

![HarmonyOS]({result['hos_path']})  
**HarmonyOS 实现**

"""
            if similarity < 95:
                report += f"""**差异分析**:
- 汉明距离: {result.get('distance', 'N/A')}
- 建议: {'轻微差异，可接受' if similarity >= 85 else '需要调整以提高一致性'}

"""
            report += "---\n\n"
    
    # 总体评估
    report += f"""## 总体评估

"""
    if avg_similarity >= 95:
        report += f"""✅ **优秀** - UI 高度一致

平均相似度达到 {avg_similarity:.1f}%，说明 HarmonyOS 版本的 UI 还原度非常高。
"""
    elif avg_similarity >= 85:
        report += f"""⚠️  **良好** - 有轻微差异

平均相似度 {avg_similarity:.1f}%，整体还原度良好，但存在一些细节差异需要优化。

建议:
- 检查字体大小和间距
- 确认颜色值完全一致
- 调整布局细节
"""
    else:
        report += f"""❌ **需改进** - 差异较大

平均相似度仅 {avg_similarity:.1f}%，需要重点关注 UI 一致性。

优先改进:
"""
        for r in results:
            if r.get('similarity', 0) < 85:
                report += f"- {r['page']}: {r.get('similarity', 0)}%\n"
    
    report += """
## 下一步

"""
    if matched == total:
        report += "✅ UI 对比验证通过，可以继续下一阶段\n"
    else:
        report += f"""⚠️  建议优化低相似度页面后再继续

可以：
1. 接受当前结果，继续运行 /i2h-retrospect
2. 优化 UI 差异，重新运行 /i2h-verify
"""
    
    # 写入文件
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(report)
    
    print(f"✅ 报告已生成: {output_file}")
    print(f"   总体相似度: {avg_similarity:.1f}%")
    print(f"   匹配页面: {matched}/{total}")

if __name__ == "__main__":
    generate_report('spec/verify/comparison-results.json', 'spec/verify/ui-comparison.md')
SCRIPT

python3 /tmp/generate_ui_report.py
```

### Step 4.6: 输出摘要

```bash
# 读取结果摘要
avg_similarity=$(python3 -c "
import json
with open('spec/verify/comparison-results.json') as f:
    results = json.load(f)
    avg = sum(r.get('similarity', 0) for r in results) / len(results) if results else 0
    print(f'{avg:.1f}')
")

matched=$(python3 -c "
import json
with open('spec/verify/comparison-results.json') as f:
    results = json.load(f)
    print(len([r for r in results if r.get('similarity', 0) >= 95]))
")

total=$(python3 -c "
import json
with open('spec/verify/comparison-results.json') as f:
    print(len(json.load(f)))
")

echo ""
echo "=" * 60
echo "CHECK-4: UI 对比验证 - 完成"
echo "=" * 60
echo ""
echo "📊 对比结果:"
echo "   总页面数: $total"
echo "   高度匹配: $matched"
echo "   平均相似度: ${avg_similarity}%"
echo ""
echo "📄 详细报告: spec/verify/ui-comparison.md"
echo ""

# 设置状态
if [ $(echo "$avg_similarity >= 95" | bc) -eq 1 ]; then
    echo "✅ CHECK-4: PASS"
elif [ $(echo "$avg_similarity >= 85" | bc) -eq 1 ]; then
    echo "⚠️  CHECK-4: WARN (轻微差异)"
else
    echo "❌ CHECK-4: FAIL (差异较大)"
fi
echo ""
```

**关键改进**:
1. ✅ **完全自动化** - 从设备检测到截图对比全自动
2. ✅ **读取配置** - 从 .migbot/config.json 读取工具路径和项目信息
3. ✅ **不重复探测** - 配置文件中已有路径，直接使用
4. ✅ **双端对比** - iOS baseline + HarmonyOS 截图 + 相似度计算
5. ✅ **不暂停** - 批量处理所有页面，最后一次性输出报告
6. ✅ **详细报告** - 包含每个页面的截图和相似度分析

## 7. CHECK-5: 行为验证（可选，需真机）

如果用户选择：

### Step 5.1: 引导功能测试

```markdown
请手动测试核心功能：

□ 页面导航
  - 首页 → 设置页 → 返回
  - Tab 切换

□ 数据输入
  - 表单填写
  - 数据保存

□ 数据显示
  - 列表加载
  - 详情查看

□ 基础交互
  - 按钮点击
  - 滚动列表
```

### Step 5.2: 生成行为报告

生成 `spec/verify/behavior-report.md`:

```markdown
# 行为验证报告

## 测试结果

### 页面导航
✅ 通过 - 导航流畅无卡顿

### 数据输入
✅ 通过 - 表单正常工作

### 数据显示
✅ 通过 - 列表正确显示

### 基础交互
✅ 通过 - 交互响应正常

## 发现的问题
1. ⚠️  列表滚动略微卡顿（性能问题）
2. ⚠️  某些按钮点击反馈不明显（UI细节）

## 总体评估
功能完整性: 95%
可用性: ✅ 良好
```

## 8. 汇总验证报告

生成 `spec/verify-report.md`:

```markdown
# 验证报告

生成时间: 2024-11-01T23:59:59Z

## 验证维度

### CHECK-1: 编译验证
结果: ✅ 通过
错误: 0
警告: 3
详情: spec/verify/compile-report.md

### CHECK-2: 结构验证
结果: ✅ 通过
文件完整性: 100%
详情: spec/verify/structure-report.md

### CHECK-3: API 验证
结果: ✅ 通过
API 使用正确
详情: spec/verify/api-report.md

### CHECK-4: UI 对比验证
结果: ⚠️  良好
相似度: 88%
详情: spec/verify/ui-comparison.md

### CHECK-5: 行为验证
结果: ✅ 通过
功能完整性: 95%
详情: spec/verify/behavior-report.md

## 总体评估
状态: ✅ 验证通过

### 主要成就
✅ 代码可编译
✅ 文件完整
✅ API 使用正确
✅ UI 基本还原
✅ 功能正常工作

### 已知问题
⚠️  3 个编译警告（非阻断）
⚠️  UI 细节差异（字体、间距）
⚠️  列表滚动性能待优化

### 建议
1. 优化列表渲染性能
2. 微调 UI 细节（字体大小、间距）
3. 处理编译警告

## Findings
- Blocking: 0
- Warnings: 6（已记账）

## 下一步
运行 /i2h-retrospect 生成最终报告
```

## 9. 完成标记

创建 `spec/verify-complete.txt`

## 10. 输出摘要

```
✅ CHECK-1 编译验证: 通过
✅ CHECK-2 结构验证: 通过
✅ CHECK-3 API 验证: 通过
⚠️  CHECK-4 UI 对比: 88% 相似度
✅ CHECK-5 行为验证: 通过

总体状态: ✅ 验证通过

下一步: 运行 /i2h-retrospect 生成最终报告
```

## 收尾：上报阶段用量

```bash
.migbot/bin/i2h mark-stage i2h-verify
```
