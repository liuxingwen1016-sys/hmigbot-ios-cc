---
description: 用人话确认自动探测到的 android / harmonyos / hvigorw / deveco / adb / hdc 路径。首次安装或路径变化时跑。
allowed-tools: Bash(a2h-bootstrap*), Bash(bash .migbot/bin/a2h-bootstrap*), Bash(a2h-agreement*), Bash(.migbot/bin/a2h-tool *), Bash(.migbot/bin/a2h *), Bash(test *), Bash(ls *), Bash(cat .migbot/config.json), Read, Edit, Write
---

`$ARGUMENTS` 忽略。

## 目标

用对话式提示带用户逐项确认 `.migbot/config.json` 中的路径（`android`、`harmonyos`、`deveco`、`hvigorw`、`adb`、`hdc`）。完成后置 `confirmed: true`，让 `/a2h-run` 不再跳到这里。

**顺序很重要：用户体验改善计划的同意（§2）最先执行**——在静默就位运行时之后、任何路径询问之前。协议**以带外方式**展示给用户（弹窗，或文件路径），**绝不**贴进本对话，以免占用 Agent 的上下文窗口。

## 1. 就位运行时并读当前配置

若工程有 `.migbot/install.json`，改用 `bash .migbot/bin/a2h-bootstrap --lang <zh|en>`；否则用插件 PATH 上的入口。

先跑 `Bash: a2h-bootstrap --lang <zh|en>`（plugin 的 `bin/` 在 PATH 上，可作裸命令直接调用）。它**幂等**，在 plugin 模式下扮演 install.sh 的角色：把运行时就位到 `.migbot/bin`（a2h-tool，外加 `a2h` 遥测二进制，按 `a2h <子命令>` 调用）、把策略文档就位到 `.migbot/policies`，并在 `.migbot/config.json` 不存在时创建骨架（含 `telemetry_consent: "unset"`）。已存在的 config 绝不覆盖。

bootstrap 在就位结果之前会输出 OTA JSON。公开更新源内置在 `a2h` 中，不要求用户填写
OBS URL 或环境变量。若 `status` 为 `updated`，告知旧版本、新版本并请用户重启 CLI，
结束本次初始化，避免已缓存的旧 skill 和新包混用；若为 `error`，简短说明更新失败，
继续使用当前版本初始化。`up_to_date` 和主动跳过保持安静。源码目录不当作已安装发布包。

然后读 cwd 下的 `.migbot/config.json`。

- 若 `a2h-bootstrap` 不可用（migbot plugin 未启用）**且**文件不存在 → 停下并告诉用户：`"未找到 migbot plugin 运行时。请确认 migbot plugin 已启用，然后重新运行 /a2h-init。"`
- 解析这些字段：`language`、`android`、`harmonyos`、`deveco`、`hvigorw`、`adb`、`hdc`、`confirmed`。

**先别问路径**——直接进 §2。

## 2. 用户体验改善计划——同意（最先执行，无条件）

MigBot（迁移精灵）包含一个**可选**的用户体验改善计划（协议全文：`.migbot/policies/user-experience-improvement-plan.<lang>.md`）。参与后，工具会在 `/a2h-run` 收尾时上传工作过程产物（不涉及个人数据），用于改进迁移效果与产品质量。在用户**明确同意**之前**绝不**上传任何数据。

> **同意流程只有一套，由 `/a2h-privacy accept` 定义。** plugin 模式没有安装期询问，所以**首次运行**时 a2h-init 会在最开始就**就地内联执行那套流程**（§2.2）——先展示协议全文、征询用户选择，再做其它任何事。已决定状态则只告知并继续。§2.2 的步骤**必须与 `/a2h-privacy` §B 完全一致**，不得漂移。

本节在**每次**调用时都运行（确保老版本升级上来、还没设置过授权的用户也能补登）。它无条件、且排在路径步骤之前。

### 2.1 按当前参与状态分支

> **安装级同意（每台机器只同意一次）。** 在读取下面的状态之前，先跑 `Bash: .migbot/bin/a2h init-run`（不带参数）。它会生成或沿用本机的 `install_id`（`~/.migbot/install.json`），写进 `.migbot/config.json`；若用户在本机已经接受/拒绝过，会把该决定（`telemetry_consent`、`telemetry_consent_at`、`agreement_version`）复制进本工程（stderr 出现 `inherited from install`）。继承到 `granted` 的工程无需再看协议；`migbot_session_id` 仍按工程各自生成。

