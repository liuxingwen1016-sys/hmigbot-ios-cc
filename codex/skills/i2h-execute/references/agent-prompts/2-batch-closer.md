# 子代理派发 Prompt — Batch Closer

> 派发前必读: `_common.md` + 本文件


## 任务目标

完成一个 Batch 的收尾工作，包括资源 sweep、布局复核、产出 writeback manifest。


## 输入上下文

派发时主线程会提供：

```json
{
  "batch_id": "batch-001",
  "pages": ["HomePage", "ProfilePage", "SettingsPage"],
  "converter_briefs": [
    "spec/execution/briefs/stage1-page-001-brief.md",
    "spec/execution/briefs/stage1-page-002-brief.md",
    "spec/execution/briefs/stage1-page-003-brief.md"
  ],
  "ios_project": "<ios_project_root>",
  "hmos_project": "<hmos_project_root>"
}
```


## 执行步骤

### Step 1: 读取所有 Converter Briefs

```bash
# 读取所有 brief
Read: spec/execution/briefs/stage1-page-001-brief.md
Read: spec/execution/briefs/stage1-page-002-brief.md
Read: spec/execution/briefs/stage1-page-003-brief.md
```

**提取信息**:

1. **产出文件列表**:
   - 所有新建的 `.ets` 文件
   - 修改的配置文件

2. **资源缺失列表**:
   - 汇总所有 converter 报告的缺失资源

3. **占位符列表**:
   - 汇总所有新增的占位符

4. **依赖关系**:
   - 页面间的依赖
   - Base 层依赖

### Step 2: 资源 Sweep

#### 2.1 收集资源引用

**扫描所有生成的文件**:

```bash
# 使用 grep 收集所有 $r(...) 引用
grep -r "\$r('app\." entry/src/main/ets/pages/ > resource-refs.txt
```

**解析引用**:

```
$r('app.media.icon_home')
$r('app.color.text_primary')
$r('app.string.home_title')
```

#### 2.2 检查资源是否存在

```bash
# 检查资源文件
ls entry/src/main/resources/base/media/icon_home.png
ls entry/src/main/resources/base/element/color.json
ls entry/src/main/resources/zh_CN/element/string.json
```

#### 2.3 转换缺失资源

**调用资源转换脚本**:

```bash
python3 scripts/sweep_resources.py \
  --project-root . \
  --ios-root <ios_project> \
  --missing-list resource-missing.txt
```

**脚本自动完成**:
1. 读取 iOS 资源（Images.xcassets, Colors.xcassets, Localizable.strings）
2. 转换为 HarmonyOS 格式
3. 写入 `entry/src/main/resources/`

**记录到 brief**:

```markdown
## 资源 Sweep 结果
- 转换图片: 15 个
- 转换颜色: 8 个
- 转换字符串: 32 个
- 失败: 2 个（iOS 资源不存在）
```

### Step 3: 布局尺寸复核

#### 3.1 检查源布局尺寸

**调用布局检查脚本**:

```bash
python3 scripts/layout_dims_gate.py \
  --ios-root <ios_project> \
  --pages HomePage,ProfilePage,SettingsPage \
  --output spec/execution/layout-dims-check.json
```

**脚本检查**:
- iOS 布局中的所有 dp/sp 值
- HarmonyOS 代码中是否落进 vp 值
- 误差是否在允许范围（<2vp）

**检查结果**:

```json
{
  "HomePage": {
    "status": "PASS",
    "dimensions": {
      "padding_top": {"ios": 16, "hmos": 16, "diff": 0},
      "title_font_size": {"ios": 18, "hmos": 18, "diff": 0}
    }
  },
  "ProfilePage": {
    "status": "WARN",
    "dimensions": {
      "avatar_size": {"ios": 80, "hmos": 78, "diff": 2}
    },
    "warnings": ["头像尺寸有 2vp 误差"]
  }
}
```

#### 3.2 修正布局问题

