---
description: |
  Migbot-Increment 工作流初始化命令，用于首次使用 migbot-increment-workflow 前检查环境、配置目录路径。
  当用户说"初始化"、"init"、"环境检查"或首次使用 migbot-increment-workflow 前触发。
  功能：项目路径验证、环境检查、TEST_ROOT 检测、目录配置确认、Git 状态检查、会话恢复检查。
compatible: ["{项目名}-main"]
---

# migbot-increment-init

在开始 Migbot-Increment 工作流之前，执行初始化检查确保环境和目录配置就绪。

---

## 准入门控（必须最先执行）

开始前先跑 `Bash: .migbot/bin/a2h verify-access`；退出码非 0 则把它的输出转述给用户并停下，不再继续。

继续前确认授权状态：跑 `Bash: .migbot/bin/a2h verify-consent`；退出码非 0 则把它的输出转述给用户（提示其执行 `/a2h-privacy accept` 同意《用户体验改进计划》后再使用）后停下。

**未通过上述两项校验前，禁止执行本命令的任何后续步骤。**

---

## 输入

`/migbot-increment-init` - 执行初始化检查
`/migbot-increment-init --force` - 跳过会话恢复提示，强制重新初始化

---

## 执行流程

```
Step 1: 检查初始化状态
Step 2: 验证项目路径
Step 3: 检查环境
    ├─ 3-1: 构建工具版本
    ├─ 3-2: 编译测试
    ├─ 3-3: TEST_ROOT 检测与确认
    └─ 3-4: 测试框架检查（含环境变量和路径收集）
Step 4: 创建目录结构
Step 5: 用户确认目录配置
Step 6: Git 状态检查
Step 7: 会话恢复检查
Step 8: 写入初始化标记 + README.md 配置摘要
```

---

## Step 1: 检查初始化状态

检查 `specs/initialized.flag` 是否存在：

| 状态 | 处理 |
|------|------|
| 文件存在 | 显示已初始化信息，询问用户选择 |
| 文件不存在 | 继续 Step 2 |

```
## 检测到已初始化

最后初始化时间：{date}
项目：{PROJECT_ROOT}

选项：
1. 继续（使用现有配置）→ 执行 Step 6-7 后完成
2. 重新初始化 → 删除现有标记并重新执行
```

---

## Step 2: 验证项目路径

### 2-1: 检测项目类型

| 构建文件 | 项目类型 | 编译命令 | 测试命令 |
|---------|---------|---------|---------|
| `hvigorw` | HarmonyOS | `hvigorw assembleHap` | `hvigorw test@entry` |
| `package.json` | Node/JS/TS | `npm run build` | `npm test` |
| `gradlew` | Gradle/Android | `gradlew assembleDebug` | `gradlew test` |
| 其他 | 未知类型 | 询问用户 | 询问用户 |

### 2-2: 验证项目路径

检查 `{PROJECT_ROOT}/` 是否存在，构建文件是否存在。

**失败处理（必须修复）：**
```
## ❌ 项目路径验证失败

未找到目标项目。请确认项目路径。

检查路径：./{项目名}-main

错误详情：{error_message}

请选择：
1. 指定正确路径 → 请提供正确的项目路径
2. 创建新项目 → 在当前目录初始化新项目
3. 列出可用目录 → 我来帮你查找当前目录下的项目

请输入选项编号或直接提供项目路径：_
```

---

## Step 3: 检查环境

### Step 3-1: 检查构建工具版本

| 项目类型 | 检查命令 | 成功标准 |
|---------|---------|---------|
| HarmonyOS | `hvigorw --version` | 输出版本号 |
| Node/JS/TS | `node --version && npm --version` | 输出版本号 |
| Gradle | `gradlew --version` | 输出版本号 |

**失败处理（循环直到修复）：**
```
## ⚠️ 构建工具检查失败

{build_tool} 未安装或不可用。

检查命令：{command}
错误详情：{error_message}

请选择：
1. 我已修复 → 重新检查
2. 需要更多信息 → 询问具体问题
3. 使用其他工具 → 指定替代构建命令

请输入选项编号：_
```

### Step 3-2: 编译测试

| 项目类型 | 编译命令 | 成功标准 |
|---------|---------|---------|
| HarmonyOS | `hvigorw assembleHap` | BUILD SUCCESS |
| Node/JS/TS | `npm run build` | 退出码 0 |
| Gradle | `gradlew assembleDebug` | BUILD SUCCESSFUL |

**失败处理（循环直到修复）：**
```
## ⚠️ 编译测试失败

编译命令：{command}
错误摘要：{error_summary}

| 错误类型 | 解决方案 |
|---------|---------|
| 缺少依赖 | 运行 npm install / ohpm install |
| 语法错误 | 检查错误指向的文件 |
| 路径错误 | 检查 hvigorw 是否在项目根目录 |

请选择：
1. 我已修复 → 重新编译
2. 需要帮助分析错误 → 我来详细解释错误原因
3. 环境问题，需要配置 → 指导配置编译环境

请输入选项编号：_
```

