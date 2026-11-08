# Agent 派发 Prompt — 页面转换器 (Converter)

> 派发前必读: `_common.md` + 本文件


## 任务目标

将 iOS 页面（UIViewController/SwiftUI View）转换为 HarmonyOS ArkTS 页面。


## 输入上下文

派发时主线程会提供：

```json
{
  "task_id": "page-001",
  "page_name": "HomeViewController",
  "ios_file": "<ios_project>/ViewControllers/HomeViewController.swift",
  "target_file": "entry/src/main/ets/pages/HomePage.ets",
  "runtime_snapshot": "spec/execution/runtime-snapshots/HomeViewController.json",
  "ui_facts": "spec/execution/ui-facts/HomeViewController.json",
  "dependencies": {
    "base_required": ["Base-1", "Base-3"],
    "slices": []
  }
}
```


## 执行步骤

### Step 1: 理解 iOS 页面

**读取 iOS 源码**:

```bash
# 读取 iOS 页面源码
Read: <ios_file>

# 读取相关依赖
Read: <ios_file> 的 imports
```

**提取关键信息**:

1. **页面结构**:
   - 主容器类型（UIViewController / SwiftUI View）
   - UI 层级
   - 布局方式（Auto Layout / SwiftUI）

2. **状态管理**:
   - `@State` 属性
   - `@Published` 属性
   - `@ObservedObject` 依赖

3. **数据模型**:
   - 使用的 Model 类
   - 数据源

4. **业务逻辑**:
   - 用户交互（按钮点击、输入等）
   - 数据请求
   - 页面跳转

5. **生命周期**:
   - `viewDidLoad` / `onAppear`
   - `viewWillAppear` / `onAppear`
   - 其他生命周期方法

6. **状态刷新边界**:
   - 标记由持久化数据、异步任务或计时器驱动的字段，以及页面在写入完成后必须立即反映的派生状态。
   - 记录页面是否位于 `Navigation`、`NavDestination`、Tab 或其他可缓存的路由容器内。路由容器中的页面不能只依赖首次构造时的快照。

### Step 2: 读取运行时快照（如有）

**读取快照**:

```bash
Read: spec/execution/runtime-snapshots/<page_name>.json
```

**快照包含**:

```json
{
  "page": "HomeViewController",
  "snapshot_type": "runtime_required",
  "captured_at": "2024-11-03T10:00:00Z",
  "ui_hierarchy": {
    "root": {
      "type": "UIViewController",
      "frame": {"x": 0, "y": 0, "width": 375, "height": 812},
      "children": [...]
    }
  },
  "state_values": {
    "title": "首页",
    "items": [...],
    "isLoading": false
  },
  "screenshots": {
    "normal": "spec/execution/screenshots/HomeViewController-normal.png",
    "edge_cases": [...]
  }
}
```

**使用快照**:
- 验证 UI 层级理解
- 获取实际的状态值
- 对比截图确保布局保真

### Step 3: 生成 HarmonyOS 页面

#### 3.1 生成页面框架

```typescript
// entry/src/main/ets/pages/HomePage.ets
import { HomeViewModel } from '../viewmodels/HomeViewModel';

@Entry
@ComponentV2
export struct HomePage {
  @Local viewModel: HomeViewModel = new HomeViewModel();

  aboutToAppear(): void {
    // 对应 iOS viewDidLoad
    this.viewModel.loadData();
  }

  onPageShow(): void {
    // 对应 iOS viewWillAppear
  }

  onPageHide(): void {
    // 对应 iOS viewWillDisappear
  }

  build() {
    NavDestination() {
      Column() {
        // UI 内容
      }
      .width('100%')
      .height('100%')
    }
    .title('首页')
    .onReady((context: NavDestinationContext) => {
      this.viewModel.pathStack = context.pathStack;
    })
  }
}
```

#### 3.2 生成 UI 组件

**UIKit → ArkTS 映射**:

