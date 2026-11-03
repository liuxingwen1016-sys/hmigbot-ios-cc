<!-- when: 生成 feature-plan.md（L1 调度索引）+ plans/base-plan.md（Base 层正文）时加载 -->
<!-- topics: feature-plan 索引, plan_format, Base 层 stub, base-plan.md, Group 分节, group-closer 插入点, slice 头部, FV, indexed 布局 -->

# feature-plan.md（L1 调度索引）+ base-plan.md 完整模板

**indexed 布局唯一**：feature-plan.md 是纯调度索引——无状态列、无 spec 复述、无步骤契约样板、无依赖 ASCII 树；Base 层正文外置 `plans/base-plan.md`（仅 Stage 2 消费）；逐 slice 账本在 `plans/slices/slice-NN-<fid>.md`（模板见 [slice-plan-template.md](./slice-plan-template.md)）。

## 文件一：feature-plan.md（索引）

```markdown
# Feature Execution Plan

## Context
- plan_format: indexed-v1                  # 版本标记（消费脚本检测旧 monolith 的依据）
- Source: spec/baseline/feature-index.md, spec/baseline/feature-base.md
- Style: <style_set 值，none 或具体风格名>
- Total features: <N>
- Total slices: <N>
- Base tasks: <Base 层任务数>
- 定位 / 工程锚点: <decision-ledger D0 摘要一行，不复述 ledger 正文>

## Base 层（<N> tasks；执行序 Phase 0；Base-0/Base-7 blocking）
detail: plans/base-plan.md

<Base 层到此为止——正文在 base-plan.md，索引不展开任何 Base 任务行>
```

## 文件二：plans/base-plan.md（Base 层正文，与索引同批生成）

**只读态**：与 slice 文件同律——无 checkbox、无 evidence 槽（完成性由 execute `stage2_brief.md` HARD-GATE 记录，plan 不承载执行态）。

```markdown
# Base 层任务（执行时序 Phase 0，先于所有 Slice）

所有 Feature Slices 共用的基础设施，必须先完成。

- Base-0: 资源前置扫描与迁移
  - suggested_skills: [ios2hmos_resources_convert]
  - input: 所有 spec 中引用的资源 ID 全集（扫描 spec/baseline/ui/page_*.md、spec/baseline/features/F-*.md、feature-base.md）
  - output: entry/src/main/resources/ 全量资源 + spec/baseline/plans/resource-mapping.md
  - acceptance: 缺失资源显式标 `$r('app.media.MISSING_xxx')`（编译期失败暴露而非静默 fallback）
  - blocking: true

- Base-1: Models — 所有 entity / DTO 定义
  - suggested_skills: [arkts-data-model]
  - input: feature-base.md Models 段
  - output: entry/src/main/ets/models/*.ets
  - parallel_group: 1
  - iOS 映射: Swift Codable / struct → ArkTS @Observed class

- Base-2: Database — Schema + DAO
  - suggested_skills: [arkts-data-layer]
  - input: feature-base.md Database 段
  - output: entry/src/main/ets/database/*.ets
  - parallel_group: 2
  - iOS 映射: CoreData / SwiftData → RelationalStore

- Base-3: Network — HttpClient + interceptors
  - suggested_skills: [arkts-data-layer, arkts-network-troubleshoot]
  - input: feature-base.md Network 段
  - output: entry/src/main/ets/network/*.ets
  - parallel_group: 3
  - iOS 映射: URLSession / Alamofire → @ohos.net.http
  - data_chain_refs: chain-auth L2-L3    # 仅 chain-auth 项目填（Step 4.3 注入；字段名必须如此，§7 第 10 项按字段名校验）

- Base-4: Events — EventHub 常量 + pub/sub wrapper
  - suggested_skills: [arkts-state-manager]
  - input: feature-base.md Events 段
  - output: entry/src/main/ets/events/*.ets
  - parallel_group: 2
  - iOS 映射: NotificationCenter / Combine → EventHub / emitter

- Base-5: Preferences — 偏好设置迁移
  - suggested_skills: [arkts-data-layer]
  - input: feature-base.md Preferences 段
  - output: entry/src/main/ets/preferences/*.ets
  - parallel_group: 2
  - iOS 映射: UserDefaults / @AppStorage → Preferences

- Base-6: 公共组件库
  - suggested_skills: [arkts-component-builder, arkts-pattern-library]
  - input: ui-manifest.md 共享组件表 + feature-base.md 公共组件段
  - output: entry/src/main/ets/components/common/*.ets
  - parallel_group: 2
  - iOS 映射: SwiftUI 自定义 View / UIKit 自定义组件 → @Component

- Base-7: 编译验证 — Base 层全量编译
  - suggested_agents: [hmos-builder]
  - blocking: true
  - parallel_group: 4
```