先**静默**探测当前协议版本：跑 `Bash: a2h-agreement --lang <language> --check`，从其单行 JSON 里读 `version`（**不弹窗、不显示任何正文**）。记为 `<current_version>`。

读 `.migbot/config.json` 的 `telemetry_consent` 与 `agreement_version` 字段：

| 当前值 | 行为 |
|---|---|
| `"granted"` 且存储的 `agreement_version` == `<current_version>`（或 `<current_version>` 为空） | 告知 `"您已参与用户体验改善计划（同意时间：<telemetry_consent_at>）。输入 /a2h-privacy deny 可退出，/a2h-privacy status 可查看你的 migbot_session_id。"`，然后继续到 §3。 |
| `"denied"` 且存储的 `agreement_version` == `<current_version>`（或为空） | 告知 `"⚠ 您已拒绝用户体验改善计划，因此迁移流水线已被禁用。同意本计划是使用 migbot 的前提——拒绝将导致无法使用该工具。输入 /a2h-privacy accept 即可启用。"`，然后**立即终止当前初始化流程，不再执行 §3-§10 的任何后续步骤**。 |
| `"granted"` 或 `"denied"`，**但**存储的 `agreement_version` != `<current_version>` | 计划发生了**实质性变更**——您此前的选择不再适用（依协议"实质性变更⇒重新征求同意"条款）。告诉用户 `"用户体验改善计划已更新（<stored> → <current_version>），请重新阅读并再次选择。"`，并**立即执行 §2.2 的同意流程**，然后继续到 §3。 |
| `"unset"` / 缺失 / 任何其他值 | **首次运行——立即执行 §2.2 的同意流程**，然后继续到 §3。 |

> 运营方注意：**仅**在发生实质性变更（新增数据类别、变更用途/存储地/运营主体）时才提升协议 `版本号`。错别字/措辞修订须保持版本不变，以免无谓地每次都重新弹问（协议第七条第四款）。

### 2.2 首次同意流程——就地执行 `/a2h-privacy accept`

这与 `/a2h-privacy accept`（该命令的 §B）是**同一套流程**。**现在就执行它**——不要只让用户自己去跑。这些步骤必须与 `/a2h-privacy` §B 保持同步。

1. **以带外方式展示协议（绝不贴进对话）。** 跑 `Bash: a2h-agreement --lang <language>`，解析它输出的单行 JSON 结论——`{"shown":..,"method":..,"path":..,"version":..,"reason":..}`。**绝不**把协议正文读进/回显到本对话；用户在弹窗/文件里读。按 `shown` 分支：
   - `"popup"` → 告诉用户：`"用户体验改善计划已在单独的窗口中打开。若没弹出窗口，请自行打开：<path>。读完后在下方作答。"`
   - `"path"` → 告诉用户：`"请在决定前打开并阅读用户体验改善计划：<path>。（当前环境无法弹窗，请手动打开文件。）"`
   - `"error"`，或 `a2h-agreement` 不可用 / 不在 PATH 上 → 定位不到协议文件。告诉用户 `"协议文件缺失。请重装 migbot plugin 或联系运营方。同意状态未做任何修改。"`，**不要**改 config，继续到 §3。（若你已知路径 `.migbot/policies/user-experience-improvement-plan.<language>.md` 且文件存在，可改为把该路径给用户并继续——但仍**绝不**贴出其内容。）
   - 保留 JSON 里的 `version` 作为下面第 4 步的 `agreement_version`。
2. 指引用户去看协议之后，另起一块，原样输出：

   > ```
   > 您是否同意以上协议？请选择：
   >   1) 我接受
   >   2) 我拒绝
   > 请输入 1 或 2：
   > ```

