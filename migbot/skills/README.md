# Android→ArkTS 迁移 Skill 体系

**三层货架 + 治理底座**：按需路由，只装配最相关的 Skill，不一股脑塞给模型。

- **Pipeline 层（6）** — 用户接口（solution）：5 主线 + 1 增量入口，承载确定性阶段编排
- **Capability 层（24）** — 跨场景复用的稳定能力模块（理解 / 分析 / 代码生成 / Spec 决策）
- **Domain 层（27）** — 具体平台知识、Kit 知识、转换规约（UI / System / Media / State / Data…）
- **Companion 层（14）** — 验证 / 修复 / 工具，白名单挂接式调用，不进主货架

> 货架由 **Skill Hub** 治理（`scripts/skill-hub/`，元数据标准化 + 生成 + 评测 + 优化 + 下架）。
> 当前 registry 已认证 57 个（solution 6 / capability 17 / domain 25 / companion 9），其余为待登记或独立工具。

用户只需 5 句话完成从 Android 源码到可编译 ArkTS 项目的全流程。

---

## 架构总览

```
                    ┌─────────────────────────────────────────────┐
                    │ 按需路由：只装配最相关的 Skill，不全量塞进去   │
                    └────────────────────┬────────────────────────┘
                                         │
┌──────────────────────────────────────────────────────────────────────┐
│ 分层 Skills 货架                                                        │
│                                                                        │
│ ┌────────────────────────────────────────────────────────────────┐   │
│ │ Pipeline 层（6 · solution）  用户接口 / 确定性阶段编排            │   │
│ │   a2h-spec → a2h-plan → a2h-execute → a2h-verify → a2h-retrospect │   │
│ │   (+ a2h-incremental-migration 增量入口)                          │   │
│ └────────────────────────────────┬───────────────────────────────┘   │
│                                  │ 智能路由 + runtime 覆盖             │
│ ┌────────────────────────────────▼───────────────────────────────┐   │
│ │ Capability 层（24）  跨场景复用的稳定能力模块                     │   │
│ │   理解: codebase-*, *-fact-tree, app-relationship-tree           │   │
│ │   分析: ui-graph-builder/query, screenshot-analyzer, view-to-arkui│   │
│ │   生成: component/navigation/data-layer/pattern/scaffolder         │   │
│ │   决策: spec-evolver, library-migration                           │   │
│ └────────────────────────────────┬───────────────────────────────┘   │
│                                  │ 按需下沉调度                        │
│ ┌────────────────────────────────▼───────────────────────────────┐   │
│ │ Domain 层（27）  具体平台 / Kit / 转换规约                        │   │
│ │   UI · Navigation · System · Media · State · Data · I18n …        │   │
│ │   [新增 domain skill 有正确 description 即自动可用，无需改上层]    │   │
│ └──────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────────┬───────────────────────────────────┘
                                     │
┌────────────────────────────────────▼───────────────────────────────────┐
│ Companion 层（14） + 货架化治理底座                                       │
│   验证: ui/ut/dt-verifier, router-verify, structural-closure,            │
│         ui-coverage-auditor, visual-verify                               │
│   修复: knowledge-verifier, hmos_fix_build_errors, hmos-env-doctor       │
│   工具: skill-checker, drawio, fix-issue, grill-with-docs                 │
│   治理: 元数据标准化 + Skill Hub + 生成 + 评测 + 优化 + 下架              │
└──────────────────────────────────────────────────────────────────────┘

Agent（4，执行载体）: a2h-migration-worker, a2h-activity-converter,
                      a2h-android-analyzer, a2h-fixer
```

---

## Pipeline Skills（用户接口，6 个：5 主线 + 1 增量入口）

| Skill | 触发 | 说明 | 产出物 |
|-------|------|------|--------|
| `a2h-spec` | "分析项目" / "开始迁移" / "功能缺失" | 三阶段 Spec 生成（数据准备 + UI 清单 + 功能 Spec） | `spec/baseline/ui-manifest.md` + `feature-index.md` + `features/` |
| `a2h-plan` | "生成计划" | 按 Spec 智能拆分执行计划 | `spec/baseline/plans/plan.md` |
| `a2h-execute` | "执行" | Subagent 驱动执行 + runtime skill 覆盖 | ArkTS 代码 + `spec/migration-report.md` |
| `a2h-verify` | "验证" / "测试" | 编译 + 静态分析 + 页面状态审计 + UI 对齐 | `spec/verify-report.md` |
| `a2h-retrospect` | "回顾" / "优化" | 沉淀经验，优化 domain skill | `docs/retrospect-report-YYYY-MM-DD.md` |

