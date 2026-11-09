# 失败处理与复检

本次可选项选择沿用启动时的范围，回环不重新询问或补跑未选项。只从本次实际执行结果提取失败，未选项的历史报告不触发修复。

## 修复归属

| 失败来源 | 处理 |
|---|---|
| CHECK-1 静态 ERROR | 在当前任务允许修复时生成执行阶段修复任务 |
| CHECK-2 身份 FAIL | 在当前任务允许修复时生成配置/资源修复任务 |
| CHECK-3 功能性失败 | 简化版实现记录差异，由后续阶段或手动处理 |
| CHECK-3 纯 ALIGN 差异 | 记建议项，由视觉优化阶段处理 |
| CHECK-4 | 由 UT verifier 按选定模式处理；i2h-verify 不再包一层同类 fix-loop |
| CHECK-5 | SKIP/WARN/DEFERRED/ERROR 均只报告，不触发 i2h-execute，也不重新初始化 run、重置轮数或自动追加第二轮 |
| 输入缺失、设备不可用或执行环境失败 | 写明恢复条件；不把恢复当作自动修复任务或开工前置 |

## 外层修复回环

### 回环触发条件

只有 CHECK-1 静态 ERROR 和 CHECK-2 身份 FAIL 触发外层回环。

**触发流程**：
1. CHECK-1/2 执行完成，发现 ERROR 或 FAIL
2. 在当前任务允许修复时，提取失败项
3. 生成修复计划：`spec/plans/plan-fix-verify-<timestamp>.md`
4. 委托 `i2h-execute` 执行修复
5. 读取改动，复检并更新报告

### 回环次数限制

最多 **3 轮**：
- Round 1：首次修复
- Round 2：二次修复
- Round 3：最终尝试

3 轮后仍有失败 → 记录到最终报告，退出回环

### 修复计划生成

```markdown
# i2h-verify 修复计划

生成时间: 2024-11-03 23:30:00  
轮次: Round 1

## CHECK-1 静态分析失败项

### 1. DispatchQueue 未改造

**文件**: entry/src/main/ets/utils/NetworkManager.ets:42  
**问题**: 使用 DispatchQueue.global()，必须改为 TaskPool  
**级别**: ERROR

**修复要求**:
```typescript
// 错误写法
DispatchQueue.global().async {
    let data = loadData()
    DispatchQueue.main.async {
        this.updateUI(data)
    }
}

// 正确写法
import taskpool from '@ohos.taskpool'
taskpool.execute(() => {
  let data = loadData()
  return data
}).then((data) => {
  this.updateUI(data)
})
```

### 2. UserDefaults 未改造

**文件**: entry/src/main/ets/common/PreferencesHelper.ets:15  
**问题**: 使用 UserDefaults.standard，必须改为 Preferences  
**级别**: ERROR

**修复要求**:
```typescript
// 错误写法
UserDefaults.standard.set(value, forKey: key)

// 正确写法
import preferences from '@ohos.data.preferences'
let prefs = await preferences.getPreferences(context, 'myStore')
await prefs.put(key, value)
await prefs.flush()
```

## CHECK-2 App 身份失败项

### 1. bundleName 仍为示例值

**问题**: bundleName 仍为 `com.example.myapp`  
**级别**: FAIL  
**iOS 值**: com.company.myapp

**修复要求**:
修改 `AppScope/app.json5`:
```json5
{
  "app": {
    "bundleName": "com.company.myapp",  // 改为实际值
    ...
  }
}
```

### 2. 应用图标缺失

**问题**: layered-image.json 引用的前景图标不存在  
**级别**: FAIL

**修复要求**:
1. 从 iOS Assets.xcassets/AppIcon.appiconset/ 提取图标
2. 转换为 PNG 格式
3. 放置到 AppScope/resources/base/media/
4. 更新 layered-image.json 引用

---

**总计**: 4 个失败项（2 个 ERROR + 2 个 FAIL）
```

### 委托执行修复

```typescript
// 伪代码
const plan = generateFixPlan(check1Failures, check2Failures)
writePlan('spec/plans/plan-fix-verify-<timestamp>.md', plan)

// 调用 i2h-execute
await Skill('i2h-execute', {
  plan: 'spec/plans/plan-fix-verify-<timestamp>.md',
  scope: 'verify-fixes',
  round: currentRound
})
```

### 读取修复结果