3. **【硬约束】解析用户的下一条输入**——仅当它（忽略大小写、去首尾空白）匹配以下之一才视为**同意**：`1`、`accept`、`agree`、`yes`、`y`、`i accept`、`我接受`、`同意`。**其他任何**输入（`2`、`拒绝`、`deny`、`no`、空、`cancel`、或转移话题）一律视为**拒绝**。绝不从上下文推断同意。
4. **拒绝** → Edit `.migbot/config.json`：`"telemetry_consent": "denied"`、`"telemetry_consent_at": "null"`、`"agreement_version": "null"`；其余字段不动（**不**生成安装句柄，**不**写入 `migbot_session_id`）。然后**明确输出警告**：`"⚠ 您已拒绝用户体验改善计划。参与本计划是使用 migbot 的前提——拒绝将导致无法使用该工具，迁移流水线（从 /a2h-spec 起）已被禁用，拒绝期间也不上报任何数据。随时可输入 /a2h-privacy accept 启用。"`。**立即终止当前初始化流程，不再执行 §3-§10 的任何后续步骤。**

   > **拒绝即禁用 migbot 且阻断流程。** 参与本计划是使用 migbot 的前提：拒绝后迁移流水线将拒绝运行，拒绝期间也不上报任何数据。拒绝时不执行任何脚本（不生成安装句柄、不写入 `migbot_session_id`），直接终止，严格阻断后续所有 skill 流程的执行。
5. **接受** → 写 config：
   - 先确定安装句柄：若 `.migbot/config.json` 已有非空的 `migbot_session_id`，**原样沿用**（绝不轮换已有句柄——此前上报都挂在它下面）。只有缺失/为空时才生成：跑 `Bash: uuidgen | tr 'A-Z' 'a-z'`，取其 stdout（不透明令牌——原样记录）。它用于删除句柄与活跃用户计数，本身**不**等于同意授权。
   - 用第 1 步里 `a2h-agreement` 返回的 `agreement_version`（即协议文末 `Version: vX.Y`）。若为空则不写该字段。
   - Edit `.migbot/config.json`，写入/更新：`"telemetry_consent_at": "<当前 ISO-8601 UTC>"`、`"agreement_version": "<版本>"`；其余字段不动。
   - 运行 `Bash: .migbot/bin/a2h init-run --consent granted --migbot-session-id <句柄>`。它把 `telemetry_consent: "granted"` 与 `migbot_session_id` 写入 `.migbot/config.json` 并固化运行标识。（`--migbot-session-id` 仅在字段为空时回填，重复执行不会覆盖已有句柄。）同意凭证会在首次上传时自动登记到服务端。
   - 继续到 §3。

## 2.5 App 名称确认（init 时锁定）

**鸿蒙 APP 显示名在 init 这里锁定。** 之后的流水线阶段——尤其是 execute 的 `arkts-app-identity`——**必须**读取这个锁定值作为 app_name 输入，不得再从安卓源码重新推导。重跑 init（包括 plus 引导页之后的 init）会看到非空锁定值并跳过询问，用户永远不会被问两次。

读 `.migbot/config.json` 的 `app_name` 字段：

- **非空** → 回显一行：`App 名称（已锁定）：<app_name>`。然后跑下面的 AppScope 改名检查；不再询问新名称。
- **为空** → 获取自动检测的安卓名：跑 `Bash: .migbot/bin/a2h count-lines`，然后从 `.migbot/metrics/<run_id>/facts/code-lines.json` 读 `android_app_name`（下面 §9 的基线步骤还会再跑一次 count-lines——没关系，它是幂等的）。然后问用户：

  > `检测到的安卓 App 名称：<名称>。用它作为鸿蒙 APP 名称吗？(yes / <新名称>)`

  - `yes` / `y` / 空输入 → 使用检测到的名称。
  - 其它任何输入 → 原样当作新名称。
  - 然后锁定：跑 `Bash: .migbot/bin/a2h init-run --app-name "<名称>"`。它把 `app_name` 写入 `.migbot/config.json`。

  **无人值守 / 自动模式（用户始终不回答）：** 不要卡住。读到了安卓名就用它锁定；没读到就保持 `app_name` 为空并继续——下游阶段回退为读取安卓源码，与锁定前的行为一致。

**AppScope 改名检查（仅锁定名非空时）。** 重跑 `Bash: .migbot/bin/a2h count-lines`（幂等；§9 还会再跑一次），从 `.migbot/metrics/<run_id>/facts/code-lines.json` 读 `harmonyos_app_name`——AppScope 解析出的显示名（鸿蒙工程不存在前为空）。非空且 ≠ 锁定名，说明用户手改过 AppScope 名——询问：

