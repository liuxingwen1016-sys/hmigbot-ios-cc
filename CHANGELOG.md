# Changelog

本文件记录 migbot（Android → ArkTS / HarmonyOS 迁移工具包）各迭代的关键改动。

## [version v1.8.0] - 2026-10-24

汇总 ArkTs-Core 自 `version_930`（`c03d7323`）之后、截至 `version_1030@62d2b332` 的 Claude Code 相关更新，覆盖标准迁移主流程与 `1to1` 变体，并完善双平台发布与交付检查（PR #106）。

### ✨ 新增 (Added)

* **安卓自动遍历与快速视觉验证**：新增 `android_fast_traverse` 和 `visual-verify-speed`。安卓侧采集页面、交互状态、截图与跳转证据；鸿蒙侧复用安卓遍历树走查、配对和预筛，按文件冲突分组修复，复验受影响单元。支持断点续跑、弹窗处理和手驱补采，并记录不可达与业务状态漂移。

### 🔧 优化 (Improved)

* **完整 UI 交付**：补齐 Spec、Plan 与 Execute 的证据交接，按批准的页面、组件和状态清单生成、装配及验收；关联源码、HAP、设备、实际到达和截图证据，避免用安装成功或静态装配代替真实页面验证。
* **Stage 1 快速修复**：视觉问题按严重程度分档，有界修复并收窄后续修复范围；按源码引用与资源变化计算受影响页面，增量复采、沿用未受影响结果，并在当前安装包上完成正式页面冒烟检查。
* **门禁分类与迁移闭环**：按精确、推断、管线和环境问题分类处置并记录放行依据；加强 Spec/Plan 产物利用、装配完成断言、登录链及网络依赖初始化检查，减少弹窗清单、页面接线、共享实例和覆盖率检查误报。放行保留原始失败与欠账，不改写为验证通过。
* **一比一迁移**：同步 `1to1` 的 UI 交付、结构闭包和视觉验证能力，补齐跨 skill 导入及图构建的静态资源依赖，减少变体在打包态缺少辅助模块或资源导致的中断。

### 🐛 修复 (Fixed)

* **视觉验证收敛与 Windows 兼容**：将整轮完成检查、未结问题单和报告生成接入收口；补齐回放降级、页面归属、新鲜截图及空采集结果检查，并修正 Windows 编码、设备工具与临时目录处理。
* **环境体检与打包执行**：修复 `hmos-env-doctor` 将 `--project` 拆成单字符的问题，恢复体检结果落账辅助脚本；修复跨 skill 导入、同名 CLI 与包冲突、仅供导入模块的分发及 CPython 文档字符串兼容问题，补齐共享运行时兼容性预检。
* **发布稳定性**：增加 Git 提交前的构建副本清理与目标仓资源预检；裁剪目标仓禁止的 Linux 宿主载荷，保留 Windows/macOS 工具；修复嵌套 Git 属性导致编译包数据被换行转换的问题，保护运行时原始字节并刷新交付清单；补齐创建 PR 返回 502 时的存在性确认。

### ✅ 校验 (Validated)

* 本次同步的标准流程与 `1to1` Windows x64 / macOS ARM64 standalone 构建及源码与自身编译产物验证均通过；PR 的完整哈希 drift、插件检查、双平台原生包、apktool、升级安装及 native/arch 端到端检查均通过。

## [version v1.7.0] - 2026-09-30

本次同步（ArkTs-Core `930_version_codex`@9d6ff92，PR #87 / #95 等）有三条主线：**迁移策略可选**——新增 Skill Router，`$a2h-init` 末尾可在标准迁移与一比一迁移之间切换；**行为验证成线**——新增 `arkts-behavior-verify`，对照双端实现验证设置与点击的效果链并有界修复；**Codex 侧性能优化**——任务书瘦身、出错只补不重做、门禁卡住不停机，Token 与耗时同时下降。仓库同步拆为 `migbot/`（标准，102 skills / 33 agents）与 `migbot-1to1/`（一比一）两棵工作流树，由 `migbot/router/` 统一装载。

### ✨ 新增 (Added)

* **Skill Router（迁移策略切换）**：CLI 方式迁移时，`$a2h-init` 的最后一步可选择**标准迁移工作流**（默认）或**一比一迁移工作流**——后者以业务与后端逻辑的一比一还原为重点，逐项保持业务规则、数据处理、接口交互与状态流转的一致性（不等于逐行复制，也不自动保证 100% 等价）。策略由 `.migbot/plugin/install.json` 单一持有，切换只经 `python3 .migbot/bin/a2h-router.py` 这一个入口，不手改 `.agents/skills/` 或 `.codex/agents/`。
* **行为验证（`arkts-behavior-verify`）**：以 Android 与 HarmonyOS/ArkTS 两端实现对照为依据，成线验证并修复两类断链——**设置**（保存、读取到业务生效的完整链路，含持久化/临时覆盖优先级、生效时机、默认值与全分支）与**点击**（入口、业务处理到结果反馈的完整链路）。默认一次初始化 + 一轮修复 + 一次集中交付，需要时再续跑 Quick Review 与 Round 2。

### 🔧 优化 (Improved)

* **Codex 侧 Token 消耗**：① 信息提前写进任务书，由脚本先算好、代理不必自己摸索，第一次派出去就做对的比例更高（E243–E261）；② 接口签名只给本任务用得到的部分，每份任务书小 23%（E193），规则片段去重再小 9.8%（E197），`SKILL.md` 拆出运行手册后主会话每次压缩后少读 65%（E202）；③ 每个任务处理的页面从 3 页增加到 4 页，任务数随之下降（E194）。
* **Codex 侧整跑耗时**：① **不停机**——门禁卡住时记欠账继续跑（E207），失败按统一规则自动处理、不停下来等人（E265 / E266）；② **无人值守整跑**——一键起跑、额度用完自动重启（E208），续跑时不重做已完成的部分（E211）；③ **减少来回**——落账后直接接着排下一批，推算少约 200 次请求（E199）；④ 同一工程只允许一个 runner 在跑，避免多个实例互相覆盖（E275）。
* **一比一迁移工作流**：更新 API 调用知识，修复已知 UI bug。

### 🐛 修复 (Fixed)

* **Dialog 恢复正常**：迁移后应用中弹出 Dialog 内的按钮和选项可以正常响应 tap——此前有些 Dialog 能打开，但点击任何内容都没有反应。
* **Page 能显示正确内容**：从列表打开 podcast、episode 等 page 时可以正确接收对应 item，不再出现空白 page。
* **Screen 行为与原应用保持一致**：切换 screen 时 tab bar 和 player bar 会继续显示；以 splash screen 启动的应用也能正确布局。
* **自动修复不再破坏正常 screen**：每次 automatic visual fix 后重新检查应用，修复若引入上述问题，会在 build 前停止。
* **不再遗漏 Dialog**：自动发现原应用中的所有弹出 Dialog，每个 Dialog 必须完成迁移，或者被明确排除。

### ✅ 校验 (Validated)

* `migbot/validate.sh`：`VALIDATE: PASS`（skills checked: 102，agents checked: 33；静态闸已从 `publish.yml` 拆到独立的 `validate.yml`）。

### ⚠️ 升级提示

* **迁移策略要重装才可选**：策略切换依赖插件装进工程后写下的 `.migbot/plugin/install.json`；旧安装（无该记录）会保留原有配置并提示「策略切换需先安装插件到本工程」，不影响既有迁移。切换策略请走 `python3 .migbot/bin/a2h-router.py`（Windows 用 `python .migbot\bin\a2h-router.py`），它是唯一被授权改写 skills / agents 的入口。
* **仓库布局变化**：skills 与 agents 按工作流分到 `migbot/` 与 `migbot-1to1/` 两棵树下，此前位于仓库根的 `skills/` / `agents-codex/` 路径不再有效；README / CHANGELOG 留在仓库根。

## [version v1.6.2] - 2026-09-20

本版主线是「915 性能轮」：砍 plan / execute 的固定开销，把 Stage 3 从一条串行链改成依赖驱动的流水线，给 spec 扇出与门禁补上运力和确定性判定，并让子代理卡死可被发现、可被回收。改动同步自源仓库 ArkTs-Core `version_915_core` 分支（YunjiQ、Tianhao1108，2026-09-07 至 09-16）。

