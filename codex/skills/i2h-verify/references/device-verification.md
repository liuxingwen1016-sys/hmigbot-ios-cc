# 设备验证

依据开始时的用户选择，仅对已选项按 CHECK-3 → CHECK-4 的相对顺序串行执行。两项均选时执行 CHECK-3 → 静默 5 秒 → CHECK-4；只选一项时直接执行该项。两项均未选则不进入本文件的设备流程。CHECK-5 另按 [行为验证](check5-behavior-verify.md) 执行；它不沿用下面 CHECK-3/4 的设备前置短路条件。

每项只读取自身所需输入和 verifier 当前 SKILL.md。未选项不要求设备、源码或报告，其状态为 SKIP（用户未选择）。各已选 verifier 内部必要的准备、测试设计、构建和修复仍按自身契约执行。

---

## CHECK-3：视觉对齐（简化版实现）

**实现方式**：在 i2h-verify 主对话中执行双端截图对比，不依赖 arkts-visual-verify。

### 前置条件

#### iOS 设备检测

**iOS 模拟器**：
```bash
# 检测运行中的模拟器
xcrun simctl list devices | grep "Booted"

# 获取设备 ID
ios_device=$(xcrun simctl list devices | grep "Booted" | head -1 | sed -E 's/.*\(([^)]+)\).*/\1/')
```

**iOS 真机**（需要 libimobiledevice）：
```bash
# 检测连接的真机
idevice_id -l

# 获取设备 ID
ios_device=$(idevice_id -l | head -1)
```

**工具检测**：
```bash
# 模拟器工具（系统自带）
which xcrun  # /usr/bin/xcrun

# 真机工具（可选，需要安装）
which idevice_id  # /usr/local/bin/idevice_id
which idevicescreenshot
```

#### HarmonyOS 设备检测

```bash
# 检测连接的设备
hdc list targets

# 获取设备 ID
hos_device=$(hdc list targets | grep -v "Empty" | head -1)
```

### 设备可用性判定

| iOS | HarmonyOS | 结果 |
|-----|----------|------|
| ✅ 可用 | ✅ 可用 | 继续执行 |
| ❌ 不可用 | ✅ 可用 | DEFERRED (iOS 设备不可用) |
| ✅ 可用 | ❌ 不可用 | DEFERRED (HarmonyOS 设备不可用) |
| ❌ 不可用 | ❌ 不可用 | DEFERRED (双端设备都不可用) |

**DEFERRED 时的操作**：
1. 生成说明文档：`spec/verify/ui-comparison.md`
2. 说明缺失的设备和恢复条件
3. 退出 CHECK-3，继续其他检查项

### 执行流程

#### Step 1: 准备工作

```bash
# 创建截图目录
mkdir -p spec/verify/screenshots/ios
mkdir -p spec/verify/screenshots/harmonyos
mkdir -p spec/verify/screenshots/comparison

# 读取页面列表
python3 << 'EOF'
import json
from pathlib import Path

pages = []

# 1. 从 ui-manifest.md 提取页面
manifest_path = Path("spec/baseline/ui-manifest.md")
if manifest_path.exists():
    with open(manifest_path) as f:
        content = f.read()
        import re
        pages = re.findall(r'##\s+(\w+View|\w+Page)', content)

# 2. 扩展：纳入 gate-release 放行项
gate_release = Path("spec/gate-release/verify-focus.json")
if gate_release.exists():
    with open(gate_release) as f:
        data = json.load(f)
        for item in data.get("items", []):
            pages.extend(item.get("pages", []))

# 去重
pages = list(set(pages))

# 输出
with open("spec/verify/.page-list.txt", "w") as f:
    f.write("\n".join(pages))

print(f"📋 待验证页面: {len(pages)}")
for page in pages:
    print(f"  - {page}")
EOF
```

#### Step 2: iOS 端截图