```bash
# 读取改动文件列表
git diff --name-only HEAD@{1} HEAD

# 对于每个改动的 .ets 文件，重跑 CHECK-1 受影响规则
# 对于 app.json5 / module.json5 / 资源文件，重跑 CHECK-2
```

## 复检范围

### 源码改动的复检

- **有生产源码改动** → 重跑 CHECK-1
- **涉及 App 配置、名称或图标资源** → 重跑 CHECK-2
- **修复 CHECK-3 功能性失败后** → 简化版不包含自动修复，记录人工修复需要重测
- **对本次已选且已通过的 CHECK-3/4** → 若后续改动影响其已测代码、配置或行为，则串行重跑受影响部分并保留未受影响的有效证据

### 复检规则

不能确定影响范围时重跑该项；未选项仍为 SKIP。

- **CHECK-1**：只重跑改动文件涉及的规则
- **CHECK-2**：重跑全部 6 项检查
- **CHECK-3**：重跑受影响页面的截图对比
- **CHECK-4**：按 UT verifier 契约复测

无法完成复检时，原结论注明未覆盖当前改动，该项记 PARTIAL；已有确认失败不能因此消失。

## 退出条件

### 正常退出

- 所有 ERROR 和 FAIL 修复完成
- 复检全部通过
- 生成最终报告

### 收敛退出

- 达到最大轮数（3 轮）
- 最后一轮无新进展（失败数不变）
- 记录剩余失败项，标注"收敛但未完全通过"

### 异常退出

- 执行环境失败（编译失败、设备断开）
- 输入缺失（源码不可达）
- 记录退出原因和恢复条件

## CHECK-5 的特殊处理

CHECK-5 修改源码同样适用上述复检规则。其构建/安装失败留在行为报告，CHECK-1 仍只做静态分析。后续其他修复又改变源码时，注明 CHECK-5 证据对应的源码版本和未覆盖改动；不能复用旧 run 冒充本次结果，也不自动补跑行为修复。

**关键点**：
- CHECK-5 的失败**不触发**外层回环
- CHECK-5 的修复**不重置**回环轮数
- CHECK-5 只报告，修复由其自身契约处理

## 失败报告格式

最终报告中的失败汇总：

```markdown
## 失败项汇总

### 未解决的 ERROR (2 项)

1. **DispatchQueue 未改造**
   - 文件: entry/src/main/ets/utils/NetworkManager.ets:42
   - 轮次: 已尝试 3 轮修复
   - 状态: 仍未解决
   - 原因: 自动修复逻辑复杂，需要人工介入

2. **UIKit 导入未移除**
   - 文件: entry/src/main/ets/pages/ProfileView.ets:1
   - 轮次: Round 2 修复后引入
   - 状态: 新增失败
   - 原因: 修复过程中误引入

### 未解决的 FAIL (1 项)

1. **应用图标尺寸过小**
   - 问题: 前景图标仅 800 bytes
   - 轮次: Round 1 修复未生效
   - 状态: 仍为疑似默认图
   - 建议: 使用高分辨率图标（建议 ≥ 10 KB）

---

**总计**: 3 个未解决失败项  
**已修复**: 1 项（bundleName 已改为实际值）
```

## 修复历史记录

保留每轮的修复历史：

```
spec/verify/
├── verify-report.md              # 最终报告
├── fix-history/
│   ├── round-1/
│   │   ├── plan-fix-verify-20241103-2330.md
│   │   ├── changes.log           # git diff 输出
│   │   └── recheck-result.md     # 复检结果
│   ├── round-2/
│   │   ├── plan-fix-verify-20241103-2345.md
│   │   ├── changes.log
│   │   └── recheck-result.md
│   └── round-3/
│       ├── plan-fix-verify-20241104-0000.md
│       ├── changes.log
│       └── recheck-result.md
└── final-status.json             # 最终状态（JSON 格式）
```

## 注意事项

1. **不要修改未选项的历史结果** - SKIP 保持 SKIP
2. **不要把环境失败当作产品失败** - 区分 ERROR 类型
3. **不要无限重试** - 最多 3 轮
4. **不要假设自动修复全能** - 记录需要人工介入的项
5. **不要丢失已确认的失败** - 即使环境变化，已有失败仍保留

---

**版本**: v1.0  
**创建时间**: 2024-11-03  
**作者**: 模型 Opus 5.5
