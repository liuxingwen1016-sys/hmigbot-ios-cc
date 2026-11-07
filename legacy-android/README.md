# Legacy Android Reference Plugin

This opt-in compatibility bundle preserves the original Android migration workflow for maintenance, comparison, and reproducible regression checks. It is intentionally separate from the iOS plugin, so Claude Code will not route iOS requests to Android analyzers or consume Android baselines by accident. Install it only when an Android reference project is the actual input.

Marketplace installation: `/plugin install hmigbot-android-reference --marketplace liuxingwen1016-sys/hmigbot-ios-cc`.

这是从 `hmigbot-ios` 主插件中隔离出的历史 Android→HarmonyOS 参考包，包含 `a2h-*`、`android-*` Skill、旧 Android 代理、打包脚本和原始清单。它用于阅读和维护 `hmigbot-1.8.0` 的 Android 迁移链，不参与 iOS 主插件的自然语言路由，也不会被 `--plugin-dir ./migbot` 自动加载。

需要维护旧 Android 流水线时，请显式加载：

```bash
claude --plugin-dir ./legacy-android
```

其中的 Android 源码事实、布局图谱、设备截图和旧门禁只适用于 Android→HarmonyOS 兼容场景；iOS 迁移请使用仓库根目录 `migbot` 插件及 `i2h-*` Skill。