### 五步流水线

```
用户: "分析这个 Android 项目"  → a2h-spec     → Spec + UI 图谱     → 人工审批
用户: "生成计划"              → a2h-plan     → 1-N 个 plan.md     → 人工审批
用户: "执行"                 → a2h-execute  → ArkTS 代码          → 编译通过
用户: "验证"                 → a2h-verify   → verify-report.md   → P0 页面 verified
用户: "回顾"                 → a2h-retrospect → retrospect-report → 人工审批
```

---

## Capability Skills（跨场景复用能力，24 个）

> **定位**：被 Pipeline / Capability 调用的稳定能力模块——理解、分析、代码生成、Spec 决策。
> 与 Domain 的区别：Capability 跨多个 domain 复用（"怎么理解 / 怎么生成 / 怎么决策"），Domain 承载单一垂直领域的具体规约。

### 理解类（Code Understanding，9）

面向已有 Android / ArkTS 工程的事实抽取与智能问答。

| Skill | 用途 | 典型触发 |
|-------|------|---------|
| `arkts-codebase-locator` | 功能定位 — 快速找到功能入口和核心文件 | "xx 功能在哪实现？""导出逻辑在哪？" |
| `arkts-codebase-explainer` | 功能解释 — 分析执行流程、交互逻辑、技术细节 | "点击下载后发生了什么？""数据怎么流转的？" |
| `arkts-codebase-debug` | 缺陷诊断 — 定位问题入口和可疑点，提供修复建议 | "列表不刷新""页面白屏""网络请求失败" |
| `arkts-codebase-modifier` | 修改建议 — 基于代码仓事实的功能修改方案（不直接改代码） | "怎么加个下拉刷新？""如何扩展搜索功能？" |
| `arkts-codebase-config` | 配置问答 — 定位配置项定义、读取位置、默认值及覆盖路径 | "权限在哪配的？""这个 Flag 在哪控制？" |
| `toolkit-fact-indexer` | 把 harmony-migration-toolkit 产物加工成扁平「Android 端事实树」`spec/toolkit-fact-tree.json` | Phase 1 |
| `android-fact-tree` | 给任意架构 Android 工程（XML / Compose / 混合）产出统一 `toolkit-fact-tree.json` | Phase 1 |
| `compose-fact-tree` | 从 Jetpack Compose 源码逆向生成与 toolkit 一致的 `toolkit-fact-tree.json` | Phase 1 |
| `app-relationship-tree` | 在 fact-tree 上多源补全页面/导航/组件关系树（融合 spec + ui-graph + ArkTS 源码） | Phase 1 / Phase 7 |

### 分析类（Requirement Understanding，5）

| Skill | 用途 | 阶段 |
|-------|------|------|
| `android-ui-graph-builder` | Python 确定性解析 Android XML 布局，构建 UI 知识图谱 (4 JSON) | Phase 1 |
| `android-ui-graph-query` | 查询 UI 图谱，获取迁移上下文（组件树/属性/导航关系） | Phase 6c |
| `android-screenshot-analyzer` | App 页面截图分析与命名，识别页面功能/布局/风格，输出结构化文档 | Phase 1（辅助） |
| `android-view-to-arkui` | Android View/XML UI 到 ArkUI 的受控批次迁移（特性批次流程） | Phase 6c |
| `android-api-inventory` | 提取外部 API 使用清单（HTTP/WebSocket/SSE/三方 SDK），平台参数化（android/harmony） | Phase 1 / Phase 3 |

### 代码生成引擎（Code Generation，6）

