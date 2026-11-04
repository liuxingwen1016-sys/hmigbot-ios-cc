# i2h-verify 深度分析与改造方案

**项目**: hmigbot-ios 工具改造  
**阶段**: i2h-verify 优化  
**分析时间**: 2024-11-03  
**分析人**: Claude Opus 5.5

---

## 📋 目录

1. [原版 a2h-verify 实现逻辑](#1-原版-a2h-verify-实现逻辑)
2. [调用的资源清单](#2-调用的资源清单)
3. [Android vs iOS 差异分析](#3-android-vs-ios-差异分析)
4. [改造方案](#4-改造方案)
5. [实施计划](#5-实施计划)

---

## 1. 原版 a2h-verify 实现逻辑

### 1.1 核心架构

**Pipeline 第四步定位**：
- 职责：验证 Android→HarmonyOS 迁移产出
- 输入：迁移完成的 HarmonyOS 工程
- 输出：`spec/verify-report.md` 完整验证报告

### 1.2 五项检查体系

| 编号 | 检查项 | 执行方式 | 是否可选 | 通过条件 |
|------|--------|---------|---------|---------|
| CHECK-1 | 静态分析 | 主对话执行 | ❌ 固定 | ERROR 为 0；WARN 附报告 |
| CHECK-2 | App 身份校验 | 主对话执行 | ❌ 固定 | FAIL 为 0；WARN 附报告 |
| CHECK-3 | 视觉对齐 | `arkts-visual-verify` | ✅ 可选 | 完成范围内实测且无未解决差异 |
| CHECK-4 | 单元测试 | `arkts-ut-verifier` | ✅ 可选 | 全范围实际 GREEN，无未验证设计点 |
| CHECK-5 | 行为验证 | `arkts-behavior-verify` | ✅ 可选 | 只报告，不判全域 PASS |

### 1.3 执行流程

```
开始
 ↓
用户选择可选项 (CHECK-3/4/5)
 ↓
执行 CHECK-1: 静态分析
 ↓
执行 CHECK-2: App 身份校验
 ↓
按顺序执行已选项: CHECK-3 → CHECK-4 → CHECK-5
 ↓
失败处理与修复回环 (最多 3 轮)
 ↓
汇总到 spec/verify-report.md
 ↓
上报用量 (count-lines + mark-stage)
 ↓
结束
```

### 1.4 CHECK-1: 静态分析

**扫描内容**（针对 Android → HarmonyOS）：

| 检查项 | 定位方式 | 级别 | 原因 |
|--------|---------|------|------|
| `any` 类型 | 搜索 `\bany\b` | ERROR | ArkTS 强类型要求 |
| 旧 `@ohos.*` 导入 | 搜索 `@ohos\.` | WARN | API 版本迁移建议 |
| SQL 拼接 | 搜索 SQL 关键字 | ERROR | SQL 注入风险 |
| `as` 类型断言 | 搜索 `\bas\b` | WARN | 类型安全警告 |
| `eval()` | 搜索 `\beval\s*\(` | ERROR | 动态执行风险 |
| `aboutToAppear` 路由参数 | 定位 `aboutToAppear` | ERROR | 生命周期错误 |

**Android 特性**：
- 针对 Java/Kotlin → ArkTS 的迁移特点
- 关注 Android 原生 API 的错误使用

### 1.5 CHECK-2: App 身份校验

**检查项**：

| 项目 | 检查规则 | 判定 | Android 上下文 |
|------|---------|------|---------------|
| bundleName | 仍匹配 `com.example.*` | FAIL | Android package name 默认值 |
| vendor | 仍为 `example` | FAIL | 示例厂商名 |
| versionName | 仍为 `1.0.0` | WARN | 未与 Android APK 版本同步 |
| app_name | 与锁定名称不一致 | FAIL | 从 `.migbot/config.json` 读取 |
| 前景/背景图标 | ≤ 1 KB | WARN | 疑似默认图标 |
| 自适应图标 | 引用错误 | FAIL | Android adaptive icon 迁移 |

**数据源**：
- `.migbot/config.json` 的 `app_name`（init 阶段锁定）
- `AppScope/app.json5`
- 资源文件

### 1.6 CHECK-3: 视觉对齐

**委托 `arkts-visual-verify`**：
- 双端真实页面截图
- 比对和 visual-fixer 调度
- 读取产物：
  - `spec/visual-verify/report.md`
  - `spec/fix/_state.yaml` 和当前轮摘要
  - `ui/`、`feat/` 未解决问题

**状态映射**：
- PASS：范围内验证完成，无未解决差异
- FAIL-visual：仅有 ALIGN 纯视觉差异（建议项）
- FAIL-functional：崩溃、URL_MISMATCH、IMPL_MISSING
- PARTIAL：比对未完成或修复后尚未复测

### 1.7 CHECK-4: 单元测试

**委托 `arkts-ut-verifier`**：
- 默认 `MODE=verify_fix`
- 仅验证时 `MODE=verify_only`
- Android 源码：`ANDROID_SOURCE_ROOT` 入口

**读取产物**：
- `spec/verify/ut/ut-report.md`
- `_state.yaml` 和当前轮 `_ut_summary.md`
- 修复循环退出摘要

**判定**：
- PASS：全范围 GREEN，无未验证设计点
- FAIL：有 RED、ERROR 或最终 FAIL
- PARTIAL：CONVERGED、缺证据、外部前置阻塞

### 1.8 CHECK-5: 行为验证（非门控）

**特殊定位**：
- 可扩展的行为验证总入口
- 技术名称：`arkts-behavior-verify`
- **只报告，不参与整体判定**

**两条 lane**：
- CHECK-5.1：设置候选审查与修复
- CHECK-5.2：点击 core 候选审查修复

**统一调用**：
- 只调用一次 `Skill(arkts-behavior-verify)`
- 传入参数：`android_root`、`arkts_root`、`out`、`max_agents`
- 默认 `repair_mode=single-round`
- 明确授权才执行 `--full-repair` 第二轮

**状态映射**：
- WARN：已修改/安装，但正确性未验证
- DEFERRED：前置不满足
- ERROR：构建/安装/流程失败

**非门控特性**：
- 不加入基础及已选视觉/UT 范围结论
- 不触发 `failure-loop.md` 的 a2h-execute 回环
- 不决定 `ui-manifest.md` 的 `verified` 回写
- 源码修复后需复检 CHECK-1/2 及已选 CHECK-3/4

### 1.9 失败处理与修复回环

**修复归属**：

| 失败来源 | 处理方式 |
|---------|---------|
| CHECK-1 静态 ERROR | 生成执行阶段修复任务 |
| CHECK-2 身份 FAIL | 生成配置/资源修复任务 |
| CHECK-3 功能性失败 | 读取 visual verifier 修复结果，遗留项进入外层回环 |
| CHECK-3 纯 ALIGN 差异 | 记建议项，由 visual verifier 处理 |
| CHECK-4 | 由 UT verifier 按选定模式处理 |
| CHECK-5 | 只报告，不触发 a2h-execute |

**外层回环**（最多 3 轮）：
1. 提取任务 → `spec/plans/plan-fix-<timestamp>.md`
2. 委托 `a2h-execute` 执行修复
3. 读取改动，复检并更新报告

### 1.10 收尾：上报用量

```bash
# 1. 统计 Android + HarmonyOS 两侧代码行，上传"迁移完成信号"
.migbot/bin/a2h count-lines

# 2. 上报本阶段 token 用量（usage.v2 快照）
.migbot/bin/a2h mark-stage a2h-verify
```

**关键点**：
- `count-lines` 是迁移"已完成"的判定点
- 服务端凭 HarmonyOS total 判定完成
- 生命周期 hook 上传的会话切片归属到 verify 阶段

---

## 2. 调用的资源清单

### 2.1 SKILL.md

**文件**: `/migbot/skills/a2h-verify/SKILL.md`
- 106 行
- 定义五项检查体系
- 执行流程和状态判定规则

### 2.2 References (5 个文件)

| 文件名 | 行数 | 作用 |
|--------|------|------|
| `static-and-identity.md` | 34 | CHECK-1/2 执行规则 |
| `device-verification.md` | 47 | CHECK-3/4 调用与结果读取 |
| `check5-behavior-verify.md` | 105 | CHECK-5 执行契约、状态映射 |
| `failure-loop.md` | 37 | 外层修复范围、退出条件和复检 |
| `verify-report-template.md` | 84 | 五项结果与证据汇总模板 |

**总计**：~307 行

### 2.3 Scripts (1 个核心脚本)

| 文件名 | 类型 | 作用 |
|--------|------|------|
| `check5_result_adapter.py` | Python launcher | CHECK-5 结果适配器（调用编译版二进制）|

**编译版二进制**：
- `scripts/bin/macos-arm64/_entry.dist/`
- `scripts/bin/windows-x64/_entry.dist/`
- 使用 Nuitka 编译的 Python 程序

### 2.4 外部 Skills 依赖

| Skill | 用途 | 调用阶段 |
|-------|------|---------|
| `arkts-visual-verify` | 视觉对齐验证 | CHECK-3 |
| `arkts-ut-verifier` | 单元测试验证 | CHECK-4 |
| `arkts-behavior-verify` | 行为验证（设置+点击）| CHECK-5 |
| `a2h-execute` | 执行修复任务 | 失败修复回环 |

### 2.5 Templates

**无模板文件** - 报告模板直接内嵌在 `verify-report-template.md` reference 中

### 2.6 产物位置

```
spec/
├── verify-report.md                    # 最终汇总报告
├── verify/
│   ├── check5/
│   │   ├── CHECK5_SUMMARY.md          # CHECK-5 摘要
│   │   └── behavior-effect/<run-id>/  # 行为验证运行目录
│   │       ├── result.json
│   │       ├── behavior-effect-adapter.json
│   │       └── ...
│   ├── ut/
│   │   ├── ut-report.md
│   │   └── _state.yaml
│   └── visual-verify/
│       ├── report.md
│       └── ...
├── plans/
│   └── plan-fix-<timestamp>.md        # 修复计划
└── gate-release/
    └── verify-focus.json              # 迁移放行项
```

---

## 3. Android vs iOS 差异分析

### 3.1 CHECK-1: 静态分析差异

#### Android 特定检查

| 检查项 | Android 上下文 | iOS 对应 | 是否需要 |
|--------|---------------|---------|---------|
| `any` 类型 | Java/Kotlin 动态类型遗留 | Swift `Any` 类型遗留 | ✅ **需要** |
| 旧 `@ohos.*` 导入 | Android SDK 迁移路径 | 同样适用（API 版本） | ✅ **需要** |
| SQL 拼接 | Android SQLite 常见问题 | iOS CoreData/SQLite | ✅ **需要** |
| `as` 类型断言 | Kotlin `as` 强转 | Swift `as` / `as!` / `as?` | ✅ **需要** |
| `eval()` | 罕见，但需检查 | JavaScript 桥接可能用 | ✅ **需要** |
| `aboutToAppear` 路由参数 | Android Activity 参数传递 | iOS ViewController 参数 | ✅ **需要** |

**iOS 特有问题需要添加**：

| 检查项 | iOS 特性 | 级别 | 原因 |
|--------|---------|------|------|
| 强制解包 `!` | Swift 特性 | WARN | 可能导致崩溃 |
| `@escaping` 闭包 | Swift 闭包逃逸 | WARN | 生命周期管理 |
| `weak`/`unowned` 遗留 | Swift 内存管理 | WARN | ArkTS 不需要手动管理 |
| `@objc` / `@objcMembers` | OC 互操作 | WARN | 迁移遗留 |
| `#available` / `@available` | iOS 版本检查 | WARN | HarmonyOS 不适用 |
| `DispatchQueue` | GCD 调度 | ERROR | 需要改为 ArkTS 并发 |
| `NotificationCenter` | iOS 通知机制 | WARN | 需要改为 Emitter |
| `UserDefaults` | iOS 本地存储 | ERROR | 必须改为 Preferences |
| `UIKit` / `SwiftUI` 导入 | iOS UI 框架 | ERROR | 迁移未完成 |

**差异总结**：
- Android 版：6 项检查（Java/Kotlin 特性）
- iOS 版需要：6 项通用 + **9 项 iOS 特有** = **15 项**

### 3.2 CHECK-2: App 身份校验差异

#### Android 特定

| 项目 | Android 默认值 | iOS 默认值 | 检查规则调整 |
|------|---------------|-----------|-------------|
| bundleName | `com.example.*` | `com.example.*` | ✅ 相同 |
| vendor | `example` | `example` | ✅ 相同 |
| versionName | `1.0.0` | `1.0` / `1.0.0` | ✅ 相同（格式略不同）|
| app_name | 从 AndroidManifest.xml | 从 Info.plist `CFBundleDisplayName` | ⚠️ **读取源不同** |
| 图标 | `mipmap-*/ic_launcher.png` | `Assets.xcassets/AppIcon.appiconset/` | ⚠️ **路径完全不同** |
| 自适应图标 | `layered_image.json` | 无（iOS 用多尺寸图标）| ⚠️ **结构不同** |

**iOS 特有配置**：

| 项目 | iOS 来源 | HarmonyOS 对应 | 检查规则 |
|------|---------|---------------|---------|
| Bundle Identifier | Info.plist `CFBundleIdentifier` | bundleName | 一致性检查 |
| Display Name | `CFBundleDisplayName` | app.json5 label | 一致性检查 |
| Version | `CFBundleShortVersionString` | versionName | 同步检查 |
| Build Number | `CFBundleVersion` | versionCode | 同步检查 |
| Icon | Assets.xcassets | layered-image.json | 存在性检查 |
| Launch Screen | LaunchScreen.storyboard | - | 不检查 |

**差异总结**：
- 检查项数量相同（6 项）
- **配置文件读取逻辑需要重写**
- **图标检查规则需要适配**

### 3.3 CHECK-3: 视觉对齐差异

#### Android 实现

- 双端设备：Android (`adb`) + HarmonyOS (`hdc`)
- 截图方式：`adb shell screencap`
- 比对算法：由 `arkts-visual-verify` 实现

#### iOS 实现需求

| 对比维度 | Android | iOS | 差异 |
|---------|---------|-----|------|
| 设备连接 | `adb devices` | `xcrun simctl list` / `idevice_id -l` | ⚠️ **命令不同** |
| 截图方式 | `adb shell screencap` | `xcrun simctl io screenshot` / `idevicescreenshot` | ⚠️ **命令不同** |
| 应用启动 | `adb shell am start` | `xcrun simctl launch` / iOS 手动 | ⚠️ **命令不同** |
| 应用安装 | `adb install` | `xcrun simctl install` / `ios-deploy` | ⚠️ **命令不同** |
| 比对算法 | 感知哈希 | 感知哈希 | ✅ 相同 |

**iOS 特殊情况**：
1. **模拟器 vs 真机**：
   - 模拟器：`xcrun simctl` 命令
   - 真机：需要 `libimobiledevice` 工具链（`idevice_id`、`idevicescreenshot`、`ideviceinstaller`）
   
2. **应用签名**：
   - iOS 真机需要开发者证书签名
   - HarmonyOS 也需要签名（相同）

3. **应用 Bundle ID**：
   - Android：`package name` (com.example.app)
   - iOS：`Bundle Identifier` (com.example.app)
   - 两者格式相同，但来源不同

**调用 `arkts-visual-verify` 的参数差异**：

```bash
# Android 版
arkts-visual-verify \
  --android-root /path/to/android \
  --harmonyos-root /path/to/harmonyos \
  --android-device <adb-device-id> \
  --harmonyos-device <hdc-device-id>

# iOS 版需要
arkts-visual-verify \
  --ios-root /path/to/ios \                    # ⚠️ 参数名不同
  --harmonyos-root /path/to/harmonyos \
  --ios-device <xcrun-device-id> \            # ⚠️ 参数名不同
  --ios-device-type <simulator|physical> \    # ⚠️ 新增参数
  --harmonyos-device <hdc-device-id>
```

**差异总结**：
- 核心逻辑相同（双端截图 + 比对）
- **设备检测和控制命令完全不同**
- **需要判断 iOS 模拟器 vs 真机**
- **可能需要修改 `arkts-visual-verify` 支持 iOS**

### 3.4 CHECK-4: 单元测试差异

#### Android 实现

- 读取 Android 源码：`ANDROID_SOURCE_ROOT`
- 测试框架：JUnit / Espresso
- 测试用例位置：`src/androidTest/` 或 `src/test/`

#### iOS 实现需求

| 对比维度 | Android | iOS | 差异 |
|---------|---------|-----|------|
| 源码位置 | `ANDROID_SOURCE_ROOT` | `IOS_SOURCE_ROOT` | ⚠️ 参数名不同 |
| 测试框架 | JUnit / Espresso | XCTest / XCUITest | ⚠️ 框架不同 |
| 测试位置 | `src/test/` / `src/androidTest/` | `<Project>Tests/` / `<Project>UITests/` | ⚠️ 路径不同 |
| 测试文件 | `*Test.java` / `*Test.kt` | `*Tests.swift` | ⚠️ 命名约定不同 |
| 断言 | `assertEquals()`, `assertTrue()` | `XCTAssertEqual()`, `XCTAssertTrue()` | ⚠️ API 不同 |

**iOS 特有测试特征**：

| 特征 | iOS | ArkTS | 需要映射 |
|------|-----|-------|---------|
| 测试类继承 | `XCTestCase` | 无需继承 | ✅ 需要 |
| 测试方法前缀 | `func test*()` | `it('...')` | ✅ 需要 |
| 异步测试 | `XCTestExpectation` | `done()` callback | ✅ 需要 |
| UI 测试 | `XCUIApplication` | ArkUI 组件测试 | ✅ 需要 |
| Mock/Stub | `protocol` + 实现 | 接口 + 实现 | ✅ 需要 |

**调用 `arkts-ut-verifier` 的参数差异**：

```bash
# Android 版
arkts-ut-verifier \
  --android-source-root /path/to/android \
  --harmonyos-root /path/to/harmonyos \
  --mode verify_fix

# iOS 版需要
arkts-ut-verifier \
  --ios-source-root /path/to/ios \              # ⚠️ 参数名不同
  --harmonyos-root /path/to/harmonyos \
  --mode verify_fix \
  --test-framework xctest                        # ⚠️ 新增：指定测试框架
```

**差异总结**：
- 参数名需要从 `android` 改为 `ios`
- 测试框架识别逻辑不同
- **可能需要修改 `arkts-ut-verifier` 支持 XCTest**

### 3.5 CHECK-5: 行为验证差异

#### Android 实现

- 设置 lane：审查系统设置使用
- 点击 lane：审查交互流程
- Oracle：Android APK 实际运行行为

#### iOS 实现需求

| 对比维度 | Android | iOS | 差异 |
|---------|---------|-----|------|
| Oracle 应用 | Android APK | iOS IPA / App | ⚠️ 格式不同 |
| 设备运行 | `adb shell am start` | `xcrun simctl launch` | ⚠️ 命令不同 |
| 日志收集 | `adb logcat` | `xcrun simctl spawn log` / `idevicesyslog` | ⚠️ 命令不同 |
| 应用状态 | `adb shell dumpsys` | `xcrun simctl` / Instruments | ⚠️ 工具不同 |

**iOS 特有行为特征**：

| 特征 | iOS | HarmonyOS | 验证方式 |
|------|-----|----------|---------|
| 权限请求 | `Info.plist` + 运行时弹窗 | `module.json5` + 运行时 | 对比权限列表 |
| 后台模式 | `UIBackgroundModes` | 后台任务 API | 验证后台行为 |
| 通知 | `UNUserNotificationCenter` | `notificationManager` | 验证通知功能 |
| 位置服务 | `CLLocationManager` | `geoLocationManager` | 验证定位功能 |
| 相机/相册 | `UIImagePickerController` | `picker` | 验证媒体访问 |

**调用 `arkts-behavior-verify` 的参数差异**：

```bash
# Android 版
arkts-behavior-verify \
  --android-root /path/to/android \
  --arkts-root /path/to/harmonyos \
  --out <run-dir> \
  --max-agents 6

# iOS 版需要
arkts-behavior-verify \
  --ios-root /path/to/ios \                     # ⚠️ 参数名不同
  --arkts-root /path/to/harmonyos \
  --out <run-dir> \
  --max-agents 6 \
  --ios-device-type <simulator|physical>        # ⚠️ 新增参数
```

**差异总结**：
- 核心逻辑相同（设置 + 点击验证）
- **Oracle 来源从 APK 改为 IPA/App**
- **设备控制命令完全不同**
- **可能需要修改 `arkts-behavior-verify` 支持 iOS**

### 3.6 设备管理差异汇总

| 操作 | Android | iOS 模拟器 | iOS 真机 |
|------|---------|-----------|---------|
| 列出设备 | `adb devices` | `xcrun simctl list devices` | `idevice_id -l` |
| 安装应用 | `adb install app.apk` | `xcrun simctl install <device> app.app` | `ideviceinstaller -i app.ipa` |
| 启动应用 | `adb shell am start -n <package>/<activity>` | `xcrun simctl launch <device> <bundle-id>` | 手动或 `ios-deploy` |
| 截图 | `adb shell screencap -p /sdcard/screen.png` | `xcrun simctl io <device> screenshot <file>` | `idevicescreenshot <file>` |
| 日志 | `adb logcat` | `xcrun simctl spawn <device> log stream` | `idevicesyslog` |
| 文件传输 | `adb push/pull` | 直接访问模拟器路径 | `idevice` 工具 |

**关键差异**：
1. **命令体系完全不同**：`adb` vs `xcrun simctl` vs `idevice*`
2. **iOS 需要区分模拟器和真机**
3. **iOS 真机需要额外工具链**：`libimobiledevice`

### 3.7 配置文件差异

| 配置项 | Android | iOS | HarmonyOS |
|--------|---------|-----|-----------|
| 应用清单 | `AndroidManifest.xml` | `Info.plist` | `module.json5` |
| 包名/Bundle ID | `package` | `CFBundleIdentifier` | `bundleName` |
| 版本名 | `versionName` | `CFBundleShortVersionString` | `versionName` |
| 版本号 | `versionCode` | `CFBundleVersion` | `versionCode` |
| 应用名 | `android:label` | `CFBundleDisplayName` | `label` (string.json) |
| 图标 | `android:icon` (mipmap) | `CFBundleIcons` (Assets.xcassets) | `icon` (media/) |
| 权限 | `<uses-permission>` | `Info.plist` keys | `requestPermissions` |

**`.migbot/config.json` 需要包含的 iOS 信息**：

```json
{
  "ios_bundle_id": "com.example.app",
  "ios_project_path": "/path/to/iOS/Project.xcodeproj",
  "ios_scheme": "MyApp",
  "ios_device_type": "simulator",  // 或 "physical"
  "xcrun": "/usr/bin/xcrun",
  "idevice_tools": "/usr/local/bin"
}
```

### 3.8 迁移放行项差异

**Android 版**：
- `spec/gate-release/verify-focus.json`
- 由 `a2h-spec` 的 `scripts/gate_ledger.py check` 产出
- 记录工具缺口、未达标放行、阶段不可判定

**iOS 版**：
- 同样需要 `spec/gate-release/verify-focus.json`
- 由 `i2h-spec` 的对应脚本产出
- **需要确认 i2h-spec 是否已实现此功能**

---

## 4. 改造方案

### 4.1 总体策略

**原则**：
1. ✅ **保持架构一致** - 五项检查体系不变
2. ✅ **适配 iOS 特性** - 调整检查规则和数据源
3. ✅ **完全对齐原版** - 100% 功能对等
4. ✅ **复用外部 Skills** - 优先参数适配，必要时修改 Skills

### 4.2 SKILL.md 改造

#### 改动点

| 章节 | 改动类型 | 详情 |
|------|---------|------|
| frontmatter | 名称替换 | `a2h-verify` → `i2h-verify` |
| description | 上下文调整 | `Android→HarmonyOS` → `iOS→HarmonyOS` |
| 输入与范围 | 路径调整 | `Android 源码根目录` → `iOS 源码根目录` |
| CHECK-1 规则 | ⚠️ **新增** | 添加 9 项 iOS 特有检查 |
| CHECK-2 规则 | ⚠️ **重写** | 适配 iOS 配置文件和图标结构 |
| CHECK-3/4/5 调用 | 参数调整 | `--android-*` → `--ios-*` |
| 收尾命令 | 命令替换 | `.migbot/bin/a2h` → `.migbot/bin/i2h` |

#### 预估工作量

- 保留：~60% 内容（架构、流程、判定逻辑）
- 调整：~30% 内容（参数、命令、配置路径）
- 新增：~10% 内容（iOS 特有检查规则）
- **预计**: ~400-500 行（Android 版 106 行的 4-5 倍，因为需要详细说明 iOS 特性）

### 4.3 References 改造

#### 4.3.1 `static-and-identity.md`

**改动**：⚠️ **重写 80%**

**CHECK-1 新增规则**（9 项 iOS 特有）：

```markdown
| 检查项 | 定位与复核方式 | 级别 |
|--------|---------------|------|
| 强制解包 `!` | 搜索 `\w+!\.` 或 `\w+!\s*$`，确认强制解包 | WARN |
| `@escaping` 闭包 | 搜索 `@escaping`，复核是否已正确转换 | WARN |
| `weak`/`unowned` | 搜索 `\bweak\b` / `\bunowned\b`，ArkTS 不需要 | WARN |
| `@objc` / `@objcMembers` | 搜索 `@objc`，迁移遗留标记 | WARN |
| `#available` / `@available` | 搜索 `available`，iOS 版本检查已无意义 | WARN |
| `DispatchQueue` | 搜索 `DispatchQueue`，需改为 TaskPool/Worker | ERROR |
| `NotificationCenter` | 搜索 `NotificationCenter`，需改为 Emitter | WARN |
| `UserDefaults` | 搜索 `UserDefaults`，必须改为 Preferences | ERROR |
| `UIKit` / `SwiftUI` 导入 | 搜索 `import UIKit` / `import SwiftUI` | ERROR |
```

**CHECK-2 重写**：

```markdown
## CHECK-2：App 身份校验

读取 iOS 源码的 `Info.plist` 和 HarmonyOS 的 `AppScope/app.json5`、模块配置及实际引用的字符串/图标资源；名称以 **init 锁定的 `.migbot/config.json` 的 `app_name`** 为依据。

| 项目 | 检查规则 | 判定 | iOS 数据源 |
|------|---------|------|-----------|
| bundleName | 仍匹配 `com.example.*` | FAIL | 对比 iOS `CFBundleIdentifier` |
| vendor | 仍为 `example` | FAIL | - |
| versionName | 与 iOS `CFBundleShortVersionString` 不一致 | WARN | Info.plist |
| versionCode | 与 iOS `CFBundleVersion` 不一致 | WARN | Info.plist |
| app_name | 与 iOS `CFBundleDisplayName` 不一致 | FAIL | Info.plist |
| 应用图标 | `layered_image.json` 不存在或引用错误 | FAIL | 对比 iOS `Assets.xcassets/AppIcon.appiconset/` |
| 图标尺寸 | 前景/背景图 ≤ 1 KB | WARN | 疑似默认图 |
```

#### 4.3.2 `device-verification.md`

**改动**：⚠️ **调整 50%**

**CHECK-3 调用参数**：

```markdown
## CHECK-3：视觉对齐

调用 `arkts-visual-verify`，传入：
- `--ios-root <ios-project-root>`
- `--harmonyos-root <harmonyos-project-root>`
- `--ios-device <device-id>`
- `--ios-device-type <simulator|physical>`
- `--harmonyos-device <hdc-device-id>`
- 当前任务的修复授权范围

**iOS 设备检测**：
1. 模拟器：`xcrun simctl list devices | grep Booted`
2. 真机：`idevice_id -l`（需要 libimobiledevice）

**设备前置短路条件**：
- iOS 设备不可用 → 记 DEFERRED
- HarmonyOS 设备不可用 → 记 DEFERRED
- 两者都可用 → 继续执行
```

**CHECK-4 调用参数**：

```markdown
## CHECK-4：单元测试

调用 `arkts-ut-verifier`，传入：
- `--ios-source-root <ios-project-root>`
- `--harmonyos-root <harmonyos-project-root>`
- `--mode verify_fix` / `verify_only`
- `--test-framework xctest`

**iOS 测试位置**：
- 单元测试：`<Project>Tests/`
- UI 测试：`<Project>UITests/`
- 文件命名：`*Tests.swift`
```

#### 4.3.3 `check5-behavior-verify.md`

**改动**：⚠️ **调整 30%**

**调用参数调整**：

```markdown
2. 主对话调用 `Skill(arkts-behavior-verify)` 一次，传：
   - `ios_root`（原 `android_root`）
   - `arkts_root`
   - `out=<hmos-project>/spec/verify/check5/behavior-effect/<run-id>`
   - `max_agents`（默认 6）
   - `ios_device_type=<simulator|physical>`（新增）
```

**Oracle 来源说明**：

```markdown
- iOS Oracle：从 iOS 项目构建的 IPA 或 .app
- 运行环境：iOS 模拟器或真机
- 日志收集：`xcrun simctl spawn log` 或 `idevicesyslog`
```

#### 4.3.4 `failure-loop.md`

**改动**：✅ **保持 95%**

- 仅调整命令路径：`a2h-execute` → `i2h-execute`

#### 4.3.5 `verify-report-template.md`

**改动**：✅ **保持 90%**

- 调整描述：`Android 源码` → `iOS 源码`
- 调整产物路径：`android_app_name` → `ios_app_name`

### 4.4 Scripts 改造

#### 4.4.1 `check5_result_adapter.py`

**改动**：✅ **保持 100%**

- 这是一个通用的适配器 launcher
- 调用编译版二进制，不涉及 Android/iOS 差异
- **无需修改**

**但需要**：
- 确认 `arkts-behavior-verify` 已支持 iOS
- 或者在 `arkts-behavior-verify` 中添加 iOS 支持

#### 4.4.2 新增脚本需求

| 脚本名 | 作用 | 实现方式 | 优先级 |
|--------|------|---------|--------|
| `ios_device_checker.py` | 检测 iOS 设备（模拟器/真机）| Python | ⭐⭐⭐⭐⭐ |
| `ios_config_parser.py` | 解析 Info.plist 和 Assets | Python | ⭐⭐⭐⭐⭐ |
| `ios_static_analyzer.py` | iOS 特有静态分析规则 | Python + rg | ⭐⭐⭐⭐ |

### 4.5 外部 Skills 适配需求

#### 是否需要修改外部 Skills？

| Skill | 是否需要修改 | 修改范围 | 优先级 |
|-------|------------|---------|--------|
| `arkts-visual-verify` | ⚠️ **可能需要** | 添加 iOS 设备控制逻辑 | ⭐⭐⭐⭐⭐ |
| `arkts-ut-verifier` | ⚠️ **可能需要** | 添加 XCTest 识别和映射 | ⭐⭐⭐⭐ |
| `arkts-behavior-verify` | ⚠️ **可能需要** | 添加 iOS Oracle 支持 | ⭐⭐⭐ |
| `i2h-execute` | ✅ **已存在** | 用于修复回环 | - |

**建议策略**：
1. **先尝试参数传递** - 通过 `--ios-*` 参数，Skills 内部自动适配
2. **必要时提交 PR** - 如果 Skills 不支持 iOS，提交功能增强
3. **临时方案** - 在 `i2h-verify` 中实现简化版，标注 TODO

### 4.6 文件结构对比

#### Android 版

```
a2h-verify/
├── SKILL.md (106 行)
├── references/
│   ├── static-and-identity.md (34 行)
│   ├── device-verification.md (47 行)
│   ├── check5-behavior-verify.md (105 行)
│   ├── failure-loop.md (37 行)
│   └── verify-report-template.md (84 行)
└── scripts/
    ├── check5_result_adapter.py (30 行)
    ├── bin/
    │   ├── macos-arm64/_entry.dist/
    │   └── windows-x64/_entry.dist/
    └── tests/
        └── test_check5_result_adapter.py
```

#### iOS 版规划

```
i2h-verify/
├── SKILL.md (~450 行, +324 行)
├── references/
│   ├── static-and-identity.md (~150 行, +116 行) ⭐⭐⭐⭐⭐
│   ├── device-verification.md (~80 行, +33 行) ⭐⭐⭐⭐⭐
│   ├── check5-behavior-verify.md (~130 行, +25 行) ⭐⭐⭐⭐
│   ├── failure-loop.md (~40 行, +3 行) ⭐⭐
│   ├── verify-report-template.md (~90 行, +6 行) ⭐⭐⭐
│   └── ios-specific-checks.md (NEW, ~200 行) ⭐⭐⭐⭐ 
├── scripts/
│   ├── check5_result_adapter.py (30 行, 0 改动) ✅
│   ├── ios_device_checker.py (NEW, ~150 行) ⭐⭐⭐⭐⭐
│   ├── ios_config_parser.py (NEW, ~200 行) ⭐⭐⭐⭐⭐
│   ├── ios_static_analyzer.py (NEW, ~300 行) ⭐⭐⭐⭐
│   ├── bin/ (复用)
│   └── tests/
│       ├── test_check5_result_adapter.py (复用)
│       ├── test_ios_device_checker.py (NEW)
│       ├── test_ios_config_parser.py (NEW)
│       └── test_ios_static_analyzer.py (NEW)
└── templates/
    └── (考虑是否需要模板)
```

**新增文件说明**：

| 文件 | 作用 | 工作量估算 |
|------|------|-----------|
| `ios-specific-checks.md` | iOS 特有检查规则详细说明 | 2-3 小时 |
| `ios_device_checker.py` | iOS 设备检测（模拟器/真机）| 3-4 小时 |
| `ios_config_parser.py` | 解析 Info.plist 和 Assets | 4-5 小时 |
| `ios_static_analyzer.py` | iOS 特有静态分析 | 6-8 小时 |

### 4.7 产物对比

#### Android 版产物

```
spec/
├── verify-report.md
├── verify/
│   ├── check5/
│   │   ├── CHECK5_SUMMARY.md
│   │   └── behavior-effect/<run-id>/
│   ├── ut/
│   └── visual-verify/
└── plans/
    └── plan-fix-<timestamp>.md
```

#### iOS 版产物（完全相同）

```
spec/
├── verify-report.md                    # ✅ 相同
├── verify/
│   ├── check5/
│   │   ├── CHECK5_SUMMARY.md          # ✅ 相同
│   │   └── behavior-effect/<run-id>/  # ✅ 相同
│   ├── ut/
│   └── visual-verify/
└── plans/
    └── plan-fix-<timestamp>.md        # ✅ 相同
```

**无需改动** - 产物结构完全一致

---

## 5. 实施计划

### 5.1 Phase 1: 核心文档改造（必须）

**目标**：完成 SKILL.md 和核心 references

| 任务 | 产出 | 工作量 | 优先级 |
|------|------|--------|--------|
| 改造 SKILL.md | i2h-verify/SKILL.md (~450 行) | 4-6h | ⭐⭐⭐⭐⭐ |
| 改造 static-and-identity.md | references/static-and-identity.md (~150 行) | 3-4h | ⭐⭐⭐⭐⭐ |
| 改造 device-verification.md | references/device-verification.md (~80 行) | 2-3h | ⭐⭐⭐⭐⭐ |
| 新增 ios-specific-checks.md | references/ios-specific-checks.md (~200 行) | 2-3h | ⭐⭐⭐⭐ |

**小计**：11-16 小时

### 5.2 Phase 2: 辅助文档和模板（必须）

| 任务 | 产出 | 工作量 | 优先级 |
|------|------|--------|--------|
| 改造 check5-behavior-verify.md | references/check5-behavior-verify.md (~130 行) | 2-3h | ⭐⭐⭐⭐ |
| 改造 failure-loop.md | references/failure-loop.md (~40 行) | 0.5-1h | ⭐⭐ |
| 改造 verify-report-template.md | references/verify-report-template.md (~90 行) | 1-2h | ⭐⭐⭐ |

**小计**：3.5-6 小时

### 5.3 Phase 3: 核心脚本实现（必须）

| 任务 | 产出 | 工作量 | 优先级 |
|------|------|--------|--------|
| iOS 设备检测脚本 | scripts/ios_device_checker.py (~150 行) | 3-4h | ⭐⭐⭐⭐⭐ |
| iOS 配置解析脚本 | scripts/ios_config_parser.py (~200 行) | 4-5h | ⭐⭐⭐⭐⭐ |
| iOS 静态分析脚本 | scripts/ios_static_analyzer.py (~300 行) | 6-8h | ⭐⭐⭐⭐ |
| 脚本单元测试 | scripts/tests/ | 4-6h | ⭐⭐⭐ |

**小计**：17-23 小时

### 5.4 Phase 4: 外部 Skills 协调（可能需要）

| 任务 | 工作量 | 优先级 | 策略 |
|------|--------|--------|------|
| 调研 `arkts-visual-verify` iOS 支持 | 1-2h | ⭐⭐⭐⭐⭐ | 先查文档 |
| 调研 `arkts-ut-verifier` iOS 支持 | 1-2h | ⭐⭐⭐⭐ | 先查文档 |
| 调研 `arkts-behavior-verify` iOS 支持 | 1-2h | ⭐⭐⭐ | 先查文档 |
| 实现临时 workaround（如需）| 8-12h | ⭐⭐⭐ | 标注 TODO |

**小计**：3-6 小时（调研）+ 0-12 小时（临时方案）

### 5.5 Phase 5: 验证和文档（必须）

| 任务 | 产出 | 工作量 | 优先级 |
|------|------|--------|--------|
| 对比报告 | docs/i2h-verify-gap-analysis.md | 2-3h | ⭐⭐⭐⭐⭐ |
| 完成报告 | docs/i2h-verify-complete-report.md | 1-2h | ⭐⭐⭐⭐ |
| 使用指南 | docs/i2h-verify-usage-guide.md | 2-3h | ⭐⭐⭐⭐ |
| 真实项目测试 | - | 4-6h | ⭐⭐⭐⭐⭐ |

**小计**：9-14 小时

### 5.6 总工作量估算

| Phase | 内容 | 最少 | 最多 | 平均 |
|-------|------|------|------|------|
| Phase 1 | 核心文档改造 | 11h | 16h | 13.5h |
| Phase 2 | 辅助文档和模板 | 3.5h | 6h | 4.75h |
| Phase 3 | 核心脚本实现 | 17h | 23h | 20h |
| Phase 4 | 外部 Skills 协调 | 3h | 18h | 10.5h |
| Phase 5 | 验证和文档 | 9h | 14h | 11.5h |
| **总计** | | **43.5h** | **77h** | **60.25h** |

**务实估算**：
- 乐观：~45 小时（外部 Skills 完全支持 iOS）
- 现实：~60 小时（需要少量 workaround）
- 悲观：~75 小时（需要完整实现临时方案）

### 5.7 分阶段交付策略

#### Milestone 1: 文档完整（Week 1）

**产出**：
- ✅ SKILL.md 完整
- ✅ 所有 references 完整
- ✅ iOS 特有检查规则文档

**可验证**：
- 文档完整性 100%
- 与 Android 版对齐度 100%

#### Milestone 2: 脚本可用（Week 2）

**产出**：
- ✅ iOS 设备检测脚本可用
- ✅ iOS 配置解析脚本可用
- ✅ iOS 静态分析脚本可用
- ✅ 单元测试覆盖核心逻辑

**可验证**：
- CHECK-1/2 可以执行
- 脚本测试通过

#### Milestone 3: 端到端可用（Week 3）

**产出**：
- ✅ CHECK-1/2 完整可用
- ✅ CHECK-3/4/5 可用或 DEFERRED（取决于外部 Skills）
- ✅ 修复回环可用
- ✅ 验证报告生成

**可验证**：
- 真实项目可以运行完整流程
- 生成正确的 verify-report.md

---

## 6. 风险和挑战

### 6.1 外部 Skills 依赖

**风险**：`arkts-visual-verify`、`arkts-ut-verifier`、`arkts-behavior-verify` 可能不支持 iOS

**缓解方案**：
1. **优先调研** - 立即查看这些 Skills 的文档和代码
2. **参数传递** - 尝试通过参数适配（`--ios-*`）
3. **临时方案** - 实现简化版 CHECK-3/4/5
4. **标注 DEFERRED** - 暂时标记为 DEFERRED，待 Skills 支持后启用

### 6.2 iOS 工具链依赖

**风险**：iOS 真机需要额外工具链（libimobiledevice）

**缓解方案**：
1. **优先支持模拟器** - `xcrun simctl` 是标准工具
2. **真机作为可选** - 检测到工具链才启用真机支持
3. **文档说明** - 清晰说明真机支持的安装步骤

### 6.3 配置文件复杂性

**风险**：iOS Info.plist 格式复杂（XML / Binary），Assets.xcassets 结构多样

**缓解方案**：
1. **使用成熟库** - Python `plistlib`（标准库）解析 plist
2. **简化检查** - 只检查关键字段，不做完整校验
3. **提供示例** - 文档中提供标准配置示例

### 6.4 测试框架差异

**风险**：XCTest 与 JUnit 差异巨大，测试映射复杂

**缓解方案**：
1. **先支持基础场景** - 识别测试文件和基本断言
2. **标注复杂场景** - 异步测试、UI 测试标记为待完善
3. **依赖 arkts-ut-verifier** - 核心逻辑由外部 Skill 处理

---

## 7. 下一步行动

### 立即行动（今天）

1. ⭐⭐⭐⭐⭐ **调研外部 Skills iOS 支持情况**
   ```bash
   # 检查 arkts-visual-verify
   Read ~/Codes/ios2harmony/hmigbot-ios/migbot/skills/arkts-visual-verify/SKILL.md
   
   # 检查 arkts-ut-verifier
   Read ~/Codes/ios2harmony/hmigbot-ios/migbot/skills/arkts-ut-verifier/SKILL.md
   
   # 检查 arkts-behavior-verify
   Read ~/Codes/ios2harmony/hmigbot-ios/migbot/skills/arkts-behavior-verify/SKILL.md
   ```

2. ⭐⭐⭐⭐⭐ **确认 i2h-spec 是否实现了 gate-release 功能**
   ```bash
   # 检查是否有 gate_ledger.py 或类似脚本
   find ~/Codes/ios2harmony/hmigbot-ios/migbot/skills/i2h-spec -name "*gate*" -o -name "*ledger*"
   ```

3. ⭐⭐⭐⭐⭐ **开始 Phase 1: 核心文档改造**
   - 创建 `i2h-verify/SKILL.md`
   - 创建 `i2h-verify/references/static-and-identity.md`

### 短期行动（本周）

4. ⭐⭐⭐⭐ **完成 Phase 1 所有文档**
5. ⭐⭐⭐⭐ **实现 iOS 设备检测脚本**
6. ⭐⭐⭐ **实现 iOS 配置解析脚本**

### 中期行动（2-3 周）

7. ⭐⭐⭐⭐ **完成 Phase 2-3**
8. ⭐⭐⭐ **真实项目测试**
9. ⭐⭐ **完善文档和单元测试**

---

## 8. 附录

### 8.1 关键命令对照表

| 操作 | Android | iOS (模拟器) | iOS (真机) |
|------|---------|------------|-----------|
| 列出设备 | `adb devices` | `xcrun simctl list devices \| grep Booted` | `idevice_id -l` |
| 安装应用 | `adb install app.apk` | `xcrun simctl install <device> app.app` | `ideviceinstaller -i app.ipa` |
| 启动应用 | `adb shell am start -n <pkg>/<activity>` | `xcrun simctl launch <device> <bundle-id>` | 手动 |
| 截图 | `adb shell screencap -p <path>` | `xcrun simctl io <device> screenshot <file>` | `idevicescreenshot <file>` |
| 日志 | `adb logcat` | `xcrun simctl spawn <device> log stream` | `idevicesyslog` |

### 8.2 配置文件字段映射

| 字段 | Android | iOS | HarmonyOS |
|------|---------|-----|-----------|
| 包名/Bundle ID | `<manifest package="">` | `CFBundleIdentifier` | `bundleName` |
| 应用名 | `<application android:label="">` | `CFBundleDisplayName` | `label` |
| 版本名 | `android:versionName` | `CFBundleShortVersionString` | `versionName` |
| 版本号 | `android:versionCode` | `CFBundleVersion` | `versionCode` |

### 8.3 参考资源

- Android 原版：`~/Codes/ios2harmony/hmigbot-1.8.0/migbot/skills/a2h-verify/`
- iOS 当前版：`~/Codes/ios2harmony/hmigbot-ios/migbot/skills/i2h-verify/`
- i2h-execute 完成报告：`~/Codes/ios2harmony/hmigbot-ios/docs/i2h-execute-complete-report.md`
- 本文档：`~/Codes/ios2harmony/hmigbot-ios/docs/i2h-verify-analysis.md`

---

**分析完成时间**: 2024-11-03  
**分析人**: Claude Opus 5.5  
**版本**: v1.0  
**状态**: ✅ 完整分析完成，待开始实施
