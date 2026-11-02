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

## 6. CHECK-4: UI 对比验证（可选，需真机）

如果用户选择且真机已连接：

### Step 4.1: 部署到真机

```bash
# 安装 HAP
hdc install "$HOS_PATH/entry/build/default/outputs/default/entry-default-unsigned.hap"

# 启动应用
hdc shell aa start -a EntryAbility -b com.example.cuike
```

### Step 4.2: 引导截图对比

```markdown
请手动进行 UI 对比：

1. 在 iPhone 上打开 iOS 版本
2. 在鸿蒙设备上打开 HarmonyOS 版本
3. 对比以下页面：
   - 首页
   - 设置页
   - 列表页
   
4. 拍照记录差异
```

### Step 4.3: 生成对比报告

生成 `spec/verify/ui-comparison.md`:

```markdown
# UI 对比验证

## 首页
iOS 截图: [需要手动添加]
HarmonyOS 截图: [需要手动添加]

观察结果:
- 布局: ✅ 一致
- 颜色: ⚠️  略有差异（色值偏差 < 5%）
- 字体: ⚠️  字体大小略有不同
- 间距: ✅ 基本一致

相似度: 约 87%

## 设置页
相似度: 约 90%

## 总体评估
平均相似度: 88%
可接受程度: ✅ 良好
```

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