| Skill | 用途 | 阶段 |
|-------|------|------|
| `arkts-project-scaffolder` | 项目骨架搭建（目录/配置/EntryAbility/GlobalState/AppRouter） | Phase 2 |
| `arkts-component-builder` | 声明式 UI 组件生成（Column/Row/List/Grid/ForEach，V2 优先） | Phase 6c |
| `arkts-navigation-builder` | 页面导航（Navigation/NavPathStack/Tabs/路由映射） | Phase 6a |
| `arkts-data-layer` | 数据层（Model/DAO/HTTP/IDataSource/Preferences） | Phase 4-5 |
| `arkts-pattern-library` | 完整业务功能编排（搜索/列表详情/登录/设置） | Phase 6c |
| `arkts-design-tokens-extractor` | 魔鬼数字扫描 + DesignTokens.ets / float.json / color.json 资源化 codemod | Phase 6c / Phase 7 |

### Spec 决策 & 执行支撑（4）

| Skill | 用途 | 阶段 |
|-------|------|------|
| `arkts-spec-evolver` | 增量 spec 演进（功能补全/Bug 修复/优化/审计） | Phase 8+ |
| `arkts-library-migration` | 三方库替代方案查找与决策 | Phase 3 |
| `arkts-scenario-runner` | 模拟器执行复杂 UI 场景（登录/上传/前置导航），为验证 skill 提供就绪状态 | Phase 7 |
| `commit` | 7 字段结构化 git commit message 生成器，让 retrospect 可机器解析 | 全阶段 |

---

## Domain Skills（具体平台 / Kit 知识，27 个）

> **定位**：单一垂直领域的具体平台知识、Kit 知识、转换规约。新增 domain skill 只要有正确的 `description`，上层 Pipeline / Capability 自动发现，无需改动。

### UI（12）

| Skill | 用途 | 阶段 |
|-------|------|------|
| `arkts-ui-alignment` | Android UI 视觉还原（Material Design 映射/SymbolGlyph） | Phase 6c |
| `arkts-animation-builder` | 动画效果（animateTo/transition/手势动画/弹簧动画） | Phase 6c |
| `arkts-animation-migrate` | Android → ArkTS 动画迁移（Lottie/属性/补间/帧/SVGA/转场/共享元素/MotionLayout）；写法细节走 arkts-animation-builder | Phase 6c |
| `arkts-truncation-fix` | 多设备 UI 截断 / 折叠屏布局切换 / 响应式断点修复（**沉浸式 / 安全区已迁到 arkts-immersive-safearea**） | Phase 6c / Phase 7 |
| `arkts-text-truncation` | 纯文本截断修复（与 truncation-fix 互补） | Phase 6c / Phase 7 |
| `arkts-immersive-safearea` | 沉浸式 + 安全区双解架构（4 层：EntryAbility → 根 Navigation expandSafeArea → WindowModel 响应式 padding → 滚动特化） | Phase 6c / Phase 7 |
| `arkts-icon-sizing` | 检测并修复因丢失 `.width()/.height()` 导致的图标渲染尺寸/比例错误 | Phase 6c / Phase 7 |
| `arkts-multi-device` | 跨设备/断点适配根因定位与修复（手机/平板/2in1/折叠屏/车机/TV，sm/md/lg/xl） | Phase 7 |
| `arkts-multi-window` | 窗口形态切换根因修复（分屏/自由窗口/悬浮窗/PiP/UIExtension/模式切换） | Phase 7 |
| `arkts-dark-mode` | 深色模式根因定位与修复（硬编码颜色/资源切换/状态栏/SVG 变色/ColorMode 刷新） | Phase 7 |
| `arkts-large-font` | 大字体场景（fontSizeScale 1.15~3.2x）截断/溢出/重叠/位置错乱根因修复 | Phase 7 |
| `arkts-accessibility` | 无障碍/适老化根因修复（焦点/热区 ≥48vp/朗读标签/对比度/选中播报） | Phase 7 |

### System（7）

| Skill | 用途 | 阶段 |
|-------|------|------|
| `arkts-system-capabilities` | 系统 API（权限/文件/媒体查询/后台任务/沙箱路径） | Phase 4 |
| `arkts-app-identity` | App 身份迁移（名称 label / 分层自适应图标 / 版本号 / 包名 / 厂商） | Phase 2 |
| `arkts-webview` | WebView 开发（WebviewController / CSS·JS 注入 / 多 WebView / 字体 / 页内搜索 / 翻译 / TTS） | 全阶段 |
| `arkts-customer-service` | 三方在线客服 / IM SDK 集成（七鱼 @ysf/sdk、网易云信 @nimsdk、腾讯云 IM @tencentcloud/imsdk） | Phase 6c |
| `arkts-login` | 三方登录通用集成（微信 SendAuthReq + 支付宝 cashiersdk + 华为 Account Kit + SMS） | Phase 6c |
| `arkts-payment` | 三方支付通用集成（微信支付 wxopensdk + 支付宝 cashiersdk + H5 + IAP + 订阅签约） | Phase 6c |
| `arkts-ad` | 广告 SDK 迁移（穿山甲 / 优量汇 / 快手 / 华为 HMS Ads / 百度 / GroMore） | Phase 6c |