### ✨ 新增 (Added)

* **默认迁移原则 + 审批确认表（a2h-spec / a2h-plan）**：C0 产出定位 / C2 范围 / C5 死码 / C12 原版缺陷 / C16 持久化 与 plan 侧 C6 / C8 无鸿蒙对等残余不再逐条实时拷问，改按 `references/default-policy.md` 裁定、写 ledger `approval_source: default-policy`，并逐条进 Gate C / §8 摘要的确认表，用户 `[1]` 整体确认或 `#N → 改为` 逐行改判。检出登录 / 鉴权链路或外部 API 时 C15 / C17 仍前置询问，auth-chain 探针不变。
* **FV-1 ArkUI 安全检测器（arkts-structural-closure）**：新增只读词元分析器 `verify_arkui_safety.py`，接入 pipeline 模式必需集：@BuilderParam 收到裸方法引用且 builder 体依赖父组件成员（子组件以子 this 调用即崩）、NavDestination 根形状、带槽位组件的无守卫常量下标、源码解析失败 → FAIL 进指纹走 fix-forward；布局类 WARN 不进指纹，随 `review_findings` 由 closer 复核后写 final brief，a2h-verify 读取。cofi v3 产物实测 11 处此前三道门全部漏过的真崩溃点。
* **卡死回收协议（a2h-execute §3a ⑦ / a2h-spec 派发纪律）**：观察点只有回轮与宿主等待工具的有界返回；进展只认新工具结果、写权文件变更、检查证据；连续无进展达阈值即催询一次、再超时请求取消并按空信封规则重派。spec 五处子 agent 派发共用同一段，并补「空回执 = 中断」。
* **spec 扇出运力 + 绝对量深度门禁**：新增 `scripts/plan_batches.py` 产 `spec/.a2h/batch-plan.json`，B2 分页按模块聚类等量切、C4 feature 按 anchored_LOC LPT 配平，派发模板写进 skill；C4.6f 加 `SPEC.PAGE_DEPTH_COLLAPSE` / `SPEC.ADDENDA_COLLAPSE` 项目级塌陷闸。实测第二轮 V2 主线独扛 58 页时 AC 从 545 塌到 134 而全部门禁照常 PASS，本项即为其兜底。
* **Dialog 枚举盲区四道防线（a2h-spec）**：Step A1 明确 DialogFragment 子类为第三类枚举源并统一 `page_NNNN_<Class>` 命名，A2 / A3 逐页分析口径同步；B2.5 对话框维度改道到 ui-manifest 并对 P0 缺失自动补充；新增 `SPEC.DIALOG_FRAGMENT_UNACCOUNTED` 确定性闸与 Gate C 产物闸。实测某项目 20 个业务弹窗整层漏出页面清单而三道审计全绿。
* **功能依赖两列表定真源 + 分组机器闸（a2h-spec / a2h-plan）**：feature-index 功能清单表拆「排序依赖 / 契约依赖」两列（格内只写裸 F-ID 或 base），依赖图降级为只读渲染件，执行顺序整段删除；plan Step 5 分组补三条可校验规则（最早可行组 / 组容量 / size-1 组可并候选为空，例外走 Summary 结构化块），§7 第 12 项按 slice `depends_on` 复算。cofi v3 因执行顺序散文把 9 个 feature 分成 5 组，修后回到 3 组。
* **宿主并发表 + 后台派发参数**：BATCH_MAX / HOST_MAX 按宿主取表（Claude Code 20 / Codex 8 / DevEco Code 10），Stage 1 批数 = ceil(页数 ÷ BATCH_MAX)；派发一律带后台参数，按首次派发的返回形态判同步 / 异步，同步模式改为一条消息一波、波内派满。execute §3a 槽位调度从零写到六条：在飞计数、Base 组优先、批内补位、超限排队、closer 同步点、空信封即中断并降档重派。
* **DevEco 适配器活性监督**：后台 task 无 wait / status / cancel 原语，在飞单位全部失活时主线永不再被唤醒；adapter 侧以 overlay 注入可执行的派发协议，随后按复跑数据收敛为低频 deadman timer（首版有界等待 87/88 次在 1.5 秒内返回、退化成忙轮询；stale 默认 300 秒会把 764–1412 秒才首次落盘的 C4 worker 全判僵尸），并砍掉 attempt 暂存整套。

### 🔧 优化 (Improved)

* **Stage 2 与 Stage 1 重叠推进**：Base 组起跑条件从「Stage 1 完成」改为「Stage 0 PASS」，首道编译门统一到 Base-7；Stage 1 逐批编译门与 checkpoint 删除。cofi v2 实测省下约 80 分钟。
* **Stage 3 依赖驱动流水化**：worker 起跑条件改为「`depends_on` 列出的 slice 全部返回」，`parallel_group` 退为 closer 的收口 checkpoint；closer 组内不再编译（`build_status: deferred-to-stage3-gate`），与在飞 worker 真并行，首道编译门统一到 §5f 由 hmos-builder 一次结清；19 个下游文本同步「收尾不编译」，末组 defer 分支补判据。v2 Stage 3 实测 3h05m 中纯等待占大头（S10 依赖就绪后白等 1h45m），理论关键路径约 62 分钟；按时间戳估算 v2 / v3 Stage 3 分别降到约 2h02m / 1h57m。
* **plan / execute 固定开销瘦身**：删 tier / depth 调度分档与 P0→P1→P2 顺序编排；`GROUP_HARD_LIMIT` 定死 8；删 V1 / V2 字样改按 P0 / P1 / P2；§4 表 3d / 3e 行只留 arkts-state-manager，编译 / 结构 skill 归 closer agent 定义。
* **Stage 3 slice worker 四份 step prompt 合并为一份**：§5a 早已规定每 slice 恒一个 worker，但 3a / 3b / 3c / 3d 各是独立 `Agent()` 模板，主线只能自行拼接；合并后抬头、skill 清单、写盘边界、impl 指针各写一次，信封统一，14.3 KB 减到 10.1 KB。Step 3a–3d 编号作为 registry `resolve_by` 数据值保持不变。
* **记账精简**：group closer 信封 30 行减到 12 行（接线 / 资源 / 占位 / 页面计数只进 brief）；ui-manifest `verified` 唯一写者归 a2h-verify §6.1，execute 全程不置位；registry resolved 只翻状态不删行；brief 删已废弃的 `unresolved_placeholders` 字段。
* **a2h-spec SKILL.md 838 → 685 行**：B2.5 / C4.5 步骤、§5 产出清单、A3 填充规则、C4.6f finding 目录五处纯搬迁到对应 reference，执行语义零变更；常驻加载体量下降。
* **AC 机器契约收口**：模板明写 AC ID 形态（序号纯数字、禁字母后缀）、多源符号写法、`判:` / `真:` 取值与三条事实边界。实测一次 spec 运行 726 次 tool 调用中 132 次是 worker 读检查器源码反推格式，本项让其归零。
* **Step C5b 出口序列**：`build_traceability_index` 与 `lint_divergence --gate` 从 C4.6 挪到 Gate C 批准后、进 plan 前一次性执行，派生物与差异权威判定排在最后一次内容修改之后，requirements-index 的 `assertion_digest` 不再与最终 AC 错位。
* **structural-closure group loop 在 indexed-v1 上自证**：作用域并入 wires 页 / VM 文件与 `--scope-files`；parser 剥行内注释（此前 C3 handler 正则永不匹配）；C1 按类名在引用图定位真实文件记 DIVERGENCE 不计 FAIL（三工程 STALLED 头号原因）；E1 同文件兄弟渲染豁免；六脚本 stdout / stderr 统一 UTF-8（Windows cp936 遇 ✓ 即崩）。

### 🐛 修复 (Fixed)