> Base 任务的 input 一律写**指针**（feature-base.md 对应段），不复述能力清单内容。
> `parallel_group:` 是 execute Stage 2 编排依据（同组并行、组间串行、末组 = Base-7 编译；Base 层的组无 closer）：默认 Base-1 = 1，Base-2 / 4 / 5 / 6 = 2，Base-3 = 3（Network 常依赖 Preferences 的 token 与 Events 的登出广播），Base-7 = 4。**默认值是待确认项**：writer 必须逐任务核对 feature-base.md 对应段，确认不 import 同组其他任务的产出才可留在默认组，否则拆到下一组并在行尾 `#` 注原因；概念上的先后不算依赖。Base-0 属 Stage 0，不标组。

## 文件一（续）：Slice 索引（按 parallel_group 以 `## Group N` 分节；每组末尾一行 group-closer 插入点）

```markdown
## Slice 索引

## Group 1

## Slice 1: <功能名> (F001)
parallel_group: 1 | complexity: complex
depends_on: [Base]
pages_owned: 2 | placeholders: 1
detail: plans/slices/slice-01-F001.md

## Slice 2: <功能名> (F002)
parallel_group: 1 | complexity: simple
depends_on: [Base]
pages_owned: 1 | placeholders: 0
detail: plans/slices/slice-02-F002.md

> group-closer @ G1：落地本组 cross_slice_edits + embed 槽位 → 资源校验 → 结构 fix-forward → 各 slice brief（组内无编译；全工程编译见 i2h-execute §5f）

## Group 2

## Slice 3: <功能名> (F003)
parallel_group: 2 | complexity: complex
depends_on: [Slice 1]
pages_owned: 1 | placeholders: 2
detail: plans/slices/slice-03-F003.md

> group-closer @ G2：同上（每 parallel_group 末尾恰一个 group-closer，size-1 组亦然）

<每 slice 头部固定 4 行字段，除此之外不写任何账本内容——账本在 slice 文件；
 Group 标题与 group-closer 行都是分节排列（parser 按 `## Slice` 头切段、二者天然容忍），slice 编号才是身份>

---

## Final Verification（Stage 3 全部 Slice 完成后顺序执行）

- FV-1: Final Structural Closure（i2h-execute §6）
  - suggested_skills: [arkts-structural-closure]
  - blocking: true
  - details: 调 `Skill({skill: "arkts-structural-closure", args: "mode=pipeline target=final"})` 跑整工程兜底。**禁止 grep / 自跑脚本替代**。CONTINUE 派 repair worker 重调；其他 verdict 处置见该 skill SKILL.md §3.3。
  - acceptance: `final_state == PASS`（完成性凭据由 execute §6 落 loops JSON + fv brief，plan 零回填）

- FV-2: 终态全量编译
  - suggested_agents: [hmos-builder]
  - blocking: true
  - details: FV-1 通过后（其修复可能改码）跑终态全量编译（≤20 轮）；编译修复仅限编译级小改，**不回跑 FV-1**。
  - acceptance: BUILD_STATUS=PASS（真实构建，非 up-to-date 空转；凭据落 fv brief）

## Summary
- Base 层: <N> tasks（执行序 Phase 0）
- Feature Slices: <N>
- 并行组: <M> 组
  size1_exceptions:                      # 无 size-1 组时省略
    - { group: <N>, merge_candidates: [] }   # 同层可并候选；附挂可行性由 lint 自算