### Media（3）

| Skill | 用途 | 阶段 |
|-------|------|------|
| `arkts-media-playback` | AVPlayer **音频**播放（fd:// 协议 / 后台播放 / AVSession；视频走 arkts-video-playback） | Phase 6c |
| `arkts-video-playback` | 视频播放（AVPlayer + XComponent Surface + letterbox + 横屏全屏 + 自动隐藏控件 + PiP）；前置依赖 media-playback | Phase 6c |
| `arkts-download-manager` | 大文件下载（request.agent / 进度追踪 / 队列管理） | Phase 6c |

### State / Data（2）

| Skill | 用途 | 阶段 |
|-------|------|------|
| `arkts-state-manager` | 状态管理（@State/@Prop/@Link/AppStorage/Preferences） | Phase 6b |
| `arkts-network-troubleshoot` | 网络层 / 启动期 / 加密签名 / 响应式订阅的系统化排查与预防 SOP | 全阶段 |

### Resource / I18n / 重构（3）

| Skill | 用途 | 阶段 |
|-------|------|------|
| `android2hmos_resources_convert` | Android 资源转换（strings/colors/drawables → HarmonyOS） | Phase 2 |
| `arkts-i18n` | 国际化支持（多语言/动态切换/资源配置/硬编码扫描） | 全阶段 |
| `arkts-architecture-refactor` | 按《鸿蒙客户端原生开发规范》结构化重构（壳/features/components 三段式 + 私仓接入） | 独立使用 |

---

## Companion Skills（验证 / 修复 / 工具，14 个）

> **定位**：白名单挂接式调用，不进主货架，挂在特定 Pipeline 阶段上做验证、修复、兜底、治理。

### 验证类（Verification，7）

| Skill | 用途 | 阶段 |
|-------|------|------|
| `arkts-dt-verifier` | Spec 驱动 TDD 验证（自动生成单测 + UI 测试，测逻辑层与 UI 层实现率，置信度 ≥95%） | Phase 7 |
| `arkts-ut-verifier` | Spec 驱动**单元测试（逻辑层）**验证 | Phase 7 |
| `arkts-ui-verifier` | Spec 驱动**UI 测试（UI 层）**验证（arkxtest，真机/模拟器实现率） | Phase 7 |
| `arkts-router-verify` | 静态验证并自动修复页面路由跳转（控件级导航图对账） | Phase 7 |
| `arkts-structural-closure` | 工程结构性验证（skeleton 占位 / orphan VM / wiring 闭包 / dangling FWD-REF / 沉浸式四件套 + icon 自愈） | Phase 7 |
| `arkts-ui-coverage-auditor` | UI 覆盖率三层对账（Android Screen × ArkTS Page × spec page），识别二三层 UI 缺口 + builder 校验 | a2h-spec Phase C 末尾 + a2h-verify 回归 |
| `arkts-visual-verify` | 按页面粒度自动截图对比验证（adb + hdc + 多模态对比），单页闭环修复，a2h-verify CHECK-7 执行器 | Phase 7 |

### 修复 / 兜底（3）

| Skill | 用途 | 阶段 |
|-------|------|------|
| `arkts-knowledge-verifier` | ArkTS 知识验证兜底（API 兼容性/装饰器语法/导入路径） | 全阶段 |
| `hmos_fix_build_errors` | 自动编译修复循环（最多 20 轮，全阶段可用） | 全阶段 |
| `hmos-env-doctor` | HarmonyOS 开发环境诊断与修复（DevEco/工具链/签名/权限/真机运行） | Phase 0 / 全阶段 |

### 工具（4）

