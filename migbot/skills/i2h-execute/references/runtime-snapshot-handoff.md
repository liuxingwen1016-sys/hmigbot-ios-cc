# 运行时快照交接契约

**用途**: 定义真机 snapshots 在 Execute 的消费契约  
**加载时机**: Stage 1 页面派发前确认真机遍历证据

---

## §1 概述

Execute 阶段消费 Spec 阶段采集的运行时快照，用于辅助代码生成。

**核心原则**:
- 运行时快照是**只读证据库**
- Execute 不直接扫描原始运行目录
- 只消费已审计并接管到 `spec/baseline/ui-snapshots/` 的快照

---

## §2 运行时证据策略

根据 `ui_capture_policy` 分流：

### runtime_required（严格模式）
- 必须真实审计证据
- 必须有真机截图
- 必须有 UIAutomator XML

### source_only（源码模式）
- 允许源码支持的合成 view
- 无截图要求
- 适用于无需真机测试的场景

### progressive（渐进模式）
- 仅允许有 `fallback_reason` 的明确合成兜底
- 有真机截图优先使用真机
- 缺失时允许合成

---

## §3 接管后的目录结构

### 标准目录

```
spec/baseline/ui-snapshots/<page_id>/
  ├── meta.json                 # 元数据（含 runtime_evidence.status=audited）
  ├── visual.json              # 可选：静态事实投影
  ├── fixture.json             # 可选：展示候选数据
  ├── view.xml                 # 真实 UIAutomator XML
  ├── view.static.xml          # 可选：静态结构备份
  └── ios-runtime.png          # 真实运行时截图
```

### meta.json 格式

```json
{
  "version": "1.0",
  "page_id": "HomePage",
  "runtime_evidence": {
    "status": "audited",
    "run_id": "run-20241103-001",
    "unit_id": "unit-home-001",
    "state": "normal",
    "frame_id": "frame-001",
    "captured_at": "2024-11-03T10:00:00Z",
    "device_serial": "emulator-5554",
    "package": "com.example.app",
    "view_controller": "HomeViewController",
    "png_sha256": "abc123...",
    "xml_sha256": "def456..."
  }
}
```

### visual.json 格式（可选）

```json
{
  "version": "1.0",
  "page_id": "HomePage",
  "elements": [
    {
      "id": "title_label",
      "type": "UILabel",
      "text": "首页",
      "resource": "$r('app.string.home_title')",
      "style": {
        "fontSize": 18,
        "fontColor": "$r('app.color.text_primary')"
      }
    }
  ]
}
```

### fixture.json 格式（可选）

```json
{
  "version": "1.0",
  "page_id": "HomePage",
  "fixtures": [
    {
      "id": "user_list",
      "type": "array",
      "preview_data": [
        {
          "id": "1",
          "name": "用户 1",
          "avatar": "https://example.com/avatar1.png"
        }
      ]
    }
  ]
}
```

---

## §4 Execute 门禁验证

### 验证时机

**在每个 Stage 1 batch 派发 converter 前**执行验证。

### 验证脚本

```bash
python3 scripts/validate_runtime_snapshots.py \
  --project-root . \
  --pages-file spec/execution/runtime-pages-batch.json \
  --ui-capture-policy runtime_required
```

### 验证内容

**对每个页面检查**:
1. ✅ `meta.json` 存在且包含 `runtime_evidence`
2. ✅ `ios-runtime.png` 存在
3. ✅ `view.xml` 存在
4. ✅ `runtime_evidence.status` = `audited`
5. ✅ PNG/XML 的 SHA256 与 meta.json 一致

**验证失败处理**:
- **runtime_required** — 阻断该 batch
- **source_only** — 允许合成，记录 WARNING
- **progressive** — 有 fallback_reason 则允许，否则阻断

---

## §5 与 Stage 1 生成的关系

### 真实 PNG 的用途

**用于**:
- ✅ 理解首屏比例
- ✅ 理解间距、裁剪
- ✅ 理解运行时可见状态

**不用于**:
- ❌ 业务数据来源（使用 fixture.json）

### 真实 XML 的用途

