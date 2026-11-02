<!-- when: 派发 Stage 3 slice worker（a2h-migration-worker，每 slice 恒 1 个，Step 3a/3b/3c/3d 一次跑完）时加载本段 + _common.md -->
<!-- topics: Stage 3 slice worker prompt, Step 3a UI 补充, Step 3b ViewModel 三段式, Step 3c 数据层接入, Step 3d 自身页内接线, forward-ref 解除, 信封 -->

# §4. Stage 3 slice worker prompt（a2h-migration-worker）

> 公共占位规则 §2.1 + 单写者纪律见 [`_common.md`](./_common.md)，派发时一并 Read。
> 每 slice 恒 1 个 worker，Step 3a → 3b → 3c → 3d 在同一次调用内顺序完成（execute §5a 禁止按步拆 subagent）。步骤编号是 registry `resolve_by=Slice N Step 3x` 的数据值，照旧使用。跨文件接线 / 资源 sweep / 结构验证 / brief 由 group-closer 收口（[`8-group-closer.md`](./8-group-closer.md)），编译由 execute §5f 集中门完成。

```
Agent(
  prompt="你正在执行 Feature Slice [{slice_name}]：Step 3a UI 补充 → 3b ViewModel → 3c 数据层 → 3d 自身页内接线，一次完成（跨文件接线 / 结构验证 / brief 由 group-closer 收口；编译由 execute §5f 集中执行）。

  Slice 文件: {slice_file_path}          # plans/slices/slice-NN-<fid>.md（只读调度账本）
  Slice 复杂度: {complexity}            # simple 或 complex
  功能 Spec: {feature_spec_path}
  目标页面 + 嵌入子组件: {page_list}（含 ui-manifest 子组件表中的内嵌 Tab / Guide 子组件）
  页面 Spec: {page_spec_paths}
  Android 源码根目录: {android_source_dir}
  Android 源码 anchors（complex 必传，经 slice 文件 anchors_ref.source 取）:
    {anchors_yaml}
  Base 契约: spec/execution/base-contracts.md（指针，不内联）
  已有 Base 层: entry/src/main/ets/network/, entry/src/main/ets/database/, entry/src/main/ets/models/
  公共组件库: entry/src/main/ets/components/common/（Design Tokens + 共享组件，UI 补充必须引用）
  references_dir: {references_dir}       # 同 converter：$SKILLS_ROOT/android-ui-graph-query/references/
  接线清单（来自 slice 文件）:
  - integration_points_ref: {integration_points_ref}   # spec 对接点段链接——先 Read 该节取逐条结构化对（page.handler ← Target.member），spec 是唯一权威
  - wires: {wires}                                # page → viewmodel 映射
  - modifies_files: {modifies_files}              # 本 Slice 需修改的【已存在】文件
  - cross_slice_edits: {cross_slice_edits}        # 仅作上下文，本 worker 不执行——closer 落地
  产出路径: entry/src/main/ets/viewmodels/{SliceName}ViewModel.ets；entry/src/main/ets/repositories/{SliceName}Repository.ets（如需）

  使用 Skill: arkts-state-manager（3b / 3d）、arkts-data-layer（3c）、a2h-activity-converter（3a 需转换新页面时）+ slice 文件 `suggested_skills+:` 追加项
  可调用的辅助 Skills（worker frontmatter 保留的 17 个之一）: android-ui-graph-query（page/component 上下文）、android-view-to-arkui（XML→ArkTS / 类→类翻译）、arkts-knowledge-verifier（API 验证）、arkts-library-migration（三方库映射）

  写盘边界（单写者纪律，无条件，四步同适用）:
  - 只写【本 slice 自身】的 page / component / VM / repository 文件。
  - 禁碰共享文件与他切片文件：HomePage 等父页、feature-plan.md / plans 产物、cross_slice_edits 列出的文件——全部移交 group-closer。
    两项 append-only 例外照 _common.md：registry 登记行 append、资源 JSON append 缺失键。
  - 不编译（hvigorw / hmos-builder / hmos_fix_build_errors 均不调），语法自检即可。

  【Step 3a UI 补充】
  - UI 陷阱必读：本 slice 只要改/加任何 UI（含 3b / 3d 里新加的弹窗、进度浮层、层叠布局），动手前先 Read {references_dir}ui-migration-pitfalls.md，按其「修复」写法实现；P-17 / P-30 / P-31 / P-32 / P-33 / P-34（层叠命中、Stack 子组件定位、浮层条件挂载、弹窗返回键、onResume 类逻辑与防重入复位、根页退出）逐条对照自己改的代码。
  - 查页面状态用 grep ui-manifest 对应页行，禁整读 manifest。converted → 确认 .ets 存在并报告，【不跳过 Slice】；pending / 不在 ui-plan → 调 a2h-activity-converter 转换（ui-snapshots 缺失即报告，主线程走 §7 Phase A）；verified → 跳过。
  - forward-ref-uncertain 二次审视：读 spec/placeholder-registry.md，过滤 kind=forward-ref-uncertain AND resolve_by=Slice {本} Step 3a；逐 P-ID 定位 location 的 `// TODO:` 区域：升级为真实实现（删 TODO + 写真实代码 → uncertain_regions_resolved）或占位合理（运行时才知的动态值 → 保留 TODO → uncertain_regions_retained + 原因）。

  【Step 3b ViewModel + 状态管理】（complex 强制三段；simple 只做第三段）
  第一段 源码理解：Read anchors 列出的文件（grep-first 定点读，不整读）。spec 已含「## 源码 5-role 摘要」→ 只核对不重写，差异随第二段输出；无摘要 → 按 5 个 role 输出摘要（缺一不可）：
    ### Source Understanding Summary
    - role=presenter/viewmodel: ① 状态机（列出所有状态枚举）② 事件流 ③ 异常分支
    - role=service/repository:  ① 接口列表 ② fromJson 兜底 ③ 缓存策略
    - role=interceptor:         ① 拦截链顺序 ② header/参数注入 ③ 加密路径
    - role=base_class:          ① 基类 lifecycle hook ② opt-in 机制 ③ 共享状态
    - role=util:                ① 静态方法清单 ② 命中场景 ③ 副作用
    每个 role 摘要必须含具体 Kotlin 类名或方法名（grep 反查依据），缺 → WORKER FAIL；无 anchor 的 role 写 \"该 role 无 anchor\"，其他必须填齐。
    AC 锚点二型：`源:<Kotlin 符号> → 标:`（行为契约 = anchors 源码）；`决:<PD/D/G-ID> → 标:`（行为契约 = grep spec/decision-ledger.md 该决策正文 + §数据流 `替代路径` 行，不找 Kotlin 符号；落点仍是 `标`）。`[真机]` 不豁免实现，仅表示断言由 verify 设备实测。
  第二段 差异清单：对比摘要与 feature spec，列 spec 没写但源码有的隐式逻辑（触发条件 + 代码引用）：
    ### Spec Gap List
    - <差异>: ...        （为空写 \"无差异\"）
  第三段 实现：创建 ViewModel class（complex：状态机分支对齐第一段）；定义 @Local / @Param / @Event 状态变量；实现 UI 事件处理方法（complex：覆盖第一段全部异常分支）；UI 组件事件绑定到 ViewModel 方法。@BuilderParam 传参一律箭头闭包 `() => { this.x() }`（保持父 this），禁传裸方法引用 `this.x`。
  副产物（complex 强制）：spec/execution/source-understanding/{slice_name}-source-notes.md = 第二段差异清单（spec 已有 5-role 摘要时不复制摘要——单一权威源；无摘要时才含第一段）。

  【Step 3c 数据层接入】
  1. 按需创建 Repository / Service（复用 Base 层公共能力）。complex：拦截器 / header 注入 / 加密链对齐 source-notes 的 role=interceptor；所有通路独立实现，参考 role=service。
  2. 接入网络层（API）或本地存储（DB / Preferences）；ViewModel 调用 Repository；数据流 UI ← ViewModel ← Repository ← API/DB 闭环；处理数据转换与缓存策略。
  3. 多子仓约束（项目存在 module-dep-graph.json 时）：调用其它子仓的 service / 数据模型 → 签名与语义以 cross-module-contracts.md（被依赖子仓为 owner 的权威规约）+ module-dep-graph.json 接口桩为准，禁止就地发明；契约缺失 → 记「决策缺口」，不臆造。

  【页面输入与交互结果】
  读取 $SKILLS_ROOT/a2h-spec/references/interaction-data-contract.md。核对 producer → 路由传参/共享状态/缓存/seed → consumer → 渲染；入口提供的列表不能另造请求替代。接线证据应覆盖调用方传值与目标接值，跨文件修改交 closer。
  核对适用 action 的可观察结果及空态/错误态，区分错误绑定与空 handler。阻塞启动的外部等待须有操作级 deadline 和失败终态；超时/重试后取消或忽略晚到结果。跳过登录/广告等行为差异须有已批准决策。
  说明写入既有 source-notes 或交接摘要，不创建必交 sidecar，不因不存在固定测试类别阻断。

  【Step 3d 自身页内接线】
  1. 编辑 modifies_files 中属于自身页面 / 组件的【已存在】.ets（不新建）；补 import 并实例化 ViewModel（`new XxxViewModel()`）。
  2. grep 自身文件内 `// FWD-REF:` marker 逐个换真实调用：handler 绑定 ViewModel 方法、aboutToAppear 调 ViewModel / Repository 加载数据。
  3. resolve_by=本 Slice 的 forward-ref：自身文件内的必须全部解除（marker 消失 + 真实实现存在）；位于共享 / 他切片文件中的由 group-closer 解除。接线禁止留任何 placeholder / TODO / prose defer。
  4. 不回填任何 plan 文件——接线完成性由 verify_slice_wiring C2 按结构化对机械判定。

  impl: 指针（3b / 3c 共用）：功能 Spec 的 AC 组带 impl: 指针时（目标 addendum consumed_at 匹配 step-3b / step-3c，缺省按 slug 默认表）→ 按 _common.md「impl: 指针语义」精读目标 §节（≤3 节 / ≤150 行，超出记 deferred_addenda）；禁止整目录扫读 addenda。

  验收（HARD-GATE）:
  - complex: 响应含完整三段 + source-notes.md 存在；任何 role 摘要缺类名 / 方法名 → WORKER FAIL（脚本反查）
  - 全部: ViewModel / Repository 语法自检通过；UI 事件绑定完整；数据流闭环
  - 接线 evidence 指向调用方（如 `pages/XxxPage.ets:48 import` + `:81 new XxxViewModel()`），不得用 VM 文件自身行号充数

  返回报告必须含（信封，_common.md 信封契约）:
  - uncertain_regions_resolved[] / uncertain_regions_retained[]   # P-ID（retained 附原因）；主线程据此更新 registry
  - wired_files: []                    # 实际改动的自身文件（仅路径）
  - resolved_fwd_refs: []              # 本 worker 解除的 forward-ref P-ID（closer 记入 writeback `registry.resolve`）
  - integration_points_done_count: N   # 自身页内已接对接点计数（明细 closer 写 brief；机械判定归 verify_slice_wiring）
  - decision_gaps: []                  # 契约缺失等决策缺口（主线程按 §1.1 阻断）
  - pitfalls_applied: []               # 本 slice 改 UI 时对照并落实的陷阱 P-ID（没改 UI 写 []）",

  subagent_type="hmigbot:a2h-migration-worker"
)
```

**特殊领域追加 Skill**：媒体播放 → `arkts-media-playback`；文件下载 → `arkts-download-manager`；系统权限 → `arkts-system-capabilities`（在 `arkts-data-layer` 基础上追加）。

**响应模板约束**：三段式格式在 prompt 内强约束，独立 Step 3.0 派发已并入此 prompt（省 ~30-50 min 启动开销）。**反向回灌**：source-notes 差异清单非空时由 a2h-retrospect 或人工追加到 feature spec §隐式契约；本方案不强制自动回灌，差异清单可信度由 worker grep 反查保证。

> **scope 说明**：本 prompt 的写盘 scope **永远是自身文件**（任意组大小，含 size-1 组）。跨文件部分（cross_slice_edits / 父页 embed wires / registry 状态集合）整体由 §8 group-closer 收口（账本经 writeback manifest 落盘；plan 产物零回填）——不存在"worker 做全部接线"的模式。
