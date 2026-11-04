# i2h-execute 优化方案

**日期**: 2024-11-03  
**基于**: Cuike03 项目真实执行问题分析  
**参考**: `/Users/liuxingwen/DevEcoStudioProjects/Cuike03/spec/execution/I2H-EXECUTE-DEEP-ANALYSIS.md`

---

## 📊 问题总结

### 当前流程的致命缺陷

| 问题 | 影响 | 优先级 |
|------|------|--------|
| **没有调用 HarmonyOS 专业 Skill** | 生成 47 个编译错误 | P0 |
| **没有编译验证** | 用户需要手动修复 60 分钟 | P0 |
| **没有自动修复循环** | 实际耗时是预期的 2.67 倍 | P0 |

### 实际执行统计（Cuike03）

| 阶段 | 预计时间 | 实际时间 | 差异 |
|------|---------|---------|------|
| spec 生成 | 10 分钟 | ~15 分钟 | +50% |
| feature 生成 | 15 分钟 | ~20 分钟 | +33% |
| 代码生成 | 20 分钟 | ~25 分钟 | +25% |
| **手动修复** | 0 分钟 | **60 分钟** | **∞** |
| **总计** | **45 分钟** | **120 分钟** | **+167%** |

### 错误统计

**初始编译错误**: 47 个

**错误分布**:
- Object Literal 类型错误: 20 个 (43%) — 不知道 ArkTS 不支持对象字面量
- 类型转换错误: 10 个 (21%) — 使用了 `as unknown as`（ArkTS 不支持）
- SymbolGlyph API 错误: 5 个 (11%) — 没有查阅 HarmonyOS API 文档
- Builder 参数错误: 3 个 (6%) — 不了解 `@BuilderParam` 只能用于成员属性
- Indexed Access: 2 个 (4%) — 使用了 `as const` 和类型索引（ArkTS 不支持）
- 其他: 7 个 (15%)

---

## 🎯 优化目标

### 核心目标

1. **消除手动修复时间** — 从 60 分钟降到 0 分钟
2. **降低初始错误数** — 从 47 个降到 < 10 个
3. **缩短总执行时间** — 从 120 分钟降到 80 分钟
4. **提升成功率** — 从 50% 提升到 95%

### 投入产出比

- **开发投入**: 10-13 小时
- **每次执行节省**: 40 分钟
- **回本次数**: 20 次（20 × 40 分钟 = 13.3 小时）

---

## 🔧 优化方案

### Phase 1: 添加 Stage 4 编译验证与自动修复（P0）

**位置**: Stage 3 代码生成完成后

**新增内容**:

```markdown
## 5. Stage 4: 编译验证与自动修复 🚪

### Step 4.1: 自动编译验证

**目标**: 确保生成的代码能够编译通过

代码生成完成后，立即调用编译验证：

\`\`\`bash
# 调用 hmos_fix_build_errors skill
Skill({
  skill: "hmos_fix_build_errors",
  args: "--project-root <project_dir> --mode unsigned --max-iterations 20"
})
\`\`\`

### Step 4.2: 自动修复循环

**修复策略**:

1. **编译项目** → 收集错误
2. **分类错误** → 按类型处理
3. **应用修复** → 自动修复代码
4. **重新编译** → 验证修复
5. **循环执行** → 最多 20 次迭代

**常见错误的确定性修复**:

| 错误类型 | 自动修复方案 |
|---------|-------------|
| `as unknown as` | 替换为构造函数（如 `String()`） |
| Object Literal | 改为先创建实例再赋值 |
| `as const` | 移除，使用明确类型 |
| Indexed Access | 改为 switch 语句或函数 |
| `@BuilderParam` | 移到成员属性位置 |
| SymbolGlyph API | 修复参数类型（数组） |

### Step 4.3: 编译失败处理

**成功**:
- ✅ 编译通过
- 📦 生成 HAP 文件
- 🔧 记录修复次数和迭代轮数
- 📊 生成修复报告

**失败（20 轮后仍有错误）**:
- ❌ 记录剩余错误
- 📝 生成详细错误报告
- 🔍 标记需要人工介入的部分
- 📊 写入迁移报告

### Step 4.4: 生成编译报告

生成 `spec/execute/stage4-build-report.md`:

\`\`\`markdown
# Stage 4 编译验证报告

## 统计
- 初始错误: 47 个
- 修复轮次: 14 轮
- 最终状态: ✅ 编译成功

## 修复详情
| 轮次 | 错误数 | 修复类型 | 耗时 |
|------|-------|---------|------|
| 1 | 47 → 35 | Object Literal | 2min |
| 2 | 35 → 28 | as unknown as | 2min |
| ... | ... | ... | ... |
| 14 | 3 → 0 | SymbolGlyph API | 1min |

## HAP 产物
- 路径: build/default/outputs/default/entry-default-unsigned.hap
- 大小: 2.5 MB
- SHA256: abc123...
\`\`\`

### Stage 4 完成标记

创建 `spec/execute/stage4-complete.txt`
```

