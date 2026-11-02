---
name: i2h-execute
description: iOS→HarmonyOS 转换执行（Pipeline 第三步）：按 plan 派发任务，分 4 个 Stage 完成 UI+Base+Features
tags: [pipeline, migration]
type: pipeline
domain: migration
---

# i2h-execute

Pipeline 第三步：执行实际的代码转换。

## 启动检查 — 待办 findings

读取 `spec/.i2h/open-findings.json`：

| 情况 | 行动 |
|---|---|
| 有 `owner_stage: execute` 的条目 | 先处理这些 |
| 有上游 blocking findings | 🔴 拒绝开工 |

## 1. 前置检查

检查计划产出物：
- [ ] `spec/baseline/plans/ui-plan.json` 存在
- [ ] `spec/baseline/plans/feature-plan.json` 存在

缺失 → 停止，提示先运行 `/i2h-plan`

## 2. Stage 0: UI 前置准备

### Step 0.1: 启动后台资源转换

启动资源转换 worker（后台进程）：

```bash
python3 .migbot/bin/scripts/resource_converter/worker.py \
  --ios "$IOS_PATH" \
  --output "$HOS_PATH/entry/src/main/resources" \
  --daemon &

echo $! > /tmp/i2h_resource_worker.pid
```

转换内容：
- Assets.xcassets → media/
- Colors.xcassets → element/color.json
- Localizable.strings → element/string.json

**不等待完成** - 后台并行进行

### Step 0.2: 创建目标目录结构

```bash
mkdir -p "$HOS_PATH/entry/src/main/ets/"{pages,components,models,services,utils}
mkdir -p "$HOS_PATH/entry/src/main/resources/"{base/element,base/media}
```

### Step 0.3: 初始化占位注册表

创建 `spec/execute/placeholder-registry.json`:

```json
{
  "version": 1,
  "placeholders": []
}
```

### Step 0.4: Stage 0 完成标记

```
Stage 0 完成:
✅ 后台资源转换已启动 (PID: 12345)
✅ 目标目录结构已创建
✅ 占位注册表已初始化
```

创建 `spec/execute/stage0-complete.txt`

## 3. Stage 1: UI 转换

### Step 1.1: 读取 UI Plan

加载 `spec/baseline/plans/ui-plan.json`

### Step 1.2: 按批次执行转换

对每个 Batch：

#### 派发 Worker Agents

```python
from concurrent.futures import ThreadPoolExecutor

def convert_page(page_info):
    """转换单个页面"""
    # 调用模板转换器
    result = subprocess.run([
        "python3", ".migbot/bin/scripts/swiftui_converter/batch_converter.py",
        "--files", page_info["file"],
        "--output", f"$HOS_PATH/entry/src/main/ets/{page_info['output']}",
    ])
    return result

# 批内并行
with ThreadPoolExecutor(max_workers=batch["parallel_agents"]) as executor:
    futures = [executor.submit(convert_page, page) for page in batch["pages"]]
    results = [f.result() for f in futures]
```

**Worker 纪律**：
- ✅ 只写自己的页面文件
- ❌ 禁止碰共享文件
- ❌ 禁止写 Index.ets, module.json5

#### 收尾 Closer Agent

Batch 完成后，派发 Closer Agent：

```python
closer_prompt = f"""
你是 Batch {batch_id} 的 Closer Agent。

Worker agents 已完成 {len(batch['pages'])} 个页面的转换。

你的任务：
1. 检查是否有跨页面的共享组件
2. 生成共享组件文件（如需要）
3. 更新占位注册表
4. 生成批次报告

禁止：
- 不要修改 worker 已生成的页面文件
- 不要写 Index.ets（由 Stage 2 处理）
"""

# 派发 subagent
Agent(description=f"Batch {batch_id} closer", prompt=closer_prompt)
```

### Step 1.3: 生成批次报告

对每个 Batch 生成 `spec/execute/stage1-batch-{id}.md`:

```markdown
# Batch UI_001 转换报告

## 统计
- 页面数: 5
- 成功: 5
- 失败: 0
- 平均自动转换率: 92.3%

## 详细结果
| 页面 | 自动转换率 | 状态 | 耗时 |
|------|----------|------|------|
| HomeView | 93.8% | ✅ | 3min |
| SettingsView | 91.2% | ✅ | 2min |
...

## 占位符
- 1 个 (thirdparty-sdk)

## 下一步
等待其他批次完成
```

### Step 1.4: 等待资源转换完成

```bash
# 等待后台资源转换
wait $(cat /tmp/i2h_resource_worker.pid)
echo "✅ 资源转换完成"
```

### Step 1.5: Stage 1 完成标记

创建 `spec/execute/stage1-complete.txt`

汇总所有批次：
- 总页面数
- 成功数
- 平均自动转换率
- 总占位符数

## 4. Stage 2: Base 层实现

7 个任务按 parallel_group 执行：

### Base-1: 生成应用入口

基于 iOS 的 App.swift 生成 `Index.ets`:

```typescript
@Entry
@ComponentV2
struct Index {
  @Local currentTab: number = 0
  
  build() {
    Tabs({ index: this.currentTab }) {
      // 根据 iOS TabView 生成 TabContent
    }
  }
}
```

### Base-2: 生成主题配置

基于 iOS Theme.swift 生成 `theme.ets`:

```typescript
export class Theme {
  static readonly primary = "#8B7355"
  static readonly accent = "#E8DCC8"
  // ...
}
```

### Base-3: 生成导航占位

生成基础 `router.ets`:

```typescript
import router from '@ohos.router'

export class Router {
  static navigate(page: string) {
    router.pushUrl({ url: `pages/${page}` })
  }
}
```

**占位标记**：
```typescript
// PLACEHOLDER: navigation-full-impl-F002
// Trigger: Stage 3 Group 2
```

### Base-4: 生成 module.json5

基于 iOS Info.plist:

```json5
{
  "module": {
    "name": "entry",
    "type": "entry",
    "description": "$string:module_desc",
    "mainElement": "EntryAbility",
    "deviceTypes": ["phone", "tablet"],
    "pages": "$profile:main_pages"
  }
}
```

### Base-5: 生成 main_pages.json

列出所有页面：

```json
{
  "src": [
    "pages/Index",
    "pages/HomeView",
    "pages/SettingsView",
    ...
  ]
}
```

### Base-6: 生成依赖配置

更新 `oh-package.json5`（如需要）

### Base-7: 编译门 🚪

**第一道编译门**：Stage 1+2 完成后编译

```bash
cd "$HOS_PATH"
./hvigorw assembleHap --mode module -p module=entry@default
```

**编译失败处理**：

1. 收集编译错误
2. 报告到 findings: `COMPILE.BUILD_FAILURE`
3. 自动修复循环（最多 3 轮）
4. 仍失败 → 记录决策，继续

**成功**：
- 生成 `spec/execute/stage2-compile-success.txt`
- 继续 Stage 3

### Stage 2 完成标记

创建 `spec/execute/stage2-complete.txt`

## 5. Stage 3: Feature Slices

### Step 3.1: 读取 Feature Plan

加载 `spec/baseline/plans/feature-plan.json`

### Step 3.2: 按 Group 执行

对每个 Group（按 priority 顺序）：

#### 派发 Feature Agents

Group 内可并行：

```python
for feature in group["features"]:
    agent_prompt = f"""
你是 Feature Agent，负责实现功能：{feature['name']}

参考 spec: spec/baseline/features/{feature['file']}

任务：
1. 阅读 spec 理解需求
2. 生成代码文件：{feature['output']}
3. 使用占位符（如需要）
4. 更新占位注册表

禁止：
- 不要修改其他功能的文件
- 不要修改 Stage 1 生成的页面
"""
    
    Agent(description=f"Feature {feature['feature_id']}", prompt=agent_prompt)
```

#### Group Closer

Group 完成后收尾：

```python
closer_prompt = f"""
你是 Group {group_id} 的 Closer Agent。

已完成功能：{group['features']}

任务：
1. 检查功能间的接线
2. 处理占位符填充
3. 生成 Group 报告
4. 准备编译
"""
```

### Step 3.3: 集中编译门 🚪

每个 Group 完成后编译：

```bash
./hvigorw assembleHap
```

失败 → 修复循环（同 Base-7）

### Step 3.4: 生成功能报告

对每个 Group 生成 `spec/execute/stage3-group-{id}.md`:

```markdown
# Group FEAT_G1 实现报告

## 功能列表
- F001: 数据存储 ✅
- F003: 用户偏好 ✅

## 统计
- 生成文件: 5 个
- 占位符: 0 个
- 编译: ✅ 通过

## 接线完成性
- F001 → F002: ✅ 接口定义完整
```

### Stage 3 完成标记

创建 `spec/execute/stage3-complete.txt`

## 6. Stage 4: 最终整合

### Step 4.1: 占位符复查

```bash
python3 .migbot/bin/scripts/linters/audit_placeholders.py "$PROJECT_ROOT"
```

统计：
- 总占位符数
- 已填充数
- 未填充数（按 trigger_condition 分类）

### Step 4.2: 接线完成性检查

```bash
python3 .migbot/bin/scripts/linters/audit_wiring.py "$PROJECT_ROOT"
```

检查：
- 所有 import 都能解析
- 所有函数调用都有定义
- 所有数据流都完整

### Step 4.3: FV-2 终态编译 🚪

**最终编译验证**：

```bash
./hvigorw clean
./hvigorw assembleHap --mode module -p module=entry@default --no-daemon
```

**必须通过** - 失败则修复循环

### Step 4.4: 生成迁移报告

生成 `spec/migration-report.md`:

```markdown
# 迁移执行报告

## 完成时间
2024-11-01T23:59:59Z

## Stage 0: UI 前置
✅ 完成 (用时: 2分钟)
- 资源转换: ✅ 完成

## Stage 1: UI 转换
✅ 完成 (用时: 45分钟)
- 转换页面: 11 个
- 成功率: 100%
- 平均自动转换率: 91.5%

## Stage 2: Base 层
✅ 完成 (用时: 15分钟)
- Base-7 编译: ✅ 通过

## Stage 3: Feature Slices
✅ 完成 (用时: 115分钟)
- 实现功能: 4 个
- 跳过功能: 1 个（可选）
- 所有 Group 编译: ✅ 通过

## Stage 4: 最终整合
✅ 完成 (用时: 10分钟)
- FV-2 终态编译: ✅ 通过

## 总体统计
- 总用时: 187 分钟 (3.1 小时)
- Token 消耗: 约 420K
- 成本: 约 $7
- 生成文件: 65 个
- 代码行数: 约 2,500 行
- 占位符: 3 个（已登记）

## Findings
- Blocking: 0
- Warnings: 5（已记账）

## 下一步
运行 /i2h-verify 验证结果
```

## 7. 完成标记

创建 `spec/migration-complete.txt`

## 收尾：上报阶段用量

```bash
.migbot/bin/i2h mark-stage i2h-execute
```
