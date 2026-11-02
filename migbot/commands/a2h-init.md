---
description: Confirm auto-detected android / harmonyos / hvigorw / deveco / adb / hdc paths in plain language. Run on first install or whenever the paths change.
allowed-tools: Bash(a2h-bootstrap*), Bash(bash .migbot/bin/a2h-bootstrap*), Bash(a2h-agreement*), Bash(.migbot/bin/a2h-tool *), Bash(.migbot/bin/a2h *), Bash(test *), Bash(ls *), Bash(cat .migbot/config.json), Read, Edit, Write
---

`$ARGUMENTS` is ignored.

## Goal

Walk the user through confirming the paths in `.migbot/config.json` (`android`, `harmonyos`, `deveco`, `hvigorw`, `adb`, `hdc`) using plain conversational prompts. On success, set `confirmed: true` so `/a2h-run` stops redirecting here.

**Order matters: the User Experience Improvement Plan consent (§2) runs FIRST**, right after the silent runtime provisioning, before any path questions. The agreement is shown to the user *out of band* (a popup window, or a file path) — never pasted into this conversation — so it does not consume the agent's context window.

## 1. Provision runtime and read current config

For an injected install (`.migbot/install.json` exists), use `bash .migbot/bin/a2h-bootstrap --lang <zh|en>` instead; otherwise use the plugin PATH entry.