### Step 3-3: TEST_ROOT 检测与确认

**自动检测顺序：**
1. `{PROJECT_ROOT}/entry/src/test/` — HarmonyOS 标准
2. `{PROJECT_ROOT}/test/`
3. `{PROJECT_ROOT}/entry/test/`

**检测到时：**
```
## TEST_ROOT 检测

| 路径 | 状态 | 文件数 |
|------|------|--------|
| {path_1} | 推荐 | {count} |
| {path_2} | 备选 | {count} |

目录预览：{file_list_preview}

请选择：
1. 确认使用推荐目录
2. 使用其他检测到的路径
3. 指定其他路径
```

**未检测到时：**
```
## TEST_ROOT 未检测到

请选择：
1. 创建默认测试目录
2. 指定现有目录 → 请提供路径
3. 稍后配置 → 跳过，但在 APPLYING 阶段需要重新指定

请输入选项编号或路径：_
```

### Step 3-4: 测试框架检查

#### 3-4-1: 系统环境变量

```
## 系统环境变量检查

| 变量 | 状态 |
|------|------|
| SDK_HOME | {未设置/已设置} |
| JAVA_HOME | {未设置/已设置} |

未检测到 SDK 路径。
请提供 SDK 根目录路径（或直接回车跳过）：_
```

#### 3-4-2: 重要路径

```
## 重要路径检查

| 工具 | 状态 |
|------|------|
| hvigorw | {✅/❌} |
| Java | {✅/❌} |
| SDK | {⚠️ 未设置} |

请提供以下路径（如已知）：

SDK 根目录：_
hvigorw 路径：_
Java 路径：_
```

#### 3-4-3: 验证测试框架

```
## 测试框架验证

正在使用以下路径验证：

SDK: {sdk_path}
hvigorw: {hvigorw_path}

验证中...
```

**成功：**
```
✅ 测试框架验证通过

测试命令: hvigorw test@entry
可用测试: {count} 个
```

**失败：**
```
## ⚠️ 测试框架验证失败

错误: {error_message}

请选择：
1. 加载 harmony-ui-test skill（推荐）
2. 重新配置路径
3. 提供替代测试命令
4. 跳过（确认风险）

请输入选项编号：_
```

---

## Step 4: 创建目录结构

自动创建（如不存在）：
- `specs/changes/`
- `specs/guidelines/`
- `specs/guidelines/incidents/`
- `specs/archives/`

---

## Step 5: 用户确认目录配置

```
## 目录配置确认

| 目录 | 当前值 |
|------|--------|
| PROJECT_ROOT | ./MyApp-main |
| CHANGES_ROOT | specs/changes |
| SPECS_FEATURE_ROOT | specs/specs |
| TEST_ROOT | ./MyApp-main/entry/src/test |

选项：
1. 确认所有路径正确
2. 修改某个路径（请说明要修改哪个目录和新路径）
```

---

## Step 6: Git 状态检查

```
## Git 状态

当前分支：{branch}
未提交变更：{count} 个文件

选项：
1. 提交变更 → 询问提交信息
2. 暂存变更 → git stash
3. 忽略（有风险，可能丢失工作）
```

---

## Step 7: 会话恢复检查

```
## 发现未完成的会话

| 会话 | 类型 | 阶段 | 上次步骤 |
|------|------|------|---------|
| {session} | {type} | {phase} | {step} |

选项：
1. 恢复会话 → 询问选择哪个会话
2. 忽略，开始新会话
3. 取消初始化
```

---

## Step 8: 写入初始化标记

### 8-1: 创建 specs/initialized.flag

```markdown
# Migbot-Increment Skill Bank - Initialization Flag

## Init Date
{YYYY-MM-DD HH:MM}

## Project Configuration
PROJECT_ROOT: {PROJECT_ROOT}
CHANGES_ROOT: specs/changes
SPECS_FEATURE_ROOT: specs/specs
TEST_ROOT: {TEST_ROOT}

## Build Configuration
Build Tool: {build_tool}
Build Version: {version}
Build Command: hvigorw assembleHap
Build Status: success/failed

## Test Configuration
Test Command: hvigorw test@entry
Test Available: {true/false/fallback}
Test Framework: {framework_name}
Test Skills:
  - harmony-ui-test: {loaded/skipped}
Test Paths:
  Primary: {TEST_ROOT}
  Alternative: {user_provided_path}

## SDK Configuration
SDK_HOME: {sdk_path}
SDK Version: {sdk_version}
hvigorw Path: {hvigorw_path}
hvigorw Version: {version}
Java Path: {java_path}
Java Version: {version}
Platform: {macOS/Linux/Windows}
Project Type: {HarmonyOS/Node/Gradle/Other}

## User Provided Paths
SDK: {user_provided_sdk}
hvigorw: {user_provided_hvigorw}
Java: {user_provided_java}

## Directories
- [x] PROJECT_ROOT exists
- [x] specs/changes/ created
- [x] specs/guidelines/ created
- [x] specs/archives/ created
- [x] TEST_ROOT exists

## Git State
Status: {clean/dirty}
Branch: {branch}

## Session Recovery
Last Session: {none/session_id}
```

