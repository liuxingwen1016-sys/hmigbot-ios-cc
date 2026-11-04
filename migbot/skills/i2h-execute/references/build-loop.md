# 构建循环纪律

**用途**: 定义编译验证的执行纪律和策略  
**加载时机**: 每次调用 hmos-builder 前

---

## §1 编译触发点

### 三道编译门

| 编译门 | 触发时机 | 说明 |
|-------|---------|------|
| **Base-7** | Stage 2 所有 Base 完成后 | Stage 1 + Stage 2 的首道编译门 |
| **Stage 3 集中门** | Stage 3 所有 Group 完成后 | 组内无编译，错误累积至此 |
| **FV-2** | FV-1 收尾完成后 | 终态全量编译，进 i2h-verify 前最后 gate |

### 编译参数

```bash
# Base-7 编译
Skill({
  skill: "hmos-builder",
  args: "--caller i2h-execute --stage-hint stage-2-base-7 --round 1 --max-iterations 20"
})

# Stage 3 集中门
Skill({
  skill: "hmos-builder",
  args: "--caller i2h-execute --stage-hint stage-3-gate --round 1 --max-iterations 20"
})

# FV-2 终态编译
Skill({
  skill: "hmos-builder",
  args: "--caller i2h-execute --stage-hint fv-final-build --round 1 --max-iterations 20"
})
```

---

## §2 编译纪律

### 2.1 Cache 策略

**原则**: 珍惜 cache，避免无效编译

```typescript
// ✅ 正确：修改代码后编译
修改文件 → 编译

// ❌ 错误：未修改就编译
未修改 → 编译 → 浪费 cache
```

**检查点**:
- 编译前检查是否有文件修改
- 空转编译（`all tasks up-to-date`）视为无效

### 2.2 Checkpoint 策略

**每道编译门是 checkpoint**:

```
Stage 2 完成
  ↓
Base-7 编译门 ← checkpoint 1
  ↓ PASS
Stage 3 执行
  ↓
Stage 3 集中门 ← checkpoint 2
  ↓ PASS
FV-1 收尾
  ↓
FV-2 终态编译 ← checkpoint 3 (最后 gate)
  ↓ PASS
进入 i2h-verify
```

**Checkpoint 失败处理**:
- Base-7 FAIL → **阻断**（唯一停点）
- Stage 3 gate FAIL → 修复后重试，最多 3 次
- FV-2 FAIL → 修复后重试，最多 3 次

### 2.3 降级策略（CLI → IDE）

**触发条件**:

| 条件 | 说明 | 阈值 |
|------|------|------|
| Daemon 僵死 | `hvigorw` <1 秒退出且无错误 | 连续 2 次 |
| SDK 路径错误 | 错误码 `00303208`/`00303217` | 连续 2 次 |
| module.json5 损坏 | 错误码 `00305008` | 连续 2 次 |
| Linter 回改死循环 | 单文件被 linter 反复修改 | >3 次 |

**降级输出**:

```
⚠️ 构建环境已不稳定，无法继续 CLI 构建验证。
请在 DevEco Studio IDE 中执行 Build → Build HAP(s) 验证项目完整性。

原因: ${降级原因}
轮次: ${失败轮次}
```

**降级后**:
- 停止自动修复
- 不阻断 Pipeline
- 记录到迁移报告

---

## §3 自动修复循环

### 3.1 修复策略

**最多 20 次迭代**:

```
轮次 1:
├─ 编译 → 收集错误
├─ 分类错误
├─ 应用修复策略
└─ 重新编译

轮次 2-19:
├─ 编译 → 收集错误
├─ 错误减少 → 继续
└─ 错误不减少 → 分析原因

轮次 20:
├─ 编译 → 收集错误
└─ 仍有错误 → 返回 FAIL
```

### 3.2 确定性修复

**常见错误的自动修复**:

| 错误类型 | 检测规则 | 修复方案 |
|---------|---------|---------|
| `as unknown as` | 包含 `as unknown as` | 替换为构造函数 |
| Object Literal | 无明确类型的对象字面量 | 先创建实例再赋值 |
| `as const` | 包含 `as const` | 移除，使用明确类型 |
| Indexed Access | `typeof arr[number]` | 改为枚举类型 |
| `@BuilderParam` | 在方法参数位置 | 移到成员属性 |
| SymbolGlyph API | `.fontColor($r(...))` | 改为数组 `[...]` |

**修复示例**:

```typescript
// 修复 1: as unknown as
// 错误
const value = json.id as unknown as string;
// 修复
const value = String(json.id);

// 修复 2: Object Literal
// 错误
return { id: '123', name: 'test' };
// 修复
const obj = new MyClass();
obj.id = '123';
obj.name = 'test';
return obj;

// 修复 3: @BuilderParam
// 错误
@Builder MyBuilder(@BuilderParam content: () => void) {}
// 修复
@BuilderParam content: () => void;
@Builder MyBuilder() { this.content(); }
```

### 3.3 修复收敛判定

**收敛条件**:
- 错误数 = 0 → CONVERGED
- 错误数连续 3 轮不变 → STALLED
- 错误数增加 → REGRESSED
- 迭代达到 20 次 → EXHAUSTED

**返回状态**:

