<!-- when: i2h-plan §7.2 技术侧决策清零时加载 -->
<!-- topics: grill #2, 技术决策, 无人值守, 用户确认, decision-ledger -->

# grill #2：技术侧决策清零（HARD-GATE）

> 本文件是 i2h-plan SKILL.md §7.2 的**完整执行规范**。SKILL.md 仅保留摘要 + 指针；执行到该步时 **MUST Read 本文件全文**。
> 三道闸定位：本流程承载**闸 2（grill #2 技术侧）**；闸 1（grill #1 需求侧）在 i2h-spec Step C4.8，闸 3（CLAUDE.md 同步）在 i2h-spec Step C4.8b。
> checklist：`../i2h-spec/references/migration-decision-categories.md` C0–C17。
> 前置：i2h-spec Step C4.8 grill #1 必须已完成，`spec/decision-ledger.md` 中至少含 D0 产出定位。

## 7.2a 调用模式（严格）

覆盖率校验（§7）通过后、§8 门控之前，**立即以 Skill 工具直接调用 `grill-with-docs`**（或显式 invoke `/grill-with-docs`），传入技术侧类目（C6–C11、C13–C14、C17）。

**严禁**在调用前产生任何对话式征询语（"是否需要 grill"、"准备好了吗"、"是否调用"等）。grill 自身就是交互式流程，自己承担与用户的对话。

## 7.2b 前置检查

| 检查 | 失败动作 |
|------|---------|
| `spec/decision-ledger.md` 存在 | 阻断，提示先跑 i2h-spec |
| ledger 含 D0 产出定位 | 阻断，提示回 i2h-spec Step C4.8 补 D0 |
| ledger 状态 = `approved` | 阻断，提示先完成 spec Gate C 审批 |

## 7.2c 必问 vs 自答 分流（grill 内部规则）

> **无人值守（默认，见 [i2h-spec gate-handling.md](../../i2h-spec/references/gate-handling.md) §5）**：「先批量问用户 / 实时拷问」都不等待回复——
> 视为用户无内部已知信息，按公开文档查询 + 决策卡「← 推荐」项自答，写 D 编号（`approval_source: default-policy`）。
> 用户在对话里要求逐个确认时，才按下文提问。

| 分流 | 适用类目 | 处理 |
|------|---------|------|
| **用户预知优先 + 残余文档查询 + 残余业务决策** | **C6 平台 API 无对等** / **C8 三方 SDK 策略** | **先批量问用户**："以下 iOS API / 三方 SDK 你是否有已知的鸿蒙等价物文档/链接/内部镜像可提供？" → 用户提供项写 ledger（来源=用户）→ 残余项 grill-with-docs 查文档 → 都找不到 ⚪ 按 `i2h-spec/references/default-policy.md` 默认：PD-* proposed 阻断、进 §8 确认表，占位/降级/砍/换或替代方案由用户改判。详细子流程见 §7.2d Step 0 |
| **用户预知优先 + 按链路分级问询**（v1.3） | **C17 API 契约与数据逻辑不确定项** | 输入 = `api-inventory.json` `uncertainties[]`（`status: open`），**按 `chain` 分组呈现，auth/登录链路置顶**。② 需真包项**批量索证**（后端文档/抓包/Postman/后端同事）：索到 → `answered` + ledger 事实段；索不到 → `needs_capture`（交 arkts-network-troubleshoot Phase 0.3 定向抓包）。③ 策略项**逐条 🔴 拷问**写 D 编号。**① 类不应出现在清单里**（出现即 api-inventory 产出质量问题，模型自答后回写并记 escape）。详见 §7.2d Step 0-C17 |
| **实时交互拷问**（必须逐条问用户） | 🔴 类目：**C7 一锤定全局架构** / **C9 平台行为差异**（UX 退化逐项确认）/ **C13 签名 entitlement** / **C14 密钥安全**；以及任何 escape 候选 | 逐条问 → 答 → 写一条 D-编号 → 下一条。**单条流式，不允许批量填好再审批** |
| **模型自答 + §8 摘要呈现** | 🔵🟡 类目：C10 后台行为基线方案 / C11 失败降级标准模式 | 模型自答 + 写 ledger「已自动决策」段 + 来源依据（文档链接） |

**判断原则**：三方库选型、API 选型、UX 偏好、签名/密钥/工程配置 — **必须先索取用户内部已知信息再决定**（不让模型瞎找）；纯文档可决的技术映射（基线行为、降级模式）— 模型自决但需在 §8 摘要列出供用户整体 veto。C17 的分级铁律同理：**② 索证不轰炸、③ 必问、① 不问** —— 把用户的注意力留给真正的决策级问题。

