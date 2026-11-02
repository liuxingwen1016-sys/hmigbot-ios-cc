---
description: 初始化 iOS → 鸿蒙迁移项目。确认路径和设置。
allowed-tools: Bash, Read, Edit, Write
---

## 目标

初始化一个新的 iOS → 鸿蒙迁移项目。一次性探测所有路径，最后统一确认。

## 1. 读取或创建配置

读取当前目录的 `.migbot/config.json`。

如果不存在，创建骨架：
```json
{
  "version": "1.0.0",
  "language": "zh",
  "ios": "../ios-app",
  "harmonyos": ".",
  "xcode": "",
  "xcrun": "",
  "simctl": "",
  "deveco": "",
  "hvigorw": "",
  "hdc": "",
  "app_name": "",
  "confirmed": false
}
```

## 2. 路径确认门禁

**门禁：** 如果 `confirmed == true` 已存在，询问：`"配置已确认。重新确认路径？(yes / no)"`

- `no` → 跳到最终报告（§4）
- `yes` → 执行下面的完整探测流程

## 3. 自动探测所有路径（不打断用户）

**静默探测所有路径，收集结果**，最后一次性展示。

### 3.1 探测 iOS 源码路径

```bash
test -d "<ios>"
test -f "<ios>"/*.xcodeproj/project.pbxproj || test -f "<ios>/Package.swift"
```

记录结果：
- ✅ 存在 + 有项目 → `detected_ios = {path, status: "ok", type: "xcodeproj/package"}`
- ⚠️  存在但无项目 → `detected_ios = {path, status: "warn", msg: "目录存在但未检测到项目"}`
- ❌ 不存在 → `detected_ios = {path, status: "error", msg: "路径不存在"}`

### 3.2 探测鸿蒙项目路径

```bash
test -d "<harmonyos>"
test -f "<harmonyos>/oh-package.json5"
```

记录结果。

### 3.3 探测 Xcode 路径

尝试候选路径（停在第一个命中）：
1. `xcode` 字段值
2. `xcode-select -p` 输出
3. `/Applications/Xcode.app`

记录：`detected_xcode = {path, candidate: N, status}`

### 3.4 探测 xcrun 路径

候选：
1. `xcrun` 字段值
2. `command -v xcrun`
3. `<xcode>/Contents/Developer/usr/bin/xcrun`

记录结果。

### 3.5 探测 simctl 路径

候选：
1. `simctl` 字段值
2. `command -v simctl`
3. `"xcrun simctl"`（如果 xcrun 可用）

记录结果。

### 3.6 探测 DevEco 路径

尝试标准位置：
- macOS: `/Applications/DevEco-Studio.app`
- Windows: `C:\DevEco Studio\`
- Linux: `/opt/DevEco-Studio`

记录结果。

### 3.7 探测 hvigorw 路径

候选：
1. `hvigorw` 字段值
2. `<harmonyos>/hvigorw`
3. `<harmonyos>/hvigorw.bat`
4. `<deveco>/tools/hvigor/bin/hvigorw`

记录结果。

### 3.8 探测 hdc 路径

候选：
1. `hdc` 字段值
2. `command -v hdc`
3. `<deveco>/Contents/sdk/.../hdc`
4. `<deveco>/sdk/.../hdc`

记录结果。

### 3.9 探测应用名称

从 iOS 项目读取：
1. `.xcodeproj/project.pbxproj` → `PRODUCT_NAME`
2. `Info.plist` → `CFBundleDisplayName`
3. 目录名作为后备

记录：`detected_app_name = {name, source}`

## 4. 统一展示探测结果，一次性确认

生成完整的探测报告：

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 路径探测结果
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

iOS 项目
  路径: /Users/xxx/cuike-ios
  状态: ✅ 检测到 Xcode 项目
  
鸿蒙项目
  路径: .
  状态: ✅ 检测到鸿蒙项目

应用名称
  检测到: Cuike
  来源: Info.plist

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
iOS 工具
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Xcode
  ✅ /Applications/Xcode.app (候选 #3)
  
xcrun
  ✅ 已在 PATH 中 (候选 #2)
  
simctl
  ✅ xcrun simctl (候选 #3)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
鸿蒙工具
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

DevEco
  ✅ /Applications/DevEco-Studio.app
  
hvigorw
  ✅ ./hvigorw (候选 #2)
  
hdc
  ⚠️  未找到（设备验证将失败）

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

然后**只问一次**：

```
以上探测结果是否正确？

选项:
  1. yes     - 接受所有探测结果
  2. edit    - 修改某些路径
  3. cancel  - 取消初始化

请选择: (yes / edit / cancel)
```

### 4.1 用户选择 `yes`

直接写入所有配置，设置 `confirmed: true`，跳到 §5。

### 4.2 用户选择 `edit`

显示可编辑的项目列表：

```
请选择要修改的项目（可多选，用空格分隔）：

  1. ios          - iOS 项目路径
  2. harmonyos    - 鸿蒙项目路径
  3. app_name     - 应用名称
  4. xcode        - Xcode 路径
  5. xcrun        - xcrun 路径
  6. simctl       - simctl 路径
  7. deveco       - DevEco 路径
  8. hvigorw      - hvigorw 路径
  9. hdc          - hdc 路径

例如: 1 9  (修改 ios 和 hdc)
或输入: done (完成编辑)
```

对每个选中的项目，逐个询问新值：

```
ios 当前值: /Users/xxx/cuike-ios
新值 (或 keep 保持不变): <用户输入>
```

编辑完成后，显示更新后的结果，再次询问：`"确认以上配置？(yes / edit again)"`

### 4.3 用户选择 `cancel`

```
❌ 初始化已取消。配置未保存。
```

退出，不修改配置文件。

## 5. 写入配置 + 标记已确认

更新 `.migbot/config.json`：

```json
{
  "version": "1.0.0",
  "language": "zh",
  "ios": "<用户确认的值>",
  "harmonyos": "<用户确认的值>",
  "xcode": "<探测到的值或用户修改后的值>",
  "xcrun": "<探测到的值或用户修改后的值>",
  "simctl": "<探测到的值或用户修改后的值>",
  "deveco": "<探测到的值或用户修改后的值>",
  "hvigorw": "<探测到的值或用户修改后的值>",
  "hdc": "<探测到的值或用户修改后的值>",
  "app_name": "<探测到的值或用户修改后的值>",
  "confirmed": true
}
```

## 6. 最终报告

```
✅ 配置已确认并保存

配置摘要:
  iOS 项目: /Users/xxx/cuike-ios
  鸿蒙项目: .
  应用名称: Cuike
  
工具状态:
  iOS: ✅ Xcode + xcrun + simctl
  鸿蒙: ✅ DevEco + hvigorw, ⚠️ hdc 未设置

下一步:
  运行 /i2h-run 开始迁移流水线
```

如果有工具未设置，添加提示：

```
⚠️  hdc 未设置，真机验证功能将不可用。
   可以稍后运行 /i2h-init 重新配置。
```