```json
{
  "build_status": "PASS | FAIL",
  "final_state": "CONVERGED | STALLED | REGRESSED | EXHAUSTED",
  "iterations": 14,
  "initial_errors": 47,
  "final_errors": 0,
  "hap_path": "build/default/outputs/default/entry-default-unsigned.hap"
}
```

---

## §4 占位符回填

### 4.1 编译触发回填

**编译错误可能是占位符未回填**:

```typescript
// 占位符（Slice 1）
async loadData(): Promise<void> {
  throw new Error('PLACEHOLDER: SLICE-2');  // ← 编译时会报错
}

// 检查是否有对应实现
if (existsImplementation('Slice-2')) {
  // 自动回填
  回填占位符
} else {
  // 保持占位符
  不修复此错误
}
```

### 4.2 回填策略

**自动回填条件**:
1. 占位符对应的 Slice 已完成
2. 有明确的实现代码
3. 接口契约匹配

**手动回填**:
- 复杂逻辑
- 接口不匹配
- 需要人工决策

---

## §5 构建产物验证

### 5.1 HAP 文件验证

**必须验证**:
- HAP 文件存在
- 文件大小 > 0
- 不是空转编译产生的旧文件

**验证方法**:

```bash
# 检查 HAP 文件
HAP_PATH="build/default/outputs/default/entry-default-unsigned.hap"

if [ ! -f "$HAP_PATH" ]; then
  echo "❌ HAP 文件不存在"
  exit 1
fi

HAP_SIZE=$(stat -f%z "$HAP_PATH" 2>/dev/null || stat -c%s "$HAP_PATH" 2>/dev/null)
if [ "$HAP_SIZE" -eq 0 ]; then
  echo "❌ HAP 文件为空"
  exit 1
fi

# 检查修改时间（确保是本次编译产生的）
HAP_TIME=$(stat -f%m "$HAP_PATH" 2>/dev/null || stat -c%Y "$HAP_PATH" 2>/dev/null)
BUILD_START_TIME=$(date +%s)
if [ $((BUILD_START_TIME - HAP_TIME)) -gt 300 ]; then
  echo "⚠️ HAP 文件可能是旧文件"
fi

echo "✅ HAP 文件验证通过"
echo "   路径: $HAP_PATH"
echo "   大小: $HAP_SIZE bytes"
```

### 5.2 空转检测

**空转编译的特征**:
- 输出包含 `UP-TO-DATE` 或 `all tasks up-to-date`
- 耗时 <5 秒
- HAP 文件时间戳旧

**检测方法**:

```typescript
const buildOutput = execSync('hvigorw assembleHap').toString();

if (buildOutput.includes('UP-TO-DATE') || 
    buildOutput.includes('all tasks up-to-date')) {
  console.warn('⚠️ 检测到空转编译');
  return { status: 'EMPTY_RUN', warning: '没有文件变更' };
}
```

**处理**:
- FV-2 不允许空转
- 其他编译门允许空转但记录警告

---

## §6 错误日志管理

### 6.1 错误日志结构

```
spec/execution/build-logs/
├── base-7-round-01.log
├── base-7-round-02.log
├── ...
├── base-7-round-14.log (最终成功)
├── stage-3-gate-round-01.log
└── fv-2-round-01.log
```

### 6.2 错误分类

**自动分类**:

```typescript
interface BuildError {
  type: 'syntax' | 'type' | 'api' | 'import' | 'unknown';
  file: string;
  line: number;
  message: string;
  fixable: boolean;
}

function classifyError(error: string): BuildError {
  if (error.includes('as unknown as')) {
    return { type: 'type', fixable: true };
  } else if (error.includes('Cannot find name')) {
    return { type: 'import', fixable: true };
  } else if (error.includes('@BuilderParam')) {
    return { type: 'syntax', fixable: true };
  } else {
    return { type: 'unknown', fixable: false };
  }
}
```

### 6.3 日志保留

**保留策略**:
- 每轮编译日志独立文件
- 成功后保留最后 3 轮日志
- 失败后保留所有日志

---

## §7 性能优化

### 7.1 并行编译（未来）

**当前**: 串行编译  
**未来**: 组内 Slice 可并行，编译也可并行

### 7.2 增量编译

**利用 HarmonyOS 增量编译**:
- 仅修改部分文件时，编译更快
- 保持 daemon 活跃

### 7.3 Cache 预热

**Stage 0 预热**:
- 后台启动 hvigor daemon
- 预热编译环境
- 不阻塞主流程

---

## §8 总结

**核心纪律**:

1. ✅ **三道编译门** - Base-7 / Stage 3 gate / FV-2
2. ✅ **最多 20 次迭代** - 自动修复循环
3. ✅ **确定性修复** - 常见错误有明确修复方案
4. ✅ **降级策略** - CLI 不稳定时降级到 IDE
5. ✅ **HAP 验证** - 确保编译产物有效
6. ✅ **空转检测** - FV-2 不允许空转

**关键检查点**:
- Base-7 是**唯一停点**（FAIL → 阻断）
- 其他编译门失败可重试
- 降级到 IDE 不阻断 Pipeline

---

**版本**: 1.0  
**更新时间**: 2024-11-03  
**适用**: i2h-execute 所有编译验证