## 7.2d grill 流程

```
加载 ../i2h-spec/references/migration-decision-categories.md C6–C11、C13–C14、C17 + 必问/自答分组
  + spec/decision-ledger.md（grill #1 已产出的 D0 + D 编号）
  + 双 plan（ui-plan.md / feature-plan.md / coverage-matrix.md）
  + 自动提取事实（Podfile / Package.swift 依赖清单 / api-inventory 三方 SDK 段 + iOS Framework API 引用
    + api-inventory.json 的 uncertainties[] / auth_model —— C17 输入）
  ↓
Step 0（C6/C8 用户预知收集 · 阶段二，先于逐条 grill）：
  前置读 spec/ref/hmos-references.md（若存在，spec Step 3.0c 阶段一已收集的用户预知）：
    - 这是用户在 spec 阶段一次性提供的"通用 HarmonyOS 索引 + 厂商手册 + 内部资源"
    - 阶段二（本 Step）仅对**该文件未覆盖**的具体 API/SDK 项继续追问，避免重复要用户输入
  ↓
  从 spec / api-inventory / Podfile/Package.swift 整理三份清单：
    - iOS Framework API 清单（C6 用）：含 framework / 类名 / 调用点
    - 三方 SDK 清单（C8 用）：含 pod/package / 版本号 / 用途简述
    - API 契约不确定项清单（C17 用）：api-inventory.json uncertainties[] 中 status=open 的条目，
      按 chain 分组（auth 链路置顶），每条带 tag(②/③) / question / candidates / impact
  对每项先查 hmos-references.md 中是否有对应条目：
    · 命中 → 视为用户已提供，写入 ledger「事实」段，来源标"spec/ref/hmos-references.md#section"，跳过 grill
    · 未命中 → 进入下方批量呈现
  ↓
  对未命中项批量呈现给用户：
    "以下 API / SDK 在 spec/ref/hmos-references.md 未找到等价物记录，你是否有补充的链接 / 内部镜像 / 合作方未公开版本？"
  用户回复方式 → 后续处理：
    · 提供链接 / 文档        → 写入 ledger「事实」段，user_provided=true（建议用户也同步追加到 spec/ref/hmos-references.md 以备后续 api-inventory 重跑复用）
                              该项后续 C6/C8 grill 跳过（已有答案）
    · 答"不知道" / 部分回答  → 剩余项标 needs_doc_lookup，进入下一步
    · 答"全砍掉 / 不用"     → 直接写 ledger，C8 标 strategy=砍，跳过 C6/C8 后续
  ↓
Step 0-C17（API 契约不确定项收口 · v1.3，紧接 C6/C8 之后）：
  注：backend-facts.md 能直接回答的项已在 api-inventory Phase 3 预销账（status=answered），
      此处只处理残余 open 项；uncertainties[] 为空或全 answered → 本步自动消解，跳过
  ↓
  按 chain 打包呈现（auth 链路第一包，每包一次性呈现该链路全部 open 项）：
    ③ 策略项 → 逐条 🔴 拷问 → 用户答 → 写 D 编号 + uncertainties[].status=answered
              （用户答"照搬 iOS"也是有效决策，照常写 D 编号）
    scope=chain-owner 项（chain-auth 冒泡的非 API 层 owner 缺，如无 feature owns L1 隐私门控/L0 应用身份）
              → 🔴 问："登录链路需要该层，但 feature 未 own 它——是否漏识别了隐私/启动 feature？"
              → 补 feature 或确认后写 answered（治 feature 分解漏 L1）
    U-ENV / U-ACCOUNT（dev_info.json 缺，probe 无法跑）→ 兜底索取测试 base_url/账号
              → 回填 spec/baseline/dev_info.json（probe 可后补跑；仅测试凭证、建议 gitignore）
    ② 需真包项 → 批量索证："以下字段/逻辑源码推不准，你是否有后端接口文档 / 抓包样本 /
                Postman 集合 / 可确认的后端同事？"
      · 提供证据 → status=answered + resolution + ledger 事实段
                  （建议用户同步补充到 spec/ref/backend-facts.md 备复用）
      · 无证据   → status=needs_capture，写 ledger 运行期验证项段
                  （交 arkts-network-troubleshoot Phase 0.3 定向抓包销账）
  ↓
  同步回写 api-inventory.json 的 uncertainties[]（status / resolution / resolved_by）
  ↓
正向：逐类目在本项目 plan/spec 找实例
  - 实例不存在 → 跳过
  - 实例存在 + 🔴（C7/C9/C13/C14/escape） → 实时拷问
  - 实例存在 + 🔵🟡（C10/C11） → 模型自答
  - 实例存在 + C6/C8 且 user_provided=true → 跳过（已在 Step 0 解决）
  - 实例存在 + C6/C8 且 needs_doc_lookup → 走文档查询 fallback 链:
    · Step A: 检测 `harmonyos-development` skill 是否可用（Glob `**/harmonyos-development/SKILL.md`）
    · Step B1（skill 可用且命中本地资料）→ 写 ledger，来源 = `harmonyos-development` skill + 原文路径
      （适用域：相机 / 图片 / ArkUI 布局组件导航手势动画等；C6 系统能力侧命中率较高，C8 三方 SDK 命中率较低）
    · Step B2（skill 不可用 / 未命中）→ 降级 grill-with-docs 查公开文档/SDK仓/官网
    · Step C（仍查不到）→ ⚪ 默认 PD-* proposed 阻断 + §8 确认表行（C6: 替代方案 / C8: 占位降级砍换，由用户改判）
  ↓
反向：扫 plan 不清晰信号
  - placeholder kind=thirdparty-sdk 但 trigger_condition 模糊 → 拷问 C8（先查 Step 0 用户预知）
  - complex Slice 但 architecture 选型未定 → 拷问 C7
  - api-inventory 标 migration_concerns（WebSocket/自定义签名/流式上传）但 plan 未给方案 → 拷问 C6（先查 Step 0 用户预知 → 残余查文档 → 仍残余拷问 C10）
  - auth_model 含 unknown 字段但 uncertainties[] 无对应条目 → 补建 uncertainty 走 C17（api-inventory 产出质量缺口，记 escape）
  - 归不到任何类目 → escape，实时拷问 + 标新类目候选
  ↓
追加到 spec/decision-ledger.md：
  - Step 0 用户提供的预知信息（事实段）
  - Step 0-C17 的收口结果（③ 项 D 编号 / ② 项事实段或运行期验证项段）
  - 新 D 编号决策（🔴 用户答案 + 🔵🟡 模型自答含来源）
  - Plan 待修订项段：列出本次决策与 plan 现状冲突的位置 + 调整目标
```