* **wiring finding 不可执行导致 closer STALLED**：v2 的 G2 收尾卡四轮、升级派 worker 才修完，共付 57 分钟；findings 多数是真缺陷，卡住是因为文本指向幻影类与幻影文件。verifier 判定不放行，只让文本可执行：调用方三级定位、装饰器名不作实例化目标、as-built 候选只进修复动作。
* **spec 解析器三处静默丢数据**：`symbol_roots` 按分隔符切分把 A+B / A, B 全读成空集；`declared_symbols` 不认顶层属性使常量表文件零声明成为结构性不可满足的 blocking（Jetsnack Color.kt 由 0 → 63 个符号）；级联误报随之阻断。
* **addenda 义务与兑现形态判定不一**：SKILL 写「sibling 或主文档同名章节」，但 Tier 5 用子串命中空壳标题也算兑现、项目级只 glob sibling 使内联路线必报缺失。统一为 `inline_addendum_slugs()` 单一实现：标题精确等于 slug 且段内有实质内容。
* **C2 接线判据漏静态门面**：退化分支只认 `new X(` / `getInstance()`，对靠静态访问接线的 target 必然误判（aippt 实测 6 条误报，装机副本曾被运行时就地改过、重装即失）；按仓库规范补 usage_evidence 豁免。
* **后台子代理开启条件写反**：此前认为 `background` 参数需显式设 env 才可见，实证 RuntimeFlags 为 `withDefault(true)`、v2 三次传 `background: true` 全部成功，v2 走同步的真因是 skill 没写要传。adapter banner 与 plan 宿主表同步更正。
* **spec 扇出未写进 skill**：subagent-prompts 只有 3 个派发模板，B2 / C4 对分批只字未提，V1 模型即兴派 worker、V2 一个没派；实测 V2 跑的 3 个子 agent 恰好就是有模板的那 3 个。见「新增」扇出运力项。

### ⚠️ 兼容性：

* feature-index 功能清单表改为「排序依赖 / 契约依赖」两列，执行顺序段删除；a2h-plan 只读排序依赖列，**不兼容旧 spec**，旧工程需重跑 a2h-spec。
* group brief `build_status` 取值改为 `deferred-to-stage3-gate`；`ui_manifest.verified` 由 a2h-verify 独占写入，execute 期页面状态停在 `converted`。
* Stage 3 派发模板文件 `4-step3a-ui` / `5-step3b-vm` / `6-step3c-data` / `7-step3d-wiring` 合并为 `4-slice-worker.md`，deveco / codex 产物需重新生成。
* Codex 宿主 BATCH 区间收窄为 [6, 8]（原 [8, 12]）。

## [version v1.6.1] - 2026-09-16

本次两趟 skills 同步（ArkTs-Core `version_915_codex`@d60f288 → @3f67862，PR #64 / #65）只做一件事：**把 v1.6.0 打包态（Nuitka 二进制）在真实工程里实跑暴露的路径与调用问题修干净**。23 个 skill 的 windows-x64 / macos-arm64 二进制重编，文本改动限于 4 个测试文件、`android-fact-tree/scripts/dispatch.py`、`phase1-prepare.md` 与 skill 级 CHANGELOG；`a2h` 运行时、`agents-codex/`、安装脚本未变。

### 🐛 修复 (Fixed)

* **视觉验证前置探针在 Codex 安装布局下误报（v1.6.0 升级提示里记的已知问题）**：`check_dimension_prereqs.py` 查兄弟 skill 时把 `~/.claude/skills/` 写死在代码里，查 agent 只认 `<agent>.md`，codex-adapter 改得了文档改不了拼法，标准的 `<project>/.agents/skills/` + `.codex/agents/*.toml` 布局恒报 UNIT 缺失 → 整条视觉验证 ABORT。现在 skill 根 / agent 注册 / 模板定位收进 `sibling_exec` 一处：`.claude` 与 `.agents` 两种布局都查、`.md` 与 `.toml` 都认、判「文件在不在」不判「我在哪」；11 个业务脚本改调它。本仓实测：Codex 布局不设 `SKILLS_ROOT` 四项全 ✅，**v1.6.0 的 `SKILLS_ROOT` 绕行不再需要**。
* **打包态兄弟脚本静默不被调用**：8 处 `os.path.isfile(<兄弟>.py)` 守卫在 `_entry.dist/` 里恒 False（那里没有 `.py`），feat 单 §2 永远 UNRESOLVED、截鸿蒙前的 baseline 安全闸消失、Phase 2 出口验收 / 黑盒证据检查跳过、事务复验一律 degraded——源码态跑不出来。守卫统一改 `sibling_exec.sibling_available`（冻结态按 `find_spec` 判编没编进去）。
* **6 个模块级脚本没有 `main()`**：`build_judge_input` / `build_spec_oracle` / `inject_spec_oracle` / `merge_capture_dirs` / `slice_batches` / `trip_end_slice` 逻辑写在模块级，打包态 `_entry <stem>` 取 `.main` 报 AttributeError、退出码 1（round-1 judge 组装实锤）。全部包进 `main(argv=None)`，CLI 参数、stdout、产物路径零改动。
* **`android-fact-tree/scripts/dispatch.py`**（唯一以源码发运的脚本）：`_resolve_skill` 只认 Claude 线目录 → 两种布局都查；调 `check_dimension_prereqs` 的 `[sys.executable, …]` 改借 vv 的 `sibling_cmd`（打包态 `sys.executable` 是不可执行的 libpython）。`arkts-scenario-runner/scenario_run.py` 与 `sibling_exec.py` 副本整文件同步为源侧。

### 🔧 优化 (Improved)

* **树覆盖闸不许模型自行放宽**（`app-relationship-tree` Step 1.0.7）：0915 实跑事故——两次 FAIL 后模型自写 `_phase_markers.coverage_gate_override` 以 0.84 / 0.95 过闸。现在 E1 / E3 分母剔除非 walkable 节点（abstract / external_entry / dead_code 等，另报 `nonwalkable_excluded`），E3 默认 100% → 92%；任一 `--min-*` 低于默认必须由用户在 `spec/tree_hints.json` 写 `coverage_gate_approved`，否则 `GATE: REFUSED`（exit 3）；实际阈值与批准人写进 `tree_coverage.json`。
* **打包契约变成 pytest 静态闸**：业务脚本不得再拼 `.claude` / `.codex` / `.agents` 路径或 `<agent>.md`、不得用 isfile 守 `.py`、不得 `[sys.executable, …]` spawn，`sibling_exec.py` 副本必须与 vv 这份逐字节相同；以后新脚本过这道 pytest 就天然兼容打包态，不用装成插件实跑才发现。

### ✅ 校验 (Validated)

* `arkts-visual-verify/_tests` 638 → 683 例（新增 `test_env_neutral_0916` / `test_sibling_available_0915` / `test_entry_main_wrappers_0915` / `test_plugin_form_0915`）；`app-relationship-tree` 30 → 36；`android-fact-tree` 新增 `test_resolve_skill_0916`（6 布局矩阵）；`arkts-scenario-runner` 新增 `test_ad_dismiss_spawn_0915`。
* 影子根 Nuitka 真二进制：Codex 形状工程（显式根 / 无 env 自动发现）探针全 ✅、打包器 verify PASS=110 FAIL=0；每笔改动经独立子代理（Opus）验收后合入。本仓 `validate.sh` PASS。

### ⚠️ 升级提示

* v1.6.0 升级提示中「前置探针路径」的 `SKILLS_ROOT` 绕行可以撤掉；已设的不影响（显式指定时语义与输出一字不变）。
* 树覆盖闸变严：此前靠低阈值过闸的工程会转为 `GATE: REFUSED`，请把缺口清单与理由写进 `spec/tree_hints.json` 的 `coverage_gate_approved` 后重跑，不要改树里的 `walkability.status`。

> **二进制说明**：本版重编 23 个 skill 的 `scripts/bin/{windows-x64,macos-arm64}/_entry.dist/`（源提交 3f67862）；`bin/a2h-*` 运行时未重编，与 v1.5.2 一致。

## [version v1.6.0] - 2026-09-15

