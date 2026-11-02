<!-- when: Stage 1 正式/Preview 接线及可选 S1-V 时加载 -->
<!-- topics: page-state-output binding, preview preparation, receipts, static reachability -->
# Stage 1 最小接线与 Preview 契约

## 严格接线验收（显式批准的部分执行）

入口：「重跑 S1-V 接线验收」。先读取项目 ledger 中的批准和 `spec/execution/stage1-wiring-contract.json`；没有契约就报告前置缺失。本分支优先于下文旧冒烟范围/视觉跳过规则；失败处置先加载 [stage1-gate-policy.md](stage1-gate-policy.md)，按项目最新 ledger 区分质量缺陷与外部缺口。只复用现有页面，不重跑 Stage 0/S1-G、不开始 Stage 2/3。

契约的 `required_mounts` 是 owner_file/owner_symbol → component_file/component_symbol 的必需渲染边；`required_actions` 是已绑定 UI handler 必须能到达的 `effect_call`；`runtime_cases` 冻结实际点击、内容 landmark、选中 Tab 和返回。范围由 spec/Android 确定，不能按当前已接上的子集重新生成。核对 ledger 记录的契约 SHA256；禁止删用例、修改 landmark、缩小分母或修改检测器迁就产物。

1. **第 0 轮静态检查**：运行 `python3 .claude/skills/a2h-execute/scripts/ui_stage1_gate.py --project-root . --output-json spec/execution/wiring-experiment/preflight.json`。契约存在时自动检查必需挂载/handler 调用链；import、注释、字符串、未从 build 到达的孤立 builder 都不能替代挂载。结果为 STATIC_ONLY_RUNTIME_REQUIRED，不能据此声称接线验收 PASS。解析不支持的写法保留未核实，不能猜成通过。
2. **修复责任和轮次**：FAIL/BLOCKED 先运行根因处置脚本，质量缺陷派修复，信息/环境/工具缺口做有界恢复。每轮保存实际操作日志供统一计数；初检不消耗预算；最多 `max_repair_rounds`（缺省为 2）轮源码修复。按报告派 `a2h-migration-worker` 做 S1-W 跨文件接线，合并本轮缺口一次修复；随后重跑静态检查。只改 UI 挂载、UI 本地事件、参数/最小展示数据接入及由此暴露的 ArkTS 编译错误。保留 spec/ledger 允许的业务占位；不得通过跳过正式入口、假登录成功、清应用数据或更改 App 身份来通过。
3. **单次集中编译**：静态通过后派 `hmos-builder`，完整参数沿 agent 契约传递，`CALLER=a2h-execute, STAGE_HINT=stage-1-ui-delivery, MAX_ITER=1`。该已有例外仅构建一次，不在 builder 内另开 20 轮修复。编译错误返回第 2 步；不能删除组件或断开 import 修编译。编译通过后真实安装该 HAP，再按本文件「包回执」格式写 build/install JSON，`unit_id` 使用严格契约的值，记录当前 source/HAP SHA256 和真实 device_id。
4. **实际设备冒烟**：安装当前包后运行下方脚本。它复用 `hdc/uitest`，从真实入口启动，只执行冻结的操作，不需要 Android baseline、不调用 visual-fixer、不修改源码。它抓取本次 app UI dump 和 PNG，检查可见内容节点、Tab 选中态及二级页面覆盖/返回，保存每个 case 的证据与哈希；只有底栏/标题不算内容显示。设备/包问题保留 BLOCKED 并查根因；确认设备/捕获环境问题可有界恢复，错包/陈旧证据须重建，实际 UI 缺口返回第 2 步。

```bash
python3 .claude/skills/a2h-execute/scripts/stage1_wiring_smoke.py \
  --project-root . \
  --build-receipt spec/execution/wiring-experiment/build.json \
  --install-receipt spec/execution/wiring-experiment/install.json
# hdc 不在 PATH 时追加 --hdc <SDK 的 hdc 可执行文件绝对路径>
```

