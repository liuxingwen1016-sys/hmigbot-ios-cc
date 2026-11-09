---
name: hmos-fix-build-errors
description: Build a HarmonyOS project via CLI and automatically fix compile errors in a loop until the build succeeds. Handles ArkTS V2 errors (@ComponentV2/@Local/@Param/@Event/@Once/@Provider/@Consumer/@Monitor/@Computed/@ObservedV2/@Trace/AppStorageV2/PersistenceV2) as well as legacy V1 (@Component/@State/@Prop/@Link/@Provide/@Consume/@Observed/@ObjectLink/@StorageLink/@StorageProp/@Watch). Default unsigned HAP; pass --signed to build a signed HAP (signing config must already exist in the project's build-profile.json5).
metadata:
  type: tool
  domain: engineering
---
# HarmonyOS Auto Build & Fix

## 调用参数与工具边界（原 Claude Code frontmatter 迁移）

> 下列参数格式与操作边界由已移除的 frontmatter 字段迁移而来，在此以 body 指引形式保留、作为行为约束遵守。

- **参数格式**：`<harmonyos-project-path> <deveco-studio-path> [--signed] [--build-only]`
  - 参数按位置从调用方提示词中获取（Codex 无 slash-command 参数注入，调用时在提示词中依序给出）
- **允许的操作类型**（作为行为约束遵守、非硬性权限）：子代理派发、读取文件、写文件、编辑文件、通配搜索、内容检索、执行 shell。

Automatically build a HarmonyOS NEXT project from the command line, parse compile errors, fix them, and retry — repeating until the build succeeds.

- **HarmonyOS Project**: `$ARGUMENTS[0]` (the HarmonyOS project root, e.g. `D:/MyHmosApp`)
- **DevEco Studio Path**: `$ARGUMENTS[1]` (DevEco Studio installation root, e.g. Windows `D:/DevEco Studio`; macOS `/Applications/DevEco-Studio.app/Contents`)
- **--signed** (optional): `$ARGUMENTS[2]` — if set to `--signed`, the build produces a **signed HAP**. If omitted, the build produces an **unsigned HAP** (default).

---


**Opt-in --build-only (Stage 1 verification packages)**: perform environment/signing validation and
exactly one CLI build. Inspect and return its real result and bounded diagnostics. On failure, do not
enter automatic source fixes or rebuild; the caller owns the shared repair budget. On success verify
the HAP and return its actual path. This mode does not change the default build-fix loop below.

## Step 0: Validate Inputs & Setup Environment

1. **Verify project exists** — Check that `$ARGUMENTS[0]` contains a valid HarmonyOS project (look for `build-profile.json5`, `entry/src` directory, `oh-package.json5`).

2. **Determine platform & verify DevEco installation** — Decide the platform branch ONCE here and reuse it everywhere below (Step 1.1 Plan A/B, safeguards):
   - **Windows** → check `$ARGUMENTS[1]` contains:
     - `tools/node/node.exe` → this is `<node-path>`
     - `tools/hvigor/bin/hvigorw.js`
     - `tools/ohpm/bin/ohpm.bat` → this is `<ohpm-path>`
     - `sdk/` directory
   - **macOS / Linux** → check `$ARGUMENTS[1]` (macOS DevEco root is typically `/Applications/DevEco-Studio.app/Contents`) contains:
     - `tools/node/bin/node` → this is `<node-path>`
     - `tools/hvigor/bin/hvigorw.js`
     - `tools/ohpm/bin/ohpm` → this is `<ohpm-path>`
     - `sdk/` directory
   - If a binary is not at the listed path, Glob for it under the DevEco root (e.g. `**/node`, `**/hvigorw.js`) before failing. Record the resolved `<node-path>` / `<ohpm-path>` for reuse.

3. **Set up `local.properties`** — Ensure the project root has `local.properties` with:
   ```properties
   hwsdk.dir=<deveco-path>/sdk
   ```
   Create it if missing. Use forward slashes in the path.

4. **Run `ohpm install`** — Install dependencies before first build. Use the platform branch decided in item 2:

   **Windows (PowerShell)**:
   ```powershell
   & "<deveco-path>\tools\ohpm\bin\ohpm.bat" install
   ```
   (run with the project dir as working directory; do NOT append `2>&1` — PowerShell 5.1 wraps native stderr into error records)

   **macOS / Linux (bash)**:
   ```bash
   cd "<project-dir>"
   export PATH="<deveco-path>/tools/ohpm/bin:$PATH"
   "<ohpm-path>" install
   ```

5. **Determine Build Mode** — Check if `$ARGUMENTS[2]` equals `--signed`:
   - **If NOT `--signed`** → **Unsigned build mode**. Ensure `build-profile.json5` does NOT have `signingConfigs` or `signingConfig` references in products (remove them if present). Go to Step 1.
   - **If `--signed`** → **Signed build mode**. Proceed to Step 0.5 to validate signing config.

---

## Step 0.5: Validate Signing Config (Only for --signed Builds)

This step is ONLY executed when `--signed` is specified.

Signing information is read directly from the project's own `build-profile.json5`. The user must have already configured signing in DevEco Studio before running this skill.

### Steps:

1. **Read `build-profile.json5`** in the project root.

2. **Check for `signingConfigs`** — Look for `app.signingConfigs` array in the file.
   - If `signingConfigs` exists and has at least one entry with valid `material` fields (`certpath`, `storeFile`, `profile`), proceed to step 3.
   - If `signingConfigs` is missing or empty, **STOP and report to the user**:
     > Signing configuration not found in `build-profile.json5`.
     > Please open the project in DevEco Studio, go to **File → Project Structure → Signing Configs**, enable **Automatically generate signature**, then re-run this skill with `--signed`.

3. **Validate signing material files exist** — For the first entry in `signingConfigs`, check that the files referenced by `material.certpath`, `material.storeFile`, and `material.profile` actually exist on disk.
   - If any file is missing, **STOP and report** which files are missing. Suggest the user re-open DevEco Studio and re-generate the signing config.

4. **Ensure product references signing** — Check that the product entry in `products` array has `"signingConfig": "default"` (or matching the signing config name). Add it if missing.

5. Proceed to Step 1.

---

## Step 1: Build-Fix Loop

Execute the following loop. **Maximum 20 iterations** to prevent infinite loops.

### 1.1 Run CLI Build

Use the platform branch decided in Step 0.2. **Both plans share two hard rules**:

- **The build's output MUST be redirected to `<project-dir>/build_out.log` from INSIDE the script/command itself**, ending with a `BUILD_EXIT_CODE=<n>` sentinel line. Never rely on capturing the build's stdout: a timeout loses all piped output, and large logs exceed tool output truncation limits. The log file survives timeouts and background runs, and is inspected with Grep.
- **Keep the hvigor daemon** — do NOT pass `--no-daemon`. The daemon holds incremental compile state; killing it every iteration turns each of up to 20 fix loops into a cold build. Only stop the daemon explicitly via the safeguards below when a build hangs or SDK-path errors appear.

**Housekeeping (once, before the first build)**: if the project is a git repo, ensure `.gitignore` contains `build_temp.bat` and `build_out.log` (append if missing) so aborted runs don't pollute git status.

#### Plan A — Windows (batch file + PowerShell `cmd /c`)

Env vars must be set inside a `.bat` so they reach the native `node.exe`/`java` child processes with correct Windows path format.

1. **Write `<project-dir>/build_temp.bat`** (backslashes in paths):

   **For unsigned builds** (no `--signed`):
   ```bat
   @echo off
   set "DEVECO_SDK_HOME=<deveco-path>\sdk"
   cd /d "<project-dir>"
   "<node-path>" "<deveco-path>\tools\hvigor\bin\hvigorw.js" assembleHap --mode module -p module=entry > "<project-dir>\build_out.log" 2>&1
   set "RC=%ERRORLEVEL%"
   echo BUILD_EXIT_CODE=%RC%>> "<project-dir>\build_out.log"
   exit /b %RC%
   ```

   **For signed builds** (`--signed`): same, but add these two lines before `set "DEVECO_SDK_HOME=..."`:
   ```bat
   set "PATH=<deveco-path>\jbr\bin;%PATH%"
   set "JAVA_HOME=<deveco-path>\jbr"
   ```
   (the `SignHap` step spawns `java` as a child process)

2. **Run the batch file via the PowerShell tool** (foreground or `run_in_background` per the timeout policy below):
   ```powershell
   cmd /c '"<project-dir>\build_temp.bat"'
   ```
   - The single-quote-wrapping-double-quote form keeps paths with spaces intact.
   - Do NOT append `2>&1` (PowerShell 5.1 wraps native stderr into error records); the bat already redirects everything to the log.
   - **NEVER use `cmd.exe //c`** — the `//c` form is Git-Bash-only path-mangling. From PowerShell/cmd it is not recognized as `/c`, so cmd opens an *interactive* shell that reads EOF and exits instantly, leaving a banner-only log and no build.

3. The bat file is reused across iterations; delete `build_temp.bat` and `build_out.log` only after the loop ends (Step 2).

#### Plan B — macOS / Linux (direct bash, no script file)

`export` propagates to child processes normally on POSIX — no wrapper script needed:

```bash
cd "<project-dir>"
export DEVECO_SDK_HOME="<deveco-path>/sdk"
"<node-path>" "<deveco-path>/tools/hvigor/bin/hvigorw.js" assembleHap --mode module -p module=entry > build_out.log 2>&1
echo "BUILD_EXIT_CODE=$?" >> build_out.log
```

**For signed builds** (`--signed`), additionally export before the build line:
```bash
export JAVA_HOME="<deveco-path>/jbr/Contents/Home"   # macOS; verify $JAVA_HOME/bin/java exists, Glob under <deveco-path>/jbr if not
export PATH="$JAVA_HOME/bin:$PATH"
```

#### Timeout policy

- **First build (cold)**: run in the background (`run_in_background`). Cold start (hvigor init, SDK component load, dependency scan, antivirus scanning on Windows) routinely exceeds 5 minutes. You are notified automatically on completion — do NOT poll in a sleep loop; you may Grep `build_out.log` occasionally for progress.
- **Subsequent builds (incremental, daemon warm)**: foreground with a 600000ms (10 min) timeout.

#### Recovery protocol on timeout / lost result

1. **Check whether the build process is still alive**:
   - Windows (PowerShell): `Get-CimInstance Win32_Process -Filter "Name='node.exe'" | Where-Object { $_.CommandLine -match 'hvigor' }`
   - macOS/Linux (bash): `pgrep -f hvigorw.js`
2. **If alive** → wait and watch `build_out.log` grow. **NEVER launch a second build concurrently** — two hvigor processes corrupt each other's build dir and clobber the shared log.
3. **If dead** and the log has no `BUILD_EXIT_CODE=` sentinel → the build crashed or was killed mid-run; inspect the log tail for the last activity, then rebuild (this counts as an iteration).

### 1.2 Check Build Result

Judge the result from `build_out.log` **using Grep** (never load the whole file into context):

- Log contains `BUILD SUCCESSFUL` AND `BUILD_EXIT_CODE=0` → verify the output HAP file exists (paths in Step 2). If it exists → **Build succeeded!** Exit the loop, go to Step 2.
- Log contains `ERROR` or `BUILD FAILED` → Parse errors (Grep with `-B/-A` context) and continue to 1.3.
- Log contains only a shell banner (a few lines of `Microsoft Windows [...]` + prompt, no hvigor output) → the invocation itself was broken (see Plan A step 2). Fix the invocation and re-run; do NOT count this as a build-fix iteration.

### 1.3 Parse Errors

Extract error information from `build_out.log` (Grep for `ERROR` with context lines). Errors typically appear in these formats:

```
ERROR: <file-path>:<line>:<col> - <error-code>: <message>
```

or

```
ArkTS:ERROR File: <file-path>:<line>:<col>
  <error message>
```

Group errors by file. Focus on **actual errors**, not warnings.

### 1.4 Fix Errors

Read each file that has errors and apply fixes. Use the error reference table below to identify and fix common issues:

| Error Code / Pattern | Message | Fix |
|---|---|---|
| `arkts-limited-throw` | "throw statements cannot accept values of arbitrary types" | Change `throw err` to `throw (err instanceof Error) ? err : new Error(String(err))` |
| `arkts-no-obj-literals-as-types` | "Object literals cannot be used as type declarations" | Define a named `interface` instead of inline `{ key: Type }` |
| `arkts-no-untyped-obj-literals` | "Object literal must correspond to some explicitly declared class or interface" | Assign to typed variable: `const r: MyInterface = {...}; return r;` |
| `arkts-no-any-type` / `any` type usage | "Use explicit types instead of any" | Replace `any` with the correct concrete type or `object` |
| `arkts-no-var` | "Use 'let' or 'const' instead of 'var'" | Replace `var` with `let` or `const` |
| `10903329` | "Unknown resource name 'xxx'" | Verify resource exists in `resources/base/media/` or `element/*.json`. Use `layered_image` as fallback for missing images. **Special case**: `$r('sys.media.ohos_ic_public_xxx')` references system icons by SDK-specific names that may not exist in the build SDK — replace with `$r('app.media.ic_public_xxx')` and add the icon file to `resources/base/media/` |
| `10505001` | "Resource[] is not assignable to ResourceColor" | Remove array brackets: `.fontColor($r('app.color.x'))` not `.fontColor([$r('app.color.x')])` |
| `00303221` | "permission must be a value that is predefined within the SDK" | Remove invalid permission from `module.json5`. See valid permissions list below |
| Missing import | "Cannot find name 'xxx'" | Add the correct import (see import reference below) |
| Missing `async` | "await expression requires async function" | Add `async` to the enclosing function |
| Missing `build()` | "@ComponentV2 / @Component must have build() method" | Add a `build() {}` method to the `@ComponentV2` (V2) or `@Component` (V1) struct |
| Type mismatch | Various type errors | Fix the type annotation or cast appropriately |
| Duplicate identifier | "Duplicate identifier 'xxx'" | Remove or rename the duplicate declaration |

**For errors NOT in the table above**: Read the error message carefully, read the relevant source file, understand the context, and apply an appropriate fix. Use your knowledge of ArkTS/HarmonyOS to determine the correct solution.

### 1.5 Log Progress

After each fix iteration, briefly report:
- Iteration number
- Number of errors found
- Summary of fixes applied
- Whether re-building

Then go back to **1.1** and rebuild.

---

## Step 2: Build Success Report

When the build succeeds, present a summary:

1. **Build Status**: SUCCESS
2. **Build Type**: Signed HAP or Unsigned HAP
3. **Signing** (if signed): Confirm signing config from `build-profile.json5` was used
4. **Iterations**: How many build-fix cycles were needed
5. **Total Errors Fixed**: Count of errors fixed across all iterations
6. **Summary of Changes**: List of files modified and what was fixed in each
7. **Output HAP Path**:
   - Signed: `<project>/entry/build/default/outputs/default/entry-default-signed.hap`
   - Unsigned: `<project>/entry/build/default/outputs/default/entry-default-unsigned.hap`

8. **Cleanup**: Delete `<project-dir>/build_temp.bat` (Windows) and `<project-dir>/build_out.log` now that the loop is over. (Also perform this cleanup when giving up after max iterations.)

---

## Reference: Common HarmonyOS Imports

```typescript
// Network
import { http } from '@kit.NetworkKit';

// Data persistence
import { preferences } from '@kit.ArkData';
import { relationalStore } from '@kit.ArkData';

// UI utilities
import { router } from '@kit.ArkUI';
import { promptAction } from '@kit.ArkUI';

// Ability & Context
import { UIAbility, AbilityConstant, Want } from '@kit.AbilityKit';
import { common } from '@kit.AbilityKit';

// File I/O
import { fileIo } from '@kit.CoreFileKit';

// Logging
import { hilog } from '@kit.PerformanceAnalysisKit';

// JSON parsing — built-in, no import needed
// ArkUI built-in components (Text, Column, Row, List, Button, Image, etc.) — NO import needed
```

## Reference: Valid Permission Names

Commonly used SDK-validated permissions for `module.json5`:

- `ohos.permission.INTERNET`
- `ohos.permission.GET_NETWORK_INFO`
- `ohos.permission.GET_WIFI_INFO`
- `ohos.permission.KEEP_BACKGROUND_RUNNING`
- `ohos.permission.PUBLISH_AGENT_REMINDER`
- `ohos.permission.CAMERA`
- `ohos.permission.MICROPHONE`
- `ohos.permission.APPROXIMATELY_LOCATION`
- `ohos.permission.LOCATION`
- `ohos.permission.READ_MEDIA`
- `ohos.permission.WRITE_MEDIA`
- `ohos.permission.USE_BLUETOOTH`
- `ohos.permission.VIBRATE`

**Note**: `ohos.permission.NOTIFICATION` does NOT exist. When in doubt, omit the permission.

---

## Build-Fix Loop: Environmental Safeguards

### Cache Cleanliness

- **Single `ohpm install`**: Run `ohpm install` exactly once at the start of the build-fix loop. Do NOT re-run it inside the loop unless a new dependency was explicitly added.
- **Cache cleanup limit**: `clean` may be run at most **1 time** per entire build-fix session. Invoke it through the same platform wrapper as Step 1.1 (replace `assembleHap --mode module -p module=entry` with `clean`) — there is no `hvigorw` executable on PATH, especially on Windows. If errors increase after a clean, stop CLI build immediately and escalate to IDE-based verification.
- **Never `rm -rf entry/build`**: This destroys the hvigor daemon's incremental state and can cause unrecoverable cache corruption. The only safe cache reset is the `clean` task run through the Step 1.1 wrapper.

### SDK Path Poisoning

- **Environment variable pinning**: `DEVECO_SDK_HOME` is set explicitly *inside the Step 1.1 build script/command* to `<deveco-path>/sdk` — that value is authoritative and must match `hwsdk.dir` in `local.properties`. Never rely on a value inherited from the outer shell. If the *outer* shell carries a different stale `DEVECO_SDK_HOME`, clear it there so tools launched outside the wrapper don't pick it up:
  - Windows (PowerShell): `Remove-Item Env:DEVECO_SDK_HOME -ErrorAction SilentlyContinue`
  - macOS/Linux (bash): `unset DEVECO_SDK_HOME`
- **If `00303208` or `00303217` appears**: First verify the value set in the build script matches `hwsdk.dir` in `local.properties`. If it matches but the error persists, the hvigor daemon has cached a bad value — stop the daemon via the Step 1.1 wrapper with `--stop-daemon` as the sole argument (i.e. `"<node-path>" ".../hvigorw.js" --stop-daemon`), wait 2 seconds, then retry. After 2 consecutive SDK-path failures, **escalate to IDE build**.

### Hanged Daemon

- **If build exits <1s with no compile errors**: The hvigor daemon is likely dead or unresponsive. Stop it via the Step 1.1 wrapper: `"<node-path>" "<deveco-path>/tools/hvigor/bin/hvigorw.js" --stop-daemon` (Windows: run inside the bat / a `cmd /c` one-liner with the same env; macOS: plain bash). Wait 2 seconds, retry once. If still failing after 2 attempts, escalate to IDE build.

### Checkpoint Commit

- **After every `BUILD SUCCESSFUL`**: Immediately `git commit` all changed files with a checkpoint message: `checkpoint(base-N): build pass after K fixes`.
- **On linter revert**: If a file is reverted after the checkpoint, use `git checkout -- <file>` to restore the build-pass state rather than re-editing.

---

## Reference: ArkTS Strict Mode Rules

All code must comply with ArkTS strict mode:

1. **No `any` type** — Use explicit types or `object`
2. **No `var`** — Only `let` and `const`
3. **No dynamic property access** — Use typed interfaces instead of `obj['key']` on typed objects
4. **`throw` must throw Error instances** — Never `throw 'string'` or `throw unknownVar`
5. **All object literals must match declared interfaces** — No anonymous `{ key: val }` returns without a matching interface
6. **No inline object literal types** — `function(): { a: string }` is forbidden; define a named `interface`
7. **All `@ComponentV2` (V2) / `@Component` (V1) structs must have `build()`** — Missing build method is a compile error
8. **`$r()` resource references validated at compile time** — All referenced resources must exist
9. **`fontColor()` expects `ResourceColor`**, not `Resource[]` — Don't wrap in array brackets (exception: `SymbolGlyph`)
10. **Permission names in `module.json5`** — Must be SDK-predefined values

## Important Notes

- **Timeout**: First (cold) build → run in background, no foreground timeout applies. Incremental builds → 600000ms (10 min) foreground timeout. On timeout, follow the recovery protocol in 1.1 — never start a second concurrent build.
- **Max iterations**: Stop after 20 iterations to prevent infinite loops. If build still fails after 20 attempts, report the remaining errors to the user.
- **Don't over-fix**: Only fix errors reported by the compiler. Don't proactively refactor unrelated code.
- **Read before edit**: Always read a file before modifying it. Understand the surrounding context.
- **One error can cause many**: A single root-cause fix (like adding a missing interface) may resolve multiple reported errors. After fixing root causes, rebuild to see remaining issues.
- **ohpm errors**: If the build fails because of missing packages, run `ohpm install` again.

---

## References

- `references/arkts-strict-patterns.md` — ArkTS 严格模式编译错误的确定性修复 Pattern（throw/any/var/interface 等）
- `references/known-patterns.md` — 已知常见编译错误 Pattern 及修复方案
- `references/rdb-entity-pattern.md` — RDB 实体类编译错误 Pattern（数据库实体相关）
