# iOS → ArkTS Skill 货架

这是 `hmigbot-ios` 主插件的可加载 Skill 集合，面向 SwiftUI/UIKit 到 HarmonyOS ArkTS 的迁移。

主线入口为 `i2h-spec → i2h-plan → i2h-execute → i2h-verify → i2h-retrospect`，配套 `ios-*` 分析器、`swiftui-to-arkui`、资源转换器和 ArkTS 实现/验证能力。

Android→HarmonyOS 的原版 Skill 与 Android 代理已移到仓库根目录的 [`legacy-android/`](../../legacy-android)，不会随主插件目录自动加载。需要维护旧 Android 流水线时，显式使用 `--plugin-dir legacy-android` 或 marketplace 中的 `hmigbot-android-reference`。

主插件不把 Android 源码事实、Android UI 图谱或 Android 截图当作 iOS 输入；运行时证据缺失时只能记录 `DEFERRED`，不能合成 Android 基线。
