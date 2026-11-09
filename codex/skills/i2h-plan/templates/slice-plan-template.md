<!-- when: 生成 plans/slices/slice-NN-<fid>.md（L2 slice 文件）时加载 -->
<!-- topics: slice 文件, 只读调度账本, 结构化接线对, anchors_ref -->

# slice-NN-<fid>.md（L2 slice 文件）完整模板

**三条铁律（写进每份生成物的自我约束，违反 = plan FAIL）**：

1. **调度表而非详案**：scope 只允许名字级引用（页面序号 / VM 名 / service 名）；业务内容一律 `spec_refs` 指针指向 spec，**复制 spec 正文 = FAIL**（§7 行数启发式兜底）。
2. **生成后只读**：不含 checkbox、evidence 槽、状态字段——完成性由 verify_slice_wiring 机械校验（读代码）+ 组 brief 小节记录；worker 与 closer 均不回写本文件。
3. **不持有占位**：plan 期占位直接写 `spec/placeholder-registry.md`（P-ID 发号协议见 execute `_common.md` §2.1c）。

## 模板

```markdown
## Slice 1: 咖啡豆管理 (F001)
parallel_group: 1 | complexity: simple
depends_on: [Base]
# （chain-auth 项目）本 slice 为某层 owner 时必加：data_chain_refs: chain-auth L4-L6 —— 字段名必须如此，写进 input 指针不算（§7 第 10 项按字段名校验）

ios_source_anchors_ref: {count: 0, source: spec/baseline/features/F001-bean-management.md}

integration_points_ref: spec/baseline/features/F001-bean-management.md#对接点   # 零复制——spec 是对接点唯一权威，worker 与校验脚本顺链接读取

wires:                                  # 统一接线账本（同现行：VM 入边 + embed 入边）
  - page: entry/src/main/ets/pages/BeanListView.ets
    viewmodel: entry/src/main/ets/viewmodels/BeanViewModel.ets
  - page: entry/src/main/ets/pages/MainContainer.ets      # 组件嵌入入边 → C4
    slot: beanListTab
    embed: BeanListView()
    resolve_by: Slice 1 Step 3a

modifies_files:                         # 只列他切片所建文件（自建文件禁列）；本例 MainContainer 由别的切片创建
  - entry/src/main/ets/pages/MainContainer.ets
  cross_slice_edits:                    # 只收非 embed 的 handler 回改；beanListTab 槽位填充已由上方 wires embed 条（含 resolve_by）承载，禁止在此双登
    - file: entry/src/main/ets/pages/MainContainer.ets
      handler: onBeanShare           # 示例：真 handler 回改（非槽位填充）
      resolve_by: Slice 1 Step 3d

- Step 3a: UI 补充 — scope: 0001, 0002, 0003 (BeanListView, BeanDetailView, BeanFormView)（名字级）| input: ui-manifest 对应行
- Step 3b: ViewModel — scope: BeanViewModel | suggested_skills+: arkts-data-layer | input: spec_refs: features/F001-bean-management.md#状态管理
- Step 3c: 数据层 — scope: BeanStore | input: spec_refs: features/F001-bean-management.md#数据存储
- Step 3d/3e: 接线 + 验证 — 契约见 i2h-execute §5e（本文件零复述）
```

## 字段规则

| 字段 | 规则 |
|---|---|
| 头部 3 行 | 与索引条目一致（§7 校验快照一致性） |
| `ios_source_anchors_ref` | `{count, source}` 结构化残端；**不复制 anchors 列表**（权威在 feature spec 顶部，worker 按 grep-first 纪律定点消费） |
| `integration_points_ref` | 单行指针 `spec/baseline/features/<spec>.md#对接点`——**不搬移对接点内容**（spec 唯一权威；feature spec 无该段时整行省略）。worker 按链接读 spec 该节；verify_slice_wiring 顺链接解析成结构化对做 C2 机械判定 |
| `wires` / `cross_slice_edits` | 同现行 YAML 形态（parser 兼容）；embed 条目含 slot/embed/resolve_by。**去双登**：跨切片槽位填充只登 wires embed 条（resolve_by 即归属声明），cross_slice_edits 只收非 embed 的 handler 回改——closer 步骤 1-0/1a/1b 按 embed ∪ cross_slice_edits 并集消费，双登即噪音 |
| `modifies_files` | 只列**他切片所建**的已存在文件；**本切片自建文件禁列**（自建是 generates 事实）；无他建回改时整段省略 |
| Step 行 | 每步一行：scope + 可选 `suggested_skills+:` + input 指针；验收契约零复述（权威在 i2h-execute §5b–5e） |
| `suggested_skills+` | **差异化增量**（delta-only；字段名含 `suggested_skills` 词根便于检索、`+` 表增量）：只写超出步骤默认映射（i2h-plan §4 表）的追加 skill（如登录→arkts-login / 支付→arkts-payment / H5→arkts-webview），plan 期语义判断的确定性产出；默认映射零复述、无追加不写字段 |