```bash
echo "📱 iOS 端截图采集中..."

while IFS= read -r page; do
    echo "  截图: $page"
    
    if [ "$ios_device_type" = "simulator" ]; then
        # 模拟器截图
        xcrun simctl io "$ios_device" screenshot "spec/verify/screenshots/ios/${page}.png" 2>/dev/null
    else
        # 真机截图
        idevicescreenshot "spec/verify/screenshots/ios/${page}.png" 2>/dev/null
    fi
    
    if [ -f "spec/verify/screenshots/ios/${page}.png" ]; then
        echo "    ✅ 成功"
    else
        echo "    ⚠️  失败（页面可能不可见）"
    fi
    
    sleep 1
done < spec/verify/.page-list.txt

echo "✅ iOS 端截图完成"
```

#### Step 3: HarmonyOS 端截图

```bash
echo "📱 HarmonyOS 端截图采集中..."

# 确保应用已安装
hap_file=$(find . -name "*.hap" -type f | head -1)
if [ -n "$hap_file" ]; then
    echo "  安装应用: $hap_file"
    hdc -t "$hos_device" install "$hap_file" 2>/dev/null
fi

# 启动应用
hos_bundle=$(python3 -c "import json; print(json.load(open('.migbot/config.json'))['harmonyos_bundle'])" 2>/dev/null)
if [ -n "$hos_bundle" ]; then
    echo "  启动应用: $hos_bundle"
    hdc -t "$hos_device" shell aa start -a EntryAbility -b "$hos_bundle" 2>/dev/null
    sleep 2
fi

while IFS= read -r page; do
    echo "  截图: $page"
    
    # HarmonyOS 截图
    hdc -t "$hos_device" shell snapshot_display -f "/data/local/tmp/${page}.png" 2>/dev/null
    hdc -t "$hos_device" file recv "/data/local/tmp/${page}.png" "spec/verify/screenshots/harmonyos/${page}.png" 2>/dev/null
    
    if [ -f "spec/verify/screenshots/harmonyos/${page}.png" ]; then
        echo "    ✅ 成功"
    else
        echo "    ⚠️  失败"
    fi
    
    sleep 1
done < spec/verify/.page-list.txt

echo "✅ HarmonyOS 端截图完成"
```

#### Step 4: 图像相似度对比

使用 Python 脚本计算相似度（感知哈希算法）：

```python
# scripts/compare_screenshots.py
#!/usr/bin/env python3
"""
iOS vs HarmonyOS 截图相似度对比
"""
import sys
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
        hash1 = imagehash.phash(img1, hash_size=16)
        hash2 = imagehash.phash(img2, hash_size=16)
        
        # 计算汉明距离
        distance = hash1 - hash2
        
        # 转换为相似度百分比（16x16 = 256 位哈希）
        max_distance = 256
        similarity = (max_distance - distance) / max_distance * 100
        
        return {
            "similarity": round(similarity, 2),
            "distance": int(distance),
            "status": "match" if similarity >= 95 else "diff",
            "hash1": str(hash1),
            "hash2": str(hash2)
        }
    except Exception as e:
        return {
            "similarity": 0,
            "distance": 256,
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
    for ios_img in sorted(ios_dir.glob("*.png")):
        page_name = ios_img.stem
        hos_img = hos_dir / ios_img.name
        
        if not hos_img.exists():
            results.append({
                "page": page_name,
                "status": "missing_hos",
                "similarity": 0,
                "message": "HarmonyOS 截图缺失"
            })
            continue
        
        # 计算相似度
        result = calculate_similarity(str(ios_img), str(hos_img))
        result["page"] = page_name
        result["ios_path"] = str(ios_img)
        result["hos_path"] = str(hos_img)
        
        results.append(result)
    
    # 输出 JSON 结果
    output = {
        "total": len(results),
        "matched": len([r for r in results if r.get("similarity", 0) >= 95]),
        "avg_similarity": sum(r.get("similarity", 0) for r in results) / len(results) if results else 0,
        "results": results
    }
    
    print(json.dumps(output, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
```

**执行对比**：
```bash
echo "🔍 计算相似度中..."
python3 scripts/compare_screenshots.py \
    spec/verify/screenshots/ios \
    spec/verify/screenshots/harmonyos \
    > spec/verify/comparison-results.json

echo "✅ 对比完成"
```

#### Step 5: 生成详细报告

