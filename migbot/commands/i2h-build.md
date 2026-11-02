---
description: Validate config and run hvigorw assembleHap on the HarmonyOS project
allowed-tools: Bash(.migbot/bin/i2h-tool *), Bash(.migbot/bin/i2h *)
---

## Goal

Compile the HarmonyOS project to verify the migration results.

## Steps

### 1. Validate configuration

Run `.migbot/bin/i2h-tool validate` to check all required paths.

If it returns `{ok:false}`:
- List each failure to the user
- Suggest running `/i2h-init` to fix paths
- Stop

### 2. Run build

Run `.migbot/bin/i2h-tool build` to compile the project.

Stream the output to the user in real-time.

Report the final exit code:
- Exit 0: ✅ Build succeeded
- Non-zero: ❌ Build failed

### 3. Report token usage

Run `Bash: .migbot/bin/i2h mark-stage i2h-build` to record this stage's token usage.

This is best-effort and consent-gated — ignore its exit status (it never affects the build result).

### 4. Show build artifacts

If build succeeded, show the HAP file location:
```
✅ Build completed successfully

HAP file: entry/build/default/outputs/default/entry-default-unsigned.hap

Next steps:
  - Install: hdc install <hap-file>
  - Run: hdc shell aa start -a EntryAbility -b <bundle-name>
```

If build failed, show error summary and suggest next steps:
```
❌ Build failed

Common issues:
  1. Missing dependencies: Check oh-package.json5
  2. Syntax errors: Review the error log above
  3. Path issues: Re-run /i2h-init

For detailed errors, check: entry/build/default/cache/default/*/compiler.log
```