---

## iOS 特定说明

### ios_source_anchors_ref（源码锚点引用）

**用途**：为 `complexity: complex` 的 Slice 提供 iOS 源码追溯锚点。

**格式**：
```yaml
ios_source_anchors_ref: {count: 3, source: spec/baseline/features/F001-bean-management.md}
```

**字段说明**：
- `count`: 锚点数量（与 feature spec 顶部 `ios_source_anchors` 段的条目数一致）
- `source`: 指向包含锚点的 feature spec 文件

**什么时候填**：
- `complexity: complex` 的 Slice：**必填**（§7 校验）
- `complexity: simple` 的 Slice：可省略或 count=0

**iOS 源码锚点类型**（在 feature spec 中定义）：

| 角色 (role) | iOS 示例 | 说明 |
|------------|---------|------|
| view | HomeView.swift | SwiftUI View |
| view_controller | HomeViewController.swift | UIKit ViewController |
| viewmodel | BeanViewModel.swift | ViewModel 类 |
| service | NetworkService.swift | 服务类 |
| repository | BeanRepository.swift | 数据仓库 |
| store | BeanStore.swift | Store 类（SwiftUI） |
| manager | LocationManager.swift | 管理类 |
| coordinator | AppCoordinator.swift | 协调器 |
| util | DateFormatter+Extension.swift | 工具类 |
| data_model | Bean.swift | 数据模型 |
| delegate | TableViewDelegate.swift | 委托类 |

### wires（接线账本）

**两类入边**：

#### 1. VM 入边（ViewModel 接线）

**SwiftUI 场景**：
```yaml
wires:
  - page: entry/src/main/ets/pages/HomeView.ets
    viewmodel: entry/src/main/ets/viewmodels/HomeViewModel.ets
```

**iOS 源码模式**：
- `@StateObject var viewModel = HomeViewModel()`
- `@ObservedObject var viewModel: HomeViewModel`
- `@EnvironmentObject var viewModel: HomeViewModel`

**UIKit 场景**：
```yaml
wires:
  - page: entry/src/main/ets/pages/ProfileViewController.ets
    viewmodel: entry/src/main/ets/viewmodels/ProfileViewModel.ets
```

**iOS 源码模式**：
- `let viewModel = ProfileViewModel()`
- `var viewModel: ProfileViewModel!`

**无 ViewModel 场景**：
```yaml
wires:
  - page: entry/src/main/ets/pages/SimpleView.ets
    viewmodel: null    # 使用页面级 @Local 状态
```

#### 2. 组件嵌入入边（子组件嵌入）

**SwiftUI 场景（子 View 嵌入）**：
```yaml
wires:
  - page: entry/src/main/ets/pages/MainContainer.ets
    slot: homeContent
    embed: HomeView()
    resolve_by: Slice 1 Step 3a
```

**iOS 源码模式**：
```swift
TabView {
  HomeView()              // 嵌入子 View
    .tabItem { ... }
}
```

**UIKit 场景（Child ViewController）**：
```yaml
wires:
  - page: entry/src/main/ets/pages/ContainerViewController.ets
    slot: contentViewController
    embed: HomeViewController()
    resolve_by: Slice 1 Step 3a
```

**iOS 源码模式**：
```swift
addChild(homeViewController)
view.addSubview(homeViewController.view)
homeViewController.didMove(toParent: self)
```

**SwiftUI Sheet/FullScreenCover**：
```yaml
wires:
  - page: entry/src/main/ets/pages/ListView.ets
    slot: detailSheet
    embed: DetailView()
    resolve_by: Slice 2 Step 3a
```

**iOS 源码模式**：
```swift
.sheet(isPresented: $showDetail) {
  DetailView()
}
```

### modifies_files & cross_slice_edits

**场景 1：Tab 容器页（由其他 Slice 创建）**

**iOS 场景**：
```swift
// MainTabBarController.swift (Slice 1 创建)
class MainTabBarController: UITabBarController {
  // Slice 2 需要添加新 Tab
}
```

