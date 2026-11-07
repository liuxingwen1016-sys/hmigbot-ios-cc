# MigBot —— 开发者指南

[English](./DEVELOPER.md)

面向想定制插件（自选 skill、调权限、手动改配置）的用户。最简路径见 [QUICKSTART_CN](./QUICKSTART_CN.md)。

## 安装（完整参考）

### 作为 Claude Code 插件（推荐）

```text
/plugin marketplace add liuxingwen1016-sys/hmigbot-ios-cc
/plugin install hmigbot-ios@hmigbot-ios
```

然后进 HarmonyOS 工程根目录启动 Claude Code，跑 `/hmigbot-ios:i2h-init-zh`。首次跑时该命令会调用 `i2h-bootstrap`（插件 `bin/` 下的可执行文件），自动探测 iOS 源、DevEco 安装目录、hvigorw、xcrun、simctl、hdc 和系统语言，写入 `.migbot/config.json` 骨架，然后带你逐项确认。

### 本地开发

```bash
git clone https://github.com/liuxingwen1016-sys/hmigbot-ios-cc /path/to/hmigbot-ios
cd /path/to/your-harmony-app
claude --plugin-dir /path/to/hmigbot-ios/migbot
```

`--plugin-dir` 可以重复传，加载多个插件。改完插件后进 Claude Code 跑 `/reload-plugins` 让变更生效。

### 维护本仓库（贡献者）

若你要改的是 migbot 仓库本身（而非用它迁移），克隆后先执行一次性设置：

```bash
git config core.hooksPath .githooks              # 启用 pre-commit 提示
git config migbot.coreRoot /path/to/ArkTs-Core   # 你本机的上游仓位置
```

这两条写在 `.git/config` 里、不随仓库分发，**每人都要各自执行一次**。

原因：`skills/` 下 71 个 skill 来自上游 ArkTs-Core、16 个为 migbot 独有；前者在这里
改了必须回推上游，否则下次整版同步会被覆盖（历史上已发生 3 次）。hook 会在你改到
共享 skill 时提醒。详见 [`scripts/README.md`](./scripts/README.md)。

## 工程里会出现什么

只有一个：`.migbot/config.json`。其他都在插件目录里（Claude Code 管理，不动你的工程）。

```json
{
  "ios": "../ios-app",
  "harmonyos": ".",
  "hvigorw": "",
  "xcode": "",
  "xcrun": "",
  "simctl": "",
  "deveco": "/Applications/DevEco-Studio.app",
  "hvigorw": "",
  "hdc": "",
  "language": "zh",
  "confirmed": false
}
```

| 字段 | 说明 |
|---|---|
| `ios` | iOS 工程路径。`i2h-bootstrap` 自动探测；`/i2h-init` 确认。 |
| `harmonyos` | HarmonyOS 工程路径；默认 `.`，因为 `/i2h-init` 在该根目录跑。 |
| `hvigorw` | 可选覆盖项。空（默认）→ `<harmonyos>/hvigorw`。当 wrapper 在工程外或换了名字时设。 |
| `deveco` | DevEco Studio 安装目录。首次跑时自动探测 `$PATH` + 平台标准目录（Windows: C/D/E/F 盘；macOS: `/Applications`；Linux: `/opt`、`/usr/local`）。可空（`/i2h-init` 接受 `skip`）。 |
| `xcode`、`xcrun`、`simctl`、`hdc` | 可选的 Xcode、模拟器和鸿蒙 SDK CLI 绝对路径。空 = "靠 `$PATH`"。`/i2h-init` 会探测常见位置。 |
| `language` | `zh` 或 `en`。首次跑时由 `i2h-bootstrap` 从 `$LANG` 推断。控制 `i2h-tool` 运行时消息和 `CLAUDE.md` 标记块。改后请重跑 `/i2h-init`。 |
| `confirmed` | `/i2h-init` 完成确认后置 `true`。值非 `true` 时 `/i2h-run` 跳回 `/i2h-init`。 |

