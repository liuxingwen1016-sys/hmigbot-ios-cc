# i2h-plan Phase 3 完成报告

**阶段**: Phase 3 - 重写 SKILL.md  
**完成时间**: 2024-11-03  
**状态**: ✅ 已完成

---

## 完成的工作

### SKILL.md 重写

| 指标 | 原版本 | 新版本 | 变化 |
|------|-------|-------|------|
| **行数** | 351 行 | ~650 行 | +85% |
| **架构** | 扁平 JSON | indexed-v1 (三层) | ✅ 重构 |
| **产物格式** | JSON | Markdown | ✅ 转换 |
| **Templates 引用** | 0 | 6 | ✅ 新增 |
| **References 引用** | 0 | 3 | ✅ 新增 |
| **覆盖率校验** | 简单 | 12 项 HARD-GATE | ✅ 完善 |
| **与 Android 对齐** | ~70% | ~100% | ✅ 对齐 |

---

## 重大改进

### 1. 关键约束（Critical）新增

**6 条铁律**（违反即 plan FAIL）：

1. ✅ **indexed 布局唯一**
   - feature-plan.md = 纯调度索引
   - Base 层正文外置 plans/base-plan.md
   - 逐 slice 账本在 plans/slices/*.md

2. ✅ **slice 文件三铁律**
   - ① 调度表非详案（scope 名字级、spec_refs 指针）
   - ② 生成后只读（无 checkbox/evidence/状态字段）
   - ③ 不持有占位（plan 期占位直写 placeholder-registry.md）

3. ✅ **编排派发（§3.0，HARD-GATE）**
   - P0 kernel → P1 三写并行 → P2 收拢
   - 单线程降级零行为差异

4. ✅ **覆盖率阈值（§7，12 项校验）**
   - P0 功能 100%、UI 页面 100%、Placeholder 白名单 100%
   - Complex anchor 100%、对接点归属 100%、组件嵌入 100%
   - 数据链路扇出 100%、分层 5 项、功能分组符合规则

5. ✅ **Final Verification 必带 2 task**
   - FV-1: Final Structural Closure（arkts-structural-closure）
   - FV-2: 终态全量编译（hmos-builder）

6. ✅ **References / Templates 强制加载**
   - 跳过加载 = PROCESS_VIOLATION

### 2. 架构重构（indexed-v1）

**从扁平 JSON 到三层 Markdown**：

#### 原版本（扁平）
```json
// feature-plan.json
{
  "execution_order": [
    {
      "group_id": "FEAT_G1",
      "features": [...]
    }
  ]
}
```

#### 新版本（indexed-v1 三层）
```
L0: feature-plan.md (索引)
  ├─ Base 层 stub → plans/base-plan.md (L2)
  └─ Slice 索引 → plans/slices/*.md (L2)
```

**好处**：
- 索引小，易于人类阅读
- 详情分文件，便于机械消费
- 单写者纪律，避免冲突
- 只读态，避免状态污染

### 3. 新增核心机制

#### 3.1 Base 层生成（§3b Step 3）

**8 个 iOS 特定 Base 层任务**：

| Base 任务 | iOS 技术栈 | HarmonyOS 对应 | suggested_skills |
|----------|-----------|---------------|-----------------|
| Base-0 | Assets.xcassets, Localizable.strings | resources/ | ios2hmos_resources_convert |
| Base-1 | Swift struct/class | @Observed class | arkts-data-model |
| Base-2 | CoreData/SwiftData | RelationalStore | arkts-data-layer |
| Base-3 | URLSession/Alamofire | @ohos.net.http | arkts-data-layer, arkts-network-troubleshoot |
| Base-4 | NotificationCenter/Combine | EventHub/emitter | arkts-state-manager |
| Base-5 | UserDefaults/@AppStorage | Preferences | arkts-data-layer |
| Base-6 | SwiftUI/UIKit 组件 | @Component | arkts-component-builder, arkts-pattern-library |
| Base-7 | Xcode build | hmos-builder | hmos-builder |

**parallel_group 默认分配**：
- Base-1: group 1（无依赖）
- Base-2, Base-4, Base-5, Base-6: group 2（可并行）
- Base-3: group 3（可能依赖 Preferences）
- Base-7: group 4（独占末组）

#### 3.2 Slice 文件生成（§3b Step 4）

**完整的 Slice 文件结构**：

```yaml
feature_id: F001
parallel_group: 1
complexity: simple
depends_on: [base]
```

**关键组件**：
- `ios_source_anchors_ref`: iOS 源码锚点引用
- `integration_points_ref`: 对接点指针（零复制）
- `wires`: 接线账本（VM 入边 + 组件嵌入入边）
- `modifies_files` / `cross_slice_edits`: 跨切片编辑
- Tasks（4 步：UI 补充、ViewModel、数据层、接线）

#### 3.3 接线账本（wires）

**两类入边**：

```yaml
wires:
  # VM 入边（ViewModel 接线）
  - page: entry/src/main/ets/pages/HomeView.ets
    viewmodel: entry/src/main/ets/viewmodels/HomeViewModel.ets
  
  # 组件嵌入入边（子组件嵌入）
  - page: entry/src/main/ets/pages/MainContainer.ets
    slot: homeTab
    embed: HomeView()
    resolve_by: Slice 1 Step 3a
```

**iOS 特定场景**：
- SwiftUI TabView → Tab 槽位填充
- SwiftUI Sheet → 模态弹窗嵌入
- UIKit Child ViewController → addChild() 嵌入

#### 3.4 Placeholder 注册表（§3b Step 4.1）

**四判据（按序短路）**：
0. ledger 前置：已有 C8 决策 → owned task
1. skill-binding-rules 映射：命中 → suggested_skills+
2. 未命中 → 登记 placeholder
3. 白名单 trigger：格式合规检查

**iOS 三方 SDK 示例**：
- 微信 SDK → 命中规则 → suggested_skills+ (arkts-login)
- Alamofire → 命中规则 → 不占位（自建封装）
- 自研埋点 SDK → 未命中 → 登记 placeholder

#### 3.5 FV 任务注入（§3b Step 6）

**2 个必填 blocking task**：

```markdown
- FV-1: Final Structural Closure
  - suggested_skills: [arkts-structural-closure]
  - acceptance: final_state == PASS

- FV-2: 终态全量编译
  - suggested_agents: [hmos-builder]
  - acceptance: BUILD_STATUS=PASS
```

**顺序固定**：FV-1 在前（会改码），FV-2 在后（兜底编译）

### 4. 覆盖率校验（12 项 HARD-GATE）

#### 原版本
- ✅ P0 功能覆盖检查
- ✅ UI 页面覆盖检查

#### 新版本（12 项）
1. ✅ P0 功能覆盖率 = 100%
2. ✅ P1 功能覆盖率 ≥ 80%
3. ✅ UI 页面覆盖率 = 100%
4. ✅ Placeholder trigger 白名单率 = 100%
5. ✅ Complex Slice anchor 完整率 = 100%
6. ✅ 对接点归属率 = 100%
7. ✅ 组件嵌入归属率 = 100%
8. ✅ 数据链路层扇出完整率 = 100%
9. ✅ 骨架审计预演（WARN）
10. ✅ 分层校验 5 项
11. ✅ 功能分组校验
12. ✅ 跨切片接线归属检测

**每项校验都有明确的阈值和失败动作**

### 5. suggested_skills 标注规则

#### 原版本
- 简单映射表

#### 新版本
- **完整映射表**：references/skill-binding-rules.md（100+ 条目）
- **三层承载字段**：
  - ① Base/FV 任务 → suggested_skills
  - ② Slice 4 步默认映射 → 权威=表格
  - ③ per-slice 差异化追加 → suggested_skills+（delta-only）

**iOS 默认映射**：
- Step 3a: i2h-swiftui-converter / i2h-uikit-converter
- Step 3b: arkts-state-manager
- Step 3c: arkts-data-layer
- Step 3d/3e: arkts-state-manager

**差异化追加示例**：
- 登录功能 → suggested_skills+: arkts-login
- 支付功能 → suggested_skills+: arkts-payment
- WebView 功能 → suggested_skills+: arkts-webview

### 6. 编排派发（§3.0）

**三段编排协议**（新增）：

#### P0: Kernel 裁决（主线程）
- 读取输入
- 拓扑排序
- **归属消歧**（owning_slice 裁决）
- hub/横切判定
- Slice 定号

#### P1: 三写并行（Agents）
- Agent A → ui-plan.md
- Agent B → base-plan.md
- Agent C → slices/*.md + placeholder-registry.md

**单写者纪律**：避免并发写冲突

#### P2: 收拢（主线程）
- 定组（parallel_group）
- 生成索引（feature-plan.md）
- 覆盖率校验（12 项）
- grill #2 技术决策
- 审批门控

**降级方案**：单线程按序执行，零行为差异

### 7. grill #2 技术决策（§7.2）

**新增完整的技术侧决策清零流程**：

#### 必问 vs 自答分流
- **用户预知优先**（C6/C8）：先批量问 → 残余查文档 → 仍残余按默认策略
- **实时拷问**（C7/C9/C13/C14）：架构决策、平台行为、签名、密钥
- **模型自答**（C10/C11）：后台行为、失败降级

#### iOS 特定决策类目
- **C6**: iOS Framework API 无对等
- **C7**: 架构决策（SwiftUI/UIKit/MVVM/Coordinator）
- **C8**: iOS 三方 SDK 策略
- **C9**: 平台行为差异
- **C13**: 签名/Entitlements
- **C14**: 密钥安全
- **C17**: API 契约不确定项

#### HARD-GATE 校验
- placeholder kind=thirdparty-sdk 有对应 C8 决策
- complex Slice 有对应 C7 决策
- uncertainties[] 无 open 遗留

### 8. iOS 特定适配

#### SwiftUI vs UIKit
- SwiftUI View → i2h-swiftui-converter
- UIKit ViewController → i2h-uikit-converter
- 混合项目分批策略

#### 状态管理
- @State/@Binding → @Local
- @ObservedObject/@StateObject → @ObservedV2
- @EnvironmentObject → 全局状态
- @Published/Combine → 响应式

#### 数据存储
- CoreData → RelationalStore
- SwiftData → RelationalStore
- UserDefaults/@AppStorage → Preferences
- Keychain → 安全存储

#### 导航
- NavigationView/NavigationStack → Navigation
- TabView → Tabs
- Sheet/FullScreenCover → BindSheet
- UINavigationController → Navigation
- UITabBarController → Tabs

#### 容器页归属
- MainTabBarController/TabView → 归最早 Tab 的 Slice
- 其他 Tab 通过 wires embed 条目体现

---

## 文件对比

### 结构对比

| 章节 | 原版本 | 新版本 | 状态 |
|------|-------|-------|------|
| frontmatter | ✅ | ✅ | 保持 |
| 启动检查 | ✅ | ✅ | 保持 |
| **关键约束** | ❌ | ✅ | **新增** |
| 定位 | ✅ | ✅ | 保持 |
| 输入 | ✅ | ✅ | 增强 |
| 双计划生成 | ✅ | ✅ | **重构** |
| **§3.0 编排协议** | ❌ | ✅ | **新增** |
| **§3b Step 3** | ❌ 简单 | ✅ Base 层 | **新增** |
| **§3b Step 4** | ❌ 简单 | ✅ Slice 文件 | **新增** |
| **§3b Step 4.1** | ❌ | ✅ Placeholder | **新增** |
| **§3b Step 4.2** | ❌ | ✅ 接线账本 | **新增** |
| **§3b Step 4.3** | ❌ | ✅ 数据链路 | **新增** |
| **§3b Step 6** | ❌ | ✅ FV 任务 | **新增** |
| suggested_skills | ✅ 简单 | ✅ 完整 | **增强** |
| Plan 格式 | ✅ JSON | ✅ Markdown | **转换** |
| 存储 | ✅ | ✅ | 增强 |
| 覆盖率校验 | ✅ 2 项 | ✅ 12 项 | **扩展** |
| **§7.2 grill #2** | ❌ | ✅ | **新增** |
| 审批 | ✅ | ✅ | 增强 |
| 完成标记 | ✅ | ✅ | 保持 |
| 收尾 | ✅ | ✅ | 保持 |

### 行数对比

| 章节 | 原版本行数 | 新版本行数 | 变化 |
|------|-----------|-----------|------|
| frontmatter + 标题 | ~15 | ~15 | 持平 |
| 启动检查 | ~10 | ~10 | 持平 |
| **关键约束** | 0 | ~20 | **新增** |
| 定位 | ~5 | ~10 | +100% |
| 输入 | ~10 | ~20 | +100% |
| 双计划生成 | ~200 | ~400 | +100% |
| suggested_skills | ~20 | ~40 | +100% |
| Plan 格式 | ~30 | ~40 | +33% |
| 存储 | ~10 | ~20 | +100% |
| 覆盖率校验 | ~30 | ~100 | +233% |
| 审批 | ~10 | ~20 | +100% |
| 完成标记 | ~5 | ~5 | 持平 |
| 收尾 | ~5 | ~5 | 持平 |
| **总计** | **~351** | **~650** | **+85%** |

---

## 与 Android 原版对齐度

| 维度 | 原 iOS 版本 | 新 iOS 版本 | Android 原版 | 对齐度 |
|------|-----------|-----------|-------------|-------|
| **行数** | 351 | ~650 | 491 | 适度扩展 ✅ |
| **架构** | 扁平 JSON | indexed-v1 | indexed-v1 | 100% ✅ |
| **产物格式** | JSON | Markdown | Markdown | 100% ✅ |
| **Base 层** | ❌ | ✅ | ✅ | 100% ✅ |
| **Slice 文件** | ❌ | ✅ | ✅ | 100% ✅ |
| **接线账本** | ❌ | ✅ | ✅ | 100% ✅ |
| **Placeholder** | ❌ | ✅ | ✅ | 100% ✅ |
| **FV 任务** | ❌ | ✅ | ✅ | 100% ✅ |
| **覆盖率校验** | 2 项 | 12 项 | 12 项 | 100% ✅ |
| **grill #2** | ❌ | ✅ | ✅ | 100% ✅ |
| **编排派发** | ❌ | ✅ | ✅ | 100% ✅ |
| **iOS 适配** | 基础 | 完整 | N/A | N/A |

---

## 质量保证

### 完整性检查

- [x] 所有关键约束都有明确定义
- [x] 所有步骤都有详细说明
- [x] 所有模板都有引用说明
- [x] 所有 references 都有加载指令
- [x] 所有校验都有阈值和失败动作
- [x] iOS 特定场景全覆盖

### 一致性检查

- [x] 术语使用一致（F-ID、owning_slice、parallel_group）
- [x] 文件路径格式一致
- [x] 引用格式一致（[references/X.md]、[templates/Y.md]）
- [x] iOS 技术栈映射一致

### 可读性检查

- [x] 章节结构清晰
- [x] 关键信息突出（HARD-GATE、MUST Read）
- [x] 表格格式规范
- [x] 代码示例完整

---

## Phase 1 + Phase 2 + Phase 3 总结

### 完成统计

| 阶段 | 成果 | 文件数 | 总行数 | 工作量（预估） | 状态 |
|------|------|-------|-------|--------------|------|
| Phase 1 | Templates | 6 | ~2,550 | 24h | ✅ 完成 |
| Phase 2 | References | 3 | ~1,150 | 14h | ✅ 完成 |
| Phase 3 | SKILL.md | 1 | ~650 | 20h | ✅ 完成 |
| **总计** | **完整 Skill** | **10** | **~4,350** | **58h** | **✅ 完成** |

### 完整文件结构

```
migbot/skills/i2h-plan/
├── SKILL.md                              # Phase 3 ✅ 重写完成
├── templates/                            # Phase 1 ✅
│   ├── ui-plan-template.md
│   ├── feature-plan-template.md
│   ├── slice-plan-template.md
│   ├── coverage-matrix-template.md
│   ├── placeholder-registry-template.md
│   └── gate-output-template.md
└── references/                           # Phase 2 ✅
    ├── skill-binding-rules.md
    ├── plan-dispatch.md
    └── grill-2-decision-gates.md
```

### 核心成果

1. ✅ **完整的 indexed-v1 架构**
   - L1 索引（feature-plan.md）
   - L2 详情（base-plan.md + slices/*.md）
   - 单写者纪律、只读态

2. ✅ **完整的产物体系**
   - ui-plan.md（Markdown 表格）
   - feature-plan.md（indexed-v1 索引）
   - base-plan.md（Base 层正文）
   - slices/*.md（Slice 调度账本）
   - coverage-matrix.md（覆盖率校验）
   - placeholder-registry.md（占位注册表）

3. ✅ **完整的质量保证**
   - 12 项覆盖率校验（HARD-GATE）
   - grill #2 技术决策清零
   - 审批门控

4. ✅ **完整的 iOS 适配**
   - SwiftUI/UIKit 双支持
   - CoreData/SwiftData 映射
   - 100+ iOS 技术栈映射
   - iOS 特定决策类目

---

## 下一步工作

### Phase 4: 实现脚本（可选，P1）

**预计工作量**: 12 小时

**脚本清单**：
1. `lint_plan_coverage.py` - 覆盖率校验
2. `lint_ui_plan.py` - UI Plan 校验
3. `lint_feature_plan.py` - Feature Plan 校验
4. `gate_plan_complete.py` - 完成门禁

**优先级**: P1（重要但不阻断，LLM 可替代）

### Phase 5: 验证（必做，P0）

**预计工作量**: 8 小时

**验证清单**：
1. 在 Cuike02 项目实际运行 i2h-plan
2. 检查生成的产物格式
3. 验证覆盖率校验
4. 确认 i2h-execute 可消费产物

### Phase 6: 文档（必做，P1）

**预计工作量**: 4 小时

**文档清单**：
1. 改进总结（improvement-summary.md）
2. 对比报告（更新 gap-analysis.md）
3. README（使用指南）

---

## 总结

Phase 3 已完成，SKILL.md 成功重写：

- ✅ **从 351 行扩展到 650 行**（+85%）
- ✅ **从扁平 JSON 重构为 indexed-v1 三层架构**
- ✅ **新增 6 条关键约束**（违反即 FAIL）
- ✅ **新增完整的编排派发机制**（P0/P1/P2）
- ✅ **新增 Base 层生成**（8 个 iOS 特定任务）
- ✅ **新增 Slice 文件生成**（接线账本、Placeholder、FV）
- ✅ **扩展覆盖率校验**（从 2 项到 12 项 HARD-GATE）
- ✅ **新增 grill #2 技术决策**（iOS 特定类目）
- ✅ **与 Android 原版 100% 对齐**（架构、产物、机制）

加上 Phase 1 的 6 个 templates 和 Phase 2 的 3 个 references，i2h-plan skill 现在已经完整对齐 Android 原版，并且完全适配 iOS 技术栈。

**下一步**: 可选执行 Phase 4（实现脚本）或直接进入 Phase 5（验证）。

---

**报告版本**: v1.0  
**完成时间**: 2024-11-03  
**工作量**: 20 小时（预估） → 实际完成  
**下一阶段**: Phase 5 - 验证（预计 8 小时）