> `AppScope 应用名是「<harmonyos_app_name>」，与锁定名「<app_name>」不一致。采纳为新锁定名？(yes / no)`

- `yes` / `y` → 采纳：跑 `Bash: .migbot/bin/a2h init-run --adopt-appscope-name`。采纳是覆盖锁定名的**唯一合法路径**（需要支持该 flag 的 runtime；旧 runtime 会忽略它、锁定名保持不变）。
- `no` / `n` / 空输入 → 保持锁定名。
- **无人值守 / 自动模式：** 绝不自动采纳——保持锁定名并继续。

## 3. 路径确认门 + 确认 `android`

**门控：** 如果 `confirmed == true`，问用户：`"配置已确认过。还要重新确认路径吗？(yes / no)"`。

- `no` → 跳过 §3-§9 的路径确认，**直接到 §10**（最终报告）。同意（§2）已经跑过了，升级用户也覆盖到了。§10 完成后退出。
- `yes`（或 `confirmed` 本就不是 true）→ 继续执行下面的 §3-§9 完整流程。

现在确认 `android`。把当前值给用户看：

> `已探测到 Android 源：<android>`（或 `未探测到 Android 源。` 如果是占位符 `../android-app` 或路径不存在）

跑 `Bash: test -d "<android>"`（相对安装目录解析）确认路径是否存在。结果在行内回显：

- 存在 → `✔ 路径存在`
- 缺失 → `✘ 路径不存在`

然后问：`"用这个路径，还是改一个？(keep / <新路径>)"`。

- `keep` → 保留当前值。
- 任何其他输入 → 当作新路径。重新跑 `test -d`；缺失则警告 `"这个路径不存在。还是用它吗？(yes / no)"`。`no` → 再问；`yes` → 接受。

## 4. 确认 `harmonyos`

显示：`HarmonyOS 根：<harmonyos>`（几乎都是 `.`）。

跑 `test -d "<harmonyos>"` 和 `test -f "<harmonyos>/oh-package.json5"`。回显：

- 都存在 → `✔ 检测到 HarmonyOS 工程`
- 目录在但没 `oh-package.json5` → `⚠ 目录在但找不到 oh-package.json5`
- 缺失 → `✘ 路径不存在`

问：`"用这个路径，还是改一个？(keep / <新路径>)"`。处理同第 3 步。

## 5. 确认 DevEco 安装路径

读 `deveco` 字段。`install.sh` 装的时候会自动探测：先看 `$PATH`，再扫平台标准目录（Windows: C/D/E/F 盘；macOS: `/Applications`；Linux: `/opt`、`/usr/local`）。

**`deveco` 非空** → 显示 `DevEco 安装目录：<deveco>`，跑 `Bash: test -d "<deveco>"`。

- 存在 → `✔ DevEco 目录存在`
- 不存在 → `✘ 路径已失效`

然后问：`"用这个 DevEco 路径，保留还是覆盖？(keep / <新路径> / clear)"`。
- `keep` → 保留。
- `<新路径>` → 替换；用 `test -d` 重新校验。
- `clear` → 清空；按"跳过"处理。

**`deveco` 为空**（安装时自动探测失败）→ 告诉用户：

> `没有在这台电脑上自动探测到 DevEco 安装路径。请告诉我 DevEco Studio 装在哪里（比如 "D:\\codetool\\DevEco Studio" 或 "/Applications/DevEco-Studio.app"），或者输入 "skip" 留空。`

- 普通路径 → `test -d` 校验；不存在则警告并再问。
- `skip` → 留空。第 6 步会因此走不到候选 4-5，得直接问用户要 hvigorw 路径。

`deveco` 字段记下来给第 6 步（以及未来工具）用，避免重复扫盘找 hvigor。

## 6. 确认 `hvigorw`（解析链）

`hvigorw` 是构建包装脚本。标准 HarmonyOS 工程根目录会自带，但有些模板只发 `hvigorw.bat`，还有些情况要用 DevEco 自带的 hvigor 兜底。**按下面顺序静默尝试，命中即停**：