**预期效果**:
- 消除 60 分钟手动修复时间
- 增加 15 分钟自动修复时间
- 净节省: 45 分钟

---

### Phase 2: 在 Stage 2 加载 HarmonyOS 知识（P1）

**位置**: Stage 2 feature 生成完成后

**新增内容**:

```markdown
## 4. Stage 2: Feature 生成 + HarmonyOS 知识加载

### Step 2.3: 加载 HarmonyOS 专业知识 ✨

**目标**: 确保 Stage 3 代码生成使用正确的 ArkTS 规则

feature 文件生成后，立即加载 HarmonyOS 知识：

\`\`\`bash
# 1. 加载 ArkTS 严格模式规则
Skill({
  skill: "arkts-knowledge-verifier",
  args: "mode=get-rules"
})

# 2. 加载组件构建模式
Skill({
  skill: "arkts-component-builder",
  args: "mode=get-patterns"
})

# 3. 加载 HarmonyOS API 规范
Skill({
  skill: "hmos-api-reference",
  args: "mode=get-api-specs"
})
\`\`\`

**加载的知识**:

1. **ArkTS 严格模式规则**
   - ❌ 不支持 `as unknown as`
   - ❌ 不支持 `as const`
   - ❌ 不支持对象字面量（需明确类型）
   - ❌ 不支持类型索引访问
   - ✅ 使用构造函数进行类型转换
   - ✅ 使用明确类型定义

2. **组件构建规范**
   - `@BuilderParam` 只能用于成员属性
   - `@Builder` 函数不能有 `@BuilderParam` 参数
   - 组件参数需要明确类型

3. **HarmonyOS API 规范**
   - `SymbolGlyph.fontColor()` 需要数组类型
   - `bindSheet()` 的参数结构
   - 资源引用规范

### Step 2.4: 知识注入到 Stage 3

将加载的知识写入全局上下文：

\`\`\`typescript
// 写入 spec/execute/harmonyos-knowledge.json
{
  "arkts_rules": [...],
  "component_patterns": [...],
  "api_specs": [...]
}
\`\`\`

Stage 3 代码生成时引用此文件。
```

**预期效果**:
- 初始错误从 47 个降到 < 10 个
- 增加 5 分钟知识加载时间
- 减少约 10 轮修复迭代（节省 20 分钟）

---

### Phase 3: 在 Stage 3 使用 HarmonyOS 知识生成代码（P2）

**位置**: Stage 3 代码生成器内部

**修改内容**:

```markdown
## 5. Stage 3: 代码生成（使用 HarmonyOS 知识）

### Step 3.1: 读取 HarmonyOS 知识

代码生成前，先读取知识库：

\`\`\`typescript
const knowledge = JSON.parse(
  fs.readFileSync('spec/execute/harmonyos-knowledge.json', 'utf-8')
)
\`\`\`

### Step 3.2: 应用规则生成代码

**Model 代码生成**:

\`\`\`typescript
// ❌ 旧方式（会产生错误）
static fromJSON(json: Record<string, object>) {
  return new MyClass({
    id: json.id as unknown as string,  // 错误！
    name: json.name as unknown as string
  })
}

// ✅ 新方式（使用 ArkTS 规则）
static fromJSON(json: Record<string, object>) {
  const obj = new MyClass()
  obj.id = String(json.id)  // 使用构造函数
  obj.name = String(json.name)
  return obj
}
\`\`\`

**常量定义**:

\`\`\`typescript
// ❌ 旧方式
const COLORS = ['red', 'blue'] as const  // 错误！
type Color = typeof COLORS[number]  // 错误！

// ✅ 新方式
const COLORS: string[] = ['red', 'blue']
type Color = 'red' | 'blue'  // 明确枚举
\`\`\`

**组件代码生成**:

\`\`\`typescript
// ❌ 旧方式
@Builder
MyBuilder(title: string, @BuilderParam content: () => void) {}  // 错误！

// ✅ 新方式
@Component
struct MyComponent {
  @BuilderParam content: () => void  // 成员属性
  
  @Builder
  MyBuilder(title: string) {
    // ...
  }
}
\`\`\`

**API 调用生成**:

\`\`\`typescript
// ❌ 旧方式
SymbolGlyph($r('sys.symbol.house'))
  .fontColor($r('app.color.primary'))  // 错误！需要数组

// ✅ 新方式
SymbolGlyph($r('sys.symbol.house'))
  .fontColor([$r('app.color.primary')])  // 数组类型
\`\`\`

### Step 3.3: 验证生成的代码

生成代码后，立即验证：

\`\`\`bash
# 调用语法验证 skill
Skill({
  skill: "arkts-knowledge-verifier",
  args: "mode=verify-syntax files=<generated_files>"
})
\`\`\`
```

**预期效果**:
- 初始错误降到 < 5 个
- 代码质量显著提升
- 减少修复轮次

---

## 📈 优化效果预测

### 时间对比

| 阶段 | 当前耗时 | 优化后耗时 | 说明 |
|------|---------|-----------|------|
| Stage 1: spec | 15 分钟 | 15 分钟 | 无变化 |
| Stage 2: feature | 20 分钟 | 25 分钟 | +5 分钟（加载知识） |
| Stage 3: 代码生成 | 25 分钟 | 25 分钟 | 无变化（质量提升） |
| **Stage 4: 编译修复** | 0 分钟 | 15 分钟 | +15 分钟（新增） |
| **用户手动修复** | 60 分钟 | 0 分钟 | -60 分钟 |
| **总计** | **120 分钟** | **80 分钟** | **节省 40 分钟 (33%)** |

### 质量对比

| 指标 | 当前 | 优化后 |
|------|------|--------|
| 初始编译错误 | 47 个 | < 10 个 (预计) |
| 需要手动干预 | 是 | 否 |
| 成功率 | 50% | 95% |
| 用户满意度 | ❌ 低 | ✅ 高 |

---

## 🚀 实施计划

### Phase 1: Stage 4 编译验证（必须修复）

**投入**: 2-3 小时开发  
**优先级**: P0  
**预期收益**: 消除 60 分钟手动修复时间

**实施步骤**:
1. 在 SKILL.md 中添加 Stage 4 章节
2. 调用 `hmos_fix_build_errors` skill
3. 实现自动修复循环
4. 生成编译报告
5. 测试验证

### Phase 2: HarmonyOS 知识加载（强烈建议）

**投入**: 3-4 小时开发  
**优先级**: P1  
**预期收益**: 初始错误从 47 个降到 < 10 个

**实施步骤**:
1. 在 Stage 2 末尾添加知识加载步骤
2. 调用 `arkts-knowledge-verifier` skill
3. 调用 `arkts-component-builder` skill
4. 将知识写入 JSON 文件
5. 测试验证

### Phase 3: 代码生成使用知识（建议）

**投入**: 5-6 小时开发  
**优先级**: P2  
**预期收益**: 初始错误 < 5 个

**实施步骤**:
1. 修改 Stage 3 代码生成器
2. 读取 HarmonyOS 知识
3. 应用规则生成代码
4. 添加语法验证
5. 测试验证

### 总投入

**开发时间**: 10-13 小时  
**预期效果**: 每次执行节省 40 分钟  
**回本时间**: 20 次执行后

---

## 📝 关键设计决策

### 1. 为什么在 Stage 3 后添加编译验证？

**原因**:
- 代码已全部生成，是验证的最佳时机
- 可以一次性发现所有编译错误
- 避免用户手动修复