```typescript
// iOS: UILabel
Text('标题')
  .fontSize(16)
  .fontColor($r('app.color.text_primary'))

// iOS: UIButton
Button('点击')
  .onClick(() => {
    this.viewModel.handleClick();
  })

// iOS: UITextField
TextInput({ placeholder: '请输入' })
  .onChange((value: string) => {
    this.viewModel.keyword = value;
  })

// iOS: UIImageView
Image($r('app.media.icon'))
  .width(24)
  .height(24)

// iOS: UITableView
List() {
  ForEach(this.viewModel.items, (item: ItemModel) => {
    ListItem() {
      this.ItemComponent(item)
    }
  })
}

// iOS: UIScrollView
Scroll() {
  Column() {
    // 内容
  }
}
```

**SwiftUI → ArkTS 映射**:

```typescript
// SwiftUI: VStack
Column() {
  // 子组件
}

// SwiftUI: HStack
Row() {
  // 子组件
}

// SwiftUI: ZStack
Stack() {
  // 子组件（层叠）
}

// SwiftUI: List
List() {
  ForEach(items, (item) => {
    ListItem() {
      // 内容
    }
  })
}

// SwiftUI: NavigationLink
Button('详情')
  .onClick(() => {
    this.viewModel.pathStack.pushPath({ name: 'DetailPage', param: item });
  })
```

#### 3.3 生成 ViewModel

```typescript
// entry/src/main/ets/viewmodels/HomeViewModel.ets
import { BeanRecord } from '../models/BeanRecord';

@ObservedV2
export class HomeViewModel {
  @Trace items: BeanRecord[] = [];
  @Trace isLoading: boolean = false;
  @Trace errorMessage: string = '';
  
  pathStack: NavPathStack | null = null;

  async loadData(): Promise<void> {
    this.isLoading = true;
    try {
      // PLACEHOLDER: SLICE-2 | 数据加载 | 等待 Slice 2 实现数据服务
      throw new Error('PLACEHOLDER: SLICE-2');
      
      // 未来实现:
      // const data = await this.dataService.fetchItems();
      // this.items = data;
    } catch (error) {
      this.errorMessage = error.message;
    } finally {
      this.isLoading = false;
    }
  }

  handleClick(): void {
    // 处理点击
    this.pathStack?.pushPath({ name: 'DetailPage' });
  }
}
```

#### 3.4 ArkUI 状态与导航一致性

转换 SwiftUI 的 `@State`、`@Observable`、`@Published` 或共享 Store 时，必须让 ArkUI V2 建立与原页面等价的依赖关系。

- 可观察模型使用 `@ObservedV2`，可变字段使用 `@Trace`。读取 `@Trace` 字段计算得到、且会影响 UI 的 getter 必须使用 `@Computed`，不能用普通 getter 代替。
- 页面从共享 Store 读取数据时，通过 `@Param data` 或等价的可观察输入传递同一个 Store，并在页面内用 `@Monitor('data.revision')` 观察写入、计时器和异步持久化完成后的版本变化。不要把 Store 复制成一次性的本地快照。
- 异步写入完成后，必须先重新加载或整体替换受影响的数组、嵌套对象和派生源，再切换页面或显示成功状态。只修改嵌套对象的普通属性，或只更新一个未被页面读取的计数器，不能作为刷新方案。
- 当多个 Tab 或 `NavDestination` 共享同一 Store，且写入后要求当前页面立即刷新时，在根组件维护递增的 `navigationGeneration`。版本变化时递增它，并把包含 Tabs/Navigation 的完整子树放进 keyed `ForEach`，使用 generation 作为 key 以创建新的页面实例。例如 `ForEach([this.navigationGeneration], (generation: number) => { ... }, (generation: number) => \`${generation}\`)`。仅给外层 `Tabs` 或 `Navigation` 添加 `.id()` 不能替代完整子树重建。
- 对于完成、保存、放弃等动作后重新进入同名的临时页面，使用 `NavPathStack.pushPath` 并设置 `launchMode: LaunchMode.NEW_INSTANCE`。不要使用会复用旧 `NavDestination` 的同名快捷 push。保留用户可见的路由和返回语义。
- 完成后必须执行一次不重启进程的状态链路检查。至少覆盖异步写入后的当前页、返回列表页、重新打开同名页面和放弃/删除后的列表状态，并保留 layout dump 或截图证据。