| # | 候选                                                  | 说明                                    |
|---|------------------------------------------------------|-----------------------------------------|
| 1 | `hvigorw` 字段值（非空时）                            | 用户显式覆盖；相对路径相对安装目录解析   |
| 2 | `<harmonyos>/hvigorw`                                | 项目自带的 POSIX 包装                    |
| 3 | `<harmonyos>/hvigorw.bat`                            | 项目自带的 Windows 批处理                |
| 4 | `<deveco>/tools/hvigor/bin/hvigorw`                  | DevEco 自带的 POSIX 包装（macOS 下 deveco 已含 `/Contents`） |
| 5 | `<deveco>/tools/hvigor/bin/hvigorw.bat`              | DevEco 自带的 Windows 批处理             |

测试规则：
- 非 `.bat` 候选 → `Bash: test -x "<path>"`
- `.bat` 候选 → `Bash: test -f "<path>"`（在 Windows / Git Bash 下 `-x` 对批处理文件不可靠）

候选命中 → 它就是**解析后的 hvigorw**。

### 6.1 命中

回显：`✔ hvigorw 已解析：<path>（候选 #N）`。

问：`"用这个 hvigorw，还是覆盖？(keep / <新路径>)"`。
- `keep` → 把解析路径写到 `hvigorw` 字段。当候选在 `<harmonyos>` 之外（候选 4-5）→ 用绝对路径；候选 2-3 → 用相对形式（`hvigorw` 或 `hvigorw.bat`）；候选 1 → 保留原值。
- `<新路径>` → 用同样的 `test -x` / `test -f` 规则校验。通过则存为覆盖值。

### 6.2 全部未命中

回显：
> `✘ hvigorw 在所有标准位置都没找到：
>   - <harmonyos>/hvigorw
>   - <harmonyos>/hvigorw.bat
>   - <deveco>/tools/hvigor/bin/hvigorw[.bat]   (deveco = "<deveco 或空>")`

如果 `deveco` 是空（或第 5 步被 `clear`），告诉用户：`"DevEco 安装路径没设，所以候选 4-5 跳过了。要用 DevEco 自带的 hvigor，给我 DevEco 安装目录；要么直接给我可用的 hvigorw[.bat] 完整路径。"`

然后问：`"路径？（或者 'skip' 留空 —— 留空后续 build 会失败）"`。

- 路径像 DevEco 安装目录（包含 `tools/hvigor`）→ 设 `deveco` 字段，重新跑候选 4-5。
- 路径像直接的 hvigorw[.bat] → 用 `test -x` / `test -f` 校验，存为覆盖值。
- `skip` → 留空 `hvigorw`。继续到第 7 步。

## 7. 确认 `adb` 和 `hdc` 路径

这两个字段让 `a2h-tool validate` 在 adb / hdc 不在 `$PATH` 时也能找到它们。

### 7.1 `adb`

自动探测——**命中即停**：

| # | 候选 | 说明 |
|---|------|------|
| 1 | `adb` 字段值（非空且可执行） | config.json 里的用户显式配置 |
| 2 | `command -v adb` | 已在 PATH 上 |
| 3 | `$HOME/Library/Android/sdk/platform-tools/adb` | macOS 默认 Android SDK 位置 |
| 4 | `/usr/local/bin/adb` | 常见软链位置 |

命中 → 回显：`✔ adb 已解析：<path>（候选 #N）`。

问：`"用这个 adb，还是覆盖？(keep / <新路径> / skip)"`。
- `keep` → 写入 `adb` 字段（候选 2 命中时留空——已在 PATH，不需要硬编码）。
- `<新路径>` → `test -x` 校验；不存在则警告并重问。
- `skip` → 留空。运行时 adb 在 PATH 上就行。

全部未命中 → 告诉用户：

> `未找到 adb。模拟器检查会失败。请提供 adb 完整路径，或输入 "skip" 留空。`

### 7.2 `hdc`

自动探测——**命中即停**：

| # | 候选 | 说明 |
|---|------|------|
| 1 | `hdc` 字段值（非空且可执行） | config.json 里的用户显式配置 |
| 2 | `command -v hdc` | 已在 PATH 上 |
| 3 | `<deveco>/Contents/sdk/default/openharmony/toolchains/hdc` | DevEco 内置 hdc（macOS） |
| 4 | `$HOME/Library/Huawei/Sdk/openharmony/toolchains/hdc` | 独立安装的 HarmonyOS SDK |

命中 → 回显：`✔ hdc 已解析：<path>（候选 #N）`。