**证据**:
- Cuike03 实际执行：生成完代码后有 47 个编译错误
- Android 原版：有 Base-7、Stage 3 集中门、FV-2 三道编译门

### 2. 为什么在 Stage 2 加载 HarmonyOS 知识？

**原因**:
- feature 文件已生成，准备开始代码生成
- 可以将知识注入到 Stage 3 的生成上下文
- 避免生成错误的代码

**证据**:
- 47 个错误中 43% 是因为不知道 ArkTS 不支持对象字面量
- 21% 是因为使用了 `as unknown as`
- 11% 是因为不了解 HarmonyOS API 规范

### 3. 为什么使用 `hmos_fix_build_errors` skill？

**原因**:
- 已有可用的自动修复 skill
- 支持最多 20 次迭代
- 支持常见错误的确定性修复

**证据**:
- Cuike03 手动修复：14 轮，60 分钟
- 自动修复预计：20 轮内完成，15 分钟

---

## 🎯 成功标准

### 必须达成（P0）

- ✅ Stage 4 编译验证已添加
- ✅ 调用 `hmos_fix_build_errors` skill
- ✅ 实现自动修复循环（最多 20 次）
- ✅ 生成编译报告
- ✅ 消除手动修复时间

### 强烈建议（P1）

- ✅ Stage 2 加载 HarmonyOS 知识
- ✅ 调用 `arkts-knowledge-verifier` skill
- ✅ 调用 `arkts-component-builder` skill
- ✅ 初始错误 < 10 个

### 建议（P2）

- ✅ Stage 3 使用 HarmonyOS 知识生成代码
- ✅ 应用 ArkTS 严格模式规则
- ✅ 初始错误 < 5 个

---

## 📊 验证方法

### 1. 单元测试

创建测试项目，验证：
- Stage 4 能否正确调用编译验证
- 自动修复循环是否工作
- 编译报告是否生成

### 2. 集成测试

在真实项目（如 Cuike03）中执行：
- 完整执行 i2h-execute
- 统计初始错误数
- 统计修复轮次
- 统计总耗时
- 对比优化前后数据

### 3. 对比验证

| 指标 | 优化前（Cuike03） | 优化后（目标） | 验证方法 |
|------|-----------------|--------------|---------|
| 初始错误 | 47 个 | < 10 个 | 查看 Stage 4 报告 |
| 手动修复时间 | 60 分钟 | 0 分钟 | 记录用户操作 |
| 总耗时 | 120 分钟 | 80 分钟 | 记录总时间 |
| 成功率 | 50% | 95% | 统计成功次数 |

---

## 📂 文件清单

### 需要修改的文件

1. **`migbot/skills/i2h-execute/SKILL.md`** — 主文件，添加 Stage 4 和知识加载
2. **`migbot/skills/i2h-execute/references/`** — 新增参考文档（如需要）
3. **`migbot/skills/i2h-execute/templates/`** — 新增模板（如需要）

### 新增文件

1. **`docs/i2h-execute-optimization-plan.md`** — 本文档
2. **`docs/i2h-execute-before-after-comparison.md`** — 对比报告（执行后）
3. **`docs/i2h-execute-test-report.md`** — 测试报告（执行后）

---

## 🔗 相关文档

### 输入文档

1. **问题分析**: `/Users/liuxingwen/DevEcoStudioProjects/Cuike03/spec/execution/I2H-EXECUTE-DEEP-ANALYSIS.md`
2. **当前版本**: `migbot/skills/i2h-execute/SKILL.md`
3. **Android 原版**: `hmigbot-1.8.0/migbot/skills/a2h-execute/skill.md`
4. **交接文档**: `HANDOVER.md`

### 参考 Skill

1. **`hmos_fix_build_errors`** — 编译和修复
2. **`arkts-knowledge-verifier`** — ArkTS 规则验证
3. **`arkts-component-builder`** — 组件构建规范
4. **`hmos-api-reference`** — HarmonyOS API 规范

---

**创建时间**: 2024-11-03  
**创建人**: Claude Opus 5.5  
**状态**: ✅ 优化方案已完成，准备实施