**如果发现布局问题**:

```typescript
// 修正前
Image($r('app.media.avatar'))
  .width(78)  // ❌ 应该是 80

// 修正后
Image($r('app.media.avatar'))
  .width(80)  // ✅ 正确
```

**记录到 writeback manifest**。

### Step 4: 入口装配（首个 Batch）

**如果是首个 Batch**，需要装配入口：

#### 4.1 更新 main_pages.json

```json
{
  "src": [
    "pages/HomePage",
    "pages/ProfilePage",
    "pages/SettingsPage"
  ]
}
```

#### 4.2 创建 Navigation 外壳

```typescript
// entry/src/main/ets/pages/Index.ets
import { HomePage } from './HomePage';

@Entry
@ComponentV2
struct Index {
  @Local pathStack: NavPathStack = new NavPathStack();

  @Builder
  PageMap(name: string) {
    if (name === 'HomePage') {
      HomePage()
    } else if (name === 'ProfilePage') {
      ProfilePage()
    } else if (name === 'SettingsPage') {
      SettingsPage()
    }
  }

  build() {
    Navigation(this.pathStack) {
      HomePage()
    }
    .navDestination(this.PageMap)
    .mode(NavigationMode.Stack)
  }
}
```

#### 4.3 更新 EntryAbility

```typescript
// entry/src/main/ets/entryability/EntryAbility.ets
onWindowStageCreate(windowStage: window.WindowStage): void {
  windowStage.loadContent('pages/Index', (err) => {
    if (err.code) {
      return;
    }
  });
}
```

### Step 5: 产出 Writeback Manifest

**生成 writeback manifest**:

```json
{
  "batch_id": "batch-001",
  "timestamp": "2024-11-03T10:30:00Z",
  "operations": [
    {
      "type": "create",
      "file": "entry/src/main/resources/base/profile/main_pages.json",
      "content": "{\n  \"src\": [\n    \"pages/HomePage\",\n    \"pages/ProfilePage\",\n    \"pages/SettingsPage\"\n  ]\n}"
    },
    {
      "type": "create",
      "file": "entry/src/main/ets/pages/Index.ets",
      "content": "<full_content>"
    },
    {
      "type": "modify",
      "file": "entry/src/main/ets/pages/ProfilePage.ets",
      "changes": [
        {
          "line_range": [45, 47],
          "old_content": "  .width(78)",
          "new_content": "  .width(80)  // 布局复核修正"
        }
      ]
    },
    {
      "type": "fill_placeholder",
      "placeholder_id": "PH-003",
      "file": "entry/src/main/ets/viewmodels/HomeViewModel.ets",
      "line_range": [32, 35],
      "new_content": "// 资源已补齐，移除占位符\nconst icon = $r('app.media.icon_home');"
    }
  ],
  "resources": {
    "images": ["icon_home.png", "icon_profile.png", "icon_settings.png"],
    "colors": ["text_primary", "background"],
    "strings": ["home_title", "profile_title", "settings_title"]
  },
  "stats": {
    "total_operations": 4,
    "creates": 2,
    "modifies": 1,
    "fills": 1
  }
}
```

**写入文件**:

```bash
# 写入 writeback manifest
Write: spec/execution/writeback/batch-001-writeback.json
```

### Step 6: 生成 Batch Brief

