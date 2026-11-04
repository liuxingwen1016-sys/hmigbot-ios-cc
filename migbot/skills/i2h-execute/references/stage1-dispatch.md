# Stage 1 派发规则

**用途**: 定义 Stage 1 UI Pipeline 的派发规则和控制策略  
**加载时机**: Stage 1 开始前

---

## §1 概述

Stage 1 UI Pipeline 负责将 iOS 页面转换为 HarmonyOS ArkTS 页面，采用 Batch 分批执行策略。

### 执行流程

```
Stage 1: UI Pipeline
├─ Batch 1 (3-5 个页面)
│  ├─ Converter 1 → Page 1
│  ├─ Converter 2 → Page 2
│  ├─ Converter 3 → Page 3
│  └─ Batch Closer 1 → 收尾
├─ Batch 2 (3-5 个页面)
│  └─ ...
└─ Batch N
   └─ ...
```

---

## §2 Batch 划分规则

### 2.1 Batch 大小

**推荐大小**: 3-5 个页面 / Batch

**原因**:
- 太小（<3）: 频繁调用 closer，overhead 大
- 太大（>5）: 单个 Batch 耗时长，错误累积多

**特殊情况**:
- 首个 Batch: 3 个页面（需要入口装配）
- 最后 Batch: 可以 < 3 个（剩余页面）

### 2.2 Batch 分组策略

**按功能模块分组**（推荐）:

```json
{
  "batch-001": {
    "theme": "核心功能",
    "pages": ["HomePage", "ProfilePage", "SettingsPage"]
  },
  "batch-002": {
    "theme": "数据管理",
    "pages": ["DataListPage", "DataDetailPage"]
  }
}
```

**按依赖关系分组**:
- 被依赖的页面放在前面
- 依赖其他页面的放在后面

**按复杂度分组**:
- 简单页面 + 复杂页面混合
- 避免全是复杂页面

---

## §3 Converter 派发规则

### 3.1 槽位控制

**并发槽位**: 最多 3 个 converter 并行

```typescript
// 主线程控制
const MAX_CONCURRENT = 3;
const runningConverters: Promise<any>[] = [];

for (const page of batch.pages) {
  // 等待槽位
  if (runningConverters.length >= MAX_CONCURRENT) {
    await Promise.race(runningConverters);
  }

  // 派发 converter
  const converter = Agent({
    description: `转换 ${page.name}`,
    prompt: converterPrompt(page)
  });

  runningConverters.push(converter);
}

// 等待所有完成
await Promise.all(runningConverters);
```

**原因**:
- 避免资源竞争
- 控制 token 消耗速度
- 便于错误追踪

### 3.2 Converter 上下文

**必须提供的上下文**:

```json
{
  "task_id": "page-001",
  "page_name": "HomePage",
  "ios_file": "<ios_project>/ViewControllers/HomeViewController.swift",
  "target_file": "entry/src/main/ets/pages/HomePage.ets",
  "runtime_snapshot": "spec/execution/runtime-snapshots/HomePage.json",
  "ui_facts": "spec/execution/ui-facts/HomePage.json",
  "dependencies": {
    "base_required": ["Base-1", "Base-3"],
    "pages": []
  }
}
```

**运行时快照**（可选，但强烈推荐）:
- 包含实际运行时的 UI 层级
- 包含实际的状态值
- 包含截图（用于布局对比）

### 3.3 空信封重派

**检测空信封**:

```typescript
// Converter 返回的 brief 检查
const brief = await converter;

if (brief.status === 'EMPTY' || brief.files.length === 0) {
  console.warn(`⚠️ Converter ${page.name} 返回空信封`);
  
  // 重派（最多 2 次）
  if (retryCount < 2) {
    console.log(`🔄 重派 Converter ${page.name} (第 ${retryCount + 1} 次)`);
    return dispatchConverter(page, retryCount + 1);
  } else {
    console.error(`❌ Converter ${page.name} 3 次均返回空信封，标记为失败`);
    return { status: 'FAIL', reason: 'EMPTY_ENVELOPE' };
  }
}
```