本次 skills 同步（来自 ArkTs-Core `version_915_codex`@1b3088d，经 PR #60 skills-sync/codex-53 合入，CI 修正 4ea40f5）有两条主线。**DT Verify**：`a2h-verify` 验证编排从 11 项收敛为 4 项、结论只覆盖本次实际验证的范围；`arkts-ut-verifier` 引入 Android 行为依据、oracle / 设计 / 生成三段 8 路并发，并封死测试「假绿」与统计失真。**Visual Verify**：让视觉验证「跑得更快、更少熔断、账目更真」——判定从「一趟一个 judge 扛 3.5 小时」改为按负载切包并行，工单跨轮结转 / 判定包合并 / 页账回写三处断点接通，鸿蒙回放与安卓边遍历经 0909→0913 十余趟真机回归逐条修通，源侧 23 个 shell 脚本全部 Python 化并修通打包线（Nuitka 二进制）校验。配套 `agents-codex/` 新增 9 个具名 agent（`arkts-ut-*` 5 个、`arkts-ui-*` 4 个，`.codex/agents` 由 22 → 31），`visual-fixer` / `visual-fixer-reviewer` 与 `app-relationship-tree` / `toolkit-fact-indexer` / `arkts-scenario-runner` 同步更新；`a2h` 运行时二进制与 `install.sh` / `install.ps1` 未变。

### ✨ 新增 (Added)

#### Visual Verify（arkts-visual-verify）

* **判定按负载切包并行（`slice_judge_input.py`）**：判定输入不再绑在采集切段上，而是按「页级产物必读 + 证据抽看 + 归属 escalations」的字节负载装箱，切成 K 个判定包、一包一个 judge 并行；关联组不拆、同屏别名原子、DFS 连续切，`--max-parallel`（默认 8）分波、`--max-packets` 硬上限，不写死页数。实测同一工程 round-0：trip_1 15 页 → 5 包、trip_2 20 页 → 7 包，判定段 33+20.5 分钟 → 约 10 分钟（对照此前单 judge 每趟 3.5 小时）。
* **判定包合并器（`merge_judge_packets.py`，J2.5 ①）**：K 份 `notes_partNN.json` 机械合并为 `batch_notes.json`。包齐闸（缺包 exit 21 不落盘）；list 拼接去重、dict 逐层递归并集、只有叶子标量冲突才记 `_merge.conflicts[]`（保 owner 包）；确定性。替代此前主会话手写合并（真实数据上当场崩过）。
* **工单跨轮结转脚本（`carry_forward.py`）**：文件名 = 工单 id 跨轮恒定，结转信息落 `carried_from_round` / `carried_rounds`；fixed / skipped / manual_review / problematic 不结转，其余原样带走不重置；幂等。根治此前 shell 片段结转的五处同根缺陷（改名破坏「文件名 = id」、pending 占位被清空、占位不被认、二次结转被自己前缀过滤、delta 按 id 差集虚高）。真实三轮数据：自检 FAIL 67 → 0、占位认出 0 → 4、丢过的 7 张单找回。
* **回放模式下游接线**：`build_batches.py` 新增 `android_edgewalk_partition`（无 chunk manifest 时按 `_trip_assignment.json` + 安卓基线 png 全集分批）；`mark_batch_done.py` 真写 `progress.pages` 页账；规范新增 J2.5 步骤。治干跑实爆的三处断点（Phase 3.5 从树重推 45/49 页、Phase 5/6 读不到回放 manifest 聚类为 0、`assert_run_success` 62 页假红）。
* **鸿蒙回放：计划外门放行 + 哨兵静态键**：目标未到 ∧ 认不出任何计划页 ∧ 不在登录门页 → 机械尝试一次门控件（首启隐私门只点「同意并继续」）；哨兵选词优先树里的静态文案并补「必要条件」，治「大纲页被认成 PPT 页」类误判。
* **鸿蒙回放：翻译对等性 + 门放行移植**：`--android-edges` 救回安卓已确认的边（安卓验证过的边鸿蒙一条不许静默放过，安卓被门拦住的边鸿蒙要去验门还在不在）；索引按 `(from, to[, trigger])` 分级避免取到兄弟边；`gate_pass` 从安卓侧移植到鸿蒙执行器，UI 词表单一真源。
* **安卓边遍历：熔断包自带诊断与决策菜单（`escalate`）**：熔断时给出有序 `options[]`（第一项为执行器推荐，每项带可执行 `cmd` / 适用条件 / 后果 / 覆盖损失），能机械收的不再熔断；哨兵消费 LLM 的 `verify_signal`、首启门边进 walk_0、尾部回栈剪枝、输入守卫出 `type` 步、分派表新鲜度闸。
* **判读债链路与跨趟隔离**：`walk_ledger.binding_debt` 三态为唯一定义（闸 / 驱动 / 收尾账共用）；`walk_finalize` 新增 §2.6 真拦；新动作 `settle_binding_debt`；BLOCKED 单默认 `binding_pending`；债池读不出来也判红。
* **树侧反哺与体检**：`tree_feedback.py` 只报不删（重复节点交树侧根治，`app-relationship-tree` Phase 1.7 折叠调用点节点）；边体检与契约闸（`guard_flags`）；auto 转场边编成 `wait` 步而非跳过。
* **调试截图三层治理**：`adhoc_capture` 通道 + fixer 看 / 判分离 + 收口自动归档；设备截图落点纪律与收口卫生检查（`check_scratch_pollution.py`），治客户实报的工程根目录截图污染。

### 🔧 优化 (Improved)

#### DT Verify（a2h-verify / arkts-ut-verifier）

* **a2h-verify 验证编排精简**：原 11 项检查收敛为 4 项——静态分析（CHECK-1）与 App 身份校验（CHECK-2）固定执行，视觉对齐（CHECK-3）、单元测试（CHECK-4）由用户按需选择；构建、安装及内部修复交由对应 verifier 完成。统一报告明确区分 PASS / FAIL / PARTIAL / DEFERRED / SKIP，结论仅覆盖本次选择和实际验证的范围，保留迁移完成信号与阶段用量上报。
* **arkts-ut-verifier 引入 Android 行为依据**：新增可选的 Android oracle 采集，提取可溯源的行为、分支与预期值；Spec 限定验证范围，Android 源码及已批准的平台差异决定功能行为与测试预期。补充未实现功能诊断和逐用例生成记录，缺入口、缺证据的条目显式列出。
* **测试生成与修复流程提效**：oracle、设计、生成各支持最多 8 路并发，单个 Feature 设计完成即可进入生成队列；增加公共设施预检、首批编译试跑和分批编译检查点。修复按文件所有权并行，覆盖生产实现、必要业务接线及测试更新，经独立质量复核、完整构建和设备复测后确认结果。

#### Visual Verify（arkts-visual-verify）