**Step 0 的设计理由**：用户掌握的内部信息模型从公开渠道查不到。先批量索取再让模型查公开文档。C17 同理且更甚——后端契约（响应壳 / 失效码 / 必填字段 / enum）**只有**用户或后端团队知道，公开文档查无可查，不前置索取就只能等联调撞坑。

## 7.2e HARD-GATE 校验

| 校验项 | 失败动作 |
|--------|---------|
| registry 中 plan 期写入的 `kind=thirdparty-sdk` 条目在 ledger 中均有对应 C8 决策 | 阻断，要求补决策 |
| 所有 `complexity: complex` 的 Slice 在 ledger 中有对应 C7 决策（如媒体方案/加密 passthrough） | 阻断，要求补决策 |
| `uncertainties[]` 无 `status: open` 遗留（v1.3）：③ 项全部有 D 编号；② 项状态 ∈ {answered, needs_capture} | 阻断，回 Step 0-C17 补收口 |
| `auth_model` 存在时，其 `unknown` 字段全部有对应 uncertainty 且已收口（登录链路优先原则） | 阻断，补建 uncertainty 走 C17 |
| Plan 待修订项段 ≠ 空 | 提示：execute 阶段将按本表覆盖 plan，请用户确认 |

## 7.2f 与 plan 内容的关系

grill #2 **不直接改写 plan**，所有冲突项记入 ledger 的 **Plan 待修订项**段。i2h-execute 执行时按本表覆盖 plan 原文。

---

## iOS 特定说明

### iOS Framework API 清单（C6）

从 feature spec 和 api-inventory 提取的 iOS Framework API 使用情况：

**示例清单**：
```markdown
### iOS Framework API 清单

| Framework | 类/API | 调用点 | 用途 |
|----------|-------|-------|------|
| CoreData | NSManagedObject | BeanStore.swift:45 | 数据模型定义 |
| CoreData | NSFetchRequest | BeanStore.swift:78 | 数据查询 |
| SwiftData | @Model | Bean.swift:12 | 数据模型（iOS 17+） |
| AVFoundation | AVCaptureSession | CameraView.swift:34 | 相机功能 |
| MapKit | MKMapView | MapView.swift:23 | 地图显示 |
| UserNotifications | UNUserNotificationCenter | NotificationService.swift:56 | 推送通知 |
| WebKit | WKWebView | WebView.swift:29 | 网页加载 |
| StoreKit | SKPaymentQueue | PaymentService.swift:67 | 应用内购买 |
```