First run `Bash: a2h-bootstrap --lang <zh|en>` (the plugin's `bin/` is on PATH, so it is invokable as a bare command). This is **idempotent** and plays the role install.sh does in the non-plugin distribution: it stages the runtime into `.migbot/bin` (a2h-tool plus the `a2h` telemetry binary, invoked as `a2h <subcommand>`) and the policy docs into `.migbot/policies`, and creates a `.migbot/config.json` skeleton (with `telemetry_consent: "unset"`) if one does not exist yet. It never overwrites an existing config.

The bootstrap emits an OTA JSON result before its provisioning result. The public update
source is built into `a2h`; do not ask the user for an OBS URL or environment variable.
If `status` is `updated`, report the old and new versions and ask the user to restart
the CLI before continuing migration; end this init invocation so cached skills are
not mixed with the newly installed package. For `error`, briefly report that the
update failed and continue initialization with the installed version. Keep
`up_to_date` and intentional skips quiet. A source checkout is not an installed release.

Then read `.migbot/config.json` from the current working directory.

- If `a2h-bootstrap` is unavailable (the migbot plugin is not enabled) **and** the file does not exist, stop and tell the user: `"migbot plugin runtime not found. Make sure the migbot plugin is enabled, then re-run /a2h-init."`
- Parse these fields: `language`, `android`, `harmonyos`, `deveco`, `hvigorw`, `adb`, `hdc`, `confirmed`.

Do **not** ask about the paths yet — go straight to §2.

## 2. User Experience Improvement Plan — consent (runs first, unconditionally)

MigBot (迁移精灵) has an **optional** User Experience Improvement Plan (full agreement: `.migbot/policies/user-experience-improvement-plan.<lang>.md`). Upon participation, the tool uploads work-process artifacts (no personal data involved) at the end of the `/a2h-run` pipeline. Until the user **explicitly consents**, nothing is ever uploaded.

> **There is one consent flow, defined by `/a2h-privacy accept`.** In plugin mode there is no install-time prompt, so on a **first run** a2h-init runs that exact flow inline (§2.2) right here at the start — it shows the full agreement and asks for the decision before anything else. For an already-decided state it just notes the state and moves on. The steps in §2.2 **MUST stay identical to `/a2h-privacy` §B** — keep them in sync.

This section runs on **every** invocation (so users upgrading from an older client that had no consent field still get prompted). It is unconditional and comes before the path steps.

### 2.1 Branch on the current participation state

> **Install-level consent (agree once per machine).** Before reading the state below, run `Bash: .migbot/bin/a2h init-run` (no flags). It mints or reuses this machine's `install_id` (`~/.migbot/install.json`), copies it into `.migbot/config.json`, and — if the user already accepted or declined on this machine — copies that decision (`telemetry_consent`, `telemetry_consent_at`, `agreement_version`) into this project (stderr shows `inherited from install`). A project that inherits `granted` is enrolled without seeing the agreement again; the `migbot_session_id` is still minted per project.

First, **silently** probe the current policy version: run `Bash: a2h-agreement --lang <language> --check` and read `version` from its single-line JSON (this raises **no** window and shows **no** text). Call it `<current_version>`.

Read the `telemetry_consent` and `agreement_version` fields from `.migbot/config.json`:

| Current value | Action |
|---|---|
| `"granted"` and stored `agreement_version` == `<current_version>` (or `<current_version>` is empty) | Note `"You are enrolled in the User Experience Improvement Plan (consented at <telemetry_consent_at>). Run /a2h-privacy deny to withdraw, or /a2h-privacy status to see your migbot_session_id."`, then continue to §3. |
| `"denied"` and stored `agreement_version` == `<current_version>` (or empty) | Note `"⚠ You have declined the User Experience Improvement Plan, so the migration pipeline is DISABLED. Agreeing to the Plan is required to use migbot — declining means the tool cannot be used. Run /a2h-privacy accept to enable it."`, then **terminate the current initialization flow immediately — do not execute any subsequent steps (§3–§10)**. |
| `"granted"` or `"denied"` **but** stored `agreement_version` != `<current_version>` | The plan **materially changed** — your prior choice no longer applies (per the agreement's "material change ⇒ re-consent" clause). Tell the user `"The User Experience Improvement Plan was updated (<stored> → <current_version>); please review and choose again."` and **run the consent flow in §2.2 now**, then continue to §3. |
| `"unset"` / missing / any other value | **First run — run the consent flow in §2.2 now**, then continue to §3. |

> Operators: bump the policy `Version:` line **only** for material changes (new data category, changed purpose/storage/operator). Typo/wording fixes must keep the version so they don't needlessly re-prompt every user (agreement §7.4).

### 2.2 First-run consent flow — run the `/a2h-privacy accept` flow inline

This is the **same** flow as `/a2h-privacy accept` (§B of that command). **Perform it now** — do not merely tell the user to run it. These steps must stay in sync with `/a2h-privacy` §B.

1. **Display the agreement out of band (do NOT paste it into the conversation).** Run `Bash: a2h-agreement --lang <language>` and parse its single-line JSON verdict — `{"shown":..,"method":..,"path":..,"version":..,"reason":..}`. **Never** read or echo the policy body into this chat; the user reads it in the popup / file. Branch on `shown`:
   - `"popup"` → tell the user: `"The User Experience Improvement Plan has opened in a separate window. If no window appeared, open it yourself: <path>. Read it, then answer below."`
   - `"path"` → tell the user: `"Please open and read the User Experience Improvement Plan before deciding: <path>. (Your environment can't pop a window — open the file manually.)"`
   - `"error"`, or `a2h-agreement` is unavailable / not on PATH → the policy could not be located. Tell the user `"Policy file is missing. Reinstall the migbot plugin or contact the operator. Consent state was NOT modified."`, do **not** edit config, and continue to §3. (If you have the path `.migbot/policies/user-experience-improvement-plan.<language>.md` and it exists, you may instead give the user that path and proceed — but still never paste its contents.)
   - Keep the `version` value from the JSON as `agreement_version` for step 4 below.
2. After pointing the user at the agreement, on a separate block output exactly:

   > ```
   > Do you agree to the policy above? Please choose:
   >   1) I accept
   >   2) I refuse
   > Enter 1 or 2:
   > ```

3. **[HARD CONSTRAINT] Parse the user's next input** — treat it as **consent** if and only if it matches (case-insensitive, trimmed): `1`, `accept`, `agree`, `yes`, `y`, or `i accept`. **Any** other input (`2`, `refuse`, `deny`, `no`, empty, `cancel`, or changing the subject) is a **refusal**. Never infer consent from context.
4. **Refuse** → Edit `.migbot/config.json`: `"telemetry_consent": "denied"`, `"telemetry_consent_at": "null"`, `"agreement_version": "null"`; leave everything else untouched (**do not** mint the install handle, **do not** write `migbot_session_id`). Then **explicitly warn the user**: `"⚠ You have declined the User Experience Improvement Plan. Participation in the Plan is required to use migbot — declining means the tool cannot be used. The migration pipeline (from /a2h-spec onward) is DISABLED, and nothing is uploaded while declined. You can enable it any time with /a2h-privacy accept."`. **Terminate the current initialization flow immediately — do not execute any subsequent steps (§3–§10).**

   > **Refusing disables migbot AND blocks the flow.** Participation in the Plan is required to use migbot: the migration pipeline will refuse to run, and nothing is uploaded while declined. On refusal, no scripts are executed (no install handle is minted, no `migbot_session_id` is written) — the flow terminates immediately, strictly blocking all subsequent skill execution.
5. **Accept** → write config:
   - First, resolve the install handle: if `.migbot/config.json` already holds a non-empty `migbot_session_id`, **reuse it verbatim** (never rotate an existing handle — prior uploads are keyed to it). Only if it is missing/empty, mint one: run `Bash: uuidgen | tr 'A-Z' 'a-z'` and take its stdout (an opaque token — record it verbatim). It identifies this install for the deletion handle and for active-user counting; it is **not** a consent grant by itself.
   - Use the `agreement_version` returned by `a2h-agreement` in step 1 (the policy's bottom `Version: vX.Y`). If it was empty, leave the field out.
   - Edit `.migbot/config.json`, writing/updating: `"telemetry_consent_at": "<current ISO-8601 UTC>"` and `"agreement_version": "<version>"`; leave everything else untouched.
   - Run `Bash: .migbot/bin/a2h init-run --consent granted --migbot-session-id <handle>`. This writes `telemetry_consent: "granted"` and `migbot_session_id` into `.migbot/config.json` and pins the run identity. (`--migbot-session-id` only backfills an empty field, so a re-run never rewrites an existing handle.) Server-side registration of the consent happens automatically on the first upload.
   - **Clean up legacy OTel export config (one-time migration).** Earlier plugin versions enabled Claude Code's native OpenTelemetry export here; that channel is retired. If the project's `.claude/settings.json` exists, remove the top-level `otelHeadersHelper` key and any `env` keys named `CLAUDE_CODE_ENABLE_TELEMETRY`, `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA`, `CLAUDE_CODE_OTEL_HEADERS_HELPER_DEBOUNCE_MS`, or starting with `OTEL_` — **merge-preserve every other key**, and drop the `env` block only if it ends up empty. Skip silently when the file or the keys are absent.
   - Continue to §3.

## 2.5 App name confirmation (locked at init)

The **HarmonyOS APP display name is locked here, at init**. Later pipeline stages — in particular execute's `arkts-app-identity` — MUST read this locked value as the app_name input and never re-derive it from the Android source. Re-running init (including plus's post-onboarding init) sees a non-empty lock and skips the prompt, so the user is never asked twice.

Read the `app_name` field from `.migbot/config.json`:

- **Non-empty** → echo one line: `App name (locked): <app_name>`. Then run the AppScope hand-edit check below; do not prompt for a new name.
- **Empty** → determine the detected Android app name: run `Bash: .migbot/bin/a2h count-lines`, then read `android_app_name` from `.migbot/metrics/<run_id>/facts/code-lines.json` (the §9 baseline step below re-runs count-lines — that is fine; it is idempotent). Then ask the user:

  > `Detected Android app name: <name>. Use it as the HarmonyOS APP name? (yes / <new name>)`

  - `yes` / `y` / empty input → use the detected name.
  - Any other input → use that input verbatim as the new name.
  - Then lock it: run `Bash: .migbot/bin/a2h init-run --app-name "<name>"`. This writes `app_name` into `.migbot/config.json`.

  **Unattended / auto mode (the user never answers):** do NOT block. Lock the detected Android name if one was read; if none was detected, leave `app_name` empty and continue — downstream stages fall back to reading the Android source, same as pre-lock behavior.

**AppScope hand-edit check (locked name only).** When the locked name is non-empty, re-run `Bash: .migbot/bin/a2h count-lines` (idempotent; §9 re-runs it) and read `harmonyos_app_name` from `.migbot/metrics/<run_id>/facts/code-lines.json` — the AppScope-resolved display name (empty until the HarmonyOS project exists). If it is non-empty and differs from the locked `app_name`, the user hand-edited the AppScope name — ask:

> `AppScope app name is "<harmonyos_app_name>", which differs from the locked name "<app_name>". Adopt it as the new locked name? (yes / no)`

- `yes` / `y` → adopt: run `Bash: .migbot/bin/a2h init-run --adopt-appscope-name`. Adoption is the ONE sanctioned overwrite of the locked name (requires a runtime that supports the flag; older runtimes ignore it and keep the lock).
- `no` / `n` / empty input → keep the locked name.
- **Unattended / auto mode:** never adopt automatically — keep the locked name and continue.

## 3. Path confirmation gate + confirm `android`

**Gate:** If `confirmed == true` already, ask the user: `"Config already confirmed. Re-confirm paths? (yes / no)"`.

- `no` → skip §3-§9 path confirmation and **jump straight to §10** (the final report). Consent (§2) has already run, so upgraders are still covered. Exit after §10.
- `yes` (or `confirmed` was not already true) → run the full §3-§9 flow below.

Now confirm `android`. Show the current value to the user:

> `Detected Android source: <android>` (or `Android source not detected.` if value is the placeholder `../android-app` or the path doesn't exist)

Run `Bash: test -d "<android>"` (resolved relative to the install dir) to check whether the path exists. Report the result inline:

- exists → `✔ path exists`
- missing → `✘ path missing`

Then ask: `"Use this path, or enter a different one? (keep / <new path>)"`.

- `keep` → retain current value.
- Any other input → treat as the new path. Re-run `test -d` on the new value; if missing, warn `"That path doesn't exist. Use it anyway? (yes / no)"`. On `no`, ask again. On `yes`, accept.

## 4. Confirm `harmonyos`

Show: `HarmonyOS root: <harmonyos>` (almost always `.`).

Run `test -d "<harmonyos>"` and `test -f "<harmonyos>/oh-package.json5"`. Report:

- both exist → `✔ HarmonyOS project detected`
- dir exists, no `oh-package.json5` → `⚠ directory exists but no oh-package.json5 found`
- missing → `✘ path missing`

Ask: `"Use this path, or enter a different one? (keep / <new path>)"`. Same handling as step 3.

## 5. Confirm DevEco install path

Read the `deveco` field. `install.sh` auto-detects DevEco by scanning `$PATH`, then platform-appropriate locations (Windows: C/D/E/F drives; macOS: `/Applications`; Linux: `/opt`, `/usr/local`).

**If `deveco` is non-empty**, show: `DevEco install: <deveco>` and run `Bash: test -d "<deveco>"`.

- exists → `✔ DevEco directory found`
- missing → `✘ path no longer exists`

Then ask: `"Use this DevEco path, keep it, or override? (keep / <new path> / clear)"`.
- `keep` → retain.
- `<new path>` → replace; re-test with `test -d`.
- `clear` → set to empty string; treat as "skip".

**If `deveco` is empty** (auto-detection failed at install time), tell the user:

> `DevEco install path was not auto-detected on this machine. Please tell me where DevEco Studio is installed (e.g. "D:\\codetool\\DevEco Studio" or "/Applications/DevEco-Studio.app"), or type "skip" to leave it empty.`

- Plain path → run `test -d`; if missing, warn and ask again.
- `skip` → leave empty. Step 6 will then have to fall through to asking the user for hvigorw directly.

`deveco` is recorded so step 6 below (and any future tooling) can locate DevEco's bundled hvigor without re-scanning.

## 6. Confirm `hvigorw` (resolution chain)

`hvigorw` is the build wrapper. Standard HarmonyOS projects ship one at the project root, but some templates ship only `hvigorw.bat`, and others rely on DevEco's bundled hvigor. Walk this chain — **try silently in order, stop at the first hit**:

| # | Candidate                                            | Notes                                  |
|---|------------------------------------------------------|----------------------------------------|
| 1 | `hvigorw` field value (if non-empty)                 | Explicit user override; relative paths resolve against install dir |
| 2 | `<harmonyos>/hvigorw`                                | Project-local POSIX wrapper            |
| 3 | `<harmonyos>/hvigorw.bat`                            | Project-local Windows batch            |
| 4 | `<deveco>/tools/hvigor/bin/hvigorw`                  | DevEco-bundled POSIX wrapper (on macOS, deveco already includes `/Contents`) |
| 5 | `<deveco>/tools/hvigor/bin/hvigorw.bat`              | DevEco-bundled Windows batch           |

Test rules:
- For non-`.bat` candidates, use `Bash: test -x "<path>"`.
- For `.bat` candidates, use `Bash: test -f "<path>"` (the `-x` bit is unreliable for batch files on Windows / Git Bash).

When a candidate hits, that becomes the **resolved hvigorw**.

### 6.1 If a candidate hit

Report: `✔ hvigorw resolved: <path> (candidate #N)`.

Ask: `"Use this hvigorw, or override? (keep / <new path>)"`.
- `keep` → write the resolved path into the `hvigorw` field. Use absolute path when the candidate is outside `<harmonyos>` (i.e. candidates 4-5); use relative form (`hvigorw` or `hvigorw.bat`) for candidates 2-3; preserve the original value for candidate 1.
- `<new path>` → validate with the same `test -x` / `test -f` rule. If valid, store as override.

### 6.2 If no candidate hit

Report:
> `✘ hvigorw not found in any of the standard locations:
>   - <harmonyos>/hvigorw
>   - <harmonyos>/hvigorw.bat
>   - <deveco>/tools/hvigor/bin/hvigorw[.bat]   (deveco = "<deveco-or-empty>")`

If `deveco` is empty (or `clear`-ed in step 5), tell the user: `"DevEco install path is not set, so I couldn't check candidates 4-5. If you want me to use DevEco's bundled hvigor, give me the DevEco install dir; otherwise give me the full path to a working hvigorw[.bat]."`

Then ask: `"Path? (or 'skip' to leave hvigorw empty — build will fail until you fix this)"`.

- Path looks like a DevEco install dir (contains `tools/hvigor`) → set `deveco` field, then re-run candidates 4-5 from the chain above.
- Path looks like a direct hvigorw[.bat] → validate with `test -x` / `test -f`, store as override.
- `skip` → leave `hvigorw` empty. Continue to step 7.

## 7. Confirm `adb` and `hdc` paths

These two fields let `a2h-tool validate` locate adb / hdc when they are not on `$PATH`.

### 7.1 `adb`

Try to auto-detect — **stop at the first hit**:

| # | Candidate | Notes |
|---|-----------|-------|
| 1 | `adb` field value (if non-empty and executable) | Explicit user override in config.json |
| 2 | `command -v adb` | Already on PATH |
| 3 | `$HOME/Library/Android/sdk/platform-tools/adb` | macOS default Android SDK location |
| 4 | `/usr/local/bin/adb` | Common symlink location |

If a candidate hits, report: `✔ adb resolved: <path> (candidate #N)`.

Ask: `"Use this adb, or override? (keep / <new path> / skip)"`.
- `keep` → write resolved path into `adb` field (leave empty for candidate 2 — it's already on PATH, no need to hardcode).
- `<new path>` → validate with `test -x`; if missing, warn and re-ask.
- `skip` → leave `adb` empty. validate will still pass if adb is on PATH at runtime.

If no candidate hits, tell the user:

> `adb not found. Android emulator checks will fail. Please provide the full path to adb, or type "skip" to leave it empty.`

### 7.2 `hdc`

Try to auto-detect — **stop at the first hit**:

| # | Candidate | Notes |
|---|-----------|-------|
| 1 | `hdc` field value (if non-empty and executable) | Explicit user override in config.json |
| 2 | `command -v hdc` | Already on PATH |
| 3 | `<deveco>/Contents/sdk/default/openharmony/toolchains/hdc` | DevEco-bundled hdc (macOS) |
| 4 | `$HOME/Library/Huawei/Sdk/openharmony/toolchains/hdc` | Standalone HarmonyOS SDK |

If a candidate hits, report: `✔ hdc resolved: <path> (candidate #N)`.

Ask: `"Use this hdc, or override? (keep / <new path> / skip)"`.
- `keep` → write resolved path into `hdc` field (leave empty for candidate 2).
- `<new path>` → validate with `test -x`; if missing, warn and re-ask.
- `skip` → leave `hdc` empty.

If no candidate hits and `deveco` is empty, hint: `"DevEco install path is not set, so I couldn't check DevEco-bundled hdc. Provide the full path to hdc, a DevEco install dir, or type 'skip'."`.

If user gives a DevEco install dir → set `deveco` field, re-run candidate 3.

## 8. Write config + mark confirmed

Use the Edit tool to update `.migbot/config.json`. The final shape:

```json
{
  "android": "<confirmed>",
  "harmonyos": "<confirmed>",
  "hvigorw": "<resolved-or-empty>",
  "deveco": "<confirmed-or-empty>",
  "adb": "<resolved-or-empty>",
  "hdc": "<resolved-or-empty>",
  "language": "<preserved>",
  "confirmed": true
}
```

Preserve `language` and any extra keys the user may have added; only overwrite `android`, `harmonyos`, `hvigorw`, `deveco`, `adb`, `hdc`, and `confirmed`. **Preserve** `telemetry_consent`, `telemetry_consent_at`, `migbot_session_id`, `agreement_version` — those are managed by §2 above; do not touch them here.

## 9. Final validation

After the path work is done, capture and report the init-stage signals (both best-effort and tier-gated — ignore their exit status; neither blocks init):

1. **Pin the run identity.** Run `Bash: .migbot/bin/a2h init-run`. This pins `run_id` / `project` / `app_version` into `.migbot/config.json` — the identity every telemetry upload of this migration hangs off. It is **idempotent**: an existing run_id is reused as-is (re-running init is harmless), and if the config was lost but `.migbot/metrics/` still holds a run directory the original run_id is recovered. A deliberate restart requires the explicit `--fresh` flag (never pass it unless the user asked to start the migration over).
2. **Android baseline.** Run `Bash: .migbot/bin/a2h count-lines`. This counts the Android-side code lines and reads the Android app name, recording them as a fact (HarmonyOS doesn't exist yet at init). It is the top-of-funnel signal the dashboard uses for active-user / active-project stats.
3. **Init-stage boundary.** Run `Bash: .migbot/bin/a2h mark-stage a2h-init`. This marks the `a2h-init` stage boundary; the session transcript that the lifecycle hooks upload is attributed to it server-side.

Run `.migbot/bin/a2h-tool validate`. If it returns `{"ok":true}`, tell the user:

> `Config confirmed. You can now run /a2h-build to verify HarmonyOS compiles, or /a2h-run to start the migration pipeline.`

**If `telemetry_consent` is `granted`**, append on its own line (substituting the actual value from `.migbot/config.json`): `Please keep a record of your migbot_session_id: <migbot_session_id> — it is the credential you'll need to request deletion of your uploaded data later.` (Echo only the stored value; never explain how it is generated.)

If it returns failures, list them and tell the user:

> `Config saved with confirmed: true, but a2h-tool reports: <failures>. Re-run /a2h-init or fix the paths manually.`

## 10. Migration strategy (standard ↔ 1to1)

Run this after §9 validation succeeds and only if the config was written and read back without
error. This is the last init step; do not run it if §8 or §9 failed. Readiness warnings from §9 do
not skip it.

### 10.1 Read the installed strategy

The plugin install record `.migbot/plugin/install.json` owns the strategy. Do **not** duplicate a
strategy field in `.migbot/config.json` or infer the installed strategy from previous chat messages.
Run:

```bash
python3 .migbot/bin/a2h-router.py
```

(On Windows use `python .migbot\bin\a2h-router.py`; the launcher is plain stdlib Python. This is an
internal replacement script, not a separate slash command.)

- If the record or launcher is absent (a legacy install without the plugin), keep the confirmed
  config, explain that strategy switching requires installing the plugin into this project, and
  proceed to the final report with strategy selection unavailable. Do not scan other projects or
  copy resources by hand.
- If the command errors, skip the remaining strategy steps and give the final report with the error.
- If `recoveryRequired` is true, report that recovery requires exiting Claude Code and running
  `python3 .migbot/bin/a2h-router.py --recover --offline`; skip selection and give the final report.
- If `request` is non-null, report its pending target strategy and finish this turn so it can be
  applied; do not submit another request or ask for a new selection while one is pending.

### 10.2 Display the comparison before asking (required visible output)

You MUST send a normal user-visible message containing the current strategy and the comparison
below BEFORE asking. Printing it only in tool output, or showing only option labels/descriptions,
does not fulfill this step. Show it on every init that reaches strategy selection, including
reinitialization and when a strategy is already installed.

There are exactly two migration strategies; keeping the current strategy is an action, not a third
strategy. Replace `<当前策略>` with the launcher's result and translate the following text into the
selected `language` in `.migbot/config.json`. Preserve all three comparison rows.

当前迁移策略：**<当前策略>**。可选择以下两种迁移方式；“保持当前策略”表示不切换。

| 对比项 | 标准流水线（默认） | 一比一迁移 |
|---|---|---|
| 核心目标 | 按功能需求完成 HarmonyOS 迁移，交付可用的 UI 和业务功能 | 重点一比一还原原应用的业务、后端逻辑，保持业务规则、数据处理、接口交互、状态流转及异常处理的一致性 |
| 实现方式 | 按功能 Spec 和功能切片组织实现，可结合 HarmonyOS 特性调整代码结构 | 按源类、方法和逻辑单元逐项对应目标实现，保留业务控制流；平台差异按已确认的适配方案处理 |
| 验证重点 | 检查功能契约、编译结果、UI 和业务功能是否满足需求 | 在功能验证基础上，逐项核对源逻辑与目标实现，并保留业务行为一致性的验证证据 |

两种方式均使用 `a2h-spec → a2h-plan → a2h-execute → a2h-verify → a2h-retrospect` 流程。
一比一迁移以业务、后端逻辑还原为重点，不代表逐行复制或自动保证 100% 等价。

Do not promise either strategy is necessarily faster or more successful. Explain class/method
mappings, graphs, sidecars, Base Bundles, and verification evidence only as support for business
and backend logic restoration when more detail is needed. Common skills remain shared; matching
skills are replaced as whole directories and variant-only skills/agents are added.

### 10.3 Ask for the strategy after displaying the comparison

After sending the comparison, ask the user with one single-choice question. Use Claude Code's
built-in `AskUserQuestion` tool (it is always available; there is no feature gate), keeping the
short contrast in the question text too:

```json
{
  "questions": [
    {
      "header": "Migration strategy",
      "question": "Initialization paths are confirmed; the current strategy is <current strategy>.\nStandard pipeline: migrate by feature requirement, free to adjust structure for HarmonyOS.\nOne-to-one: prioritize restoring business/backend logic, keeping business rules, data handling, interface interaction and state flow consistent.\nWhich migration strategy should this project use?",
      "multiSelect": false,
      "options": [
        { "label": "Keep current strategy", "description": "Continue with the current strategy; replace nothing." },
        { "label": "Standard pipeline", "description": "Install default; migrate by feature Spec and slices, free to adjust structure for HarmonyOS." },
        { "label": "One-to-one migration", "description": "Prioritize one-to-one restoration of business/backend logic, matching rules, data handling, interfaces and state flow." }
      ]
    }
  ]
}
```

If `AskUserQuestion` is **not** available (non-interactive mode), do **not** write the
multiple-choice question as a textual message. Ask ONE concise plain-text question instead and wait
for an explicit answer in the next user message.

- Map standard to `standard` and one-to-one to `1to1`. Accept a free-text answer only when it clearly
  selects one of them; if it is ambiguous or asks about differences, explain and ask again.
- Keeping the current strategy, cancelling, or rejecting the question changes nothing; preserve the
  confirmed paths and proceed to the final report. No answer means keep waiting, not auto-selecting.
- Because the reply arrives asynchronously, end the turn after asking if the answer has not arrived
  yet; process the answer when it arrives. Do not submit any switch before the answer.

### 10.4 Preview and submit only after the answer

For one-to-one run, in order (use `standard` for the standard pipeline):

```bash
python3 .migbot/bin/a2h-router.py --profile 1to1 --dry-run
python3 .migbot/bin/a2h-router.py --profile 1to1 --offline
```

Submit only if the preview succeeds. Claude Code has no idle-session callback, so the submission
uses `--offline` to apply immediately on disk. The script replaces only managed
skills/agents/commands and preserves custom resources, plugin configuration, and the initialization
config written above. Existing Spec/execution artifacts prevent switching; explain that a new
migration project is required. Do not remove artifacts to bypass that check.

- If managed resources have manual edits, show the conflicts and ask whether to back up those edits
  and replace them; only after that explicit answer add `--backup-modified` to both preview and
  submission. Unmanaged same-name resources always block replacement.
- `status=unchanged` means the target strategy is already active.
- `status=applied` means the disk switch completed: report the new strategy, give the final report,
  and end the turn. Skills under `.claude/skills/` and agents under `.claude/agents/` are re-read
  automatically within the session (the agent watcher picks up changes within a few seconds), and
  commands are identical across both strategies and never change — no manual reload is needed. Only
  if the host reports a newly added skill/agent as unavailable, mention `/reload-skills` as a
  fallback; a session restart is needed only when `.claude/skills/` or `.claude/agents/` did not
  exist when the session started (plugin installed mid-session). Do not start `/a2h-build` or
  `/a2h-run` in this turn.
- `status=queued` (only when submitted without `--offline`) means only a request was submitted; end
  the turn and apply it later with a bare `--offline`. `--recover --offline` is for interrupted
  transactions, not for applying a queued request. A queued request is not a completed switch.
- On failure, preserve the confirmed initialization config and explain the switch error separately.
  Never rewrite install records by hand. A request can be cancelled with `--cancel`; recovery of an
  interrupted transaction requires exiting Claude Code before `--recover --offline`. Never run
  recovery from inside this session.

## 11. Final report

After the §9 validation result (or directly here if the §3 gate chose `no`), **append** this block — it is **mandatory**, so the user always knows how to join/withdraw:

> ```
> ── User Experience Improvement Plan ──
> Current state: <granted (enrolled — migbot enabled) / denied (declined — migbot DISABLED)> (last changed: <telemetry_consent_at>)
> Participation in the Plan is REQUIRED to use migbot; declining disables the migration pipeline.
> Full agreement: .migbot/policies/user-experience-improvement-plan.<language>.md
> Change participation:
>   /a2h-privacy accept   enrol in the Plan and enable migbot (the Plan is shown in full first)
>   /a2h-privacy deny     decline — disables migbot
>   /a2h-privacy status   show the current state
> You may also manually edit .migbot/config.json's telemetry_consent field.
> ```

Also report the migration strategy outcome separately from this telemetry block: the current
strategy, and one of — switched (`applied`, matching `profile`), queued (pending; check the next
turn), unchanged (already active), selection unavailable (plugin not installed), or failed (with the
error and the next action). A passing `/a2h-init` certifies the initialization config only; it does
not certify that a queued or failed strategy switch completed.

---

## Notes

- Path inputs are taken verbatim — do not auto-resolve relative paths to absolute. The user may prefer relative paths (e.g. `../android-app`) for portability. **Exception**: candidates 4-5 of the hvigorw chain ARE stored as absolute paths because they live outside `<harmonyos>`.
- Never edit `.claude/skills/`, `.claude/agents/`, or `.claude/commands/` directly from this command — the only sanctioned writer of skills/agents/commands is the router launcher in §10. This command otherwise touches only `.migbot/config.json` (plus the `CLAUDE.md` language block).
- §2 captures consent **only on a first run** (`telemetry_consent` unset), by running the exact `/a2h-privacy accept` flow inline (§2.2). For `granted`/`denied` states it is read-only. There is still a single consent flow — §2.2 mirrors `/a2h-privacy` §B and must not diverge; never invent a different consent path here.
- The agreement is **never** pasted into this conversation. `a2h-agreement` shows it out of band (popup window, else a file path) to keep it out of the agent's context window. If the popup cannot be raised (WSL / Git Bash / headless / macOS sandbox), the script degrades to printing the path — it does **not** fall back to dumping the text, and neither should you.