- Final Verification: 2 tasks
```

## 必填规则

1. 每 slice 头部字段齐全：`parallel_group / complexity / depends_on / pages_owned / placeholders / detail`（**无 priority**——优先级权威在 feature-index，调度只由 parallel_group + depends_on 驱动，快照即冗余）。`detail:` 必须指向实际生成的 slice 文件（§7 校验索引 ↔ 文件一一对应）。**`placement:` 仅横切 / hub / 附挂三类例外时写**。
1b. **Base 层 stub 恰 3 行**（`## Base 层` 标题含任务数与 blocking 标注 + `detail: plans/base-plan.md`，执行序 Phase 0 作括注）；指针指向同批实际生成的 base-plan.md；索引内**禁止展开任何 Base 任务行**（正文只在 base-plan.md 一处）。
1c. **Slice 索引按 parallel_group 以 `## Group N` 分节**（子组 2a/2b 各自分节）；Group 标题是排列不是身份——slice 编号才是引用键（P-S{N} / resolve_by / briefs），parser 按 `## Slice` 头切段、Group 行天然容忍。
1d. **每个 `## Group N` 末尾一行 `> group-closer @ GN`**（blockquote 插入点：落地本组 cross_slice_edits + embed → 资源校验 → 结构 fix-forward → brief；**组内无编译**，全工程编译由 execute §5f 的 hmos-builder 承担）；对称 ui-plan 的「结算检查点」行——plan 只标插入点 + 指向 execute §5e，**不复述 closer 五步**（单一权威源）。
1e. **base-plan.md 只读**：Base 任务行无 `- [ ]` checkbox、无 `evidence:` 槽（对齐 slice 文件三铁律②；Base 完成性由 execute `stage2_brief.md` 记录）。
2. `complexity` 为一词级快照（spec 为权威，§7 校验一致性）。
3. `placeholders:` 为 registry 派生显示值（plan 期占位直接写 `spec/placeholder-registry.md`，索引不持有占位内容）。
4. **禁止**：依赖 ASCII 树（feature-index 已有，此处只留 depends_on/parallel_group 可执行编码）、步骤契约文本、integration_points / wires 等账本内容、任何状态列（执行状态在 feature-index / ui-manifest / briefs）。

---

## iOS 特定说明

### Base 层 iOS 技术栈映射

#### Base-1: Models（数据模型）

**iOS → HarmonyOS 映射**：

| iOS 技术 | HarmonyOS 对应 | 转换要点 |
|---------|---------------|---------|
| Swift struct | @Observed class | 响应式需求用 @Observed |
| Swift class | class | 普通类直接映射 |
| Codable | 手动序列化方法 | toJSON() / fromJSON() |
| @Published | @Trace | 属性变化通知 |
| Optional (T?) | T \| undefined | 可选类型 |
| enum | enum | 枚举直接映射 |

**示例**：
```swift
// iOS
struct User: Codable {
    let id: String
    var name: String
    var age: Int?
}
```

```typescript
// HarmonyOS
@Observed
export class User {
  id: string
  @Trace name: string
  @Trace age: number | undefined

  toJSON(): object { ... }
  static fromJSON(json: object): User { ... }
}
```

#### Base-2: Database（数据存储）

**iOS → HarmonyOS 映射**：

| iOS 技术 | HarmonyOS 对应 | 转换要点 |
|---------|---------------|---------|
| CoreData | RelationalStore | 关系型数据库 |
| SwiftData (@Model) | RelationalStore | 同上 |
| NSManagedObject | 普通 class + DAO | 分离模型和持久化 |
| NSFetchRequest | RdbPredicates | 查询谓词 |
| @FetchRequest | 手动查询 | 无自动绑定，需手动刷新 |

**关键差异**：
- CoreData 的上下文（NSManagedObjectContext）→ RdbStore 实例
- 自动保存 → 手动调用 store.executeSql()
- 关系（一对多、多对多）→ 手动管理外键

#### Base-3: Network（网络层）

**iOS → HarmonyOS 映射**：

| iOS 技术 | HarmonyOS 对应 | 转换要点 |
|---------|---------------|---------|
| URLSession | @ohos.net.http | 原生 HTTP 客户端 |
| Alamofire | http + 封装层 | 需自建封装 |
| URLRequest | http.HttpRequest | 请求对象 |
| Combine (dataTaskPublisher) | Promise / async-await | 异步模式 |
| URLSessionDelegate | http.on('headerReceive') | 回调监听 |

**拦截器映射**：
- iOS: URLProtocol → HarmonyOS: 自建拦截器链

#### Base-4: Events（事件系统）

**iOS → HarmonyOS 映射**：

| iOS 技术 | HarmonyOS 对应 | 转换要点 |
|---------|---------------|---------|
| NotificationCenter | emitter.EventPriority | 事件发送接收 |
| Combine (Publisher) | 自建 EventBus | 响应式事件流 |
| @Published + sink | @ObservedV2 + watch | 属性监听 |
| NotificationCenter.default.post | emitter.emit() | 发送事件 |
| addObserver | emitter.on() | 监听事件 |