5. **收口**：以脚本返回的本次 `spec/execution/wiring-smoke/<run_id>/report.json` 为设备证据。静态、真实编译、全部运行用例均通过才记 wiring PASS；只写到 `spec/execution/wiring-experiment/result.json` / brief，不覆盖旧视觉报告、不改页面为 business_ready。源码或契约改变后旧构建/安装/设备证据失效，须重建重测。预算耗尽后，质量缺陷/根因未明保持阻断；有证据的外部缺口按根因协议记账 RELEASE_WITH_GAPS，原失败与未验证项保留。两种结果均结束本次部分验收，不扩大预算。视觉比较单独按原用户选择运行。

验证纪律：按当前源码与已批准的 spec 独立修复；受控回放实验应隔离参考答案，不能通过切换对照版本或复用旧包冒充本次修复。历史 wiring 中的 not_wired 不能覆盖新的必需清单，修复后如实更新接线记录。词法闸只做定点缺口检查，实际显示与交互由当前包设备用例验证。

S1-W 接通选定的正式启动/主容器/详情路径；S1-P 在正式入口或 provider 尚未齐备时准备受控 Preview。两者复用正式页面和 VM，不等于 Stage 3 业务完成。原 EntryAbility、loadContent、pageMap 不因截图临时替换；Preview 接入加载 `assets/ui-delivery/owner-integration.md`。

## 单一 manifest

在 `spec/execution/wiring/` 每单元保存一个 manifest。所有 Stage 1 脚本使用相同的 `pages` 记录，page 与 state 不再分别存成两个独立数组：

```json
{
  "schema_version": 1,
  "unit_id": "preview-weather-main",
  "status": "preview_prepared",
  "delivery_mode": "preview_host",
  "entry_file": "entry/src/main/ets/pages/OriginalEntry.ets",
  "entry_route": "MainPage",
  "preview_host_file": "entry/src/main/ets/verification/VerificationNavigationHost.ets",
  "pages": [
    {
      "page_id": "page_0027_MainActivity",
      "state_id": "main_weather",
      "output_file": "entry/src/main/ets/pages/MainPage.ets",
      "fixture_id": "source-backed-weather"
    }
  ],
  "target_files": [
    "entry/src/main/ets/pages/OriginalEntry.ets",
    "entry/src/main/ets/pages/MainPage.ets",
    "entry/src/main/ets/viewmodels/MainVM.ets"
  ]
}
```

正式 smoke 单元使用 `delivery_mode=formal_smoke`，按实际接通的每个 page/state 列记录。一个文件可以承载多个显式状态；不根据文件名猜 page 身份，也不按数组笛卡尔积扩范围。

- `output_file` 是必需的项目相对文件路径，可以位于 pages/components 等正式目录。每个 page/state 显式绑定自己的输出。
- `target_files` 列入口、页面、VM、必要组件及真正使用的 adapter。规范化时自动纳入各 output_file。每一个选定目标都检查存在性，目录外路径拒绝。
- Preview 还须以 `preview_host_file` 指向实际接入工程的 host；它自动加入 target_files，不能拿 skill 目录中的模板存在性当成产品已接入的证据。
- `entry_file` 使用真实入口；省略时只在实际 EntryAbility 中能解析唯一字面量 loadContent 时推导，无法确定则补清入口，不默认 Index。
- 旧单数 `page_id/state_id` 仅在同时显式提供 `output_file` 时兼容；旧复数数组必须长度相同并有 `page_outputs` 显式映射，按位置配对。无法确定时要求迁移 manifest，不从 target_files 猜。
- `fixture.json/visual.json/facts-manifest.json/visual-facts.md/view.static.xml` 继续是可选增强资料，不以其缺失、陈旧或格式阻断接线。动态展示数据需有来源，可以由正式 provider、源码/运行时证据支撑的 adapter 提供，不以猜造成功数据填空。

## 接线步骤与静态检查

