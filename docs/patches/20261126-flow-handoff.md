# CC 流程交接修复集：20261126-flow-handoff

本修复以 `main_ui_optimize` 的 `c919b99858c66faa54f7a215acb53f95291a2c29` 为基线，补齐以下四项工具自身的流程交接。本文记录源码变更、验证范围及发行要求；更新源码不会自动替换其他项目已安装的工具。

## 修复结果

| 用户报告 | 原因与现在的行为 |
|---|---|
| Init → Execute | 原来读取了 Init 未写入的旧配置。现在两个 Execute 输入入口共用 `.migbot/config.json.ios` 校验，按项目根解析相对路径，核对原生工程描述文件及已有 Spec/Plan 源根绑定；非法输入先诊断并停止。 |
| Plan → Execute | 原来启动与报告仍要求旧单计划。现在使用 `ui-plan.md`、`feature-plan.md`、`base-plan.md` 与 `slices/`；旧计划只在明确 `--plan-format legacy` 时消费，既有 Plan 覆盖/lint 门不变。 |
| Spec → Stage 0 | 按真实 `target_input_sha256`/`inventory` 回执与资源索引消费本轮事实，核对当前批准清单及来源。摘要是源输入集合摘要，不是 JSON 文件摘要。真实 `usage.resources` 是字典、每项含 `references`；选中范围的缺失资产阻断，系统符号单列为待目标映射义务，不能声称已交付或丢掉该义务。 |
| Retrospect | 两侧逐文件统计，缺目录/坏编码/权限错误为 `UNKNOWN/null`，有效空目录才为零；剔除测试、依赖与越界链接。Execute 回执按原 marker 合同核对输入和产物摘要，原 Verify Markdown 保留路径/SHA 并明确未证明本轮绑定。计时原件可发现但不猜用时，用量缺失保持未知。报告不再预设项目数字、成功或 OCR 状态。收尾仍由原 schema-2 writer 生成 `spec/retrospect-complete.txt`，与 `mark-stage` 分开，缺输入摘要不写完成标记。 |

## 逐文件变更原因

| 文件 | 变更原因 |
|---|---|
| `migbot/bin/i2h` | 提供并安装可调用的 `execute-source`、`execute-inputs`、`retrospect-metrics` 接线；只读命令加载不生成项目内字节码。旧命令保持原行为。 |
| `migbot/bin/scripts/pipeline/flow_handoff.py`（新增） | 让路径、计划、资源、统计与回执校验由确定性实现负责，避免依赖模型照着不一致示例猜测；只读，不替代编译、UI 或行为门。 |
| `migbot/skills/i2h-execute/SKILL.md` | 正式启动片段调用新入口且失败即停止；列出三计划/切片并实际加载 Stage 0 资源合同。 |
| `migbot/skills/i2h-execute/references/stage-0-resources.md` | 对齐 Spec 真正写出的字段/索引/批准范围；保留明确 legacy、资源落地/闭包/保真硬门，清理不存在的示例命令。 |
| `migbot/skills/i2h-execute/templates/migration-report-template.md` | 正式报告列出当前计划文件，旧单计划仅在兼容说明中出现。 |
| `migbot/skills/i2h-retrospect/SKILL.md` | 用真实统计与 `receipts` 索引填报告，删除固定案例数字与成功结论，并保留真正的 schema-2 收尾。 |
| `tests/test_cc_flow_handoff.py`（新增） | 48 项安装后正反例：真实 Spec 生产者到消费者、源/摘要/scope 错配、系统符号义务、目录/编码/链接、旧升级保留、真实 Skill 启动和收尾脚本。缺生产者必须失败，不能静默跳过。临时工程独占且自动清理。 |
| `.github/workflows/ios-contracts.yml` | 将新流程回归纳入后续 CI。保留原全部测试、macOS 必要验收和可选非阻塞 Windows/Linux 策略。 |
| `README.md`、`README_CN.md` | 对外解释新入口、错误/未知状态、真实验证范围和待发布边界。 |
| 本文 | 为合并和下次发布保留逐文件原因、测试和保留清单，防止只移植文档而漏掉新脚本。 |

## 实际验证（macOS / Python 3.12.1）

- 48 项新增回归 + 777 项原有回归 = **825 项通过，0 失败，0 跳过**。
- Codex 另以真实安装器、真实 Spec 生产者和原 schema-2 writer 做 **32 项独立入口正反例，32 项通过**；不与上面的 pytest 计数合并冒充更多独立测试。
- 通过干净安装、升级保留配置与 Spec/Plan、原 e057 G0 字节保持和重新汇总、G1 结构验收。
- CLI 源码路径、资源事实、统计、回执与完成标记脚本均从实际安装目录调用。没有用设备结果补工具测试，也没有修改真实应用。
- 本候选未执行远端 CI、Windows/Linux 或实际应用的完整迁移/编译/设备 Verify；本轮不宣称两小时目标达成。

复跑新增入口：`python3 -B -m pytest -q tests/test_cc_flow_handoff.py`；全量分组命令沿用 `.github/workflows/ios-contracts.yml`。本仓库保留通用合成回归；应用实例、设备证据和本机维护日志不进入本次提交。

## 合入/后续发布要求

1. 本修复集不删除任何线上文件；前轮保留的 48 个线上能力文件及测试必须继续保留，不归类为旧 Android 清理。
2. **必须一起加入新增 `flow_handoff.py` 和 `test_cc_flow_handoff.py`**。只更新 Skill/README 会再次造成“描述有能力、正式入口没有实现”。安装器已有 scripts/pipeline 复制路径，真实安装回归已验证此模块随安装交付。
3. 保留源事实、当前批准 UI/source_only、需求索引/覆盖、路由/累计预算/agent 和旧 G0 合同；本修复不移植或删除 CHECK-5 行为录制、`uitest_scenario.py`、`layout_from_step` 等另一条链路。
4. 固定源码版本后完成发行安装和必要的 macOS CI。通过正常安装器在阶段断点升级，保留已有配置和回执，不整树覆盖其他运行中的安装。
5. 项目实际是否生成、编译、功能/视觉通过，仍由各项目自己的正式回执判定。`BOUND` 仅表示 Execute 标记与输入/产物摘要绑定有效，Verify 原件存在或工具测试通过都不能代替项目 PASS。
