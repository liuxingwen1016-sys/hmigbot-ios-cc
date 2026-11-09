<!-- when: 启动、恢复或结束 fast_fix 时读取 -->
<!-- topics: stage order, resume, non-gating, build, install -->

# 设置快速流程协议

## 已启用阶段

统一运行以 `run-config.json` 的冻结模式为准：默认 single-round 在 Round 1 后直接进入构建/安装与导出；full-repair 才执行下图的 post-round1/Quick 和 Round 2。已封存单轮的第二轮续跑按[续跑协议](../../../references/round2-continuation.md)从 Quick 开始，继承 Baseline/Round 1，不重做。

```text
result init
  → minimal preflight（源码/输出/保护硬前置；构建环境只记录 readiness）
  → baseline full detector
  → compact AI review
  → round-1 bounded repair
  → [仅已启用第二轮：one post-round-1 full detector + quick AI review
       → round-2 targeted repair]
  → signed HAP build（最多两次编译纠偏）
  → hdc install -r
  → result finalize / validate
```

快速审查后只允许一个 Round 2；Round 2 后禁止再做 Detector、AI Review、Admission、Closure、Round 3、final gate、tests、启动或 UI 操作。

## 三小时调度目标

以下为完整双轮的历史软预算，不授权开启第二轮；统一运行的并发与阶段准入以[设置 adapter](../../../references/setting-adapter.md)为准。中型设置域总目标 2 小时 30 分至 2 小时 55 分：Preflight 10–15 分钟；Baseline Detector + 紧凑审计 45–60 分钟；Round 1 60–70 分钟；快速审查 20–30 分钟；Round 2 35–45 分钟；构建安装 10–20 分钟。普通修复批限制 3 项，强关联 foundation 批最多 4 项，快速审查批默认 6 项；原生计划保留每 wave 最多四批，统一执行槽位使用设置 adapter 的额度。软预算不允许截断 Baseline exactly-once 覆盖，也不允许通过省略完整 consumer/terminal chain 换时间。

## 恢复与复用

只复用能机械校验的正式产物：

- `result.json` 必须通过 `export_fast_result.py validate`；未 finalized 只表示流程尚未结束。
- `preflight.json` 必须通过 `fast_preflight.py validate`。`build_readiness=READY` 时，`toolchain.lock.json` 必须通过 `resolve_hmos_toolchain.validate_lock`，`task-discovery.json` 必须绑定该 lock，build profile 与 signing storeFile 仍存在；`UNAVAILABLE` 时只复用实际存在且能校验的环境证据，不要求补造 lock/discovery/storeFile。
- Baseline/quick-review fragment 必须有合法 seal，并绑定当前 plan SHA-256。
- 各已启用轮次的 repair result 必须由 `publish-result` 原子发布，绑定当前 round plan，且有 exactly-once `key_results`。
- build/install evidence 必须通过 exporter 校验，HAP SHA-256 仍匹配。

产物缺失或 hash 漂移先核实具体缺口，按对应恢复协议处理未封存阶段，不覆盖封存证据或重新 init 清空计数。同批失败分三类处理：

- **格式纠正**：由原 Agent 在原上下文修正 schema、引用等格式问题，不因此换 Agent 或声明业务重审完成。
- **业务内容重审**：原生审查允许时，最多使用一个新上下文重审一次；再次失败分别用 `mark-unreviewed` / `mark-failed` 记录真实审查缺口，并按统一 complete 协议收口。
- **模型故障恢复**：限流、容量或服务中断按[统一恢复协议](../../../references/unified-dispatch.md)在原 batch、原 Agent 上恢复，最多三次且累计退避不超过 180 秒，与业务重审分开计数；仅确认原身份丢失/不可恢复时走受支持的替代流程，不能把模型故障当业务失败以获得新预算。

只有已启用 Quick/第二轮时，快速审查失败的 key 才按原生准入保守进入 Round 2；这些未决项本身不阻止可执行的集中交付。

## Preflight

