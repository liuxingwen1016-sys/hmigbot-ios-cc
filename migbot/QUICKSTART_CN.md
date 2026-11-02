# MigBot — 快速开始

```bash
# 1. 在 Claude Code 里装插件：
#      /plugin marketplace add fuxi-artifacts/hmigbot
#      /plugin install hmigbot@hmigbot
#
#    本地开发：
claude --plugin-dir /path/to/migbot

# 2. cd 到 HarmonyOS 工程根目录。如果还没有，
#    在 DevEco Studio 新建一个空工程（File → New → Entry Ability）。
cd /path/to/harmony-app
claude
```

进 Claude Code：

```text
/hmigbot:a2h-init-zh   # 自动探测并确认路径（首次跑）
/hmigbot:a2h-build     # 验证 HarmonyOS 能编译
/hmigbot:a2h-run       # spec → plan → execute → verify → retrospect（每阶段暂停，自动续跑）
/hmigbot:a2h-build     # 编译迁出来的代码
```

任何命令的英文版去掉 `-zh` 后缀（`/hmigbot:a2h-init`）。语言一旦在 `/a2h-init` 里选定，就会写进 `.migbot/config.json:language` 和 `CLAUDE.md` 标记块，后续即便跑英文版命令，输出仍按你选的语言渲染。

阶段 skill 也支持自然语言触发（"生成 spec"、"a2h-spec <feature>"）。

## 常见问题

- `hvigorw not executable` → `chmod +x <harmony-root>/hvigorw`。
- `harmonyos path missing` / `android path missing` → 再跑一次 `/hmigbot:a2h-init-zh`。

完整参考：[DEVELOPER_CN](./DEVELOPER_CN.md)。