**对应 HarmonyOS API**（Step B1/B2 查询结果）：
- CoreData → RelationalStore
- SwiftData → RelationalStore
- AVCaptureSession → @ohos.multimedia.camera
- MKMapView → @ohos.map.MapComponent
- UNUserNotificationCenter → @ohos.notificationManager
- WKWebView → Web 组件
- SKPaymentQueue → @ohos.account.osAccount（IAP）

### iOS 三方 SDK 清单（C8）

从 Podfile / Package.swift 提取的第三方依赖：

**示例清单（CocoaPods）**：
```ruby
# Podfile
pod 'Alamofire', '~> 5.8'
pod 'Kingfisher', '~> 7.10'
pod 'SnapKit', '~> 5.6'
pod 'RxSwift', '~> 6.6'
pod 'WechatOpenSDK', '~> 1.9'
pod 'AlipaySDK-iOS', '~> 15.8'
pod 'Firebase/Analytics', '~> 10.18'
```

**示例清单（Swift Package Manager）**：
```swift
// Package.swift
dependencies: [
  .package(url: "https://github.com/Alamofire/Alamofire.git", from: "5.8.0"),
  .package(url: "https://github.com/onevcat/Kingfisher.git", from: "7.10.0"),
  .package(url: "https://github.com/ReactiveX/RxSwift.git", from: "6.6.0")
]
```

**分类处理**（C8 决策）：

| SDK | 分类 | 决策 | 说明 |
|-----|------|------|------|
| Alamofire | 网络封装 | 砍（自建） | Base-3 自建 HTTP 封装 |
| Kingfisher | 图片缓存 | 砍（自建） | Base-6 自建图片缓存 |
| SnapKit | 布局库 | 砍（转换） | 转为 ArkTS 声明式布局 |
| RxSwift | 响应式 | 砍（转换） | 转为 Combine 风格 + 自建 |
| WechatOpenSDK | 微信 SDK | 留桩（占位） | P-S2-001, trigger: 微信 SDK 入仓 |
| AlipaySDK | 支付宝 SDK | 留桩（占位） | P-S3-001, trigger: 支付宝 SDK 入仓 |
| Firebase | 分析统计 | 降级（换） | 换用华为分析服务 |

### iOS 特定决策类目

#### C6: iOS Framework API 无对等

**常见场景**：

| iOS API | 对等性 | grill 处理 |
|---------|-------|-----------|
| CoreData | ✅ 有对等 | RelationalStore（自答） |
| SwiftData | ✅ 有对等 | RelationalStore（自答） |
| Sign in with Apple | ⚠️ 部分对等 | 华为账号登录（拷问用户偏好） |
| Apple Pay | ⚠️ 部分对等 | 华为支付（拷问用户偏好） |
| HealthKit | ❌ 无对等 | 拷问：砍/降级/留桩 |
| HomeKit | ❌ 无对等 | 拷问：砍/降级/留桩 |
| CarPlay | ❌ 无对等 | 拷问：砍 |

#### C7: 架构决策

**iOS 特定架构选型**：

| 场景 | 问题 | 决策项 |
|------|------|-------|
| SwiftUI + Combine | 状态管理方案 | @ObservedV2 / EventHub / 自建 Combine 风格 |
| MVVM 架构 | ViewModel 模式 | 保留 MVVM / 改为 MVC / 平铺到页面 |
| Coordinator 模式 | 路由方案 | 保留 Coordinator / 用 NavPathStack / 简化路由 |
| CoreData 复杂模型 | 关系映射 | 保留关系 / 扁平化 / 改用 JSON |

#### C8: iOS 三方 SDK 策略

**决策矩阵**：

| SDK 类别 | 典型 SDK | 策略选项 |
|---------|---------|---------|
| 网络库 | Alamofire, Moya | 砍（自建封装） |
| 图片库 | Kingfisher, SDWebImage | 砍（自建缓存） |
| 布局库 | SnapKit, Masonry | 砍（转声明式） |
| 响应式 | RxSwift, Combine | 砍（转 @ObservedV2） |
| 社交登录 | 微信 SDK, Facebook SDK | 留桩（占位） |
| 支付 | 支付宝 SDK, 微信支付 | 留桩（占位） |
| 统计 | Firebase, 友盟 | 换（华为分析） |
| 推送 | JPush, 个推 | 换（华为推送） |
| 地图 | 高德, 百度 | 留桩（占位） |
| IM | 融云, 腾讯云 IM | 留桩（占位） |