* **源侧 23 个 `.sh` 全部退役为同名 `.py`，与 Codex 产物合流**：行为等价，116 例 parity 全过后冻成 golden 接班；三平台同一套脚本，Windows 原生无需 bash / awk / grep / sed / jq / yq / sips。此前只在 Codex 产物里单独移植的 `render_report.py` / `assert_round_complete.py` / `check_reviewer_report.py` / `assert_gap_ticket_coverage.py` / `resolve_hmos_impl.py` / `smoke_one_page.py` / `device_triage.py` 回流为源侧正式工具并在 `cli-cheatsheet.md` 登记调用点，Codex 版不再与源侧分叉；文档里 153 行 shell 一行式改为 python 一行式或跨平台写法，`TRIP_ID=x bash …` 改为 `--trip` 参数。顺带消灭 `.sh` 里 7 处真 bug（4 处变量紧贴全角标点让闸「形同虚设」或静默吞退出码；2 处 `sort -u` 缺 `LC_ALL=C` 在中文页名上分母塌缩、覆盖率虚高；1 处债数拼接错）。
* **鸿蒙回放判位改「路径先验 + 同平台参考」**：`PAGE_REF` / `texts_pos` / `on_page_by_ref`，跨 resume 恢复 `PAGE_REF_RESTORED`；模糊匹配落错页不再判路由错；back 已在目标页不按（栈顶判据）。严格 A/B 验收通过，t2a 起 11/11 恢复生效。
* **回放 A/B 档 7 项**：rid-only 身份兜底按安卓屏上文案定位（`no_screen_identity` 归因）、数值形文案不当哨兵、探测步 kind 按目标类型推、续跑重建 DFS 栈、dumpsys 叠层弹窗识别（`overlay_dialogs`）进采集硬闸。全部零应用常量，每条先在 101 份真实 dump 上离线回放再落。
* **按趟真值**：安卓真值按趟隔离（别趟确认不救回、`confirmed_other_trip`）；`android_edge_lookup_how` 区分 label / pair / none 命中 + `label_gate`；遭遇账聚合；排除表子串匹配。
* **安卓瞬态页采集根治**：到达判定尺子从「uiautomator 等 idle」换成 `dumpsys activity top`（0.05 秒一次、不看动画），治「交付基线是首页图却账本 verified」；弹窗叠层采集并入。
* **关单口径统一**：四处「sbs similarity ≥ 0.95」统一为「页级 similarity ≥ 0.95 且无 CRASH → 页关闭、页内单随页关闭」；rubric 只豁免顶部状态栏与底部系统导航条，`overall_similarity` 必须由 `differences[]` 按 high 0.05 / medium 0.02 / low 0.01 扣分算出（清单空 = 1.0）。
* **工单账本**：fixed 单不再改名（`RESOLVED_` 前缀取消，改写三字段），`is_closed_ticket()` 按 disposition 判闭；`render_round_summary` 的 delta 改按 disposition 迁移并新增 `still_open`；BLOCKED 占位原名结转、不计 open、到达后出正常单并删占位；`render_finding_skeleton` 拒绝同轮同 id 重复出单。
* **`run_fix_self_check` 并入第 10 项**（原 Codex 侧 `check_fix_schema` 三条硬约束：`nav_failed` 必须 `android_verified` / BLOCKED 的 `blocked_by` 必须指向存在文件 / `FACT_TREE_INVALID_EDGE` 归属 `app-relationship-tree`），补 9 例正向测试并做突变自证。
* **golden / parity 路径无关化**：占位符 `<SKILLS>` / `<REAL_PROJECT>`，新闸「golden 里不许出现绝对路径」；真实工程用例恒在矩阵、夹具缺席显式 skip 并打出环境变量名，治「换台机器少跑 8 例、报告照写全绿」。

### 🐛 修复 (Fixed)

#### DT Verify（arkts-ut-verifier）

* **防止测试「假绿」与统计失真**：禁止弱化断言、删除用例或扩大 mock 来凑通过；按真实 Hypium 日志逐用例解析，分别报告原始通过率、设计验证比例和 AC 完成比例，未生成、忽略及未执行项保留在未验证范围中。
* **修正收敛与通过判定**：可处理问题清空但仍有真实验证缺口时标为 CONVERGED，仅全范围实际验证通过才判 PASS；修复新增入口后同步补测并更新旧分类，避免沿用 `no_entry` 等状态漏验。
* **隔离验证产物与状态**：UT 设计、报告、诊断和修复轮次统一归入 `spec/verify/ut/`，避免与 UI、视觉验证共享目录和状态造成干扰。

#### Visual Verify（arkts-visual-verify）

* **打包线（Nuitka 二进制）校验 24 例失败**：调度壳按 `main()` 必填参数个数分派，移植脚本写成 `main(argv)` 接列表 → 打包态收到单个字符串被逐字符迭代；兄弟脚本用 `sys.executable` spawn 在打包态指向不可执行的 libpython（Errno 13）；`arkts-ut-verifier/android_source.py` 的错误收口写在 `__main__` 里被调度壳绕过。修法：28 个脚本 `main(argv=None)` 缺省自读参数；兄弟 spawn 全部改 `sibling_exec.sibling_cmd`（开发态直跑 `.py`，冻结态自调 `_entry` 二进制）；`python_exe()` 冻结态判据改用 Nuitka `__compiled__` 标记；`run_scenario_with_verify` 的 skills 根改走 `ARKTS_SKILL_DIR`。同一打包线：visual-verify PASS=87 FAIL=23 → **PASS=110 FAIL=0**，ut-verifier PASS=5 FAIL=0。
* **鸿蒙回放假单归因四轮修复**（t1d → t1i 六趟真机验证）：`not_found + control_missing` 假账 17 → 0、rendered 3 → 14；wait 步开始前先判位，已站在别页立即 `AUTO_LANDED_ELSEWHERE` 不空等；熔断前把游标推到下一步、位置 = 本步落点。
* **安卓边遍历第三、四轮通用修复**（0910 真机 41 次熔断归因 10 条工具缺陷）：宿主上子 activity 的 `back_then_resume` / `renav_then_resume` 回位；node_sweep 链模式合并写回 `run_meta`、chain-mode 不再第二份破坏性词表；链趟 `walk_6_chain_sweep` 按 walk_0 步序重走首启链补欠账页。
* **路径反哺与账本收口**：dialogs 漏遍历、失败静默吞、运行时 rid 不许回填三处断点；命中链探针 + 三闸接线 + 整轮账本路径收口；顽固单判据扩域、跨轮次、阻断升级。
* **fixer**：行为类缺陷必须读到「行为承载体」的安卓源；回补丢失的安卓真值表 + 登录经验入册；工单加「必用参考」段（诊断命令直接摆进单里）。

### ✅ 校验 (Validated)

* `arkts-visual-verify/scripts/_tests`：490 → 638 例（设 `VV_PARITY_REAL_PROJECT` 时；不设 630 passed / 8 skipped），跑时 38.9 秒 → 24.4 秒；`app-relationship-tree` 30、`toolkit-fact-indexer` 23 不变。
* 真机 / 真实产物验收：t1f→t1i、t2a→t2c 共九趟鸿蒙回放严格 A/B；0913 全流程干跑 5h18m；0913–14 三轮修复闭环 open 73 → 31 → 14 作为归因与回归数据源；每笔改动由独立子代理验收后合入。
* 本仓 `validate.sh`：`VALIDATE: PASS`（skills checked: 99，agents checked: 31）；上游 publish-skills CI（windows-x64 + macos-arm64 build + verify / publish）在 `version_915_codex` 1b3088d 全绿。

### ⚠️ 升级提示

* **新增 agent 需重装**：`arkts-ut-*`（5）/ `arkts-ui-*`（4）九个具名 agent 随本版进入 `agents-codex/`，已有工程请重跑 `install.sh` / `install.ps1` 把它们装进 `.codex/agents/`（幂等）；`arkts-ut-verifier` 派发时角色缺失会明确报配置缺口而不是静默降级。
* **a2h-verify 交互变化**：进入验证前会先问「本次要执行哪些设备验证」（CHECK-3 视觉对齐 / CHECK-4 单元测试，可多选或都不选）；未选项记 SKIP、不参与结论计算，结论只对本次选择的范围负责。
* **UT 产物落点**：`arkts-ut-verifier` 的设计 / 报告 / 诊断 / 修复轮次改落 `spec/verify/ut/`，不再与 UI、视觉验证共用目录；旧工程续跑请以新路径为准。
* **脚本调用方式**：Codex 版本就以 `python3 …/x.py` 调用，本版不需要改；文档里 `TRIP_ID=<trip> bash run_scenario_with_verify.sh` 写法统一为 `python3 run_scenario_with_verify.py … --trip <trip>`（PowerShell 无 env 前缀语法）。`scripts/*.py` 是自动生成的 launcher，实际执行 `scripts/bin/<平台>/_entry.dist/` 下的二进制。
* **工单文件名规则**：fixed 单不再改名为 `RESOLVED_*`，闭合状态以 frontmatter `disposition` 为准；跨轮结转不再生成 `CARRYOVER_*` 文件，同一 id 跨轮恒定。旧前缀仍兼容读取。
* **关单判据**：页级 similarity ≥ 0.95（rubric 只豁免系统栏）且无 CRASH 才关页，页内单随页关闭；此前四处口径不一的 0.95 已统一。
* **前置探针路径（已知问题）**：视觉验证 1.1.f 三级探针 `check_dimension_prereqs.py` 查 agent 时已按 `~/.codex/agents/` / `<project>/.codex/agents/` 找，但查兄弟 skill（`arkts-scenario-runner` 的 `scenario_run.py`、`hmos-fix-build-errors`）时未设 `SKILLS_ROOT` 就退回 `~/.claude/skills/`——`install.sh` 装到 `<project>/.agents/skills/` 的标准布局会被误报 ❌ UNIT 缺失（2026-09-15 本仓实测复现，提示语也仍写 `.claude/skills`，已记为待修）。绕行：跑视觉验证前按 SKILL.md「路径约定」先设 `SKILLS_ROOT` 指向 `.agents/skills/`，探针即正常 ✅。

