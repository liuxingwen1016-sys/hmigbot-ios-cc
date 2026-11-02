---
description: Validate plugin config and run hvigorw assembleHap on the HarmonyOS repo
allowed-tools: Bash(.migbot/bin/a2h-tool *), Bash(.migbot/bin/a2h *)
---

1. Run `.migbot/bin/a2h-tool validate`. If it returns `{ok:false}`, list each failure to the user, suggest running `/a2h-init` to fix paths, and stop.
2. Otherwise run `.migbot/bin/a2h-tool build`. Stream output. Report final exit code.
3. Report this stage's token usage: run `Bash: .migbot/bin/a2h mark-stage a2h-build`. Best-effort and consent-gated — ignore its exit status (it never affects the build result).
