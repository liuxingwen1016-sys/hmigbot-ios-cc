---
description: 校验插件配置并在 HarmonyOS 仓上跑 hvigorw assembleHap
allowed-tools: Bash(.migbot/bin/a2h-tool *), Bash(.migbot/bin/a2h *)
---

1. 跑 `.migbot/bin/a2h-tool validate`。返回 `{ok:false}` → 把每条失败列给用户，建议跑 `/a2h-init` 修正路径，然后停下。
2. 否则跑 `.migbot/bin/a2h-tool build`。流式输出。报告最终退出码。
3. 上报本阶段 token 用量：跑 `Bash: .migbot/bin/a2h mark-stage a2h-build`。尽力而为、受授权门控——忽略其退出码（绝不影响构建结果）。