问：`"用这个 hdc，还是覆盖？(keep / <新路径> / skip)"`。
- `keep` → 写入 `hdc` 字段（候选 2 留空）。
- `<新路径>` → `test -x` 校验；不存在则警告并重问。
- `skip` → 留空。

全部未命中且 `deveco` 为空 → 提示：`"DevEco 安装路径没设，所以候选 3 跳过了。请提供 hdc 完整路径、DevEco 安装目录，或输入 'skip'。"`

用户给的是 DevEco 安装目录 → 设 `deveco` 字段，重跑候选 3。

## 8. 写配置 + 标记确认

用 Edit 工具更新 `.migbot/config.json`。最终形态：

```json
{
  "android": "<已确认>",
  "harmonyos": "<已确认>",
  "hvigorw": "<解析后或空>",
  "deveco": "<已确认或空>",
  "adb": "<解析后或空>",
  "hdc": "<解析后或空>",
  "language": "<保留>",
  "confirmed": true
}
```

保留 `language` 和用户可能加的其他键；只覆盖 `android`、`harmonyos`、`hvigorw`、`deveco`、`adb`、`hdc`、`confirmed` 七个字段。**保留** `telemetry_consent`、`telemetry_consent_at`、`migbot_session_id`、`agreement_version`——这些字段由 §2 维护，不要在本步骤中改动。

## 9. 最终校验

路径工作完成后，采集并上报 init 阶段的两个信号（都尽力而为、受档位门控——忽略退出码，都不阻断 init）：

1. **固化运行标识。** 跑 `Bash: .migbot/bin/a2h init-run`。它把 `run_id` / `project` / `app_version` 固化进 `.migbot/config.json`——本次迁移所有遥测上传都挂在这个标识上。该命令**幂等**：已有 run_id 直接沿用（重复执行 init 无害）；若 config 丢失但 `.migbot/metrics/` 仍残留 run 目录，会恢复原 run_id。推倒重来必须显式加 `--fresh`（除非用户明确要求重新开始迁移，否则绝不要传）。
2. **Android 基线。** 跑 `Bash: .migbot/bin/a2h count-lines`。它统计 Android 侧代码行数、读取 Android 应用名并记为 fact（init 时 HarmonyOS 侧尚不存在），是看板用于活跃用户/活跃 APP 统计的漏斗顶端信号。
3. **init 阶段边界。** 跑 `Bash: .migbot/bin/a2h mark-stage a2h-init`。它标记 `a2h-init` 阶段边界；生命周期 hook 上传的会话 transcript 在服务端据此归属到本阶段。

跑 `.migbot/bin/a2h-tool validate`。返回 `{"ok":true}` → 告诉用户：

> `配置已确认。可以跑 /a2h-build 验证 HarmonyOS 编译，或者 /a2h-run 启动迁移流水线。`

**若 `telemetry_consent` 为 `granted`**，另起一行追加（替换为 `.migbot/config.json` 中的实际值）：`请妥善记录您的 migbot_session_id: <migbot_session_id>——这是日后申请删除已上传数据所需的凭据。`（只回显已存储的值；绝不解释它是如何生成的。）

返回失败 → 列出失败原因并告诉用户：

> `配置已写入 confirmed: true，但 a2h-tool 报告：<failures>。请重新跑 /a2h-init 或手动修正路径。`

## 10. 迁移策略（标准 ↔ 1to1）

在 §9 校验成功之后、且仅在配置已写入并读回无错误时执行。这是 init 的最后一步；若 §8 或 §9 失败则不要执行。§9 的就绪警告不跳过本步。

### 10.1 读取已安装策略

插件安装记录 `.migbot/plugin/install.json` 拥有策略。**不要**在 `.migbot/config.json` 里重复策略字段，也不要根据之前的聊天推断已安装策略。运行：

```bash
python3 .migbot/bin/a2h-router.py
```

（Windows 用 `python .migbot\bin\a2h-router.py`；启动器是纯 stdlib Python。这是内部替换脚本，不是独立的 slash 命令。）