```python
# scripts/generate_ui_report.py
#!/usr/bin/env python3
"""生成 UI 对比验证报告"""
import json
from pathlib import Path
from datetime import datetime

def generate_report(results_file, output_file):
    with open(results_file) as f:
        data = json.load(f)
    
    total = data['total']
    matched = data['matched']
    avg_similarity = data['avg_similarity']
    results = data['results']
    
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

**建议**: 检查页面是否已正确迁移

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
            level = "高度匹配" if similarity >= 95 else "良好" if similarity >= 85 else "差异较大"
            
            report += f"""### {page}
{icon} **相似度: {similarity}%** ({level})

- iOS: `{result['ios_path']}`
- HarmonyOS: `{result['hos_path']}`
- 汉明距离: {result.get('distance', 'N/A')}

"""
            if similarity < 95:
                if similarity >= 85:
                    report += """**差异分析**: 轻微差异，可能是字体、间距等细节问题

**建议**: 
- 检查字体大小和间距设置
- 确认颜色值完全一致
- 调整布局细节

"""
                else:
                    report += """**差异分析**: 差异较大，需要重点关注

**建议**:
- 检查页面布局结构是否一致
- 确认所有元素都已正确渲染
- 对比具体差异点并逐项修复

"""
            report += "---\n\n"
    
    # 总体评估
    report += f"""## 总体评估

"""
    if avg_similarity >= 95:
        report += f"""✅ **优秀** - UI 高度一致

平均相似度达到 {avg_similarity:.1f}%，说明 HarmonyOS 版本的 UI 还原度非常高。

**下一步**: 可以继续其他验证项（CHECK-4 单元测试等）
"""
    elif avg_similarity >= 85:
        report += f"""⚠️  **良好** - 有轻微差异

平均相似度 {avg_similarity:.1f}%，整体还原度良好，但存在一些细节差异需要优化。

**建议**:
- 检查字体大小和间距
- 确认颜色值完全一致
- 调整布局细节

**下一步**: 可以选择：
1. 接受当前结果，继续 CHECK-4
2. 优化 UI 差异后重新验证
"""
    else:
        report += f"""❌ **需改进** - 差异较大

平均相似度仅 {avg_similarity:.1f}%，需要重点关注 UI 一致性。

**优先改进页面**:
"""
        for r in results:
            if r.get('similarity', 0) < 85:
                report += f"- **{r['page']}**: {r.get('similarity', 0)}%\n"
        
        report += """
**下一步**: 建议优化 UI 差异后再继续后续验证
"""
    
    # 写入文件
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(report)
    
    return {
        'total': total,
        'matched': matched,
        'avg_similarity': avg_similarity
    }

if __name__ == "__main__":
    stats = generate_report(
        'spec/verify/comparison-results.json',
        'spec/verify/ui-comparison.md'
    )
    print(f"✅ 报告已生成")
    print(f"   总体相似度: {stats['avg_similarity']:.1f}%")
    print(f"   匹配页面: {stats['matched']}/{stats['total']}")
```

### 状态判定

主线程读取 `spec/verify/comparison-results.json` 和 `spec/verify/ui-comparison.md`，按以下规则判定：

| 实际结果 | CHECK-3 状态 |
|---|---|
| 平均相似度 ≥ 95%，无 missing 页面 | PASS |
| 平均相似度 85-95%，无功能性问题 | FAIL-visual（建议项）|
| 平均相似度 < 85% 或有 missing 页面 | FAIL-functional |
| iOS/HarmonyOS 设备不可用 | DEFERRED |
| 截图失败 > 50% | PARTIAL |

**注意**：
- 此简化版不包含自动修复功能
- 仅做双端截图对比和相似度分析
- 发现的差异记录到报告，由后续阶段或手动处理

---

## CHECK-4：单元测试

调用 `arkts-ut-verifier`，由其完成测试设计、生成和执行。

### 调用准备

传入参数：
- `--ios-source-root <ios-project-root>`（适配参数名）
- `--harmonyos-root <harmonyos-project-root>`
- `--mode verify_fix` / `verify_only`（默认 `verify_fix`）
- `--skip-oracle true`（或设置环境变量 `UT_ANDROID_ORACLE=off`）
- `--test-framework xctest`（指定 iOS 测试框架）