#### 3.5 处理依赖

**Base 层依赖**:

```typescript
// 依赖 Base-1: Models
import { BeanRecord } from '../models/BeanRecord';

// 依赖 Base-3: Network
import { NetworkService } from '../services/NetworkService';

// 依赖 Base-5: Preferences
import { PreferencesManager } from '../services/PreferencesManager';
```

**Slice 依赖（使用占位符）**:

```typescript
// 等待 Slice 2 实现
// PLACEHOLDER: SLICE-2 | 数据服务 | 等待 Slice 2 实现数据加载逻辑
async loadData(): Promise<void> {
  throw new Error('PLACEHOLDER: SLICE-2');
}
```

### Step 4: 布局保真

**尺寸映射**:

| iOS 单位 | HarmonyOS 单位 |
|---------|---------------|
| `points` | `vp` |
| `@2x` | 无需考虑（自动适配） |
| `@3x` | 无需考虑（自动适配） |

**跨设备密度归一化**:

- `points → vp` 只定义单位，不保证两端固定几何在目标屏幕上拥有相同的像素比例。
- 如果 runtime/source frame 提供了 iOS 参考宽度，且目标设备能提供逻辑宽度（`vp`），先计算
  `layout_scale = target_logical_width_vp / source_reference_width_pt`，再把同一设计宽度下的固定几何量（卡片 inset、固定图形宽高、胶囊宽度和固定间距）乘以该比例。
- 只对有明确共同设计宽度、且由 source/runtime frame 证明为固定几何的数值应用该比例。字体字号、动态控件、可滚动内容高度、系统安全区和百分比布局保留语义映射，由目标布局自行测量。
- 记录每个页面或屏幕类别使用的 `source_reference_width_pt`、`target_logical_width_vp` 和 `layout_scale`。没有这三项证据时，沿用 source 数值并把尺寸归一化列为待验证项，不能凭经验套用全局除数。
- 完成首轮构建后，用目标设备 Accessibility/layout dump 与 iOS runtime frame 对齐局部几何，再单变量修正偏差。不要把状态栏、导航栏或字体光栅化差异当作应用布局缩放依据。

当 `presentation` 已冻结目标逻辑宽度时，先生成可追溯的 scale 产物：

```bash
python3 .claude/skills/i2h-execute/scripts/layout_scale.py \
  --ios-accessibility-json <ios-accessibility.json> \
  --target-logical-width-vp <target_width_vp> \
  --out spec/execution/layout-scale.json
```

转换报告必须引用该文件及其输入哈希。没有目标逻辑宽度时不要猜测 scale，保留原值并登记待验证项。

**布局检查**:

1. **间距保真**:
   - iOS padding/margin → HarmonyOS padding/margin
   - 保持相同的视觉间距

2. **尺寸保真**:
   - 固定尺寸 → 固定尺寸
   - 百分比尺寸 → 百分比尺寸
   - Auto Layout 约束 → Flex 布局

3. **对齐方式**:
   - leading/trailing → start/end
   - center → center
   - top/bottom → top/bottom

4. **浮动层与底部安全区**:
   - 任何悬浮 Tab、底部工具条、全局手势层或 `Stack` 覆盖层都必须为页面最后一个可交互控件预留完整的底部 inset。覆盖层不能遮住主按钮、输入框、滚动列表最后一项或弹窗触发区域。
   - 使用目标设备的 Accessibility/layout dump 检查覆盖层和底部操作控件的 bounds。对每个包含底部操作的页面执行一次滚动到末尾后的点击 smoke，记录控件可见、可点击且没有被覆盖层拦截的证据。

### Step 5: 资源处理

**资源引用**:

```typescript
// 图片
Image($r('app.media.icon_home'))

// 颜色
.fontColor($r('app.color.text_primary'))

// 字符串
Text($r('app.string.home_title'))
```