#### Base-5: Preferences（偏好设置）

**iOS → HarmonyOS 映射**：

| iOS 技术 | HarmonyOS 对应 | 转换要点 |
|---------|---------------|---------|
| UserDefaults | Preferences | 键值存储 |
| @AppStorage | AppStorage / PersistentStorage | 响应式持久化 |
| UserDefaults.standard.set() | preferences.put() | 保存数据 |
| UserDefaults.standard.object() | preferences.get() | 读取数据 |
| synchronize() | preferences.flush() | 刷新到磁盘 |
| Keychain | 安全存储（待适配） | 敏感数据存储 |

#### Base-6: 公共组件库

**SwiftUI → ArkTS 映射**：

| SwiftUI 组件 | ArkTS 对应 | 转换要点 |
|-------------|-----------|---------|
| VStack | Column | 垂直布局 |
| HStack | Row | 水平布局 |
| ZStack | Stack | 层叠布局 |
| List | List | 列表 |
| ScrollView | Scroll | 滚动容器 |
| Button | Button | 按钮 |
| Text | Text | 文本 |
| Image | Image | 图片 |
| TextField | TextInput | 文本输入 |
| Toggle | Toggle | 开关 |
| Picker | Select | 选择器 |
| NavigationView | Navigation | 导航容器 |
| TabView | Tabs | 标签页 |
| Sheet | BindSheet | 模态弹窗 |

**UIKit → ArkTS 映射**：

| UIKit 组件 | ArkTS 对应 | 转换要点 |
|-----------|-----------|---------|
| UIView | @Component | 自定义组件 |
| UILabel | Text | 文本标签 |
| UIButton | Button | 按钮 |
| UIImageView | Image | 图片视图 |
| UITextField | TextInput | 文本输入 |
| UITableView | List | 列表 |
| UICollectionView | Grid / WaterFlow | 网格/瀑布流 |
| UIScrollView | Scroll | 滚动视图 |
| UIStackView | Column / Row | 栈布局 |
| UISwitch | Toggle | 开关 |
| UISegmentedControl | SegmentButton | 分段控件 |
| UIActivityIndicatorView | LoadingProgress | 加载指示器 |

### 常见 iOS 依赖处理

#### 系统框架依赖

| iOS 框架 | Base 任务归属 | suggested_skills+ |
|---------|--------------|-------------------|
| Foundation | Base-1 (Models) | - |
| UIKit | Base-6 (公共组件) | - |
| SwiftUI | Base-6 (公共组件) | - |
| CoreData | Base-2 (Database) | arkts-data-layer |
| SwiftData | Base-2 (Database) | arkts-data-layer |
| CoreLocation | Base-3 (Network) 或独立 Slice | arkts-location |
| MapKit | 独立 Slice | arkts-map |
| AVFoundation | 独立 Slice | arkts-media |
| WebKit (WKWebView) | 独立 Slice | arkts-webview |
| StoreKit | 独立 Slice | arkts-payment |
| UserNotifications | 独立 Slice | arkts-notification |
| Combine | Base-4 (Events) | arkts-state-manager |

#### 三方库依赖（需要 placeholder）

| iOS 三方库 | 处理方式 | 建议 |
|-----------|---------|------|
| Alamofire | Base-3 封装 + 自建替代 | 用 @ohos.net.http 重写 |
| Kingfisher (图片加载) | Base-6 或独立 Slice | 用 Image 组件 + http 实现缓存 |
| SnapKit (布局) | Base-6 | 转为 ArkTS 声明式布局 |
| Moya (网络抽象) | Base-3 | 保留抽象层，底层用 http |
| RxSwift | Base-4 | 转为 Combine 思路 + 自建 |
| Firebase | 各功能独立 Slice | 按功能模块拆分适配 |
| SDWebImage | Base-6 | 同 Kingfisher |

### parallel_group 分配建议

**iOS 项目典型依赖关系**：

```
Base-1 (Models)
   ↓
Base-2 (Database/SwiftData) ← Base-5 (UserDefaults)
   ↓
Base-3 (Network) ← Base-4 (NotificationCenter)
   ↓
Base-6 (公共组件，可能依赖 Models)
   ↓
Base-7 (编译)
```

