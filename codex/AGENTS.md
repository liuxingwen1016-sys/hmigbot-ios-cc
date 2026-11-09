# Codex 运行约定

- 先读取当前阶段 skill 的 `SKILL.md`，再执行其脚本和验收步骤。
- `$i2h-init`、`$i2h-run`、`$i2h-build` 是从 `migbot/commands` 迁移的入口 skill。
- 子代理使用 `spawn_agent`，角色定义位于 `.codex/agents/*.toml`。运行时脚本继续使用目标项目的 `.migbot/bin/i2h`。
- 阶段标记、恢复检查和 P0/P1/P2 验收契约保持源侧定义。不要以文件存在代替 hash、marker 和报告检查。
