# MigBot — Developer Guide

[中文文档](./DEVELOPER_CN.md)

For users who want to customize the plugin (skill selection, permissions, manual config). For the happy path see [QUICKSTART](./QUICKSTART.md).

## Install (full reference)

### As a Claude Code plugin (recommended)

```text
/plugin marketplace add liuxingwen1016-sys/hmigbot-ios-cc
/plugin install hmigbot-ios@hmigbot-ios
```

Then launch Claude Code from inside your HarmonyOS project root and run `/hmigbot-ios:i2h-init`. On first run, the command invokes `i2h-bootstrap` (one of the executables shipped in the plugin's `bin/`) to auto-detect iOS source path, DevEco install, hvigorw, xcrun, simctl, hdc, and locale. It writes a skeleton `.migbot/config.json` next to your `oh-package.json5`, then walks you through confirming each path.

### Local development

```bash
git clone https://github.com/liuxingwen1016-sys/hmigbot-ios-cc /path/to/hmigbot-ios
cd /path/to/your-harmony-app
claude --plugin-dir /path/to/hmigbot-ios/migbot
```

Repeat `--plugin-dir` to load multiple plugins. After editing the plugin, run `/reload-plugins` from inside Claude Code to pick up changes.

### Maintaining this repository (contributors)

If you are changing the migbot repository itself (rather than using it to migrate),
run this one-time setup after cloning:

```bash
git config core.hooksPath .githooks              # enable the pre-commit reminder
git config migbot.coreRoot /path/to/ArkTs-Core   # where your upstream clone lives
```

Both live in `.git/config` and are not distributed with the repository, so **every
contributor must run them once**.

Why: of the skills under `skills/`, 71 come from the upstream ArkTs-Core and 16 are
migbot-only. Changes to the former must be pushed back upstream, or the next full
sync will overwrite them (this has happened three times). The hook reminds you when
a commit touches a shared skill. See [`scripts/README.md`](./scripts/README.md).

## What gets written into your project

Only one file: `.migbot/config.json`. Everything else is in-plugin and lives inside the plugin install directory (managed by Claude Code, not your project).

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
  "language": "en",
  "confirmed": false
}
```

| Field | Notes |
|---|---|
| `ios` | Path to the source iOS project. Auto-detected by `i2h-bootstrap`; confirmed by `/i2h-init`. |
| `harmonyos` | Path to the HarmonyOS project; defaults to `.` because `/i2h-init` runs inside that root. |
| `hvigorw` | Optional override for the `hvigorw` executable. Empty (default) → `<harmonyos>/hvigorw`. Set this when your wrapper lives outside the project root or under a different name. |
| `deveco` | DevEco Studio install directory. Auto-detected at first run via `$PATH` + platform-specific scan (Windows: C/D/E/F drives; macOS: `/Applications`; Linux: `/opt`, `/usr/local`). May be empty (`/i2h-init` accepts `skip`). |
| `xcode`, `xcrun`, `simctl`, `hdc` | Optional explicit paths to Xcode, simulator and HarmonyOS SDK CLIs. Empty means "rely on `$PATH`". `/i2h-init` auto-detects common locations. |
| `language` | `zh` or `en`. Set on first run by `i2h-bootstrap` from `$LANG`. Drives `i2h-tool` runtime messages and the `CLAUDE.md` marker block. To switch later, edit this field and re-run `/i2h-init`. |
| `confirmed` | Set to `true` by `/i2h-init` once the user has confirmed paths. `/i2h-run` redirects to `/i2h-init` when this is `false` or missing. |

`ios` / `harmonyos` must exist; relative paths resolve against the install dir.

## Slash commands

Every command is available in English and Chinese (`-zh` suffix). Pick whichever you prefer — both write to the same `.migbot/config.json` and respect the `language` field for runtime output.

- **`/hmigbot-ios:i2h-init`** (or `-zh`) — auto-detect on first run; then confirm `ios` / `harmonyos` / `xcode` / `xcrun` / `simctl` / `deveco` / `hvigorw` / `hdc` paths in plain language. Sets `confirmed: true` on success. Also refreshes the `CLAUDE.md` marker block.
- **`/hmigbot-ios:i2h-build`** (or `-zh`) — validates `.migbot/config.json` paths and runs `hvigorw assembleHap`. Self-heals a misplaced `hvigorw`.
- **`/hmigbot-ios:i2h-run`** (or `-zh`) — runs the full migration pipeline (`i2h-spec → i2h-plan → i2h-execute → i2h-verify → i2h-retrospect`) with per-stage confirmation and auto-resume on re-entry. Redirects to `/i2h-init` if config is unconfirmed.

Per-stage skills also trigger via natural language ("生成 spec", "i2h-spec <feature>").

## Customizing skills

The 40 skills live under `skills/<id>/SKILL.md` inside the plugin. Because plugins are managed by Claude Code, edit them via local development (`claude --plugin-dir`) rather than editing the installed copy in `~/.claude/plugins/`. To disable a single skill, rename its `SKILL.md` to `SKILL.md.disabled` in your local copy.

## Permissions

Each command declares its own `allowed-tools` in its frontmatter, so the plugin's runtime permissions are scoped per-command. To allow the plugin's `i2h-tool` invocations project-wide (so you don't see per-call permission prompts), add this to your project's `.claude/settings.json`:

```json
{
  "permissions": {
    "allow": ["Bash(i2h-tool *)", "Bash(i2h-bootstrap *)"]
  }
}
```

## How language switching works

1. **Bootstrap time.** `i2h-bootstrap` reads `$LANG` and writes the matching `language` value into `.migbot/config.json` on first run.
2. **CLAUDE.md marker block.** `/i2h-init` step 8 renders a language-specific marker-guarded block into `CLAUDE.md`. The block is overwritten on every re-run of `/i2h-init`, so it always reflects the current `language` field.
3. **Skill / agent frontmatter.** Every skill and agent under `skills/` and `agents/` carries `output_language: from-config` in its frontmatter. Combined with the CLAUDE.md directive, this ensures Claude consistently produces output in the chosen language regardless of which language the skill body itself is written in.

To switch language post-install: edit `.migbot/config.json:language`, then re-run `/i2h-init` to refresh the marker block.

## Troubleshooting

- **`hvigorw not executable`.** `chmod +x <harmony-root>/hvigorw`, or set `hvigorw` in `.migbot/config.json` to point at a wrapper outside the project root.
- **`harmonyos path missing` / `ios path missing`.** Run `/i2h-init` again, or set absolute paths in `.migbot/config.json`.
- **`/i2h-run` always sends me to `/i2h-init`.** The config still has `confirmed: false`. Complete the `/i2h-init` flow and confirm at the end.
- **`xcrun` / `hdc` not found.** Either install the corresponding SDK and add it to `$PATH`, or set explicit absolute paths in `.migbot/config.json` and re-run `/i2h-init`.

## Tests

```bash
I2H_SKIP_DEVICE_CHECK=1 bash tests/i2h-tool.test.sh
```

The skip flag disables iOS simulator/device runtime checks so tests can run without an iOS simulator or connected device.