| Skill | 用途 | 阶段 |
|-------|------|------|
| `skill-checker` | 检查新增/修改的 Skill/Agent/Command/Rule 是否符合规范与 Skill Hub 管理规范 | 独立使用 |
| `drawio` | 生成 .drawio 流程图/架构图/时序图，可导出 PNG/SVG/PDF | 独立使用 |
| `fix-issue` | GitHub Issue 驱动修复工作流 | 全阶段 |
| `grill-with-docs` | 用领域模型拷问计划、统一术语，并就地更新文档（CONTEXT.md / ADR） | 独立使用 |

---

## Agent（4 个）

| Agent | 用途 | 编排的 Skill | 阶段 |
|-------|------|-------------|------|
| `a2h-android-analyzer` | Android 项目分析，生成 spec.md + design.md 参考文档 | (无 skill 依赖) | Phase 0（可选前置） |
| `a2h-migration-worker` | 通用迁移工作 agent，执行任何迁移 task | 41 个 domain skills | Phase 1-7 |
| `a2h-activity-converter` | 单个 Activity UI 页面迁移到 ArkTS | graph-query + resources-convert + fix-build-errors | Phase 6c |
| `a2h-fixer` | a2h-verify CHECK-7 修复循环：扫 spec/fix/round-N 单问题文件，按 fixer_layer 路由修主应用源码 | (无 skill 依赖) | Phase 7（CHECK-7 内部循环） |

位置：`arkts-agents/agents/`

---

## Skill 绑定机制

```
Plan 生成时: 每个 task 标注 suggested_skills: [...]
  │
  ▼ Execute 执行时:
  ├─ 主路径: 读 suggested_skills，加载对应 capability / domain skill
  ├─ 覆盖路径: subagent 检查 runtime 上下文
  │   ├─ UI 迁移 → 委托 a2h-activity-converter agent
  │   ├─ 编译失败 → hmos_fix_build_errors
  │   ├─ API 不确定 → knowledge-verifier
  │   ├─ 资源缺失 → android2hmos_resources_convert
  │   └─ 国际化 → arkts-i18n
  └─ 发现机制: description 匹配 + tags 过滤
```

---

## 报告链路

```
a2h-execute   → spec/migration-report.md
                      ↓ 被读取
a2h-verify    → spec/verify-report.md
                      ↓ 被读取
a2h-retrospect → docs/retrospect-report-YYYY-MM-DD.md
```

---

## 目录结构

```
arkts-skills/
├── README.md                          ← 本文件
│
│  ── Pipeline 层（solution，6）──────────────────────────────
├── a2h-spec/                          ← 用户接口
├── a2h-plan/
├── a2h-execute/
├── a2h-verify/
├── a2h-retrospect/
├── a2h-incremental-migration/         ← 增量入口（被 a2h-spec 内部委托）
│
│  ── Capability 层（24）── 理解 / 分析 / 生成 / 决策 ─────────
├── arkts-codebase-locator/            ← Capability · 理解类
├── arkts-codebase-explainer/
├── arkts-codebase-debug/
├── arkts-codebase-modifier/
├── arkts-codebase-config/
├── toolkit-fact-indexer/              ← fact-tree 基建
├── android-fact-tree/
├── compose-fact-tree/
├── app-relationship-tree/
├── android-ui-graph-builder/          ← Capability · 分析类
├── android-ui-graph-query/
├── android-screenshot-analyzer/
├── android-view-to-arkui/
├── android-api-inventory/
├── arkts-project-scaffolder/          ← Capability · 代码生成引擎
├── arkts-component-builder/
├── arkts-navigation-builder/
├── arkts-data-layer/
├── arkts-pattern-library/
├── arkts-design-tokens-extractor/
├── arkts-spec-evolver/                ← Capability · Spec 决策 & 支撑
├── arkts-library-migration/
├── arkts-scenario-runner/
├── commit/
│
│  ── Domain 层（27）── 具体平台 / Kit / 转换规约 ────────────
├── arkts-ui-alignment/                ← Domain · UI
├── arkts-animation-builder/
├── arkts-animation-migrate/
├── arkts-truncation-fix/
├── arkts-text-truncation/
├── arkts-immersive-safearea/
├── arkts-icon-sizing/
├── arkts-multi-device/
├── arkts-multi-window/
├── arkts-dark-mode/
├── arkts-large-font/
├── arkts-accessibility/
├── arkts-system-capabilities/         ← Domain · System
├── arkts-app-identity/
├── arkts-webview/                     ← 已重命名（原 arkts-webview-manager）
├── arkts-customer-service/
├── arkts-login/
├── arkts-payment/
├── arkts-ad/
├── arkts-media-playback/              ← Domain · Media（已收窄为音频专项）
├── arkts-video-playback/
├── arkts-download-manager/
├── arkts-state-manager/               ← Domain · State / Data
├── arkts-network-troubleshoot/
├── android2hmos_resources_convert/    ← Domain · Resource / I18n / 重构
├── arkts-i18n/
├── arkts-architecture-refactor/       ← 独立 skill，不入主流程
│
│  ── Companion 层（14）── 验证 / 修复 / 工具（Pipeline 外）──
├── arkts-dt-verifier/                 ← Companion · 验证类
├── arkts-ut-verifier/
├── arkts-ui-verifier/
├── arkts-router-verify/
├── arkts-structural-closure/
├── arkts-ui-coverage-auditor/
├── arkts-visual-verify/               ← a2h-verify CHECK-7 执行器
├── arkts-knowledge-verifier/          ← Companion · 修复 / 兜底
├── hmos_fix_build_errors/
├── hmos-env-doctor/
├── skill-checker/                     ← Companion · 工具
├── drawio/
├── fix-issue/
└── grill-with-docs/
```