**空信封定义**:
- brief 中 status = 'EMPTY'
- 或 产出文件列表为空
- 或 产出文件总行数 < 10

### 3.4 停滞回收规则

**停滞检测**:

```typescript
// Converter 超时检测
const TIMEOUT = 30 * 60 * 1000; // 30 分钟

const converterWithTimeout = Promise.race([
  converter,
  new Promise((_, reject) => 
    setTimeout(() => reject(new Error('TIMEOUT')), TIMEOUT)
  )
]);

try {
  const result = await converterWithTimeout;
} catch (error) {
  if (error.message === 'TIMEOUT') {
    console.error(`❌ Converter ${page.name} 超时（30 分钟）`);
    
    // 标记为 STALLED
    return { status: 'STALLED', reason: 'TIMEOUT' };
  }
}
```

**停滞处理**:
- 记录到 brief
- 标记页面为 BLOCKED
- 不阻断其他页面
- 在 Batch closer 中报告

---

## §4 Batch Closer 派发规则

### 4.1 触发时机

**所有 converter 完成后**:

```typescript
// 等待所有 converter
const converterResults = await Promise.all(converters);

// 检查是否有失败
const failedCount = converterResults.filter(r => r.status === 'FAIL').length;

if (failedCount > 0) {
  console.warn(`⚠️ Batch ${batchId} 有 ${failedCount} 个页面转换失败`);
  // 记录但不阻断
}

// 派发 batch closer
const closer = Agent({
  description: `Batch ${batchId} 收尾`,
  prompt: batchCloserPrompt(batchId, converterResults)
});
```

### 4.2 Closer 职责

1. **资源 Sweep**
   - 收集所有资源引用
   - 转换缺失的资源

2. **布局复核**
   - 检查布局尺寸是否保真
   - 修正明显错误

3. **入口装配**（首个 Batch）
   - 创建 main_pages.json
   - 创建 Index.ets
   - 更新 EntryAbility

4. **产出 Writeback Manifest**
   - 汇总所有修改
   - 供主线程统一落盘

---

## §5 主线程应用 Writeback

### 5.1 应用流程

```typescript
// 1. Batch closer 完成
const closerBrief = await closer;

// 2. 读取 writeback manifest
const manifest = JSON.parse(
  fs.readFileSync(closerBrief.writeback_manifest)
);

// 3. 调用脚本应用
execSync(`python3 scripts/apply_writeback.py ${closerBrief.writeback_manifest} --project-root .`);

// 4. 验证应用结果
if (应用失败) {
  console.error('❌ Writeback 应用失败');
  throw new Error('WRITEBACK_FAILED');
}

console.log('✅ Writeback 应用成功');
```

### 5.2 幂等性保证

**Writeback 应用是幂等的**:
- 多次应用同一个 manifest，结果相同
- 支持崩溃恢复
- 支持断点续跑

---

## §6 Batch 间的依赖

### 6.1 串行执行

**Batch 之间串行执行**:

```typescript
for (const batch of batches) {
  console.log(`\n📦 执行 Batch ${batch.id}`);
  
  // 1. 派发 converters（并行）
  const converters = batch.pages.map(page => 
    dispatchConverter(page)
  );
  
  // 2. 等待所有 converter
  const results = await Promise.all(converters);
  
  // 3. 派发 closer
  const closer = await dispatchBatchCloser(batch.id, results);
  
  // 4. 应用 writeback
  await applyWriteback(closer.writeback_manifest);
  
  console.log(`✅ Batch ${batch.id} 完成`);
}
```

**不能并行的原因**:
- 后续 Batch 可能依赖前面的页面
- 资源 sweep 需要看到前面的产出
- 入口装配需要知道所有已转换的页面

### 6.2 首个 Batch 特殊处理

**首个 Batch 必须完成入口装配**:

```typescript
if (batch.id === 'batch-001') {
  // 检查入口装配
  if (!fs.existsSync('entry/src/main/ets/pages/Index.ets')) {
    console.error('❌ 首个 Batch 未完成入口装配');
    throw new Error('ENTRY_SETUP_MISSING');
  }
  
  console.log('✅ 入口装配已完成');
}
```

---

## §7 失败处理

### 7.1 Converter 失败

**单个页面失败**:
- 记录到 brief
- 标记为 BLOCKED
- 不阻断其他页面
- 在迁移报告中列出

**多数页面失败**（>50%）:
- 停止当前 Batch
- 分析根因
- 报告用户

### 7.2 Closer 失败

**Batch closer 失败**:
- 重试 1 次
- 仍失败 → 阻断当前 Batch
- 分析根因
- 报告用户

### 7.3 Writeback 失败

**应用 writeback 失败**:
- 回滚已应用的部分（如可能）
- 阻断继续执行
- 分析根因
- 报告用户

---

## §8 性能优化

### 8.1 并行度控制

**动态调整并行度**:

```typescript
// 根据系统负载调整
let maxConcurrent = 3;

if (系统负载低) {
  maxConcurrent = 5; // 增加并行度
} else if (系统负载高) {
  maxConcurrent = 2; // 降低并行度
}
```

### 8.2 Cache 预热

**预加载常用资源**:
- iOS 页面源码
- 运行时快照
- UI Facts

### 8.3 增量执行

**跳过已完成的页面**:

```typescript
if (fs.existsSync(page.targetFile)) {
  console.log(`⏭️  跳过 ${page.name}（已存在）`);
  continue;
}
```

---

## §9 质量保证

### 9.1 Converter 质量检查

**自动检查**:
- 产出文件数 > 0
- 代码行数 > 10
- 无明显语法错误
- 资源引用格式正确

### 9.2 Batch 质量检查

**Batch 完成后检查**:
- 所有页面都有产出
- 入口装配正确（首个 Batch）
- 资源闭包完整
- Writeback 应用成功

---

## §10 示例

### 完整的 Batch 执行流程

```typescript
async function executeBatch(batch: Batch): Promise<void> {
  console.log(`\n📦 执行 Batch ${batch.id}`);
  console.log(`   页面: ${batch.pages.map(p => p.name).join(', ')}`);
  
  // 1. 并行派发 converters
  const converters: Promise<ConverterResult>[] = [];
  
  for (const page of batch.pages) {
    // 读取上下文
    Read('references/agent-prompts/_common.md');
    Read('references/agent-prompts/1-converter.md');
    
    // 派发 converter
    const converter = Agent({
      description: `转换 ${page.name}`,
      prompt: `
        ${commonRules}
        ${converterTemplate}
        
        ## 任务上下文
        - iOS 文件: ${page.iosFile}
        - 目标文件: ${page.targetFile}
        - 运行时快照: ${page.snapshot}
      `
    });
    
    converters.push(converter);
    
    // 槽位控制
    if (converters.length >= MAX_CONCURRENT) {
      await Promise.race(converters);
    }
  }
  
  // 2. 等待所有 converter
  const results = await Promise.all(converters);
  
  // 3. 检查失败
  const failed = results.filter(r => r.status === 'FAIL');
  if (failed.length > 0) {
    console.warn(`⚠️ ${failed.length} 个页面转换失败`);
  }
  
  // 4. 派发 batch closer
  Read('references/agent-prompts/_common.md');
  Read('references/agent-prompts/2-batch-closer.md');
  
  const closer = await Agent({
    description: `Batch ${batch.id} 收尾`,
    prompt: `
      ${commonRules}
      ${batchCloserTemplate}
      
      ## Batch 上下文
      - Batch ID: ${batch.id}
      - Converter Briefs: ${results.map(r => r.brief)}
    `
  });
  
  // 5. 应用 writeback
  execSync(`python3 scripts/apply_writeback.py ${closer.writeback_manifest} --project-root .`);
  
  console.log(`✅ Batch ${batch.id} 完成`);
}
```

---

**版本**: 1.0  
**更新时间**: 2024-11-03  
**适用**: i2h-execute Stage 1