### 📝 文档 (Docs)

* `arkts-visual-verify/references/` 新增 `windows-setup.md`（源侧全 py 化后的 Windows 说明）、`layout-troubleshooting.md`、`wiring-gap-detection.md`；`phase4-replay-judge.md` 新增 J1.8 ②③ / J2.5、`phase2-edge-walk.md` §4.ab、`phase4-replay-run.md` §2；`fix-file-schema.md` §五 / §4.3-4 / §十 口径更新；`cli-cheatsheet.md` 工具箱表补齐回流脚本调用点。
* `a2h-verify/references/` 随编排精简重写：新增 `static-and-identity.md`（CHECK-1/2 规则）与 `device-verification.md`（CHECK-3/4 模式、产物、状态映射），退役 `checks-1-to-5.md` / `check6-to-7.md` / `execution-discipline.md` / `orchestration.md` 及整个 `_dormant/`。
* `arkts-ut-verifier/references/` 新增 `android-oracle-protocol.md` / `android-oracle-template.md`（Android oracle 采集）、`execution-checkpoints.md`（预检 / 试跑 / 分批编译检查点）、`fixer-dispatch.md` / `fixer-test-policy.md` / `fixer-wiring-policy.md`（修复分派与接线边界）、`mock-policy.md` / `import-mock.md`、`result-statistics.md`（三口径通过率）、`unimplemented-schema.md`；原 `agent-prompts/` 四份内联提示词退役，改由 `arkts-ut-*` 具名 agent 承接。
* 视觉验证变更细账以 `skills/arkts-visual-verify/CHANGELOG.md`（skill 根）为准，本文件为面向插件用户的摘要。

## [version v1.5.1] - 2026-08-30

统一版本线 1.5.1：配套运行时 migbot-runtime-src v1.4.7、服务端 migbot-server v1.2.32。本版把**同意改为安装级**（一台机器同意一次，新工程自动继承），`migbot_session_id` 改为每工程一个，用户数按 `install_id` 去重。

- **Install-level consent (agree once per machine)** (with migbot-runtime-src ≥ v1.4.7, migbot-server ≥ v1.2.32): `a2h init-run` mints/reuses this machine's `install_id` (`~/.migbot/install.json`) and inherits the machine's consent decision into new projects; `a2h-init` §2.1 and `a2h-privacy` §B run `init-run` before showing the agreement, so a project that inherits `granted` no longer prompts. `migbot_session_id` is now **per project** (one dashboard row = one project); users are de-duplicated by `install_id`. `/a2h-privacy status` also shows `install_id` — one deletion request clears every project on the machine.
- Runtime binaries synced to migbot-runtime-src **v1.4.7**.

## [version v1.5.0] - 2026-08-27

版本线统一：hmigbot / hmigbot-CodeX / hmigbot-set-cc / hmigbot-set-codex 自本版起同号发布（1.5.0），配套运行时 migbot-runtime-src v1.4.3。功能内容承接 v1.4.1（见下），另含 publish 版本门禁（tag 必须等于 plugin.json version）。

## [version v1.4.1] - 2026-08-27

本次迭代主线是「打点能力双产品线一致」：a2h 调用统一为合并版运行时命令集（与 hmigbot-CodeX 逐字一致），a2h-init / a2h-privacy 成为两条线的唯一源，同意流程幂等化。配套运行时 migbot-runtime-src v1.4.1+（已删除 legacy 翻译层）。

### 🔧 变更 (Changed)

- **commands/a2h-init*.md 与 a2h-privacy*.md 成为两条产品线的唯一源**：hmigbot-CodeX 的同名 skill 由其 `scripts/sync-commands.py` 从这里机械生成，宿主差异（`/`↔`$`、bootstrap/agreement 路径、OTel 清理、hook-trust）全在脚本里。回灌了 CodeX 侧的两处改进：`a2h-privacy status` 可选回显 outbox 状态；`a2h-privacy off` 改为 `init-run --consent denied` 记录（不再写 `"off"` 状态），并提示 `A2H_TELEMETRY_OFF=1` 一次性开关。措辞中性化（"禁用插件"→"禁用 migbot"）。
- **a2h 调用词表统一为合并版运行时的命令集**，与 hmigbot-CodeX 完全一致；`usage-hook` / `metrics *` / `stats *` 旧形态不再兼容（运行时已删除翻译层，旧形态返回 64）。**需配套运行时 ≥ 删除 legacy 层的那次发版**。
  - `metrics init-run` → `init-run`；`metrics report-stage <id>` → `mark-stage <id>`；`metrics count-lines|status|flush` → 去掉 `metrics`
  - `metrics upload-baseline` → `count-lines`；`metrics finalize` / `metrics report-verify` → `count-lines`（HarmonyOS total 即完成信号）
  - `metrics register-consent` + `metrics gen-consent-id` → `uuidgen | tr 'A-Z' 'a-z'` 生成句柄 + `init-run --consent granted --migbot-session-id <句柄>`（服务端登记在首次 flush 自动完成）
  - `metrics verify-consent` / `verify-access` / `stats count-loc` → 同名一等子命令 `verify-consent` / `verify-access` / `count-loc`
  - `metrics finalize-increment <x>` → `mark-stage migbot-increment-<x>`
  - hooks 启动器 `bin/a2h-usage-hook` 改为 exec `hook` 子命令（文件名不变）
- a2h-retrospect §10 收尾改为 `count-lines` + `mark-stage a2h-retrospect` 两条命令（与 CodeX 版一致）；`upload-retrospect` / `upload-sessions` 通道已由生命周期 hook 的会话切片上传取代。
- claude-session-stats 收缩为只提供 `count-loc`；`parse-session` / `find-jsonl` 移除（token 真值由服务端从会话切片推导）。
- CI `publish.yml` 的打点存在性断言改为新词表，并新增「旧形态不得回流」检查。

## [version v1.4.0] - 2026-08-15

本次迭代的主线是「让计划变轻、让执行可追责」：plan 产物从 127KB 单体文件重构为「索引 + 逐切片账本」的分层形态并由多个 subagent 并行生成；execute 的收尾链路统一到单一收尾者与脚本化回写，崩溃后秒级恢复；spec 侧引入证据驱动的覆盖门禁与 AC 级追溯，让「被静默漏掉的需求」在每个阶段都会被机械点名。全部改动均由 aippt / jetsnack 多轮端到端验证驱动。

