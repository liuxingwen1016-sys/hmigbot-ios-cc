# 统一执行策略

适用于迁移 pipeline 的派发和工具优化。运行器的模型映射、effort 与预算数值只维护在
[`config/execution-policy.json`](../config/execution-policy.json)；不在 prompt 中复制第二套上限。

| Profile | 任务边界 | 默认模型 / effort |
|---|---|---|
| `search` | 文件定位、source-index 切片、窄范围符号与证据索引；不裁决业务语义 | Haiku / low |
| `implementation` | 常规 worker、view-converter、fixer、builder，以及有明确锚点的 Spec/Plan writer | Sonnet / medium |
| `complex` | 跨模块语义、复杂依赖裁决、疑难诊断和 closure | Opus / high |
| `expert` | 用户或调度任务显式指定的疑难专用分析 | Fable；effort 读取配置，不自动升级 |

可直接派发命名 agent：轻量索引用 `i2h-source-indexer`（Haiku/low）；疑难专项仅在显式指派时用 `i2h-diagnostic-expert`（Fable/max）。两者都只读，后者不得自动全量巡检；常规修复仍交 implementation。

## 派发与运行

插件源入口在 `migbot/scripts/`；安装到项目后入口在 `.migbot/runtime/scripts/`，
共享配置和本参考文档分别在 `.migbot/runtime/config/` 与 `.migbot/runtime/references/`。
先用 `--dry-run` 检查最终路由与限制；dry-run 不代表已经运行迁移或验证。

```bash
python3 .migbot/runtime/scripts/run_claude_task.py --help
python3 .migbot/runtime/scripts/run_claude_task.py <stage-label> --task-id <stable-task-id> \
  --run-dir <stable-ledger-root> --cwd <project-root> --profile implementation \
  --prompt-file <task-prompt.txt> --plugin <plugin-root> --dry-run
```

- 统一入口为 `scripts/run_claude_task.py`，通过 `--profile` 选择路由；旧阶段 runner 使用其支持的 `--profile` / `--task-id`。`execution_policy.py` 是这些入口共享的 Python 模块，不是独立 CLI。守护层包裹实际 Claude 命令，实际参数以入口 `--help` 为准。agent frontmatter 的 model/effort 是显式默认值，运行时路由以共享配置为准。
- model 别名在共享配置映射到完整模型 ID。只向实际支持的运行器传模型、effort、turn 与费用参数；不支持时记录能力缺口，不能声称限制已生效，也不能静默继承父会话的昂贵模型。
- turn、墙钟时间与估算费用是任务资源上限；CLI usage/cost 只能按其真实口径记录，不等于实际账单。未知费用记 unknown，不能填零冒充免费。
- 同一 feature / 根因从首次执行到 resume、重试、换模型和修复复检都累计；保留同一任务身份和账本，不能通过新 session、新报告名或拆分小修重置上限。并行子任务的累计使用也归回所属任务。
- 不改已冻结的 Spec/Plan 或用户授权范围来适应模型预算；迁移暂停时不能因读取这些文档而启动模型、构建或设备工作。

## 会话与上下文

按 feature 或根因完成一组连贯工作，常规小修沿用会话。只提供目标、可写文件、验收标准、索引切片、必要源码锚点、证据路径和上一轮短摘要；文件内容变化时补读相关范围。只加载当前步骤需要的 references。

摘要至少包含已完成变更、真实检查结果与产物路径、剩余假设/阻塞、下一步和累计使用。
只有上下文不足、权限/写域隔离或需要独立语义复核时才换会话；交接摘要并继承预算，
不为每次编辑重开全量审计。

连续两轮无新证据或无进展时停止相同尝试：按具体缺口改定位方法、缩小根因、获取缺失证据，
或在剩余预算内有理由地升档。换策略的原因和新证据写入摘要；预算耗尽仍未完成时保留
未完成项和恢复条件，不写 PASS，也不自动开始下一轮。

## 确定性执行与验收

固定编译、截图/采集、source/HAP/PNG 哈希、文件排序、JSON 合并和已有结构门使用现有
确定性脚本；不让模型重复拼同一段命令或模拟执行。原有更严格的阶段修复上限继续生效，
实际轮次受阶段上限与任务剩余预算共同约束，停止时如实返回 FAIL / BLOCKED / 未完成。

`rg`、正则、`includes`、符号存在和结构扫描只用于定位或其明确的静态门；不可据此
声称业务通过。测试不得镜像生产逻辑来证明自己正确；业务断言要绑定独立预期、真实
输入/输出与执行回执。原生编译成功只证明可构建，不能代替原生功能、运行时场景与 UI
验收。预算策略不降低原真实证据门、编译门、功能或 UI 标准；设备或输入缺失按现有
契约记录 not_run / blocked / deferred。
