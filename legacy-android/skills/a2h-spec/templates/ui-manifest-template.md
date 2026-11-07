<!-- when: Phase B Step B1 生成 ui-manifest.md 时加载 -->
<!-- topics: ui-manifest, 页面清单, 全局约定, 页面状态生命周期, 转换批次, 共享组件 -->

# ui-manifest.md 模板

必填字段：全局约定、页面清单、页面状态生命周期、转换批次、共享组件表，以及
`dialog_index_schema: 1` 的固定 Dialog/Panel 索引。普通 Dialog 不增加页面清单行。

仅 static-v1：全局设计令牌引用 res-index/design-tokens.json，由 ui_facts.py render 插入 token 投影，不使用未引用的颜色。legacy 沿用原提取规则。

```markdown
# UI Manifest

## 全局约定
- 导航架构: Navigation + NavPathStack（入口 Navigation + NavDestination 子页面；常驻元素宿主不是入口页时另有宿主内容区 Navigation）
- 设计令牌: <按项目实际设计系统完整列出 — 不预设 token 数量、命名、分组方式；
      源在 Kotlin/Compose 时记录 .kt 文件路径与每个 token 的字面值/语义；
      源在 XML 资源时记录 colors.xml/themes.xml 关键 ref；
      如有 light/dark/gradient/typography/shape 子系统按项目结构分别列出>
- 命名规范: 页面 XxxPage.ets，组件 XxxComponent.ets
- 图标方案: SVG 资源 $r('app.media.ic_xxx')
- **沉浸式 + 安全区**：本工程全屏页统一采用 [arkts-immersive-safearea](../arkts-immersive-safearea/SKILL.md) 四层架构（API 细节由该 skill 维护，spec 不重复以避免漂移）；每页是否需要由 meta.json `needs_immersive_safearea` 字段决定

## 页面清单
| 序号 | Android | ArkTS 产出 | 优先级 | confidence | 状态 |
|------|---------|-----------|--------|-----------|------|
| 0001 | MainActivity | MainPage.ets | P0 | high | pending |
| 0002 | HomeFragment | HomePage.ets | P0 | high | pending |
| 0003 | QueueFragment | QueuePage.ets | P0 | medium | pending |
| ... |

### 页面状态生命周期
pending → converted → verified
- pending: 待转换
- converted: UI 已转换，等待验证
- verified: 编译通过 + 切片级功能验证通过
- skipped: 本轮不转换（V2 范围外）

## 转换批次
- Batch 1 (P0): 0001-0005 (App Shell + Home + 核心列表页)
- Batch 2 (P0): 0006-0010 (播放器 + 订阅 + 搜索)
- Batch 3 (P1): 0011-0016 (下载 + 统计 + 设置)
- Batch 4 (P2): 0017-0023 (次要页面)

## 共享组件
| 组件 | 用于页面 | Android 来源 |
|------|---------|-------------|
| ExternalPlayerBar | MainPage | external_player_fragment.xml |
| NavDrawer | MainPage | nav_list.xml |
| EpisodeListItem | Queue, Inbox, AllEpisodes | ... |

dialog_index_schema: 1

## 弹窗 / 面板索引
| dialog key | row kind | source FQN | call site | hosts | usage / presentation | snapshot ref | body spec location | instance spec location | closure |
|---|---|---|---|---|---|---|---|---|---|
| `dlg_xxx` | named | `com.example.FilterDialog` | `FeedPage.java:120` | `com.example.FeedPage` | bottom sheet / host inline | `spec/baseline/dialog-snapshots/dlgsnap_xxx_FilterDialog` | `spec/baseline/ui/page_0002_FeedPage.md#filter-dialog` | `spec/baseline/ui/page_0002_FeedPage.md#filter-dialog` | host_inline |
```

索引事实列由 `dialog-inventory.json` 机械枚举，不得删行缩小分母。`row kind` 仅
`named/anonymous`；inline builder/name-only candidate 只进 auditor WARN。一个 snapshot group 的所有
行必须共享同一 body spec location；每个 resolved host 必须有 instance spec location。
使用 `dialog_index.py --skeleton` 生成整表；只填写 skeleton 中四类 `TODO`（呈现、body、instance、
closure），禁止手抄 hashed key/source/call-site/host/snapshot 事实列。

全局约定的推导逻辑：
- **导航架构**：从 AndroidManifest.xml 的 Activity 数量 + Navigation Component 使用情况推断。单 Activity + NavHost → NavPathStack，多 Activity → 评估是否合并；带跨子页常驻元素（底部导航、播放条）的宿主页不是入口页时（如入口为启动页），写成「入口 Navigation + 宿主内容区 Navigation」，做法见 [v2-advanced-nav-patterns.md §3](../../arkts-navigation-builder/references/v2-advanced-nav-patterns.md)
- **设计令牌**：从 `styles.xml` / `themes.xml` / `colors.xml` 提取主色、文字色、背景色
- **命名规范**：Activity → Page，Fragment → Page 或 Component（依据使用方式）；普通
  DialogFragment/BottomSheetDialogFragment 不作为 page，正文写宿主页/共享章节，结构证据写
  `dialog-snapshots/`。Dialog theme Activity 仍是 Page。
- **图标方案**：扫描 `res/drawable*` 目录，确定图标格式（SVG/PNG/VectorDrawable）
- **沉浸式 + 安全区**：本节展示全工程统一的标准方案（4 Layer）；**每页是否需要产出对应配置由 `meta.json` 的 `page_type` / `needs_immersive_safearea` 字段自动决定**（见 `android-ui-graph-builder/scripts/synthesize_meta_json.py` 的 `detect_page_type()`）—— 本段无需再做词汇判定

优先级分配规则：
- P0：Launcher Activity + 其直接 Fragment + 核心业务页面
- P1：次级功能页面（设置、搜索、下载管理等）
- P2：辅助页面（关于、许可证、同步设置等）