改动同步自源仓库 ArkTs-Core：[#77 a2h-plan/execute 分层优化]、[#79 Spec 证据驱动覆盖门禁]，及 version_815_planFix 分支的后续调度修正。

### ✨ 新增 (Added)

* **证据驱动覆盖门禁（a2h-spec）**：从 Android 源码机械检出行为信号与具名实例（埋点事件、桥方法、枚举、阈值等），逐实例记账——每一条要么被 AC 认领、要么显式跳过并披露，漏账即阻断。取代旧的「AC 数量预算」，数量不再参与判定。
* **AC 级跨阶段追溯**：spec → plan → execute → verify 每阶段一份账本、一个 linter，漏认领 / 绑旧断言 / 双实现自动检出并定责到具体阶段；同一问题多轮不收敛自动熔断，转为决策卡交用户裁决。
* **plan 三写并行编排**：ui-plan、base-plan、全部切片账本由三个 subagent 并行生成，主线程只负责全局裁决（拓扑、归属、分组）与收拢审批。
* **统一收尾者 + 回写脚本**：execute 各阶段收尾统一为一个四模式 agent；状态账本与 brief 的落盘交给幂等脚本执行——收尾崩溃后重跑脚本即恢复，不再重做接线与编译。

### 🔧 优化 (Improved)

* **计划体量与读取开销大幅下降**：plan 产物 127KB → 约 33KB（-74%），执行期 plan 相关上下文读取约 -95%；subagent 返回一律压缩为 30 行内信封。
* **编译链路精简**：删除 Stage 1 逐批编译门（页面互不依赖，统一在阶段末一次容忍性编译收口）；全程增量构建 + 环境预热；发布门强制真实构建防「空转假通过」。
* **调度规则收敛**：UI 分批改为纯优先级分组；单任务的组/批一律消除（并组、附挂或并批）；组容量改为直接按切片数计数，不再加权。
* **spec 生成提速**：最长的 api-inventory 子任务前置隐藏约 15–18 分钟；切片生成即自检，覆盖修复不再拖串行尾巴；DataBinding 与自定义资源目录的布局解析一次通过。

### 🐛 修复 (Fixed)

* **切片被按步骤拆成多个 subagent**：废除单元化波次派发（实测有害无益），改为每切片恒一个 worker，确实过大时按依赖断面拆分。
* **444 条「需求未认领」**：根因是记账缺口而非实现缺口——实现认领现由收尾者从计划账本自动抄录、随回写脚本落盘。
* **结构验证产物写错目录**：Windows 下手动驱动脚本时误写 docs/，现脚本层硬拒旧路径并指引正确落点。
* **旧术语泄漏**：生成产物中残留的 handoff 旧称全量清理为 brief。

### ⚠️ 兼容性：

* 旧版单体 feature-plan 会被明确报错并提示重新生成计划（执行进度存于状态账本，重排零损失）；旧产物中的已废弃字段可被解析器容忍，无需迁移。

## [version v1.3.1] - 2026-07-30

本次以**登录能力落地**与**多项 skill 自优化**为主线：新增登录功能，并对 skill 自优化、visual verify、spec 分层分级三条能力线做了一轮打磨。

### ✨ 新增 (Added)

- **登录功能实现**：接入登录能力，迁移插件包在使用前具备账号登录入口。

### 🔧 优化 (Improved)

- **Skill 自优化**：对 skill 自优化闭环做一轮打磨，提升迭代优化的稳定性与效果。
- **Visual verify 优化**：优化视觉校验（visual verify）流程，提升 UI 验证的准确性与可用性。
- **Spec 分层分级优化**：优化 spec 的分层、分级机制，改善规格内容的组织与消费。

## [version v1.2.2] - 2026-07-17

本次以**下线 v1.2.1 落地的多模块架构迁移能力**为主线（迁移回到单 entry pageMap 模型），同步源仓库 ArkTs-Core 的 version_717 迭代，并再次回归随插件分发所需的打点与护栏。

> 源仓库的 [#63 version_717_selfopt](https://github.com/fuxi-ailabs/ArkTs-Core/pull/63) 系将 migbot 的 multi-class extension 与 AG 反馈优化**反向同步回上游**，migbot 自 v1.2.0 起已包含，故本次无净变化。

### 🔧 优化 (Improved)

- **`arkts-structural-closure` 结构闭合脚本修复**：随重新编译的运行时二进制引入源仓库 [#64 version_717_scriptfix](https://github.com/fuxi-ailabs/ArkTs-Core/pull/64) 对 `structural_loop.py` / `audit_skeletons.py` / `verify_closure_ledger.py` / `verify_slice_wiring.py` 的修复。

### ⏪ 回滚 (Reverted)

- **多模块架构迁移能力下线**：移除 v1.2.1 落地的 `mig-arch`（架构分析）与 `a2h-arch-scaffold`（三层骨架生成）两个 skill，以及其在流水线中的全部接线——`a2h-spec` 的架构并行轨（Step A0 启动 / A-join 收口 / B2.6 跨模块 seam 闭合门）、`a2h-execute` 的 `arch_multimodule` 二分与各模块 `route_map.json` 建页即注册、`arkts-structural-closure` 的 `unregistered-route` / `entry-infra-race` 静态门。迁移回到**单 entry + 入口页 `pageMap` 路由**模型；相关孤儿 references 一并清理。

### 🐛 修复 (Fixed)

- **流水线打点回归**：恢复 5 个 pipeline skill 的用量上报与授权门控——`a2h-spec` 的 `verify-access` / `verify-consent` 门控与 `report-stage`、`a2h-plan` / `a2h-execute` 的 `report-stage`、`a2h-verify` 的 `report-verify`（迁移完成信号）+ `report-stage`、`a2h-retrospect` 的 §10 三步（`report-stage` 写 `retrospect.done` / `upload-retrospect` / `upload-sessions`）。
- **构建修复循环护栏回归**：恢复 `a2h-execute` 的「构建修复循环操作纪律」与 `hmos_fix_build_errors` 的「Build-Fix Loop: Environmental Safeguards」（缓存清洁度、SDK 路径污染守卫、hvigor daemon 僵死恢复、checkpoint 提交）。
- **`arkts-component-builder` 护栏回归**：补回「Linter 共存规则」（两次即停原则、`CustomComponent` 命名冲突不可妥协、生成检查清单追加项）与「共享组件资格判定」（三项判定）。这两段与上述构建护栏同属 `169874c`，v1.2.1 声明恢复但实际遗漏，本次一并补齐。
- **skill frontmatter 引号**：`android-api-inventory` / `arkts-codebase-config` 的 `description` 含 `: ` 序列，未加引号时 YAML 解析失败、skill 元数据为空而永不触发。再次修复（描述文本不变）。

> **同步须知**：上述打点、构建护栏与 frontmatter 引号均为 migbot 仓独有、上游 ArkTs-Core 不存在，因此每次整版同步 skill 都会被覆盖（本次为第三次回归）。整版替换 `skills/` 后请按 `docs/skills-telemetry-instrumentation.md` §5 checklist 重新应用；CI 的 telemetry 断言只覆盖 8 处上报调用，护栏与引号不在其中，需人工核对。

## [version v1.2.1] - 2026-07-15

在 v1.2.0 基础上**落地多模块架构迁移能力的 skill 实体**，并回归随插件分发所需的流水线打点与执行护栏。

### ✨ 新增 (Added)

- **多模块架构 skill 落地**：新增 `mig-arch`（架构分析）与 `a2h-arch-scaffold`（`product / features / commons` 三层骨架生成）两个 skill，交付 v1.2.0 CHANGELOG 所描述的多模块迁移能力。

### 🐛 修复 (Fixed)

- **流水线打点与护栏回归**：恢复 5 个 pipeline skill 的用量上报（`report-stage` / `report-verify` / `upload-*`）与授权门控，以及 `a2h-execute` / `hmos_fix_build_errors` 的构建修复循环护栏；修正 `a2h-arch-scaffold` frontmatter 引号（否则该 skill 不触发）。

## [version v1.2.0] - 2026-07-14

本次迭代的主线是**让迁移产物从「单 entry 大杂烩」变成「符合鸿蒙工程规范的多模块架构」**：迁移不再把所有代码堆进一个 entry，而是先从 Android 源码逆向出目标模块蓝图，再据此生成 `product → features → commons` 三层骨架，并让 spec / plan / execute 全程按模块归属落盘。同时基于 AG 问题反馈对 11 个 skill 做了一轮聚类优化。

改动同步自源仓库 ArkTs-Core：[#59 Version 715 Feature_mig_arch](https://github.com/fuxi-ailabs/ArkTs-Core/pull/59)、[#60 python api diff on windows platform](https://github.com/fuxi-ailabs/ArkTs-Core/pull/60)、[#61 多类型 Skill 自优化拓展 & 基于 AG 反馈问题的自优化](https://github.com/fuxi-ailabs/ArkTs-Core/pull/61)。

### ✨ 新增 (Added)

- **架构分析 `mig-arch`**：迁移前先分析 Android 源码，逆向推导出鸿蒙侧的目标模块候选结构——产出模块清单（源路径 → 目标路径、模块类型、依赖 DAG）与逐模块说明（职责、内部结构、源类映射、事件总线、迁移关注点）。分析结果**只作为候选，不替代源码事实**，供后续 spec / plan / execute 消费。
- **多模块骨架生成 `a2h-arch-scaffold`**：依据架构蓝图幂等生成 `product`（单手机产品时即 entry）→ `features` → `commons` 三层物理骨架，并严格按依赖方向组织模块关系；同时写出模块地图供后续 agent 读取。采用**只增不毁**策略，只创建结构、不删除既有文件。
- **`a2h-spec` 接入架构分析**：Phase A 以子 agent **并行**启动架构分析并在末尾收口，成功即进入多模块模式。新增 **B2.6 门禁**校验目标模块 DAG 能否承载分页 spec 中的组件、弹窗、共享 ViewModel 与共享组件等跨模块依赖——发现非法模块边按降级规则回填，无法解析则阻断 Gate B，避免错误结构流入 plan / execute。
- **`a2h-plan` / `a2h-execute` 多模块路径规则**：plan 需记录每个 task / 文件应落到哪个目标模块，execute 按模块归属落盘，不再默认全部写进单 entry。
- **`migbot-increment-workflow` 增量开发工具**：增量开发工具通过将自然语言需求转换成需求SPEC和执行计划，最终实现对鸿蒙APP源码的增量开发，执行流程为 PLANNING → IMPLEMENTING → APPLYING。

### 🔧 优化 (Improved)

- **多类型 skill 能力拓展**：扩展并优化 `arkts-animation-builder`、`arkts-knowledge-verifier`、`arkts-system-capabilities`、`android2hmos_resources_convert` 四个 skill，覆盖手势 / 转场动画、API 修正、后台任务、相册访问（photo-access）与分享面板（share-panel）等场景。
- **基于 AG 反馈的聚类优化**：针对线上问题反馈的 Top 9 聚类，优化 11 个 skill（`android-api-inventory`、`android-ui-graph-query`、`android-view-to-arkui`、`arkts-animation-migrate`、`arkts-component-builder`、`arkts-data-layer`、`arkts-navigation-builder`、`arkts-pattern-library`、`arkts-structural-closure`、`arkts-system-capabilities`、`arkts-ui-alignment`），集中修复 UX、布局、动效、API 幻觉与知识缺失等多类缺陷。
- **架构能力全程向后兼容**：架构分析失败或工程本就是单 entry 时，自动退回原有单 entry 流程，不阻断迁移；架构分析在 Phase A 并行执行，实测 token 消耗与端到端耗时均无明显增加。

### 🐛 修复 (Fixed)

- **跨 HAR 页面白屏**：`a2h-execute` 新增入口 pageMap 形状校验——`@Builder` 必须是单条 `if / else if` 链，多个平级 `if` 会导致 ArkUI builder 注册失败，进而使跨 HAR 的页面全部白屏且无任何报错日志。此类问题此前只能在运行时才暴露，现已在生成阶段拦截。
- **多模块 barrel import 被误判为外部 HAR**：`arkts-structural-closure` 此前会把 `import { Xxx } from 'uibase'` 这类本地模块引用当成外部 HAR，导致结构闭合阶段看不到本地多模块依赖、产生 orphan ViewModel 等误报。现改为读取 `build-profile.json5` 的模块 `name → srcPath` 映射解析到对应模块入口；真外部 HAR 与单模块工程行为保持不变。
- **多模块间页面路由漏识别**：`arkts-navigation-builder` 增加对跨模块页面路由的识别与验证。
- **Windows 平台脚本调用报错**：文件保存改用跨平台一致的重命名 API（`os.rename` → `os.replace`），修复该 API 在 Windows 上不可用、导致打包为二进制后调用即报错的问题。
- **移除 `/a2h-run` 的 `mode` 死代码**：`mode` 字段从未被实际写入 `config.json`，`plugin`/`base` 分支逻辑无实际作用，skill 路径检查也已不再需要，全部移除。同时将"单独跑某个阶段"的指引从仅提 `a2h-spec` 扩展为列出全部五个 pipeline skill。

## [version v1.1.2] - 2026-07-10

维护性迭代，主题是**把此前静默失效的东西修好**：两个 skill 因 frontmatter 非法而从未触发，发布链路则一直把内部信息带进公开产物。同时 `/a2h-run` 具备了无人值守执行能力。

### 🔧 优化 (Improved)

- **`/a2h-run` 插件模式与无人值守执行**：新增 `mode: plugin`，以插件方式安装时跳过本地 skill 路径检查（skills 经 `--plugin-dir` 提供）；同时支持从**首个未完成阶段自动续跑**、阶段间**自动推进**，不再逐阶段等待交互确认。长流程迁移中断后重跑即可继续，无需值守。

### 🐛 修复 (Fixed)

- **`android-api-inventory` 与 `arkts-codebase-config` 恢复可触发**：两者的 frontmatter `description` 未加引号，而正文含 `platform: android`、`V1: AppStorage` 等 `: ` 序列，导致 YAML 解析失败、skill 以空元数据加载——名称与描述被静默丢弃，**这两个 skill 此前对用户从不触发**。现已加引号修正（描述正文一字未改）。

## [version v1.1.1] - 2026-07-02

> 补记：本条目在发布当时被遗漏，现按 v1.1.0..v1.1.1 的实际改动回溯补写。该版本以 PATCH 号发布，但实际包含 hook 事件面的新增能力，按 SemVer 应为 MINOR。

以**原始会话打点（raw-session telemetry）**为主线：把打点从少数几个时机扩展到 Claude Code 的完整 hook 事件面，并让一次迁移运行的身份在全流程中保持一致、可追溯。

### ✨ 新增 (Added)

- **七类 hook 事件全量接入**：`a2h-usage-hook` 接入 Claude Code 全部七种 hook 事件，打点覆盖从「阶段起止」扩展到会话内的完整交互面，为后续按真实使用路径做性能与质量归因提供原始数据。

### 🔧 优化 (Improved)

- **运行身份在 init 时固定**：迁移运行的标识在 `/a2h-init` 阶段即锚定，贯穿后续所有阶段，避免同一次迁移在不同阶段被记为不同运行；管道结束后额外呈现 outbox 状态，便于确认数据是否已送出。

## [version v1.1.0] - 2026-06-30

本次迭代以「评测驱动自优化」为主线，围绕 **可编译率、幻觉治理、spec 分层、性能与验证闭环** 展开：在评测中暴露的高频缺漏与幻觉缺陷上集中收敛，同时补足 compose 黑盒探索、功能树生成与 spec 分层等新能力，并强化「修复 ↔ spec」联动与 UI 双重验证。

### ✨ 新增 (Added)

- **Spec 分层分级能力（第一版）**：在 spec 体系（`a2h-spec` / `arkts-spec-evolver`）中引入 spec 的分层、分级机制，按粒度与重要程度组织规格内容，为后续按层级裁剪上下文、按级别驱动生成与验证打下基础。
- **功能树生成 skill**：新增功能树生成能力（应用功能关系树 `app-relationship-tree`），从源工程抽取并组织功能层级结构，为迁移规划、覆盖度审计与 spec 建立提供结构化输入。
- **compose 架构黑盒探索补足**：`compose-fact-tree` 适配 Jetpack Compose 架构，新增黑盒探索补足，覆盖静态解析难以触达的运行时 / 动态分发场景，提升 Compose 工程事实抽取的完整度。
- **UI 页面 dump 双重验证**：UI 侧新增「页面 dump」作为校验手段，与既有视觉校验（`arkts-ui-verifier` / `arkts-visual-verify` / `harmonyos-ui-test`）互为交叉验证，形成结构 + 视觉的双重验证闭环，降低误判与漏判。

### 🔧 优化 (Improved)

- **7 个高频 domain skill 评测自优化**：基于评测结果，对 7 个高频使用的 domain skill 补齐高频缺漏能力与硬规矩（hard rules），显著提升 skill 主导生成代码的 **可编译率**。
- **skill 整体 token 与时间消耗优化**：精简 skill 的提示词与上下文组织，降低单次调用的 token 占用与端到端耗时，在保持能力的前提下提升执行效率与成本表现。

### 🐛 修复 (Fixed)

- **多 skill 虚构 / 幻觉 API 清理**：联动排查并清理多个 skill 中引用的虚构 API，修正幻觉缺陷，使 skill 产出对齐真实可用的 ArkTS / HarmonyOS API，进一步提升生成代码的可编译率与可运行性。
- **修复流程与 spec 建立连接**：将功能修复链路（如 `hmos_fix_build_errors` 等）与 spec 打通，使修复可依据规格定位与回归，提高修复的命中率与效率。
