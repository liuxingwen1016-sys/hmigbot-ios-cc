# hmigbot-ios Codex 插件

`codex/` 是由 `codex-adapter/scripts/convert.py` 从 `migbot/` Claude 源生成的 Codex 形态产物。源文件仍保留在 `migbot/`，不要直接编辑本目录的生成文件。

## 使用

把 `codex/skills` 复制或链接到目标项目的 `.agents/skills`，把 `codex/agents` 中的 TOML 放到项目级 `.codex/agents`。入口通过 `$i2h-init`、`$i2h-run`、`$i2h-build` 以及五个 `$i2h-*` 阶段 skill 调用。`codex/commands` 保留从 Claude command 迁移的可读版本，便于安装器或宿主集成。

生命周期 hook 和便携运行时保存在 `codex/hooks` 与 `codex/bin`。它们沿用 `.migbot` 项目配置和 i2h runtime，不改变迁移业务逻辑。

## 重新生成

```bash
python3 codex-adapter/scripts/convert.py --dry-run
python3 codex-adapter/scripts/convert.py
python3 codex-adapter/scripts/verify.py --codex-dir codex
```

查看 `MIGRATION-REPORT.md` 中的自动改写、平台映射、结构校验和待人工项。
