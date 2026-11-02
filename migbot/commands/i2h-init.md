---
description: Initialize iOS → HarmonyOS migration project. Confirm paths and settings.
allowed-tools: Bash, Read, Edit, Write
---

## Goal

Initialize a new iOS → HarmonyOS migration project. Detect all paths at once, then confirm together.

## 1. Read or create config

Read `.migbot/config.json` from current directory.

If not exists, create with skeleton:
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

## 2. Path confirmation gate

**Gate:** If `confirmed == true` already, ask: `"Configuration confirmed. Re-confirm paths? (yes / no)"`

- `no` → skip to final report (§4)
- `yes` → run full detection flow below

## 3. Auto-detect all paths (no interruption)

**Silently detect all paths, collect results**, then show once.

### 3.1 Detect iOS source path

```bash
test -d "<ios>"
test -f "<ios>"/*.xcodeproj/project.pbxproj || test -f "<ios>/Package.swift"
```

Record result:
- ✅ exists + has project → `detected_ios = {path, status: "ok", type: "xcodeproj/package"}`
- ⚠️  exists but no project → `detected_ios = {path, status: "warn", msg: "dir exists but no project"}`
- ❌ missing → `detected_ios = {path, status: "error", msg: "path not found"}`

### 3.2 Detect HarmonyOS project path

```bash
test -d "<harmonyos>"
test -f "<harmonyos>/oh-package.json5"
```

Record result.

### 3.3 Detect Xcode path

Try candidates (stop at first hit):
1. `xcode` field value
2. `xcode-select -p` output
3. `/Applications/Xcode.app`

Record: `detected_xcode = {path, candidate: N, status}`

### 3.4 Detect xcrun path

Candidates:
1. `xcrun` field value
2. `command -v xcrun`
3. `<xcode>/Contents/Developer/usr/bin/xcrun`

Record result.

### 3.5 Detect simctl path

Candidates:
1. `simctl` field value
2. `command -v simctl`
3. `"xcrun simctl"` (if xcrun available)

Record result.

### 3.6 Detect DevEco path

Try standard locations:
- macOS: `/Applications/DevEco-Studio.app`
- Windows: `C:\DevEco Studio\`
- Linux: `/opt/DevEco-Studio`

Record result.

### 3.7 Detect hvigorw path

Candidates:
1. `hvigorw` field value
2. `<harmonyos>/hvigorw`
3. `<harmonyos>/hvigorw.bat`
4. `<deveco>/tools/hvigor/bin/hvigorw`

Record result.

### 3.8 Detect hdc path

Candidates:
1. `hdc` field value
2. `command -v hdc`
3. `<deveco>/Contents/sdk/.../hdc`
4. `<deveco>/sdk/.../hdc`

Record result.

### 3.9 Detect app name

Read from iOS project:
1. `.xcodeproj/project.pbxproj` → `PRODUCT_NAME`
2. `Info.plist` → `CFBundleDisplayName`
3. Directory name as fallback

Record: `detected_app_name = {name, source}`

## 4. Show detection results, confirm once

Generate complete detection report:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 Detection Results
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

iOS Project
  Path: /Users/xxx/cuike-ios
  Status: ✅ Xcode project detected
  
HarmonyOS Project
  Path: .
  Status: ✅ HarmonyOS project detected

App Name
  Detected: Cuike
  Source: Info.plist

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
iOS Tools
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Xcode
  ✅ /Applications/Xcode.app (candidate #3)
  
xcrun
  ✅ Already on PATH (candidate #2)
  
simctl
  ✅ xcrun simctl (candidate #3)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HarmonyOS Tools
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

DevEco
  ✅ /Applications/DevEco-Studio.app
  
hvigorw
  ✅ ./hvigorw (candidate #2)
  
hdc
  ⚠️  Not found (device verification will fail)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Then **ask only once**:

```
Are the above detection results correct?

Options:
  1. yes     - Accept all detected results
  2. edit    - Modify some paths
  3. cancel  - Cancel initialization

Choose: (yes / edit / cancel)
```

### 4.1 User chooses `yes`

Write all config directly, set `confirmed: true`, jump to §5.

### 4.2 User chooses `edit`

Show editable items:

```
Select items to modify (space-separated):

  1. ios          - iOS project path
  2. harmonyos    - HarmonyOS project path
  3. app_name     - App name
  4. xcode        - Xcode path
  5. xcrun        - xcrun path
  6. simctl       - simctl path
  7. deveco       - DevEco path
  8. hvigorw      - hvigorw path
  9. hdc          - hdc path

Example: 1 9  (modify ios and hdc)
Or enter: done (finish editing)
```

For each selected item, ask for new value:

```
ios current value: /Users/xxx/cuike-ios
New value (or keep): <user input>
```

After editing, show updated results and ask again: `"Confirm above configuration? (yes / edit again)"`

### 4.3 User chooses `cancel`

```
❌ Initialization cancelled. Configuration not saved.
```

Exit without modifying config.

## 5. Write config + mark confirmed

Update `.migbot/config.json`:

```json
{
  "version": "1.0.0",
  "language": "zh",
  "ios": "<user confirmed value>",
  "harmonyos": "<user confirmed value>",
  "xcode": "<detected or user modified>",
  "xcrun": "<detected or user modified>",
  "simctl": "<detected or user modified>",
  "deveco": "<detected or user modified>",
  "hvigorw": "<detected or user modified>",
  "hdc": "<detected or user modified>",
  "app_name": "<detected or user modified>",
  "confirmed": true
}
```

## 6. Final report

```
✅ Configuration confirmed and saved

Configuration summary:
  iOS project: /Users/xxx/cuike-ios
  HarmonyOS project: .
  App name: Cuike
  
Tool status:
  iOS: ✅ Xcode + xcrun + simctl
  HarmonyOS: ✅ DevEco + hvigorw, ⚠️ hdc not set

Next step:
  Run /i2h-run to start migration pipeline
```

If any tool is missing, add note:

```
⚠️  hdc not set, device verification will be unavailable.
   Can re-run /i2h-init later to reconfigure.
```