```markdown
# Brief: Batch 001 收尾

## 任务信息
- Batch ID: batch-001
- Pages: HomePage, ProfilePage, SettingsPage
- Worker: batch-closer
- Status: PASS

## 执行统计
- 开始时间: 2024-11-03T10:25:00Z
- 结束时间: 2024-11-03T10:35:00Z
- 耗时: 10 分钟

## Converter 汇总
- HomePage: PASS (150 行代码)
- ProfilePage: PASS (120 行代码)
- SettingsPage: PASS (80 行代码)
- 总计: 3 个页面，350 行代码

## 资源 Sweep
- 转换图片: 15 个
- 转换颜色: 8 个
- 转换字符串: 32 个
- 失败: 2 个（iOS 资源不存在）
  - icon_search.png (标记为 MISSING_icon_search)
  - color_accent (标记为 MISSING_color_accent)

## 布局复核
- HomePage: PASS
- ProfilePage: WARN (头像尺寸有 2vp 误差，已修正)
- SettingsPage: PASS

## 入口装配（首个 Batch）
- ✅ main_pages.json 已创建
- ✅ Index.ets Navigation 外壳已创建
- ✅ EntryAbility 已更新

## Writeback Manifest
- 文件: spec/execution/writeback/batch-001-writeback.json
- 操作数: 4 个 (创建 2, 修改 1, 回填 1)

## 占位符
- 回填: 1 个 (PH-003: 资源已补齐)
- 剩余: 5 个 (等待后续 Slice)

## 依赖验证
- Base-1 (Models): ✅ 已就绪
- Base-3 (Network): ✅ 已就绪
- Slice-2 (数据服务): ⏸️ 待实现

## 问题和风险
- ⚠️ 2 个 iOS 资源不存在，已标记为 MISSING
- ⚠️ ProfilePage 头像尺寸有 2vp 误差（已修正）

## 下一步
- 主线程应用 writeback manifest
- 进入下一个 Batch 或 Stage 2
```


## 质量检查清单

### 资源层面

- [ ] 所有资源引用已收集
- [ ] 所有缺失资源已转换或标记
- [ ] 资源 sweep 结果已记录

### 布局层面

- [ ] 布局尺寸已复核
- [ ] 布局问题已修正或记录
- [ ] 误差在允许范围

### 入口装配（首个 Batch）

- [ ] main_pages.json 已创建
- [ ] Index.ets 已创建
- [ ] EntryAbility 已更新
- [ ] Navigation 路由已配置

### Writeback

- [ ] Writeback manifest 已生成
- [ ] 所有操作已记录
- [ ] 文件路径正确
- [ ] 内容格式正确

### Brief

- [ ] Brief 包含所有必须字段
- [ ] Converter 汇总完整
- [ ] 资源 sweep 结果详细
- [ ] 布局复核结果清晰
- [ ] Writeback manifest 路径正确


## 常见问题

### Q1: 资源转换失败怎么办？

**A**: 
- 标记为 MISSING_xxx
- 在 brief 中记录
- 不阻断 Batch 完成

### Q2: 布局复核发现大量问题怎么办？

**A**:
- 修正明显错误（<5 处）
- 大量问题（>5 处）返回 FAIL
- 在 brief 中详细记录

### Q3: 首个 Batch 的入口装配失败怎么办？

**A**:
- 检查 main_pages.json 格式
- 检查 Index.ets 语法
- 返回 FAIL，等待修正

### Q4: Writeback manifest 太大怎么办？

**A**:
- 拆分为多个 manifest
- 每个 manifest < 1000 行
- 主线程按顺序 apply


## 派发示例

**主线程派发**:

```typescript
// 1. 等待所有 converter 完成
await Promise.all(converters);

// 2. 加载公共规则
Read('references/agent-prompts/_common.md')

// 3. 加载 batch-closer 派发模板
Read('references/agent-prompts/2-batch-closer.md')

// 4. 派发 batch-closer
spawn_agent({
  description: "Batch 001 收尾",
  prompt: `
${commonRules}
${batchCloserTemplate}

## 任务上下文
- Batch ID: batch-001
- Pages: HomePage, ProfilePage, SettingsPage
- Converter Briefs: [...]
- iOS Project: ${iosProject}
- HarmonyOS Project: ${hmosProject}

请按照上述规则完成 Batch 收尾。
  `
})
```

**主线程应用 writeback**:

```bash
# 5. 应用 writeback manifest
python3 scripts/apply_writeback.py \
  spec/execution/writeback/batch-001-writeback.json \
  --project-root .
```