**Slice 2 的 modifies_files**：
```yaml
modifies_files:
  - entry/src/main/ets/pages/MainContainer.ets
  cross_slice_edits:
    - file: entry/src/main/ets/pages/MainContainer.ets
      handler: addProfileTab
      resolve_by: Slice 2 Step 3d
```

**场景 2：SwiftUI NavigationLink 目标页**

**iOS 场景**：
```swift
// HomeView.swift (Slice 1 创建)
NavigationLink(destination: DetailView()) {  // DetailView 由 Slice 2 创建
  Text("Detail")
}
```

**Slice 2 无需回改 HomeView**（forward-ref 兜底）：
```yaml
modifies_files: []    # 无需回改，导航目标由 FWD-REF 机制处理
```

**场景 3：回调 handler 添加**

**iOS 场景**：
```swift
// DetailView.swift (Slice 1 创建)
// Slice 2 需要添加分享功能回调
```

**Slice 2 的 modifies_files**：
```yaml
modifies_files:
  - entry/src/main/ets/pages/DetailView.ets
  cross_slice_edits:
    - file: entry/src/main/ets/pages/DetailView.ets
      handler: onShare
      resolve_by: Slice 2 Step 3d
```

### Step 行格式

#### Step 3a: UI 补充

**格式**：
```
- Step 3a: UI 补充 — scope: {页面序号列表} ({页面名称})（名字级）| input: ui-manifest 对应行
```

**示例**：
```
- Step 3a: UI 补充 — scope: 0001, 0002, 0003 (HomeView, FeedView, DetailView)（名字级）| input: ui-manifest 对应行
```

**SwiftUI 项目**：
```
- Step 3a: UI 补充 — scope: 0001 (HomeView)（名字级）| input: ui-manifest 对应行 | suggested_skills+: i2h-swiftui-converter
```

**UIKit 项目**：
```
- Step 3a: UI 补充 — scope: 0005 (ProfileViewController)（名字级）| input: ui-manifest 对应行 | suggested_skills+: i2h-uikit-converter
```

#### Step 3b: ViewModel + 状态管理

**格式**：
```
- Step 3b: ViewModel — scope: {ViewModel 名称} | input: spec_refs: features/{feature-file}.md#状态管理
```

**SwiftUI 示例（@StateObject）**：
```
- Step 3b: ViewModel — scope: BeanViewModel | input: spec_refs: features/F001-bean-management.md#状态管理
```

**SwiftUI 示例（页面级 @State）**：
```
- Step 3b: ViewModel — scope: 页面级 @Local 状态（无独立 ViewModel）| input: spec_refs: features/F001-simple-view.md#状态管理
```

**UIKit 示例**：
```
- Step 3b: ViewModel — scope: ProfileViewModel | input: spec_refs: features/F002-profile.md#状态管理
```

**特殊技术栈追加 skill**：
```
- Step 3b: ViewModel — scope: LoginViewModel | suggested_skills+: arkts-login | input: spec_refs: features/F003-login.md#状态管理
```

#### Step 3c: 数据层接入

**格式**：
```
- Step 3c: 数据层 — scope: {Store/Service 名称} | input: spec_refs: features/{feature-file}.md#{数据相关段}
```

**SwiftData 示例**：
```
- Step 3c: 数据层 — scope: BeanStore (SwiftData) | suggested_skills+: arkts-data-layer | input: spec_refs: features/F001-bean-management.md#数据存储
```

**CoreData 示例**：
```
- Step 3c: 数据层 — scope: PersistenceController (CoreData) | suggested_skills+: arkts-data-layer | input: spec_refs: features/F001-data.md#CoreData
```

**网络请求示例**：
```
- Step 3c: 数据层 — scope: APIService (URLSession) | suggested_skills+: arkts-network | input: spec_refs: features/F002-api.md#网络请求
```

**UserDefaults 示例**：
```
- Step 3c: 数据层 — scope: SettingsStore (UserDefaults) | input: spec_refs: features/F003-settings.md#偏好设置
```

#### Step 3d/3e: 接线 + 验证

**固定格式**（不变）：
```
- Step 3d/3e: 接线 + 验证 — 契约见 i2h-execute §5e（本文件零复述）
```

### suggested_skills+ 追加规则（iOS 特定）

**仅在以下情况追加**（delta-only，默认映射已在 i2h-plan §4）：

#### 系统功能类