- 若记录或启动器不存在（未装插件的旧安装），保留已确认配置，说明策略切换需要向本工程安装插件，并进入最终报告（策略选择不可用）。不要扫描其他工程或手工拷贝资源。
- 若命令报错，跳过本步其余部分，带错误进入最终报告。
- 若 `recoveryRequired` 为 true，报告恢复需要退出 Claude Code 并运行 `python3 .migbot/bin/a2h-router.py --recover --offline`；跳过选择并进入最终报告。
- 若 `request` 非 null，报告其待处理的目标策略并立即结束本回合以便应用；不要在有待处理请求时再提交新请求或重新询问。

### 10.2 询问前先展示对比（必需的可见输出）

你**必须**在询问之前，发送一条普通用户可见消息，包含当前策略和下面的对比。只在工具输出里打印、或只显示选项标签/描述，都不算完成本步。每次到达策略选择时都要展示（包括重新初始化和已安装某策略时）。

迁移策略恰好两种；保持当前策略是一个动作，不是第三种策略。把 `<当前策略>` 替换为启动器的结果，并按 `.migbot/config.json` 里选定的 `language` 翻译以下文本。三行对比都要保留。

当前迁移策略：**<当前策略>**。可选择以下两种迁移方式；“保持当前策略”表示不切换。

| 对比项 | 标准流水线（默认） | 一比一迁移 |
|---|---|---|
| 核心目标 | 按功能需求完成 HarmonyOS 迁移，交付可用的 UI 和业务功能 | 重点一比一还原原应用的业务、后端逻辑，保持业务规则、数据处理、接口交互、状态流转及异常处理的一致性 |
| 实现方式 | 按功能 Spec 和功能切片组织实现，可结合 HarmonyOS 特性调整代码结构 | 按源类、方法和逻辑单元逐项对应目标实现，保留业务控制流；平台差异按已确认的适配方案处理 |
| 验证重点 | 检查功能契约、编译结果、UI 和业务功能是否满足需求 | 在功能验证基础上，逐项核对源逻辑与目标实现，并保留业务行为一致性的验证证据 |

两种方式均使用 `a2h-spec → a2h-plan → a2h-execute → a2h-verify → a2h-retrospect` 流程。
一比一迁移以业务、后端逻辑还原为重点，不代表逐行复制或自动保证 100% 等价。

不要承诺任一策略必然更快或更成功。只有在需要更多细节时，才把类/方法映射、图谱、sidecar、Base Bundle、验证证据作为业务与后端逻辑还原的支持来解释。公共 skills 保持共享；同名 skills 整目录替换，变体专属 skills/agents 追加。

### 10.3 展示对比后再询问

发送对比后，用单选问题询问用户。使用 Claude Code 内置的 `AskUserQuestion` 工具（它始终可用，没有 feature 门控），并在问题文本里也保留简短对比：

```json
{
  "questions": [
    {
      "header": "迁移策略",
      "question": "初始化路径已确认，当前策略为<当前策略>。\n标准流水线：按功能需求迁移，允许按 HarmonyOS 特性调整结构。\n一比一迁移：重点还原业务、后端逻辑，逐项保持业务规则、数据处理、接口交互和状态流转的一致性。\n本项目要使用哪种迁移策略？",
      "multiSelect": false,
      "options": [
        { "label": "保持当前策略", "description": "继续使用当前策略，不替换任何资源。" },
        { "label": "标准流水线", "description": "安装默认；按功能 Spec 和功能切片迁移，允许按 HarmonyOS 特性调整代码结构。" },
        { "label": "一比一迁移", "description": "以业务、后端逻辑的一比一还原为重点，逐项对应业务规则、数据处理、接口交互和状态流转。" }
      ]
    }
  ]
}
```

若 `AskUserQuestion` **不可用**（非交互模式），**不要**把多选问题写成文本消息；改为用普通文本问**一个**简洁问题，并在下一条用户消息中等待明确答复。

- 标准映射到 `standard`，一比一映射到 `1to1`。仅当自由文本答复明确选中其一才接受；若含糊或询问差异，解释后重新询问。
- 保持当前策略、取消或拒绝问题都不改资源；保留已确认路径并进入最终报告。无答复意味着继续等待，不是自动选择。
- 因为答复异步到达，询问后若答复尚未到达就结束本回合；答复到达时再处理。在答复之前不要提交任何切换。

### 10.4 只在答复后预览并提交

一比一按顺序运行（标准流水线用 `standard`）：

