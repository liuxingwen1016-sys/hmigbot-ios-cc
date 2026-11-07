<!-- when: Phase B Step B2 生成分页 ui/page_NNNN.md 时加载 -->
<!-- topics: 分页 spec, android_source_anchors, 溯源, 转换决策, 状态接口, 导航关系 -->

# 分页 UI Spec 模板

必填字段：顶部 `android_source_anchors` YAML、溯源、页面结构、转换决策表、状态接口表、导航关系表、
沉浸式配置。页面拥有或消费 Dialog 时，还必须生成下述固定行为字段/Variants；共享正文只维护一次。

仅 ui_facts_policy=static-v1：读取同页 visual.json/fixture.json/templates；
保留原必填段，视觉事实章节由 ui_facts.py render 插入并校验，不手写或修改解析出的数值。
动态义务的解释及 disposition 写入本 batch 的 ui-facts-decisions JSON，格式见
[static-ui-facts.md](../references/static-ui-facts.md)。

````markdown
# page_0001: MainActivity

```yaml
android_source_anchors:                # 文件级，stub-name → Kotlin/Java 源文件路径
  SmartCourseComponent: "app/src/main/java/com/example/holder/GySmartClazzHolder.kt"
  PartFiveBubblePage:   "app/src/main/java/com/example/ui/PartFiveBubblePage.kt"
```

## 溯源
- Android Activity: de.danoeh.antennapod.activity.MainActivity
- 源码布局: app/src/main/res/layout/main.xml
- UI 快照: ui-snapshots/page_0001_MainActivity/
- 输出文件: entry/src/main/ets/pages/MainPage.ets

## 页面结构
- 根布局: DrawerLayout → SideBarContainer
- 内容区: CoordinatorLayout → Stack
- 底部导航: BottomNavigationView → Tabs (4 tabs + More popup)
- 外部播放器: ExternalPlayerFragment → ExternalPlayerBar

## 转换决策
| Android 组件 | ArkUI 组件 | 决策理由 |
|-------------|-----------|---------|
| DrawerLayout | SideBarContainer(Overlay) | 官方侧边栏容器 |
| BottomNavigationView | Tabs(BarPosition.End) | 底部 Tab 标准实现 |
| CoordinatorLayout | Stack(Alignment.Bottom) | 叠加布局 + 底部对齐 |

## 状态接口（供 Feature Pipeline 对接）
| @Local 变量 | 类型 | 数据来源 | 关联功能 |
|------------|------|---------|---------|
| isPlaying | boolean | PlaybackService | F001-playback |
| episodeTitle | string | PlaybackService.currentItem | F001-playback |
| currentTabIndex | number | 本地 UI 状态 | — |
| sideBarShow | boolean | 本地 UI 状态 | — |

## 导航关系
| 触发 | 目标页面 | 类型 |
|------|---------|------|
| Tab: Home | page_0002_HomeFragment | Tab 切换 |
| Tab: Queue | page_0003_QueueFragment | Tab 切换 |
| Tab: More | BottomNavigationMorePopup | 弹出菜单 |
| ExternalPlayerBar 点击 | AudioPlayerPage | 页面跳转 |
| 侧边栏: Settings | PreferencePage | 页面跳转 |

## 页内弹窗 / 面板

### <Dialog 名或实例名>
- 源码锚点：<本 Dialog（或其真实祖先 / layout owner）的源文件；消费页写本 Dialog 或调用点文件；
  **匿名实例**必须写调用点 `File.java:line`（或含该行的 `:起-止`），每个匿名实例单独一个 section>
- 呈现形态：<centered dialog / bottom sheet / popup / routed dialog；目标挂载方式>
- 触发入口与输入：<show 调用方、控件/事件、条件、参数>
- 内容与初始值：<控件、选项、顺序、预填值>
- 交互状态：<选择/编辑/校验/加载/失败状态>
- 确认结果：<回调、持久化、宿主刷新、关闭时机；可引用 F0xx-ACnn>
- 取消与关闭：<按钮、返回、遮罩、手势、宿主退出>

## Variants
| source FQN | host | difference | target |
|---|---|---|---|
| `com.example.QueueSortDialog` | `com.example.QueuePage` | [F003-AC07] 显示 keep-sorted | ItemSortDialog component |

## 沉浸式 + 安全区