统一运行直接使用 IO 的[共享准备与引用](../../../references/unified-workflow.md#0-初始化源码保护和共享预检)，SO 不重复执行依赖恢复或 discovery。以下低层字段用于原生兼容与证据校验。

Preflight 不编译 ArkTS，也不连接设备。仅在原生兼容流程需要独立预检时，第一步运行：

```text
python <skill-dir>/scripts/resolve_hmos_toolchain.py \
  --project-root <arkts_root> --out <out>/toolchain.lock.json
```

Resolver 依次检查 `local.properties:hwsdk.dir`、`DEVECO_SDK_HOME`、`DEVECO_HOME/sdk` 与常见 DevEco 位置。Windows 自动检查 Program Files 和常见盘符；macOS 自动检查 `/Applications/DevEco-Studio.app/Contents`、用户 `Applications`、`~/Library/Huawei/Sdk`，并兼容 `jbr/Contents/Home`。不存在的旧机路径只标记 `stale_local_properties=true` 并继续；候选为 `sdk/default` 时提升到父级 `sdk`。不得把 component 目录写入 `DEVECO_SDK_HOME`。Resolver 只输出子进程环境，不修改系统/用户环境变量和项目配置。

Preflight `status=PASS` 表示源码修复可继续，不表示能够构建。必须写 `repair_ready=true` 和 `build_readiness=READY|UNAVAILABLE`。只有 Android/ArkTS 源码不可读、输出不可写、稳定结果无法初始化或源码保护快照无法建立，才能写 `status=FAIL`、`repair_ready=false` 并提前终止。

`build_readiness=READY` 必须冻结：

- SDK、JBR、hvigor 解析路径；
- module、product、build mode；
- toolchain lock path + SHA-256，且 SDK/JBR/hvigor 与 lock 完全一致；
- task discovery command/exit code、实际列出的 tasks 与 discovery strategy；
- `dependency_graph_loaded=true`；
- 唯一 build command 与预期 signed HAP；
- 使用的 signing config 名称、`build-profile.json5` 绝对路径、`storeFile` 绝对路径及存在性。

Task discovery 必须运行：

```text
python <skill-dir>/scripts/fast_preflight.py discover \
  --toolchain-lock <out>/toolchain.lock.json \
  --product <product> --module <module> --module-target <target> \
  --build-mode <build_mode> --out <out>/task-discovery.json
```

该命令从 lock 注入 `DEVECO_SDK_HOME/JAVA_HOME`，Agent 不得自行拼环境。若 `hvigorw tasks` exit 0，但当前版本只展示公开任务，脚本记录 `TASKS_EXIT_ZERO`；此时不得强制要求列表出现内部 build task。若列表实际包含 `CompileArkTS` 与 `assembleHap`，脚本记录 `EXPLICIT_BUILD_TASKS`。两种策略都必须冻结包含 `assembleHap` 的唯一 build command。

只有 toolchain lock 本身无法解析 SDK 根目录，或使用 lock 后的 tasks 输出明确报告组件错误，才能写 `SDK_COMPONENT_MISSING`。不得把失效的 `local.properties` 或 `sdk/default` 层级错误归类为组件缺失。

不得读取或输出 signing password。依赖缺失可恢复一次并只重验一次。task discovery、SDK/JBR/Hvigor 或 signing readiness 失败时写 `build_readiness=UNAVAILABLE` 和具体 reason code，然后继续 Baseline AI 审计；不得因此提前 finalize。

Build-ready draft 还必须包含：

```json
{
  "toolchain_lock": "<out>/toolchain.lock.json 的绝对路径",
  "toolchain_lock_sha256": "64位十六进制",
  "task_discovery_evidence": "<out>/task-discovery.json 的绝对路径",
  "task_discovery_evidence_sha256": "64位十六进制",
  "task_discovery_strategy": "TASKS_EXIT_ZERO | EXPLICIT_BUILD_TASKS",
  "discovered_tasks": ["tasks 命令实际列出的非空任务名"]
}
```

Build-ready draft 的 signing 字段固定为：

```json
{
  "signing_ready": true,
  "signing_config": {
    "name": "预定 product 实际引用的 signingConfig",
    "build_profile_path": "build-profile.json5 绝对路径",
    "store_file": "解析后的 storeFile 绝对路径",
    "store_file_config_value": "build-profile 中 storeFile 的原始字符串值",
    "store_file_exists": true
  }
}
```

Validator 会重新读取 build profile，仅匹配 `storeFile` 与 config 名称，不提取或打印密码字段。

降级 draft 至少包含：

```json
{
  "status": "PASS",
  "repair_ready": true,
  "build_readiness": "UNAVAILABLE",
  "reason_codes": ["SIGNING_STORE_FILE_MISSING"]
}
```

工具链、task discovery 或 signing 字段只记录真实获取到的部分；`signing_config.store_file` 可以指向不存在的绝对路径，但 `store_file_exists` 必须如实为 `false`。

## 非门控规则

Baseline 之后，问题数量、严重度、风险、审查失败、任一轮修复失败、无源码 diff、快速审查未闭合或 Round 2 未完成，都不得成为 correctness gate；尽可能记录后继续 build/install。

构建与安装是尽力执行的尾段，不是源码修复的前置。`build_readiness=UNAVAILABLE` 时当前已启用的修复阶段照常完成，随后以 `REPAIR_FINISHED_NOT_INSTALLED_UNVERIFIED` 收口；构建/安装失败时记录对应未验证终态，不启动应用验证。

## 编译纠偏边界

首次 build 加最多两次 correction，共最多三个 attempt。Correction 只处理当前编译输出明确指向的问题，且路径必须位于本次运行已启用 Repair 阶段的 ownership 范围；第二轮续跑仅使用本次 Round 2 ownership，不能借继承的 Round 1 扩权。禁止借编译纠偏新增业务行为、扩张 ownership 或重新审计设置。

## 中断与终止

异常中断前若具备收口条件，执行 `finalize` 和 `validate` 并核对实际结果。无法收口时，初始化的 `WORKFLOW_INCOMPLETE` 且 `finalized=false` 仅是未完成保底记录，不表示已经封存。下一次接管先校验已有产物与批次状态，再恢复未完成步骤；只有按原协议导出、校验且相应结果标记已 finalized（统一结果还须绑定合法结果锁）才能报告封存。已封存的失败或未验证终态仍保留其真实缺口，不从聊天描述或 result.json 的存在推断成功。