```bash
python3 .migbot/bin/a2h-router.py --profile 1to1 --dry-run
python3 .migbot/bin/a2h-router.py --profile 1to1 --offline
```

预览成功才提交。Claude Code 没有会话空闲回调，所以提交用 `--offline` 立即在磁盘上应用。脚本只替换受管 skills/agents/commands，保留自定义资源、插件配置和上面写好的初始化配置。已有 Spec/执行产物会阻止切换；说明需要新的迁移工程。不要删除产物绕过该检查。

- 若受管资源有手工修改，展示冲突并询问是否备份这些修改再替换；只有得到明确答复后才给预览和提交都加 `--backup-modified`。未受管同名资源始终阻止替换。
- `status=unchanged` 表示目标策略已激活。
- `status=applied` 表示磁盘切换完成：报告新策略，给最终报告，结束本回合。`.claude/skills/` 与 `.claude/agents/` 都会在当前会话内自动重读（agent watcher 几秒内生效），commands 两个策略完全相同、不随切换改变——无需手动重载。仅当宿主报某个新 skill/agent 不可见时，提示 `/reload-skills` 兜底；若会话启动时 `.claude/skills/` 或 `.claude/agents/` 目录尚不存在（会话中途装插件），才需重启会话。不要在本回合启动 `/a2h-build`/`/a2h-run`。
- `status=queued`（仅在未加 `--offline` 提交时）表示仅提交了请求；结束本回合，稍后用裸 `--offline` 应用。`--recover --offline` 用于中断事务，不是应用排队请求。排队的请求不算完成切换。
- 失败时保留已确认的初始化配置，并单独说明切换错误。绝不要手工改写安装记录。请求可用 `--cancel` 取消；中断事务的恢复需先退出 Claude Code 再 `--recover --offline`。绝不要在会话内执行恢复。

## 11. 最终报告

在 §9 校验结果之后（或当 §3 门控选了 `no` 时直接到这里），**必须**追加这段提示——**不能省略**，让用户始终知道如何参加/退出：

> ```
> ── 用户体验改善计划 ──
> 当前状态：<granted（已参与——migbot 已启用） / denied（已拒绝——migbot 已禁用）>（上次变更：<telemetry_consent_at>）
> 参与本计划是使用 migbot 的前提；拒绝将禁用迁移流水线。
> 完整协议：.migbot/policies/user-experience-improvement-plan.<language>.md
> 改变参与状态：
>   /a2h-privacy accept   参与计划并启用 migbot（会先展示计划全文征求同意）
>   /a2h-privacy deny     拒绝——禁用 migbot
>   /a2h-privacy status   查询当前状态
> 也可手工编辑 .migbot/config.json 的 telemetry_consent 字段。
> ```

还要把这个遥测块之外的迁移策略结果单独报告：当前策略，以及其中之一——已切换（`applied`，`profile` 匹配）、排队中（待处理；下一回合查看）、未变化（已激活）、选择不可用（插件未安装）、或失败（附错误与后续动作）。`/a2h-init` 通过只证明初始化配置完成；它不证明排队中或失败的策略切换已完成。

---

## 注意

- 路径输入按用户原文使用，不要把相对路径自动解析成绝对路径。用户可能更喜欢相对路径（如 `../android-app`）以便携。**例外**：第 6 步候选 4-5 用绝对路径存储（因为它们在 `<harmonyos>` 之外）。
- 永远不要从这个命令里直接改 `.claude/skills/`、`.claude/agents/` 或 `.claude/commands/`——skills/agents/commands 唯一允许的写者是 §10 的 router 启动器。本命令除此之外只动 `.migbot/config.json`（外加 `CLAUDE.md` 语言块）。
- §2 **仅在首次运行**（`telemetry_consent` 为 unset）时采集同意——就地执行与 `/a2h-privacy accept` 完全一致的流程（§2.2）。对 `granted`/`denied` 状态则只读。同意流程仍只有一套：§2.2 镜像 `/a2h-privacy` §B，不得分叉；绝不在这里另造一套同意路径。
- 协议**绝不**贴进本对话。`a2h-agreement` 以带外方式展示它（弹窗，否则给文件路径），把它挡在 Agent 上下文窗口之外。若无法弹窗（WSL / Git Bash / 无头 / macOS 沙箱），脚本会降级为打印路径——它**不会**回退到 dump 全文，你也不要。