**iOS 特性适配**：
- iOS 测试位置：`<Project>Tests/` (单元测试)、`<Project>UITests/` (UI 测试)
- 文件命名：`*Tests.swift`
- 测试框架：XCTest（使用 `XCTestCase`、`XCTAssert*` 等）

### 输入要求

| 输入 | 来源 | 缺失时的处理 |
|------|------|-------------|
| iOS 源码路径 | 项目配置或启动参数 | CHECK-4 记 DEFERRED |
| HarmonyOS 工程路径 | 当前工作目录 | 必需，缺失则失败 |
| Spec 文件 | `spec/baseline/` | 作为测试依据，缺失降级 |
| XCTest 测试文件 | iOS 源码 `*Tests/` | 可选，影响 Oracle |

### 产物读取

主线程读取以下产物并保留原始状态：

1. **主报告**：`spec/verify/ut/ut-report.md`
2. **状态文件**：`spec/verify/ut/_state.yaml`
3. **当前轮摘要**：`spec/verify/ut/round-N/_ut_summary.md`
4. **修复循环退出摘要**（如有）：`spec/verify/ut/round-N/final-summary.md`

**不要求** `verify_only` 模式生成修复循环专属产物。

### 判定规则

按 `spec/verify/ut/ut-report.md` 的实际结果判定：

| 实际结果 | CHECK-4 状态 |
|---|---|
| 全范围实际 GREEN，且无未验证设计点、待补测或复核项 | PASS |
| 有实际 RED、ERROR 或最终 FAIL | FAIL，分别记录产品、测试和环境原因 |
| CONVERGED、缺证据、外部前置阻塞或尚未复测的修复 | PARTIAL；保留原始退出状态，已确认失败仍按 FAIL 报告 |
| iOS 源码不可达或 skill 未安装 | DEFERRED |

**引用统计**：
- 通过率、设计验证率和 AC 完成率按报告原口径引用
- 不能把已执行用例通过率当作全设计范围已验证
- 区分"已执行测试通过"和"设计范围已验证"

### 限制说明

由于跳过 Android Oracle 采集（改为 iOS），存在以下限制：

1. **测试用例需要手动编写或基于 Spec**
   - 不自动从 iOS 源码生成测试
   - 依赖 Spec 的验收标准

2. **以 Spec 为准（而非 iOS 实际行为）**
   - 功能预期来自 Spec，不是 iOS 实际运行行为
   - 需要确保 Spec 准确反映需求

3. **XCTest 框架识别**
   - 需要识别 XCTest 测试语法
   - 映射到 ArkTS 测试框架（@ohos/hypium）

---

## 设备交接纪律

### 串行执行顺序

已选项按固定顺序串行执行：CHECK-3 → CHECK-4

### 设备释放确认

前一 verifier 真实退出并释放设备后，静默 5 秒，再启动下一项：

```bash
# CHECK-3 执行完成
echo "✅ CHECK-3 视觉对齐完成"
sleep 5

# 确认设备释放
hdc list targets  # 验证设备仍可用

# 启动 CHECK-4
echo "🚀 开始 CHECK-4 单元测试"
```

### 设备占用冲突处理

如果检测到设备被占用：
1. 等待最多 30 秒
2. 仍被占用 → 记录冲突，该项记 PARTIAL
3. 保留已确认的结果，注明设备冲突原因

---

## 实现脚本建议

| 脚本 | 作用 | 优先级 |
|------|------|--------|
| `scripts/ios_device_checker.py` | 检测 iOS 设备（模拟器/真机）| ⭐⭐⭐⭐⭐ |
| `scripts/ios_screenshot.py` | iOS 截图采集 | ⭐⭐⭐⭐⭐ |
| `scripts/harmonyos_screenshot.py` | HarmonyOS 截图采集 | ⭐⭐⭐⭐⭐ |
| `scripts/compare_screenshots.py` | 图像相似度对比 | ⭐⭐⭐⭐⭐ |
| `scripts/generate_ui_report.py` | 生成 UI 对比报告 | ⭐⭐⭐⭐⭐ |

---

**版本**: v1.0  
**创建时间**: 2024-11-03  
**作者**: 模型 Opus 5.5