| iOS 功能 | suggested_skills+ |
|---------|-------------------|
| Sign in with Apple | arkts-login |
| Apple Pay / StoreKit | arkts-payment |
| UNUserNotificationCenter | arkts-notification |
| CoreLocation | arkts-location |
| MapKit | arkts-map |
| AVFoundation (相机) | arkts-camera |
| AVPlayer (视频) | arkts-media-playback |
| AVAudioPlayer (音频) | arkts-audio |
| WKWebView | arkts-webview |
| UIActivityViewController | arkts-share |

#### 数据存储类

| iOS 技术 | suggested_skills+ |
|---------|-------------------|
| CoreData | arkts-data-layer |
| SwiftData | arkts-data-layer |
| Keychain | arkts-secure-storage（待定） |

#### 网络类

| iOS 技术 | suggested_skills+ |
|---------|-------------------|
| URLSession (复杂) | arkts-network |
| Alamofire | arkts-network |
| WebSocket | arkts-websocket（待定） |

#### UI 特性类

| iOS 技术 | suggested_skills+ |
|---------|-------------------|
| 复杂动画 | arkts-animation |
| 自定义手势 | arkts-gesture |
| 图表绘制 | arkts-canvas（待定） |

### 完整示例（iOS 咖啡记录应用）

```markdown
## Slice 1: 咖啡豆管理 (F001)
parallel_group: 1 | complexity: simple
depends_on: [Base]

ios_source_anchors_ref: {count: 0, source: spec/baseline/features/F001-bean-management.md}

integration_points_ref: spec/baseline/features/F001-bean-management.md#对接点

wires:
  - page: entry/src/main/ets/pages/BeanListView.ets
    viewmodel: null    # 使用页面级 @Local 状态
  - page: entry/src/main/ets/pages/BeanDetailView.ets
    viewmodel: null
  - page: entry/src/main/ets/pages/MainContainer.ets
    slot: beanListTab
    embed: BeanListView()
    resolve_by: Slice 1 Step 3a

modifies_files:
  - entry/src/main/ets/pages/MainContainer.ets

- Step 3a: UI 补充 — scope: 0001, 0002, 0003 (MainContainer, BeanListView, BeanDetailView)（名字级）| input: ui-manifest 对应行
- Step 3b: ViewModel — scope: 页面级 @Local 状态（无独立 ViewModel）| input: spec_refs: features/F001-bean-management.md#状态管理
- Step 3c: 数据层 — scope: BeanStore (SwiftData) | suggested_skills+: arkts-data-layer | input: spec_refs: features/F001-bean-management.md#数据存储
- Step 3d/3e: 接线 + 验证 — 契约见 i2h-execute §5e（本文件零复述）
```

---

## 常见错误和注意事项

### ❌ 错误示例 1：复制 spec 正文

```markdown
- Step 3b: ViewModel — scope: BeanViewModel
  input: 
    状态管理：
    - @State var beans: [Bean] = []
    - @State var selectedBean: Bean?
    ...
  ❌ 错误：不应复制 spec 内容
```

**正确**：
```markdown
- Step 3b: ViewModel — scope: BeanViewModel | input: spec_refs: features/F001-bean-management.md#状态管理
✅ 正确：只用指针
```

### ❌ 错误示例 2：添加 checkbox

```markdown
- [ ] Step 3a: UI 补充  ❌ 错误：只读态，不应有 checkbox
```

**正确**：
```markdown
- Step 3a: UI 补充 — scope: ...  ✅ 正确：无 checkbox
```

### ❌ 错误示例 3：embed 和 cross_slice_edits 双登

```yaml
wires:
  - page: MainContainer.ets
    slot: homeTab
    embed: HomeView()
    resolve_by: Slice 1 Step 3a

cross_slice_edits:
  - file: MainContainer.ets
    handler: homeTab          ❌ 错误：重复登记
    resolve_by: Slice 1 Step 3a
```

**正确**：
```yaml
wires:
  - page: MainContainer.ets
    slot: homeTab
    embed: HomeView()
    resolve_by: Slice 1 Step 3a
# cross_slice_edits 不重复登记槽位填充  ✅ 正确
```

### ❌ 错误示例 4：列出自建文件

```yaml
modifies_files:
  - entry/src/main/ets/pages/HomeView.ets    ❌ 错误：自建文件不应列出
  - entry/src/main/ets/pages/OtherView.ets   # 他切片创建
```

**正确**：
```yaml
modifies_files:
  - entry/src/main/ets/pages/OtherView.ets   ✅ 正确：只列他切片所建
```

---

## 模板版本

**版本**: v1.0  
**适配平台**: iOS → HarmonyOS  
**基于**: Android a2h-plan slice-plan-template.md  
**最后更新**: 2024-11-03