#### C9: 平台行为差异

**iOS 特有行为差异**：

| iOS 行为 | HarmonyOS 对应 | UX 影响 | 决策 |
|---------|---------------|--------|------|
| Swipe to delete | 长按菜单 | ⚠️ 手势差异 | 拷问用户接受度 |
| 3D Touch / Haptic Touch | 长按 | ⚠️ 交互差异 | 拷问用户接受度 |
| Live Activities | 卡片服务 | ⚠️ 功能差异 | 拷问：保留/降级/砍 |
| Widget | 服务卡片 | ⚠️ 实现差异 | 拷问：保留/砍 |
| App Clips | 快应用 | ⚠️ 概念差异 | 拷问：换/砍 |
| Siri Shortcuts | 语音助手 | ⚠️ 集成差异 | 拷问：换/砍 |

#### C13: 签名 / Entitlements

**iOS 特有签名**：

| Capability | iOS Entitlement | HarmonyOS 对应 | 决策 |
|-----------|----------------|---------------|------|
| Push Notifications | aps-environment | ohos.permission.NOTIFICATION | 直接映射 |
| iCloud | com.apple.developer.icloud-container-identifiers | 华为云存储 | 拷问：换/砍 |
| Apple Pay | com.apple.developer.in-app-payments | 华为支付 | 拷问：换/砍 |
| HealthKit | com.apple.developer.healthkit | 无对等 | 拷问：砍 |
| Keychain Sharing | keychain-access-groups | 共享存储 | 拷问：换/降级 |
| Associated Domains | com.apple.developer.associated-domains | Deep Link | 拷问：保留/砍 |

#### C14: 密钥安全

**iOS 密钥场景**：

| 场景 | iOS 方案 | HarmonyOS 方案 | 决策 |
|------|---------|---------------|------|
| API Key 存储 | Keychain | 安全存储（待定） | 拷问存储方案 |
| 证书固定 | SSL Pinning | Certificate Pinning | 拷问保留策略 |
| 加密密钥 | CommonCrypto | Crypto framework | 拷问加密方案 |
| OAuth Token | Keychain | 安全存储 | 拷问存储方案 |

### 完整示例（iOS 咖啡记录应用）

#### Step 0: 用户预知收集

**批量呈现**：
```
以下 iOS API / SDK 在 spec/ref/hmos-references.md 未找到等价物记录，
你是否有补充的链接 / 内部镜像 / 合作方未公开版本？

iOS Framework API:
1. CoreData (数据存储)
2. SwiftData (数据存储, iOS 17+)
3. UserNotifications (推送通知)

第三方 SDK:
（本项目无第三方 SDK）

请提供已知的对应文档，或回答"不知道"。
```

**用户回答**：
```
1. CoreData → HarmonyOS RelationalStore（官方文档）
2. SwiftData → 同 CoreData，用 RelationalStore
3. UserNotifications → @ohos.notificationManager（官方文档）
```

**写入 ledger**：
```markdown
## 事实段（用户提供）

- CoreData → RelationalStore
  - 来源: 用户提供
  - 文档: HarmonyOS 官方文档
  
- SwiftData → RelationalStore
  - 来源: 用户提供
  - 文档: 同 CoreData
  
- UserNotifications → @ohos.notificationManager
  - 来源: 用户提供
  - 文档: HarmonyOS 官方文档
```

#### 正向 Grill: 逐类目实例

**C6（已在 Step 0 解决，跳过）**

**C7（无复杂架构，跳过）**

**C8（无第三方 SDK，跳过）**

**C9（无平台行为差异，跳过）**

**C10/C11（模型自答）**：
```markdown
## 自动决策段

- D-010: 后台行为基线方案
  - 类目: C10
  - 决策: 使用 BackgroundTaskManager
  - 来源: HarmonyOS 官方文档
  - approval_source: default-policy
```

#### 反向扫描: plan 不清晰信号

**检查结果**：
- ✅ 无 placeholder kind=thirdparty-sdk
- ✅ 无 complex Slice
- ✅ 无 migration_concerns
- ✅ 无 unknown 字段

#### 输出

**追加到 decision-ledger.md**：
```markdown
## Grill #2 结果（技术侧）

### 事实段
（见上方 Step 0 结果）

### 决策段
- D-010: 后台行为基线方案（C10, default-policy）

### Plan 待修订项
（无冲突，无需修订）
```

---

## 模板版本

**版本**: v1.0  
**适配平台**: iOS → HarmonyOS  
**基于**: Android a2h-plan grill-2-decision-gates.md  
**最后更新**: 2024-11-03