`ios` / `harmonyos` 必须存在；相对路径相对安装目录解析。

## Slash 命令

每个命令都有中英两个版本（`-zh` 后缀）。两者共写同一份 `.migbot/config.json`，运行时按 `language` 字段决定输出语种。

- **`/hmigbot-ios:i2h-init-zh`**（或不带后缀的英文版）—— 首次跑自动探测；然后用人话带你确认 `ios` / `harmonyos` / `xcode` / `xcrun` / `simctl` / `deveco` / `hvigorw` / `hdc` 八个路径。成功后置 `confirmed: true`，并刷新 `CLAUDE.md` 标记块。
- **`/hmigbot-ios:i2h-build-zh`** —— 校验 `.migbot/config.json` 路径并跑 `hvigorw assembleHap`。`hvigorw` 错位时自我修复。
- **`/hmigbot-ios:i2h-run-zh`** —— 跑完整迁移流水线（`i2h-spec → i2h-plan → i2h-execute → i2h-verify → i2h-retrospect`），逐阶段确认并支持自动续跑。配置未确认时跳回 `/i2h-init`。

阶段 skill 也支持自然语言触发（"生成 spec"、"i2h-spec <feature>"）。

## 定制 skill

40 个 skill 在插件的 `skills/<id>/SKILL.md` 下。插件由 Claude Code 托管，定制请走本地开发模式（`claude --plugin-dir`），不要去改 `~/.claude/plugins/` 下的已安装副本。要禁用某 skill，在本地副本里把它的 `SKILL.md` 改名为 `SKILL.md.disabled`。

## 权限

每个命令在 frontmatter 里声明自己的 `allowed-tools`，所以插件运行时权限是按命令隔离的。要让 `i2h-tool` 调用在工程级别一次性放行（不每次弹权限提示），在工程的 `.claude/settings.json` 加：

```json
{
  "permissions": {
    "allow": ["Bash(i2h-tool *)", "Bash(i2h-bootstrap *)"]
  }
}
```

## 语言切换怎么工作

1. **Bootstrap 时刻。** `i2h-bootstrap` 读 `$LANG`，首次跑时把对应 `language` 值写进 `.migbot/config.json`。
2. **CLAUDE.md 标记块。** `/i2h-init` 第 8 步往 `CLAUDE.md` 写一段 marker 包裹的语言指令块。每次重跑 `/i2h-init` 都会覆盖，始终反映当前 `language` 字段。
3. **Skill / agent frontmatter。** `skills/` 和 `agents/` 下每个文件 frontmatter 都带 `output_language: from-config`。配合 CLAUDE.md 指令，Claude 始终按所选语言输出，不管 skill 自身写的是哪种语言。

要切换语言：改 `.migbot/config.json:language`，重跑 `/i2h-init` 刷新标记块。

## 常见问题

- **`hvigorw not executable`。** `chmod +x <harmony-root>/hvigorw`，或在 `.migbot/config.json` 里把 `hvigorw` 指到工程外的 wrapper。
- **`harmonyos path missing` / `ios path missing`。** 重跑 `/i2h-init`，或在 `.migbot/config.json` 里设绝对路径。
- **`/i2h-run` 老是跳到 `/i2h-init`。** 配置 `confirmed` 还是 `false`。把 `/i2h-init` 走完并在末尾确认。
- **`xcrun` / `hdc` 找不到。** 装对应 SDK 并加到 `$PATH`，或在 `.migbot/config.json` 设绝对路径，再重跑 `/i2h-init`。

## 测试

```bash
I2H_SKIP_DEVICE_CHECK=1 bash tests/i2h-tool.test.sh
```

skip 标志关掉 iOS simulator/device tools 运行时检查，让测试在没有 iOS 模拟器或连接设备的机器上也能过。
