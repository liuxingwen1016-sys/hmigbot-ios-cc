# MigBot — Developer Guide

[中文文档](./DEVELOPER_CN.md)

For users who want to customize the plugin (skill selection, permissions, manual config). For the happy path see [QUICKSTART](./QUICKSTART.md).

## Install (full reference)

### As a Claude Code plugin (recommended)

```text
/plugin marketplace add fuxi-artifacts/hmigbot
/plugin install hmigbot@hmigbot
```

Then launch Claude Code from inside your HarmonyOS project root and run `/hmigbot:a2h-init`. On first run, the command invokes `a2h-bootstrap` (one of the executables shipped in the plugin's `bin/`) to auto-detect Android source path, DevEco install, hvigorw, adb, hdc, and locale. It writes a skeleton `.migbot/config.json` next to your `oh-package.json5`, then walks you through confirming each path.

### Local development

```bash
git clone https://github.com/fuxi-artifacts/hmigbot /path/to/migbot
cd /path/to/your-harmony-app
claude --plugin-dir /path/to/migbot
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
  "android": "../android-app",
  "harmonyos": ".",
  "hvigorw": "",
  "deveco": "/Applications/DevEco-Studio.app",
  "adb": "",
  "hdc": "",
  "language": "en",
  "confirmed": false
}
```

| Field | Notes |
|---|---|
| `android` | Path to the source Android project. Auto-detected by `a2h-bootstrap`; confirmed by `/a2h-init`. |
| `harmonyos` | Path to the HarmonyOS project; defaults to `.` because `/a2h-init` runs inside that root. |
| `hvigorw` | Optional override for the `hvigorw` executable. Empty (default) → `<harmonyos>/hvigorw`. Set this when your wrapper lives outside the project root or under a different name. |
| `deveco` | DevEco Studio install directory. Auto-detected at first run via `$PATH` + platform-specific scan (Windows: C/D/E/F drives; macOS: `/Applications`; Linux: `/opt`, `/usr/local`). May be empty (`/a2h-init` accepts `skip`). |
| `adb` / `hdc` | Optional explicit paths to the SDK CLIs. Empty means "rely on `$PATH`". `/a2h-init` auto-detects common locations. |
| `language` | `zh` or `en`. Set on first run by `a2h-bootstrap` from `$LANG`. Drives `a2h-tool` runtime messages and the `CLAUDE.md` marker block. To switch later, edit this field and re-run `/a2h-init`. |
| `confirmed` | Set to `true` by `/a2h-init` once the user has confirmed paths. `/a2h-run` redirects to `/a2h-init` when this is `false` or missing. |

`android` / `harmonyos` must exist; relative paths resolve against the install dir.

## Slash commands

Every command is available in English and Chinese (`-zh` suffix). Pick whichever you prefer — both write to the same `.migbot/config.json` and respect the `language` field for runtime output.

- **`/hmigbot:a2h-init`** (or `-zh`) — auto-detect on first run; then confirm `android` / `harmonyos` / `hvigorw` / `deveco` / `adb` / `hdc` paths in plain language. Sets `confirmed: true` on success. Also refreshes the `CLAUDE.md` marker block.
- **`/hmigbot:a2h-build`** (or `-zh`) — validates `.migbot/config.json` paths and runs `hvigorw assembleHap`. Self-heals a misplaced `hvigorw`.
- **`/hmigbot:a2h-run`** (or `-zh`) — runs the full migration pipeline (`a2h-spec → a2h-plan → a2h-execute → a2h-verify → a2h-retrospect`) with per-stage confirmation and auto-resume on re-entry. Redirects to `/a2h-init` if config is unconfirmed.

Per-stage skills also trigger via natural language ("生成 spec", "a2h-spec <feature>").

## Customizing skills

The 40 skills live under `skills/<id>/SKILL.md` inside the plugin. Because plugins are managed by Claude Code, edit them via local development (`claude --plugin-dir`) rather than editing the installed copy in `~/.claude/plugins/`. To disable a single skill, rename its `SKILL.md` to `SKILL.md.disabled` in your local copy.

## Permissions

Each command declares its own `allowed-tools` in its frontmatter, so the plugin's runtime permissions are scoped per-command. To allow the plugin's `a2h-tool` invocations project-wide (so you don't see per-call permission prompts), add this to your project's `.claude/settings.json`:

```json
{
  "permissions": {
    "allow": ["Bash(a2h-tool *)", "Bash(a2h-bootstrap *)"]
  }
}
```

## How language switching works

1. **Bootstrap time.** `a2h-bootstrap` reads `$LANG` and writes the matching `language` value into `.migbot/config.json` on first run.
2. **CLAUDE.md marker block.** `/a2h-init` step 8 renders a language-specific marker-guarded block into `CLAUDE.md`. The block is overwritten on every re-run of `/a2h-init`, so it always reflects the current `language` field.
3. **Skill / agent frontmatter.** Every skill and agent under `skills/` and `agents/` carries `output_language: from-config` in its frontmatter. Combined with the CLAUDE.md directive, this ensures Claude consistently produces output in the chosen language regardless of which language the skill body itself is written in.

To switch language post-install: edit `.migbot/config.json:language`, then re-run `/a2h-init` to refresh the marker block.

## Troubleshooting

- **`hvigorw not executable`.** `chmod +x <harmony-root>/hvigorw`, or set `hvigorw` in `.migbot/config.json` to point at a wrapper outside the project root.
- **`harmonyos path missing` / `android path missing`.** Run `/a2h-init` again, or set absolute paths in `.migbot/config.json`.
- **`/a2h-run` always sends me to `/a2h-init`.** The config still has `confirmed: false`. Complete the `/a2h-init` flow and confirm at the end.
- **`adb` / `hdc` not found.** Either install the corresponding SDK and add it to `$PATH`, or set explicit absolute paths in `.migbot/config.json` and re-run `/a2h-init`.

## Tests

```bash
A2H_SKIP_EMU_CHECK=1 bash tests/a2h-tool.test.sh
```

The skip flag disables emulator/adb/hdc runtime checks so tests can run without a real Android SDK or running emulator.