**资源缺失记录**:

```markdown
## 资源缺失
- app.media.icon_home (iOS: home_icon.png)
- app.color.text_primary (iOS: UIColor.label)
- app.string.home_title (iOS: NSLocalizedString("home.title"))
```

### Step 6: 生成 Brief

```markdown
# Brief: HomePage 转换

## 任务信息
- Task ID: page-001
- Page: HomeViewController → HomePage
- Worker: converter
- Status: PASS

## 执行统计
- 开始时间: 2024-11-03T10:00:00Z
- 结束时间: 2024-11-03T10:15:00Z
- 耗时: 15 分钟

## 产出文件
- entry/src/main/ets/pages/HomePage.ets (新建, 150 行)
- entry/src/main/ets/viewmodels/HomeViewModel.ets (新建, 80 行)

## iOS → HarmonyOS 映射
- UIViewController → @Component struct HomePage
- @Published 状态 → @Trace 属性
- UITableView → List + ForEach
- viewDidLoad → aboutToAppear
- navigationController.pushViewController → pathStack.pushPath

## 占位符
- 新增: 2 个
  - PH-001: SLICE-2 | 数据加载
  - PH-002: SLICE-3 | 搜索功能

## 资源缺失
- app.media.icon_home (iOS: home_icon.png)
- app.color.text_primary (iOS: UIColor.label)

## 依赖
- 依赖的 Base: Base-1 (Models), Base-3 (Network)
- 等待的 Slice: Slice-2 (数据服务), Slice-3 (搜索)

## 布局保真
- ✅ 主体结构一致
- ✅ 间距保真（误差 <2vp）
- ✅ 组件层级一致
- ⚠️ 部分动画待 Slice 实现

## 问题和风险
- 无

## 下一步
- 等待 Batch Closer 资源 sweep
- 等待 Slice 2 回填数据加载
```


## 质量检查清单

### UI 层面

- [ ] 所有 UI 组件已转换
- [ ] 布局保真（间距、尺寸、对齐）
- [ ] 响应式布局已实现
- [ ] 无 ArkTS 语法错误

### 状态管理

- [ ] 状态属性已声明（@Trace）
- [ ] 状态更新逻辑已实现
- [ ] 生命周期方法已映射

### 业务逻辑

- [ ] 用户交互已实现或占位
- [ ] 数据请求已实现或占位
- [ ] 页面跳转已实现

### 资源

- [ ] 资源引用格式正确
- [ ] 资源缺失已记录
- [ ] 颜色、字符串已使用 $r()

### 占位符

- [ ] 所有占位符已登记
- [ ] 占位符格式正确
- [ ] 占位符原因清晰

### Brief

- [ ] Brief 包含所有必须字段
- [ ] 产出文件列表完整
- [ ] 依赖关系清晰


## 常见问题

### Q1: 如何处理复杂的 iOS 约束？

**A**: 优先使用 Flex 布局，必要时拆分为多层嵌套。

### Q2: iOS 动画如何转换？

**A**: 
- 简单动画直接转换（`.animation()`）
- 复杂动画标记为占位符，等待专门处理

### Q3: 第三方库如何处理？

**A**:
- 查找 HarmonyOS 对应库
- 无对应库时，标记为占位符或自行实现核心功能

### Q4: 运行时快照不可用怎么办？

**A**:
- 仅根据源码转换
- 在 brief 中说明缺少快照
- 不阻断转换


## 派发示例

**主线程派发**:

```typescript
// 1. 加载公共规则
Read('references/agent-prompts/_common.md')

// 2. 加载 converter 派发模板
Read('references/agent-prompts/1-converter.md')

// 3. 派发 converter
Agent({
  description: "转换 HomeViewController",
  prompt: `
${commonRules}
${converterTemplate}

## 任务上下文
- Task ID: page-001
- iOS 文件: ${iosFile}
- 目标文件: ${targetFile}
- 运行时快照: ${snapshotFile}
- 依赖: Base-1, Base-3

请按照上述规则转换页面。
  `
})
```


