<!-- when: 初始化、构建、安装或任一终止路径导出 result 时读取 -->
<!-- topics: result.json, terminal states, unverified -->

# 稳定终态契约

## 原则

`result.json` 从流程第一步存在。初始化与 `mark-editing` 写 fail-closed 暂态；只有 `finalize` 可写 `finalized=true`。安装成功也不代表行为正确，所有终态固定 `verification_status=NOT_PERFORMED`、`correctness_claim=NONE`。

## 终态

- `INSTALLED_UNVERIFIED`：有修复尝试，signed HAP 构建并安装成功。
- `NO_REPAIR_INSTALLED_UNVERIFIED`：没有 `FIX_REQUIRED` 或没有实际修复，构建并安装成功。
- `REPAIR_FINISHED_NOT_INSTALLED_UNVERIFIED`：Baseline、Round 1、快速审查与 Round 2 已完成，但签名或工具链等构建前置不可用，因此未构建、未安装。
- `BUILD_FAILED_NOT_INSTALLED`：build 已执行但失败，或 PASS 证据/HAP 无效。
- `INSTALL_FAILED_UNVERIFIED`：合法 HAP 已构建，但正式安装命令失败。
- `PREFLIGHT_FAILED_NOT_INSTALLED`：源码/输出/稳定结果/源码保护等硬前置失败，未进入 Baseline；签名、SDK/JBR/Hvigor、HDC 或设备缺失不得使用该终态。
- `BASELINE_FAILED_NOT_INSTALLED`：全量 Detector 或紧凑审计无法形成合法产物。
- `WORKFLOW_INCOMPLETE`：缺少足够材料判断更具体终态，包括异常中断保底。

不得存在 `GREEN`、`PASS`、`VERIFIED` 或 `STATIC_GREEN` 终态。

## Build evidence

正式文件名固定为 `final-build-evidence.json`：

```json
{
  "schema_version": 1,
  "mode": "setting-effect-build",
  "status": "PASS | FAIL",
  "attempts": [{"command":"...","exit_code":0,"summary":"..."}],
  "hap_path": "绝对路径；FAIL 可为空",
  "signed": true,
  "preflight_sha256": "64位十六进制"
}
```

PASS 要求 1–3 个 attempts、最后 exit code 0、`signed=true`、HAP 存在；exporter 写入 `hap_sha256`。FAIL 不允许伪造 HAP 成功。

## Install evidence

正式文件名固定为 `final-install-evidence.json`：

```json
{
  "schema_version": 1,
  "mode": "setting-effect-install",
  "status": "PASS | FAIL",
  "command": "hdc install -r ...",
  "exit_code": 0,
  "hap_sha256": "必须等于 build evidence",
  "device": "设备标识或空字符串"
}
```

PASS 要求 exit code 0，并绑定当前 build HAP digest。

## 报告字段

`result.json` 必须列出：工具链锁、task-discovery 与 Preflight artifact、Baseline 审计状态计数与 key、Round 1 逐 key 执行计数与 attempted keys、快速审查计数、Round 2 逐 key 执行计数与 attempted keys、两轮汇总计数、`build_readiness`、build/install 状态、changed files、artifact path+SHA、reason codes。

固定字段包括：

- `round1_repair_execution_counts`、`round1_attempted_keys`；
- `quick_review_counts`；
- `round2_repair_execution_counts`、`round2_attempted_keys`；
- 兼容汇总 `repair_execution_counts`、`repair_attempted_keys`。

`FIX_REQUIRED` 或 `CLOSED_LIKELY` 都可能在安装后存在，因为本流程不做 Round 2 后正确性复审。禁止使用 `repaired_keys`、`verified_keys` 或其他暗示正确性的字段。