### 8-2: 写入 {PROJECT_ROOT}/README.md

在项目 README.md 末尾追加：

```markdown
---

## Migbot-Increment Configuration

> Generated by migbot-increment-init. Do not edit manually.

### Project
- **Project Root**: `{PROJECT_ROOT}`
- **Spec Changes**: `{CHANGES_ROOT}`
- **Test Root**: `{TEST_ROOT}`

### Environment
| Tool | Path | Version |
|------|------|---------|
| hvigorw | {hvigorw_path} | {version} |
| Java | {java_path} | {version} |
| SDK | {sdk_path} | {sdk_version} |

### Commands
```bash
# Build
hvigorw assembleHap

# Test
hvigorw test@entry
```
```

---

## Step 9: 初始化完成

```
## ✅ Initialization Complete

**Project:** {PROJECT_ROOT}
**Build Tool:** {build_tool} {version}
**Test:** {test_available}
**Status:** Ready

**Configuration saved:**
- specs/initialized.flag
- {PROJECT_ROOT}/README.md

---

## Next Steps

### 开始新任务
/migbot-increment-workflow add <feature-name>

### 继续未完成任务
/migbot-increment-workflow continue

### 归档已完成任务
/migbot-increment-archive
```

---

## Step 10: 上报初始化阶段用量（best-effort，必须执行）

**触发条件**：Step 9 展示初始化完成后立即执行，不可省略。

init 作为增量流程的**独立阶段**单独上报本阶段的 Token / 耗时用量（阶段位置由其真实起止时间决定，不强制排在 retrospect 之后）：

```bash
.migbot/bin/a2h mark-stage migbot-increment-init
```

该命令会以 `migbot-increment-init` 为阶段名重算并上报本阶段的 Token / 耗时 / Skill / Sub-agent 用量（汇入性能看板 5002 的「按阶段」与「事件时间轴」视图，按真实时间渲染成独立 bar）。

**【硬约束】**：
- init **无命名交付物**，仅上报用量、**不**上传任何产物文档。
- 尽力而为、受授权门控：**忽略其退出码**，绝不影响初始化结果；未授权（telemetry off）时自动静默跳过。
- 严禁用 Write / Edit 手工创建或伪造 `.migbot/metrics/` 下任何文件。

---

## 防护栏

### 失败处理汇总

| 级别 | 错误类型 | 处理方式 | 可跳过？ |
|------|---------|---------|---------|
| BLOCK | 项目路径不存在 | 要求指定新路径，循环验证 | 否 |
| BLOCK | 构建工具不可用 | 要求安装/配置，循环检查 | 否 |
| BLOCK | 编译失败 | 要求修复错误，循环编译 | 否 |
| BLOCK | TEST_ROOT 不存在 | 要求指定/创建，循环验证 | 否 |
| BLOCK | 测试框架不可用 | 要求选择后备方案，确认风险 | 否 |
| ASK | 有未提交变更 | 询问提交/暂存/忽略 | 是 |
| ASK | 有未完成任务 | 询问恢复/新建/取消 | 是 |

### TodoWrite 使用

在 migbot-increment-init 执行过程中，必须使用 TodoWrite 跟踪进度：

```javascript
{
  todos: [
    { content: "migbot-increment-init: 验证项目路径", status: "in_progress", priority: "high" },
    { content: "migbot-increment-init: 检查构建工具", status: "pending", priority: "high" },
    { content: "migbot-increment-init: 执行编译测试", status: "pending", priority: "high" },
    { content: "migbot-increment-init: 检测 TEST_ROOT", status: "pending", priority: "high" },
    { content: "migbot-increment-init: 检查测试框架", status: "pending", priority: "medium" },
    { content: "migbot-increment-init: 创建目录结构", status: "pending", priority: "medium" },
    { content: "migbot-increment-init: 用户确认配置", status: "pending", priority: "high" },
    { content: "migbot-increment-init: Git 状态检查", status: "pending", priority: "medium" },
    { content: "migbot-increment-init: 会话恢复检查", status: "pending", priority: "medium" },
    { content: "migbot-increment-init: 写入初始化标记", status: "pending", priority: "high" }
  ]
}
```
### 禁止事项

1. **禁止跳过环境检查** — 所有检查项必须执行
2. **禁止跳过修复循环** — BLOCK 类错误必须修复，不能绕过
3. **禁止使用未确认的路径** — 所有路径必须验证存在
4. **禁止修改已存在的 initialized.flag** — 除非用户明确要求重新初始化