1. 冻结范围、owner 和跨切片边界；先准备契约再施工。施工前可跑静态检查定位缺口，收口时对最终源码重跑。
2. 正式单元保留真实入口和导航；Preview 通过已接入的 host 和冻结参数显示同一个正式组件，不临时改 Index、创建第二套页面或绕过真实业务保护。
3. 接入选定 Tab/content slot、最小 VM、本地事件、参数和数据来源；跨文件修改依 owner 交 closer。
4. 运行 `stage1_reachability.py --project-root <project> --wiring-manifest <manifest> --output-json <现有 reachability 报告>`。缺失文件（包括 VM/组件）、选定文件不在入口 import 图中或入口不明均 FAIL。该结果只证明静态 import 可达，不证明组件挂载、点击或运行时路由正确；这些仍由结构审计和选定的设备检查覆盖。
5. 结构审计通过后保存 wiring brief。未纳入本单元的页面仍为 skeleton_ready，不批量标成已接线。

## Preview 状态和 Stage 1 收口

```text
skeleton_ready     页面骨架已生成
smoke_wired        选定正式路径完成静态接线；尚无设备正确性结论
preview_prepared   Preview 正式文件/入口/依赖准备齐备；未声称构建或显示
preview_buildable  当前源码与当前 HAP 的真实构建回执验证通过
preview_installed  相同 HAP 在指定设备的真实安装回执验证通过
preview_ready      本次设备操作已实际到达并确认目标 page/state 显示
business_ready     Stage 3 真实 provider、业务事件与正式入口完成
```

`stage1_preview.py --project-root <project> --manifest <manifest> --output <report>` 不执行构建/安装，也不检查 skill 目录里的模板是否等于已接入产品。它检查 manifest 的正式目标文件，返回 preview_prepared。可以在用户跳过 S1-V 时以此状态完成 S1-P、进入 Stage 2，不能提前写 preview_ready。

可选 `--build-receipt/--install-receipt` 只能推进到 preview_buildable/preview_installed；页面显示由真实到页证据确认。结果写已有 preview report/brief，修改 wiring 状态时由 owner 回写，不由脚本擅自翻状态。

### 包回执

以下是执行真实构建、安装后的调用方回执，不是静态投影。禁止仅凭文件存在或任意 PASS 文本生成成功回执。

```json
{
  "kind": "build",
  "status": "PASS",
  "unit_id": "preview-weather-main",
  "source_sha256": "由 stage1_contract.source_digest(project_root) 计算",
  "hap_path": "entry/build/default/outputs/default/entry-default-signed.hap",
  "hap_sha256": "实际构建 HAP 的 SHA256"
}
```

安装回执 `kind=install,status=PASS`，同 unit_id/source_sha256/hap_sha256，并记录真实 `device_id`。安装回执不能替代构建回执；构建回执不能冒充安装回执。源码或 HAP 已变则回执失效。多个 unit 可绑定同次构建与安装的实际证据，不逐 unit 重编。安装成功只证明安装，不证明页面显示。

## 可选 S1-V

执行/跳过与续跑选择以 a2h-execute §3d 为准。选择跳过：brief 记 SKIP，保留 prepared 状态，直接 Stage 2；不检查设备或生成验证包。

选择执行：

```text
准备完成的 wiring（包含 preview_prepared）
 → ui_stage1_gate.py（显式输出/依赖检查；UI regex 仅提示 WARN）
 → stage1_visual_scope.py --project-root <project> --wiring-dir <dir> --out <scope>
 → hmos-builder 构建当前包并真实安装；源码若变则刷新 scope
 → visual-verify 的 stage1_wired 独立受限分支
 → 本次到页、截图/dump、Android 配对比较和 finalize
 → PASS / DIFF / visual_blocked
```

scope 接受 smoke_wired 及 prepared/buildable/installed/ready 的 Preview，不把安装后的状态作为开始安装的前提。输出 scope 为每个 page/state 绑定审计后的 Android PNG/XML 路径和哈希：从 snapshots 的 meta.runtime_evidence 或 runtime_evidence_by_state 取，要求 state 相符。不能复用另一个状态的帧，也不拼旧 screenshots/android 路径。

视觉 skill 的独立分支详见 `arkts-visual-verify/references/stage1-capture-compare.md`。不启动全量遍历、fixer、round budget 或清数据。只有实测显示的 Preview case 可标 preview_ready，不写页面 verified，不宣称业务通过。DIFF 保留差异供用户决定后续处理；失败按设备、应用、接线、捕获分诊，不能静默漏页。
