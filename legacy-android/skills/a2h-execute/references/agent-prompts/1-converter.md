<!-- when: 派发 Stage 1 converter（a2h-activity-converter）时加载本段 + _common.md -->
<!-- topics: Stage 1 converter prompt, 占位规则, forward-ref, stub 处理, 三源数据 -->

# §1. Stage 1 converter prompt（a2h-activity-converter）

> 公共占位规则 §2.1 见 [`_common.md`](./_common.md)，派发时一并 Read。

```
Agent(
  prompt="将 {activity_name} 从 Android 迁移到 ArkTS。

  参数:
  - activity_name: {activity_name}
  - ui_info: {ui_snapshots_path}
  - harmony_project_dir: {harmony_project_dir}
  - references_dir: {references_dir}
  - android_source_dir: {android_source_dir}
  - android_source_anchors: {来自 spec/baseline/ui/page_{page_id}.md 顶部 anchor 字段}
  - registered_placeholders: {按本页 owning_slice 前缀 grep spec/placeholder-registry.md 所得已登记占位（若无则空）}
  - wiring_ownership_map: {来自 coverage-matrix.md `Wiring Ownership Map` 段，本页相关的 (文件,handler)→owning_slice 子集}
  - owned_dialog_snapshots: {由 execute precheck 调用 `a2h-spec/scripts/dialog_index.py --owned-by <当前 page spec>` 机械派生；每项含 source_fqn/layout_owner_fqn/snapshot_ref/body_spec_ref/instance_refs；无则 []，禁止 Agent 自行增删或手工过滤}

  额外上下文:
  - 页面 Spec: spec/baseline/ui/page_{page_id}.md
  - Dialog 三源: owned_dialog_snapshots 中每个 snapshot_ref 的 meta.json + view.xml + Android layout；共享正文按 body_spec_ref 读取，消费实例按 instance_refs 接输入/结果
  - 公共组件库路径: entry/src/main/ets/components/common/（如 Stage 2 已完成，请引用这些组件作为样式锚点）
  - meta.json 关键字段
    * `needs_immersive_safearea`: true/false

  沉浸式 + 安全区 契约:
  仅当 meta.json `needs_immersive_safearea: true` 时调用 arkts-immersive-safearea 实施四层架构；false时跳过本契约。
  报告必填：needs=true → `immersive_safearea_implemented:[{layer,file,line}]×4`；needs=false → `immersive_safearea_skipped:<page_type>`

  stub 处理规则（严格）:
  1. 遇到 spec 中 stub: ComponentX(...) → 读取 android_source_anchors[ComponentX] 指向的源文件
  2. 找到源文件 → 按其 Kotlin/Java 实现生成 ArkTS 对等代码
  3. anchor 缺失 / 读取失败 / 文件路径不存在 → **必须 FAIL 返回报告，禁止 placeholder 占位**

  占位规则：converter 阶段可生成的 4 类合法占位的 marker 形态与 kind 类型:
  - `forward-ref`：未实装 handler / 跨切片 ViewModel 等代码桩，marker `// FWD-REF: <P-ID> resolve_by=Slice {N} Step 3d`
  - `thirdparty-sdk`：仅当 registry 已登记（plan 期直写）时允许，marker `// PLACEHOLDER: <P-ID> trigger=...`
  - `resource-pending-asset`：fallback 资产引用，marker `// FWD-REF: P-RES-ASSET-{seq} kind=resource-pending-asset trigger=<resource-id> 就绪`
  - `forward-ref-uncertain`：转换期自判的不确定区域（常见于 ui-manifest confidence=medium/low 页面的动态值/几何近似），marker `// TODO: <reason>` + **必须同步登记 placeholder-registry**（P-S{N}-UNC-{seq} + kind=forward-ref-uncertain + resolve_by=Slice {N} Step 3a）

  Phase 4 局部语法自检失败可留 `// TODO:` 标注 + 同步登记 registry，留待 a2h-execute 后续集中 `hmos-builder` 门收敛。
  其余形式（**未登记的** `// TODO` / 空回调 / 空 try-catch / 资源 value 含未登记 `[TODO:...]`）一律 FAIL。

  返回报告（结构化）必须含:
  - failed_stubs: []                # spec stub 无法展开清单（anchor 缺失/读取失败），与编译无关
  - generated_placeholders: []      # 每项 6 字段（P-ID + location + trigger_condition + kind + resolve_by + status）
  - illegal_placeholder_attempts: []  # 被规则拒绝的尝试（未登记 TODO / 占位禁令命中等）
  - low_confidence_uncertain_regions: []  # 仅 confidence != high 时列出 forward-ref-uncertain P-ID 及原因

  - layout_dims_gate: PASS | SKIP    # Phase 4 第 3b 步源布局尺寸自检的最终结果（FAIL 不得返回：补代码或写报告「尺寸偏差」段后重跑）

  再次强调：failed_stubs（stub 无法展开）必须为空、且无非法占位尝试、layout_dims_gate 不是 FAIL，本页才 PASS。
  ⚠️ 禁止任何编译/构建（hvigorw / hmos-builder / hmos_fix_build_errors）——Batch 收尾同样不编译；首次集中编译由 Base-7 执行，并发 hvigor 锁会拖垮流水线。
  转换报告写入 spec/execution/conversion-reports/{page_id}.md；只返回上述结构化信封 + page_id / output_file / report_path（≤30 行）。",

  subagent_type="hmigbot:a2h-activity-converter"
)
```

**五参数说明**：

| 参数 | 含义 | 来源 |
|------|------|------|
| `activity_name` | 目标 Android Activity 类名 | ui-plan.md 的 Android 来源列 |
| `ui_info` | UIAutomator 快照目录路径（含 view.xml + meta.json） | 项目中的 ui-snapshots 目录 |
| `harmony_project_dir` | HarmonyOS 工程根目录 | 当前项目路径 |
| `references_dir` | 领域知识和映射参考文件目录 | `$SKILLS_ROOT/android-ui-graph-query/references/`（`$SKILLS_ROOT` = 本套 skills 安装根，按当前 skill 目录的上一级解析，不写死宿主路径） |
| `android_source_dir` | Android 源码根目录 | 用户提供的 $ANDROID_SRC |

**三源数据**：converter agent 消费三种数据源：
1. `view.xml` — UIAutomator dump 的视图层次
2. `meta.json` — 页面元数据（可交互元素、导航路径等）
3. 源码 layout XML — Android 原始布局文件（通过 `android_source_dir` + Activity 源码中的 `setContentView` 定位）

**源布局尺寸自检**（converter Phase 4 第 3b 步，batch closer 复核）：`a2h-execute/scripts/layout_dims_gate.py` 检查 `meta.json.layout_sources` 里写死的每个 dp/sp 值，要么出现在本页代码（含直接 import 的 UI 组件；别的页面、service/model 里的逻辑数字不算），要么写进转换报告 `### 尺寸偏差` 段并说明怎么表达的。页面 spec 已转述大部分尺寸，所以这道闸查的是结果而不是"有没有读布局"：漏掉的按钮宽高、图标尺寸、整块没做的控件会在这里暴露。

## full-ui-v2 派发参数（该模式优先）

先 `ui_dispatch.py prepare --project-root <project> --unit-id <id> --attempt <N>`，把 prompt_path 全文加入派发。
它固定 component/page/output、unit_id、dispatch_id、packet_sha256 和每状态/区域的绝对图片路径。
按 required_inputs、source-derived layout_obligations 和全部 required_states 生成；先看代表/必需扩展图片，
小区域还看 full_context，不能把宿主背景观看算作子组件消费。XML 只读共享解析窗口，使用实际 density。
源码决定关系和尺寸，PNG/树选状态并验证；禁止测量值变成固定布局。保留 1030 的 route-root/wrapper/参数约束。
原始代码/报告写完立即 complete 保存 G0 并做 SDK/layout preflight；失败不改旧报告，修复使用新 attempt。
未提供 frozen packet 的旧模式仍按上文显式 page/state 调度，不按目录编号猜测目标。