---

## Skill 分类速查

### 按迁移阶段

| 阶段 | Skill（Capability / Domain / Companion） |
|------|-------------|
| Phase 1 分析 | a2h-spec (Phase A/B/C), android-ui-graph-builder, android-screenshot-analyzer（辅助） |
| Phase 2 骨架 | project-scaffolder, android2hmos_resources_convert |
| Phase 3 三方库 | library-migration |
| Phase 4 适配层 | system-capabilities, data-layer |
| Phase 5 数据层 | data-layer |
| Phase 6a 导航 | navigation-builder |
| Phase 6b 状态 | state-manager |
| Phase 6c 组件 | component-builder, pattern-library, animation-builder, media-playback, download-manager, ui-alignment, arkts-webview, android-view-to-arkui（替代方案） |
| Phase 7 验证 | knowledge-verifier, hmos_fix_build_errors |
| Phase 8+ 迭代 | spec-evolver |
| 全阶段 | knowledge-verifier, hmos_fix_build_errors, fix-issue, arkts-i18n, arkts-webview |
| 代码库问答 | codebase-locator, codebase-explainer, codebase-debug, codebase-modifier, codebase-config |

### 按使用场景

| 场景 | Skill |
|------|-------|
| 迁移流水线（核心） | 5 Pipeline + spec-evolver + scaffolder + data-layer + navigation-builder + state-manager + component-builder + activity-converter (agent) + fix-build-errors |
| UI 还原 | ui-graph-builder/query + screenshot-analyzer + view-to-arkui + ui-alignment + activity-converter (agent) |
| 代码库理解 | codebase-locator + codebase-explainer + codebase-config |
| 问题排查 | codebase-debug + knowledge-verifier + fix-issue |
| 功能增强 | codebase-modifier + pattern-library + animation-builder |
| WebView | arkts-webview |
| 国际化 | arkts-i18n |
| 工具 | drawio |

---

## 设计原则

| 原则 | 说明 |
|------|------|
| 三层分工 | Pipeline 管"什么时候做"，Capability 管"怎么理解/生成/决策"（跨场景复用），Domain 管"某个垂直领域怎么做" |
| 按需路由 | 只装配最相关的 Skill，不全量塞给模型；Capability 跨 domain 复用，Domain 命中即下沉 |
| 薄 Pipeline | Pipeline Skill 只做路由和编排，不实现业务逻辑 |
| 自动发现 | 新增 Capability / Domain Skill 只要有正确的 description，上层自动发现，无需改动 |
| 挂接式 Companion | 验证 / 修复 / 工具走白名单挂接，不进主货架，挂在特定阶段上 |
| 只升级不降级 | Execute 的 runtime 覆盖只会切到更精确的 Skill |
| 三级渐进加载 | description(~100词) → SKILL.md(<500行) → references/(按需) |
| 货架化治理 | Skill Hub 统一元数据标准化 + 生成 + 评测 + 优化 + 下架（`scripts/skill-hub/`） |
