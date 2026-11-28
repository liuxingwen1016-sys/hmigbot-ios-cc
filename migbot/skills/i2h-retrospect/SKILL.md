---
name: i2h-retrospect
description: 生成迁移回顾报告（Pipeline 第五步）：度量指标 + 经验总结 + 交付清单
tags: [pipeline, migration]
type: pipeline
domain: migration
---

# i2h-retrospect

Pipeline 第五步：生成最终的回顾报告和度量指标。

## 1. 前置检查

检查可能存在的产物（不预设存在或成功）：
- `spec/verify-report.md` （如果已验收）
- `spec/migration-report.md` （如果已完成迁移）
- `.migbot/metrics/*/stage-marks.jsonl` （阶段时间戳）

## 2. 收集度量数据

```bash
# 调用 retrospect-metrics 获取所有度量和回执索引
METRICS=$(.migbot/bin/i2h retrospect-metrics) || exit $?

# 提取 iOS 度量
IOS_STATUS=$(echo "$METRICS" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['ios'].get('status', 'UNKNOWN'))")
IOS_LINES=$(echo "$METRICS" | python3 -c "import json,sys; d=json.load(sys.stdin); v=d['ios'].get('total_lines'); print(v if v is not None else 'UNKNOWN')")
IOS_FILES=$(echo "$METRICS" | python3 -c "import json,sys; d=json.load(sys.stdin); v=d['ios'].get('files'); print(v if v is not None else 'UNKNOWN')")
IOS_PATH=$(echo "$METRICS" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['ios'].get('path', ''))")
IOS_REASON=$(echo "$METRICS" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['ios'].get('reason', ''))")

# 提取 HarmonyOS 度量
HOS_STATUS=$(echo "$METRICS" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['harmonyos'].get('status', 'UNKNOWN'))")
HOS_LINES=$(echo "$METRICS" | python3 -c "import json,sys; d=json.load(sys.stdin); v=d['harmonyos'].get('total_lines'); print(v if v is not None else 'UNKNOWN')")
HOS_FILES=$(echo "$METRICS" | python3 -c "import json,sys; d=json.load(sys.stdin); v=d['harmonyos'].get('files'); print(v if v is not None else 'UNKNOWN')")
HOS_PATH=$(echo "$METRICS" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['harmonyos'].get('path', ''))")
HOS_REASON=$(echo "$METRICS" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['harmonyos'].get('reason', ''))")

# 提取回执索引
EXEC_STATUS=$(echo "$METRICS" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['receipts']['execute'].get('status', 'UNKNOWN'))")
EXEC_PATH=$(echo "$METRICS" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['receipts']['execute'].get('path', ''))")
EXEC_SHA=$(echo "$METRICS" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['receipts']['execute'].get('sha256', ''))")

VERIFY_STATUS=$(echo "$METRICS" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['receipts']['verify'].get('status', 'UNKNOWN'))")
VERIFY_PATH=$(echo "$METRICS" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['receipts']['verify'].get('path', ''))")
VERIFY_SHA=$(echo "$METRICS" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['receipts']['verify'].get('sha256', ''))")

TIMING_STATUS=$(echo "$METRICS" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['receipts']['timing'].get('status', 'UNKNOWN'))")
TIMING_PATH=$(echo "$METRICS" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['receipts']['timing'].get('path', ''))")

USAGE_STATUS=$(echo "$METRICS" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['receipts']['usage'].get('status', 'UNKNOWN'))")
USAGE_COST=$(echo "$METRICS" | python3 -c "import json,sys; d=json.load(sys.stdin); v=d['receipts']['usage'].get('total_cost_usd'); print(v if v is not None else 'UNKNOWN')")

echo "iOS: status=$IOS_STATUS, files=$IOS_FILES, lines=$IOS_LINES"
echo "HarmonyOS: status=$HOS_STATUS, files=$HOS_FILES, lines=$HOS_LINES"
echo "Execute: $EXEC_STATUS"
echo "Verify: $VERIFY_STATUS"
```

## 3. 生成度量报告

生成 `docs/retrospect-report-$(date +%Y-%m-%d).md`:

```markdown
# iOS → HarmonyOS 迁移度量报告

生成时间: $(date -u +"%Y-%m-%d %H:%M:%S UTC")

## 代码规模

### iOS (源)
- 状态: ${IOS_STATUS}
- 文件数: ${IOS_FILES}
- 代码行数: ${IOS_LINES}
- 路径: ${IOS_PATH}
- 备注: ${IOS_REASON}

### HarmonyOS (目标)
- 状态: ${HOS_STATUS}
- 文件数: ${HOS_FILES}
- 代码行数: ${HOS_LINES}
- 路径: ${HOS_PATH}
- 备注: ${HOS_REASON}

## 执行回执

### Execute
- 状态: ${EXEC_STATUS}
- 路径: ${EXEC_PATH}
- SHA256: ${EXEC_SHA}

### Verify
- 状态: ${VERIFY_STATUS}
- 路径: ${VERIFY_PATH}
- SHA256: ${VERIFY_SHA}

### Timing
- 状态: ${TIMING_STATUS}
- 路径: ${TIMING_PATH}

### Usage
- 状态: ${USAGE_STATUS}
- 成本: ${USAGE_COST}

**说明**:
- MEASURED: 实际测量值
- UNKNOWN: 数据源不可用，total_lines/files 为 null
- BOUND: 执行回执已验证且绑定当前输入
- RECORDED_UNVERIFIED: 文件存在但缺乏可证明的运行绑定

## 注意事项

本报告从实际度量和回执生成。不预设任何项目的转换率、成功率、效率倍数或 OCR 状态。
```

## 4. 写入完成标记

```bash
# 获取当前 target_input_sha256
CURRENT_HASH=$(python3 -c "
import json
try:
    ti = json.load(open('spec/.i2h/target-input.json'))
    print(ti.get('target_input_sha256', ''))
except:
    print('')
")

# 使用 marker_contract 写入 schema2 完成标记
if [ -z "$CURRENT_HASH" ]; then
  echo "ERROR: inputs_sha256 is empty; cannot write marker without input identity" >&2
  exit 2
fi

python3 - <<EOF
import sys
sys.path.insert(0, '.migbot/bin/scripts/pipeline')
import marker_contract

marker_contract.write_marker(
    path='spec/retrospect-complete.txt',
    stage='i2h-retrospect',
    artifact_paths=['docs/retrospect-report-$(date +%Y-%m-%d).md'],
    inputs_sha256='$CURRENT_HASH',
    root='.',
    producer='i2h-retrospect'
)
EOF

# 记录阶段完成到用量日志
.migbot/bin/i2h mark-stage i2h-retrospect
```

**重要**: `mark-stage` 和 `write_marker` 是不同合同。前者记录阶段时间戳到 `.migbot/metrics/*/stage-marks.jsonl`，后者写入 schema2 JSON marker 到 `spec/retrospect-complete.txt`。阶段完成不等于项目 Verify 通过。

## 5. 路径兼容

Stage 路径别名由 [marker-contract](../i2h-plan/references/marker-contract.md) 定义：
- Canonical: `spec/retrospect-complete.txt`
- Legacy: `spec/retrospect/complete.txt`, `docs/retrospect-complete.txt`

Execute/Verify/Timing 路径也通过 marker_contract 的 `resolve_stage` 和 `STAGE_PATH_ALIASES` 解析。

## 完成

```
✅ 回顾完成
  - 度量报告: docs/retrospect-report-YYYY-MM-DD.md
  - Schema2 marker: spec/retrospect-complete.txt
  - 阶段时间戳: .migbot/metrics/*/stage-marks.jsonl
```
