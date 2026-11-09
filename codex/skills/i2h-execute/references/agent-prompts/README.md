# Agent Prompts 目录

此目录包含所有 agent 派发的标准化模板。

## 文件列表

| 文件 | 说明 | 状态 |
|------|------|------|
| **_common.md** | 公共规则（所有派发必读） | ✅ 完成 |
| **1-converter.md** | 页面转换器派发模板 | ✅ 完成 |
| **2-batch-closer.md** | Batch 收尾器派发模板 | ✅ 完成 |
| **3-worker.md** | Base Worker 派发模板 | ✅ 完成 |
| **4-slice-worker.md** | Slice Worker 派发模板 | ✅ 完成 |
| **5-final-closer.md** | FV-1 收尾器派发模板 | ⏸️ 待创建 |
| **8-group-closer.md** | Group 收尾器派发模板 | ✅ 完成 |

## 使用方式

派发任何 worker 时：

```typescript
// 1. 读取公共规则
Read('references/agent-prompts/_common.md')

// 2. 读取对应派发模板
Read('references/agent-prompts/1-converter.md')

// 3. 派发 agent
spawn_agent({
  description: "转换 HomePage",
  prompt: `${commonRules}\n${converterTemplate}\n${context}`
})
```

## 核心原则

1. **单写者** - 通过 writeback manifest 统一落盘
2. **占位规则** - 7 种 kind，必须登记
3. **资源直写** - 资源文件允许直接写入
4. **Brief 产出** - 每个 worker 必须产出 brief
5. **ArkTS 规范** - 严格遵循 ArkTS 规则

---

**版本**: 1.0  
**更新时间**: 2024-11-03