**推荐分组**：
- parallel_group: 1 → Base-1 (Models 无依赖)
- parallel_group: 2 → Base-2, Base-4, Base-5, Base-6 (可并行)
- parallel_group: 3 → Base-3 (Network 可能依赖 Preferences 的 token)
- parallel_group: 4 → Base-7 (编译，独占末组)

### 完整示例（iOS 咖啡记录应用）

```markdown
# Feature Execution Plan

## Context
- plan_format: indexed-v1
- Source: spec/baseline/feature-index.md, spec/baseline/feature-base.md
- Style: none
- Total features: 4
- Total slices: 4
- Base tasks: 8
- 定位: SwiftUI + SwiftData 架构，纯离线数据存储

## Base 层（8 tasks；执行序 Phase 0；Base-0/Base-7 blocking）
detail: plans/base-plan.md

## Slice 索引

## Group 1

## Slice 1: 咖啡豆管理 (F001)
parallel_group: 1 | complexity: simple
depends_on: [Base]
pages_owned: 3 | placeholders: 0
detail: plans/slices/slice-01-F001.md

## Slice 2: 冲煮记录 (F002)
parallel_group: 1 | complexity: simple
depends_on: [Base]
pages_owned: 2 | placeholders: 0
detail: plans/slices/slice-02-F002.md

> group-closer @ G1：落地本组 cross_slice_edits + embed 槽位 → 资源校验 → 结构 fix-forward → 各 slice brief

## Group 2

## Slice 3: 数据统计 (F003)
parallel_group: 2 | complexity: medium
depends_on: [Slice 1, Slice 2]
pages_owned: 1 | placeholders: 0
detail: plans/slices/slice-03-F003.md

## Slice 4: 用户偏好 (F004)
parallel_group: 2 | complexity: simple
depends_on: [Base]
pages_owned: 1 | placeholders: 0
detail: plans/slices/slice-04-F004.md

> group-closer @ G2：同上

---

## Final Verification

- FV-1: Final Structural Closure
  - suggested_skills: [arkts-structural-closure]
  - blocking: true
  - details: 调 arkts-structural-closure (mode=pipeline target=final)
  - acceptance: final_state == PASS

- FV-2: 终态全量编译
  - suggested_agents: [hmos-builder]
  - blocking: true
  - details: FV-1 通过后跑终态全量编译
  - acceptance: BUILD_STATUS=PASS

## Summary
- Base 层: 8 tasks（执行序 Phase 0）
- Feature Slices: 4
- 并行组: 2 组
- Final Verification: 2 tasks
```

---

## 常见错误和注意事项

### ❌ 错误示例 1：在索引中展开 Base 任务

```markdown
## Base 层
- Base-1: Models
  - suggested_skills: [arkts-data-model]
  - input: ...
  ❌ 错误：索引不应展开 Base 任务
```

**正确**：
```markdown
## Base 层（8 tasks；执行序 Phase 0；Base-0/Base-7 blocking）
detail: plans/base-plan.md
✅ 正确：只留 stub，正文在 base-plan.md
```

### ❌ 错误示例 2：在 slice 头部复制账本内容

```markdown
## Slice 1: 咖啡豆管理 (F001)
parallel_group: 1
integration_points: ...  ❌ 错误：账本内容不应在索引
wires: ...               ❌ 错误
```

**正确**：
```markdown
## Slice 1: 咖啡豆管理 (F001)
parallel_group: 1 | complexity: simple
depends_on: [Base]
pages_owned: 3 | placeholders: 0
detail: plans/slices/slice-01-F001.md
✅ 正确：只有 4 行字段 + detail 指针
```

### ❌ 错误示例 3：缺少 group-closer

```markdown
## Group 1
## Slice 1: ...
## Slice 2: ...

## Group 2  ❌ 错误：Group 1 缺少 group-closer
```

**正确**：
```markdown
## Group 1
## Slice 1: ...
## Slice 2: ...

> group-closer @ G1：...  ✅ 正确

## Group 2
```

### ❌ 错误示例 4：base-plan.md 包含 checkbox

```markdown
# Base 层任务

- [ ] Base-1: Models  ❌ 错误：只读态，不应有 checkbox
```

**正确**：
```markdown
# Base 层任务

- Base-1: Models  ✅ 正确：无 checkbox，无 evidence
```

---

## 模板版本

**版本**: v1.0  
**适配平台**: iOS → HarmonyOS  
**基于**: Android a2h-plan feature-plan-template.md  
**最后更新**: 2024-11-03
