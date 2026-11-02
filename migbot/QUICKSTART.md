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
/hmigbot:a2h-init        # auto-detect + confirm paths (first run only)
/hmigbot:a2h-build       # verify HarmonyOS compiles
/hmigbot:a2h-run         # spec → plan → execute → verify → retrospect (pauses between stages, auto-resumes)
/hmigbot:a2h-build       # compile the migrated code
```

Use the `-zh` variant of any command for Chinese output (`/hmigbot:a2h-init-zh`, etc.). The language you pick at `/a2h-init` time is written into `.migbot/config.json:language` and a `CLAUDE.md` marker block, so subsequent runs of the English commands still render output in the chosen language.

Per-stage skills also trigger via natural language ("generate spec", "a2h-spec <feature>").

## Troubleshooting

- `hvigorw not executable` → `chmod +x <harmony-root>/hvigorw`.
- `harmonyos path missing` or `android path missing` → run `/hmigbot:a2h-init` again to fix.

Full reference: [DEVELOPER](./DEVELOPER.md).
