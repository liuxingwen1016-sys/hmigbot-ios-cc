# MigBot — Quick Start

```bash
# 1. Install the plugin inside Claude Code:
#      /plugin marketplace add fuxi-artifacts/hmigbot
#      /plugin install hmigbot@hmigbot
#
#    Or, for local development, point Claude at a checkout:
claude --plugin-dir /path/to/migbot

# 2. cd into your HarmonyOS project root. If you don't already have one,
#    create an empty project in DevEco Studio (File → New → Entry Ability).
cd /path/to/harmony-app
claude
```

Inside Claude Code:

```text
/hmigbot:i2h-init        # auto-detect + confirm paths (first run only)
/hmigbot:i2h-build       # verify HarmonyOS compiles
/hmigbot:i2h-run         # spec → plan → execute → verify → retrospect (pauses between stages, auto-resumes)
/hmigbot:i2h-build       # compile the migrated code
```

Use the `-zh` variant of any command for Chinese output (`/hmigbot:i2h-init-zh`, etc.). The language you pick at `/i2h-init` time is written into `.migbot/config.json:language` and a `CLAUDE.md` marker block, so subsequent runs of the English commands still render output in the chosen language.

Per-stage skills also trigger via natural language ("generate spec", "i2h-spec <feature>").

## Troubleshooting

- `hvigorw not executable` → `chmod +x <harmony-root>/hvigorw`.
- `harmonyos path missing` or `iOS path missing` → run `/hmigbot:i2h-init` again to fix.

Full reference: [DEVELOPER](./DEVELOPER.md).