本页面 `needs_immersive_safearea = {读 meta.json 字段值}`（基于 `page_type = {读 meta.json 字段值}` 自动判定）。
- `true` → converter 按 [arkts-immersive-safearea](../arkts-immersive-safearea/SKILL.md) 四层架构实施（spec 不列 API 以避免与 skill 漂移）
- `false`（modal_overlay / dialog / sub_component）→ converter 跳过本契约
````

分页 Spec 的生成逻辑：
- **android_source_anchors（顶部 YAML 块）**：识别页面里所有 stub 引用（转换时需追溯 Android 源码理解的复杂组件，如自定义 ViewHolder、自定义 ViewGroup、运行时绑定的 Item 模板）。对每个 stub 名（用 ArkTS 端期望的组件名作 key），扫描 Android 工程中匹配的 Kotlin/Java 源文件，记录**文件级**路径（不到行号）。下游 a2h-activity-converter 遇到 stub 时**必须**读对应源文件再生成 ArkTS，缺 anchor → FAIL（见 a2h-execute §3a 占位即 FAIL 规则）。
  - 扫描策略：stub 名 ↔ `*ViewHolder.kt` / `*Component.kt` / `*View.kt` / `*Adapter.kt` / `*Page.kt` 命名约定匹配；命中多个时全部记录。
  - 自动扫描遗漏时 → 留空，由 converter 触发 FAIL 暴露 → 人工补 anchor。
  - 本页容器承载的 Fragment（经 Fragment 事务装入或在布局中声明）在 ui-manifest 页面清单中有自己的分页 spec 时，不写入本页 anchors：它按自己的 spec 生成，本页只在「页面结构」「转换决策」中引用其页面编号。弹窗 / 组件的消费页锚点仍按文末「弹窗 / 面板规格组织判断」保留。
- **溯源**：从 Phase A 的分析结果直接提取
- **页面结构**：读取 view.xml（或合成版）的层级树，提取主要 ViewGroup 结构，对应到 ArkUI 组件
- **转换决策**：对每个关键 Android 组件，记录选择的 ArkUI 替代方案和理由；承载 Fragment 的容器（`FragmentContainerView`，或作为 Fragment 事务目标的其他布局）按 [layout mapping 的 `FragmentContainerView` 行](../../android-ui-graph-query/references/android-to-harmonyOS-ui-layout-mapping-reference.md#布局容器映射) 选型，并写明所承载 Fragment 的页面编号
- **状态接口**：扫描源码中的成员变量、LiveData/Flow 订阅、SharedPreferences 读取，预定义 @Local 变量
- **导航关系**：从 Phase A Step A2 的导航分析结果提取
- **Dialog/Panel**：按 ui-manifest Dialog index 分配 body owner/consumer。Body owner 读取
  `dialog-snapshots` 三源数据并维护唯一共享正文；consumer 写本页入口、参数、结果/刷新和 body ref，
  不重复实现。七个 label 必须存在，源无行为写“无/不适用”。
- **Variants**：每个 concrete 后代均需真实继承关系；difference 以 `[F0xx-ACnn]` 或
  `[decision:key]` 开头。`decision:key` 只可放在现有三列转换决策表的“决策理由”列，不增加 key 列。

---

## 沉浸式条件注入（Step B2 执行规则）

**沉浸式 + 安全区节的条件注入**（必须执行）：

对每个 page，读 `spec/baseline/ui-snapshots/page_NNNN_XxxActivity/meta.json` 的 `page_type` 字段（由 Phase A `synthesize_meta_json.py` 自动判定，4 类：`full_screen_page` / `modal_overlay` / `dialog` / `sub_component`）：

| page_type | 生成 page spec 时的处理 |
|-----------|---------------------|
| `full_screen_page` | **必须**保留模板末尾的「沉浸式 + 安全区」节，把 meta.json `needs_immersive_safearea = true` 和 `page_type = full_screen_page` 填入节内占位 |
| `modal_overlay` / `dialog` / `sub_component` | 模板节内填实际值（`needs_immersive_safearea = false`，`page_type = {modal_overlay\|dialog\|sub_component}`），converter 据此跳过四件套实施。具体 API 由 [arkts-immersive-safearea](../arkts-immersive-safearea/SKILL.md) 提供，spec 不复述 |

设计依据：Android 源码无沉浸式/安全区概念（系统默认处理），但 HarmonyOS 全屏页必须显式四件套（系统不默认处理）——这是 Android→HarmonyOS 范式差异，必须由 spec 阶段强制注入避免 spec 作者遗漏。详见 `docs/immersive-safearea-coupling.md`。