**用于**:
- ✅ 结构参照
- ✅ bounds 参照
- ✅ 元素层级

**配合使用**:
- visual.json 补充源码资源、样式链

### visual.json 的用途

**用于**:
- ✅ 资源映射（iOS → HarmonyOS）
- ✅ 样式链
- ✅ 源码绑定关系

**缺失处理**:
- 写 WARNING
- 不阻断生成

### fixture.json 的用途

**用于**:
- ✅ 提供预览数据
- ✅ 辅助理解业务逻辑

**缺失处理**:
- 写 WARNING
- 不阻断生成
- Converter 使用占位数据

---

## §6 合成兜底规则

### 允许合成的情况

**source_only 模式**:
- ✅ 允许从源码合成 view
- ✅ 不要求真机截图

**progressive 模式**:
- ✅ 有 `fallback_reason` 时允许合成
- ⚠️ 无 `fallback_reason` 则阻断

### 合成标记

**meta.json 中标记**:
```json
{
  "runtime_evidence": {
    "status": "synthesized",
    "fallback_reason": "iOS 模拟器不可用",
    "synthesis_source": "source_code"
  }
}
```

### 不允许的合成

**严格禁止**:
- ❌ Execute 现场采集
- ❌ Execute 现场合成截图
- ❌ 从模型描述补图
- ❌ 冒充其他页面的帧

---

## §7 多状态页面处理

### 状态区分

**同一页面的不同状态**:
- 正常状态 (normal)
- 加载状态 (loading)
- 错误状态 (error)
- 空状态 (empty)

**目录结构**:
```
spec/baseline/ui-snapshots/HomePage/
  ├── normal/
  │   ├── meta.json
  │   ├── ios-runtime.png
  │   └── view.xml
  ├── loading/
  │   ├── meta.json
  │   ├── ios-runtime.png
  │   └── view.xml
  └── error/
      ├── meta.json
      ├── ios-runtime.png
      └── view.xml
```

### 按状态验证

```bash
# meta.json 中的 runtime_evidence_by_state
{
  "runtime_evidence_by_state": {
    "normal": {
      "status": "audited",
      "png_sha256": "abc123..."
    },
    "loading": {
      "status": "audited",
      "png_sha256": "def456..."
    }
  }
}
```

---

## §8 滚动帧和诊断帧

### 不进入主 snapshot

**排除的帧类型**:
- 滚动帧（用户滚动中间状态）
- 诊断帧（调试用截图）
- 未审计帧（未经审计的截图）

**保留位置**:
- 原始 run 目录
- 供后续验证追溯

### 页面状态对账

**原则**:
- 页面状态必须与 `unit_id/state` 对账
- 同一个 PNG 不得复用于不同 page/state
- 每个状态必须有独立的截图

---

## §9 验证脚本实现

### 脚本参数

```bash
python3 scripts/validate_runtime_snapshots.py \
  --project-root . \
  --pages-file spec/execution/runtime-pages-batch.json \
  --ui-capture-policy runtime_required \
  --output-json spec/execution/snapshot-validation-result.json
```

### 输出格式

```json
{
  "status": "PASS",
  "pages": [
    {
      "page_id": "HomePage",
      "status": "PASS",
      "states": {
        "normal": {
          "status": "PASS",
          "png_exists": true,
          "xml_exists": true,
          "hash_verified": true
        }
      }
    }
  ],
  "summary": {
    "total_pages": 5,
    "passed_pages": 5,
    "failed_pages": 0
  }
}
```

---

## §10 常见问题

### Q1: 缺少真机截图怎么办？

**A**: 
- runtime_required → 阻断
- source_only → 允许合成
- progressive → 需要 fallback_reason

### Q2: visual.json 缺失怎么办？

**A**: 
- 写 WARNING
- 不阻断生成
- Converter 从源码推导

### Q3: 多状态页面如何验证？

**A**: 
- 按 runtime_evidence_by_state 逐一检查
- 每个状态独立验证

### Q4: 如何处理合成的 view？

**A**: 
- 必须标记 synthesized
- 必须有 fallback_reason
- 记录到报告
