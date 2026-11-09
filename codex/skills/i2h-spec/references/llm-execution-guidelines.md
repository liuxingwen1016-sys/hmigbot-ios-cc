<!-- when: LLM 开始执行 i2h-spec 任务时加载 -->
<!-- topics: LLM 行为规范、分析深度、决策标准、输出质量 -->

# LLM 执行准则

本文档指导 LLM 在执行 i2h-spec 时的具体行为规范。

## 1. 核心职责

### LLM 的职责（必须做）

**语义分析**：
- 阅读源码，理解功能用途
- 评估复杂度（不能仅凭行数）
- 推断组件依赖关系
- 识别导航模式和数据流

**内容生成**：
- 生成人类可读的文档
- 编写代码示例（可运行的 ArkTS 代码）
- 设计迁移策略（详细、可操作）
- 评估风险（技术、数据、性能）

**决策判断**：
- 选择适用的转换器（template/semantic/manual）
- 分配优先级（P0/P1/P2/P3）
- 评估 findings 类别（精确/推断/管线/环境）
- 决定是否降级（脚本失败时）

### LLM 不应该做

**❌ 不做确定性提取**（让脚本做）：
- 不手动遍历目录查找文件（除非降级）
- 不解析 YAML/JSON 格式（除非分析内容）
- 不统计行数、文件数（除非脚本不可用）

**❌ 不绕过规范**：
- 不跳过 references 的加载
- 不用 TODO 占位（除非源文件真的缺失）
- 不简化模板要求的字段
- 不改写脚本的产出格式

**❌ 不臆测**：
- 不猜测文件路径（必须验证）
- 不假设框架选择（必须查映射表）
- 不虚构代码示例（必须基于实际 API）

## 2. 阅读源码的深度

### 必须完整阅读

以下情况必须 Read 完整源文件：

1. **Phase A2: 分析每个页面**
   - Read 整个 View/ViewController 文件
   - 理解 body 的完整结构
   - 识别所有状态变量和依赖

2. **Phase C3: 分析每个功能**
   - Read 功能的主要实现文件
   - 理解核心逻辑和架构
   - 识别关键类和函数

3. **复杂页面/功能**
   - complexity=complex 或 very_complex 时
   - 必须深入阅读，理解细节

### 可以部分阅读

以下情况可以部分阅读或扫描：

1. **Phase A1: 项目结构扫描**
   - 可以只读文件头部（识别类名）
   - 不需要理解完整逻辑

2. **简单页面**
   - complexity=simple 且行数 < 30
   - 可以快速扫描

3. **重复模式**
   - 已分析过类似组件
   - 可以参考之前的分析

## 3. 复杂度评估标准

### 不能仅凭行数

复杂度评估必须综合考虑：

```
行数（参考）：
  < 50 行 → 倾向 simple
  50-150 行 → 倾向 medium
  150-300 行 → 倾向 complex
  > 300 行 → 倾向 very_complex

但必须结合：
  □ 状态管理复杂度
    - 只有 @State → simple
    - 有 @ObservedObject → medium
    - 有 @EnvironmentObject + 复杂数据流 → complex
  
  □ UI 结构复杂度
    - 简单布局（1-2 层嵌套）→ simple
    - 中等嵌套（3-5 层）→ medium
    - 深度嵌套（> 5 层）+ 动态布局 → complex
  
  □ 系统功能
    - 无系统功能 → simple/medium
    - 有简单系统功能（UserDefaults）→ medium
    - 有复杂系统功能（Camera、Location）→ complex
  
  □ UIKit 集成
    - 纯 SwiftUI → simple/medium
    - 有 UIKit 集成 → complex/very_complex
  
  □ 自定义逻辑
    - 纯展示 → simple
    - 有交互 → medium
    - 复杂业务逻辑 → complex
```

**示例判断**：

```swift
// 40 行，但有 SwiftData + 复杂状态 → complexity=complex
struct BeanListView: View {
  @Environment(\.modelContext) var context
  @Query var beans: [Bean]
  @State private var showingAdd = false
  @State private var selectedBean: Bean?
  
  var body: some View {
    List {
      ForEach(beans) { bean in
        NavigationLink(value: bean) {
          BeanCard(bean: bean)
        }
      }
      .onDelete(perform: deleteBeans)
    }
    .sheet(isPresented: $showingAdd) {
      AddBeanView()
    }
  }
  
  func deleteBeans(at offsets: IndexSet) { ... }
}

// 评估: 虽然只有 40 行，但涉及 SwiftData（复杂数据层）
// + 导航 + 模态弹窗 + 删除操作 → complexity=complex
```

## 4. 映射规则的使用

### 必须查表

不能凭记忆猜测映射关系，必须查 `ios-to-harmonyos-mapping.md`：

```
遇到 iOS 组件时:
  1. 查映射表找到对应的 HarmonyOS 组件
  2. 检查映射说明（参数名不同、API 差异）
  3. 引用映射表的具体章节

遇到框架/API 时:
  1. 查映射表找到对应的鸿蒙框架
  2. 理解差异（ORM vs SQL、同步 vs 异步）
  3. 说明迁移策略

遇到不支持的功能时:
  1. 查映射表确认"不支持"
  2. 查看是否有替代方案
  3. 标记为需要完全重写或去掉
```

### 映射表没有的情况

如果映射表缺失某个组件：

```
1. 标记为"映射表缺失"
2. 根据类似组件推测可能的映射
3. 标记 Confidence 为 medium 或 low
4. 建议补充映射表
```

## 5. 代码示例的要求

### 必须可运行

生成的 ArkTS 代码示例必须：

```
□ 语法正确（不能有语法错误）
□ API 真实存在（不能虚构 API）
□ 导入语句完整（import ... from '@ohos...'）
□ 类型定义正确（number、string、boolean）
□ 逻辑完整（有开始、有结束）
```

### 示例的深度

```
Simple 功能:
  - 20-30 行示例即可
  - 展示核心 API 使用

Medium/Complex 功能:
  - 50-100 行示例
  - 完整的类定义
  - 包含错误处理

Very Complex 功能:
  - 可以分段给出多个示例
  - 每个示例聚焦一个方面
```

### 不要虚构 API

```
✅ 正确:
import relationalStore from '@ohos.data.relationalStore'
let store = await relationalStore.getRdbStore(context, config)

❌ 错误:
import BeanDatabase from '@ohos.data.BeanDatabase'  // 不存在
let db = new BeanDatabase()  // 虚构的
```

## 6. 迁移策略的要求

### 必须详细可操作

迁移策略必须包含：

```
□ 明确的步骤（至少 5 步）
□ 每步的具体操作（不能是"实现功能X"）
□ 使用的 API 或框架
□ 预期的输出或结果
□ 验证方法
```

**示例对比**：

```
❌ 不够详细:
1. 创建数据库
2. 实现 CRUD
3. 测试

✅ 详细可操作:
1. 定义数据表结构
   - 创建 Bean 表：id, name, origin, roast_level, purchase_date, notes
   - 创建 Recipe 表：id, bean_id, name, ...
   - 定义外键关系：Recipe.bean_id → Bean.id

2. 创建数据库管理器类
   - 使用 relationalStore.getRdbStore() 初始化数据库
   - 配置 SecurityLevel.S1（应用私有数据）
   - 实现版本迁移逻辑（从 v1 到 v2）

3. 实现 addBean() 方法
   - 使用 valueBucket 构造插入数据
   - 调用 rdbStore.insert('bean', valueBucket)
   - 返回插入的 rowId

4. 实现 getBeans() 方法
   - 使用 RdbPredicates 构造查询条件
   - 调用 rdbStore.query(predicates)
   - 遍历 resultSet，构造 Bean 对象数组

5. 实现级联删除逻辑
   - 删除 Bean 时，先查询关联的 Recipe
   - 删除所有关联 Recipe
   - 最后删除 Bean 记录

6. 集成到 UI 层
   - 在 EntryAbility.onCreate() 中初始化数据库
   - 使用 @State 管理 Bean 列表
   - 实现数据变更通知机制
```

## 7. 风险评估的要求

### 不能省略

每个复杂页面/功能都必须评估风险：

```
技术风险:
  □ 技术栈差异导致的实现困难
  □ API 不兼容
  □ 性能问题

数据风险:
  □ 数据迁移复杂度
  □ 数据格式不兼容
  □ 数据丢失风险

时间风险:
  □ 预估时间可能不准确
  □ 依赖其他功能延期
  □ 技术难点可能耗时更久
```

### 风险等级

```
🟢 Low: 
  - 直接映射，无特殊问题
  - 预估准确度高

🟡 Medium:
  - 需要重新设计，但有成熟方案
  - 预估准确度中等

🔴 High:
  - 需要完全重写或替代方案
  - 技术难点多
  - 预估准确度低
```

## 8. Findings 处理决策

### 分类判断标准

```
精确类 (Precise):
  - 有明确的对错标准
  - 可以通过代码自动验证
  - 示例: 文件缺失、ID 重复、YAML 格式错误

推断类 (Inferred):
  - 基于启发式规则或 LLM 推断
  - 没有绝对的对错标准
  - 可能误报
  - 示例: 复杂度评估不准确、描述过于简略

管线类 (Pipeline):
  - 跨阶段的约束检查
  - 当前阶段无法完全确定
  - 需要下游验证
  - 示例: 预估转换率（需实际执行）

环境类 (Environment):
  - 工具链、环境配置问题
  - 非业务逻辑错误
  - 示例: 脚本不存在、权限问题
```

### 处理决策流程

```
遇到 Finding:
  1. 分类（精确/推断/管线/环境）
  2. 判断 severity（blocking/warning/info）
  3. 决定处理方式
     ├─ 精确类 + blocking → 必须修复
     ├─ 推断类 + blocking → 尝试修复 → 记账放行
     ├─ 管线类 → 记账 + 推到下游
     └─ 环境类 → 降级方案 → 记账
  4. 记录到 decision-ledger.md
  5. 更新 open-findings.json
```

## 9. 降级决策

### 何时降级

```
脚本调用失败:
  1. 尝试调用脚本
  2. 失败 → 立即降级，不重试多次
  3. 记账"工具缺口，已降级"

脚本不存在:
  1. 检查 skill 是否存在
  2. 不存在 → 直接降级
  3. 不等待、不报错
```

### 降级后的行为

```
降级到 LLM 执行:
  □ 执行等价的确定性提取
  □ 补充所有语义字段
  □ Confidence 标记为 medium
  □ 继续正常流程
  □ 不影响最终产出质量
```

## 10. 输出质量自检

### 每个产物生成后

```
立即自检:
  □ 所有必填字段非空（不能是 null、""、TODO）
  □ 文件路径已验证存在（调用 Read 或 Bash ls 确认）
  □ 命名规范一致（page_NNNN、FXXX）
  □ 代码示例语法正确（不能有明显语法错误）
  □ 没有用 TODO 占位（除非源文件确实缺失）
  □ 章节完整（按模板要求）
  □ 内容实质（不能是"待补充"、"TBD"）
```

### 常见问题检查

```
□ 是否忘记读取 reference 文档？
□ 是否省略了模板要求的字段？
□ 是否用了虚构的 API？
□ 是否猜测了文件路径（而没有验证）？
□ 是否跳过了源码阅读（直接猜测用途）？
□ 是否用 TODO 占位了关键字段？
```

## 11. 记录决策的要求

### 何时记录

```
必须记录:
  □ Finding 放行（推断类、管线类、环境类）
  □ Gate 审批（每个 Gate）
  □ 技术选型（关键框架选择）
  □ 降级处理（脚本失败切换到 LLM）

不需要记录:
  □ 正常通过的检查
  □ 自动修复成功的 findings
```

### 记录格式

必须使用 `decision-ledger-format.md` 规定的格式：

```markdown
## Finding F001: ...

**Category**: ...
**Severity**: ...
**Decision**: ...
**Rationale**: {必须详细，不能是"已处理"}
**Decision Date**: {ISO 8601 精确到秒}
**Approval Source**: auto-policy | default-policy | user-confirmed
```

## 12. 上下文管理

### 减少重复读取

```
已经读取的文件:
  - 缓存关键信息在记忆中
  - Phase B 复用 Phase A 的分析
  - 不需要重复完整读取

但不能:
  - 完全不读（必须至少读一次）
  - 仅凭文件名猜测内容
```

### 批量操作

```
需要对多个文件做相同操作:
  - 尽量合并工具调用
  - 减少单独的 Read/Write

但不能:
  - 一次处理太多（导致质量下降）
  - 建议每批 3-5 个文件
```

## 13. 最佳实践

### DO（推荐）

✅ **深入理解源码**
- 不只是识别组件名称
- 理解业务逻辑和数据流

✅ **详细说明理由**
- 为什么选择这个映射
- 为什么评估为这个复杂度
- 为什么放行这个 finding

✅ **提供可操作的建议**
- 迁移策略具体到步骤
- 代码示例可以直接运行
- 风险评估带缓解措施

✅ **保持一致性**
- 命名规范统一
- 术语使用一致
- 格式保持相同

### DON'T（避免）

❌ **不要跳过 references**
- 不能仅凭 SKILL.md 的摘要执行
- 必须完整读取引用的 reference

❌ **不要用 TODO 糊弄**
- 除非源文件真的缺失
- 必填字段必须有实质内容

❌ **不要猜测映射关系**
- 必须查映射表
- 不能凭记忆或常识

❌ **不要虚构示例**
- 代码必须基于真实 API
- 不能编造不存在的方法

❌ **不要省略验证**
- 文件路径必须验证存在
- 产出后必须自检

## 14. 调试和问题排查

### 遇到问题时

```
问题: 生成的产物格式不对
  1. 检查是否完整读取了 template
  2. 检查是否遗漏了必填字段
  3. 重新生成（最多 2 次）

问题: Finding 无法修复
  1. 确认 finding 类别
  2. 如果是推断类 → 尝试 2 次 → 记账放行
  3. 如果是精确类 → 仔细分析根因 → 修复

问题: 不确定如何映射
  1. 查 ios-to-harmonyos-mapping.md
  2. 如果映射表没有 → 标记"映射表缺失"
  3. 根据类似组件推测 → 降低 Confidence

问题: 源文件无法访问
  1. 验证文件路径是否正确
  2. 尝试相对路径和绝对路径
  3. 确实不存在 → 标记 Confidence=low → 添加 TODO
```

### 求助机制

```
遇到无法解决的问题:
  1. 不要无限重试
  2. 不要猜测或虚构
  3. 标记问题 + 记账放行
  4. 推到下游阶段或人工处理
```

这些准则确保 LLM 在执行 i2h-spec 时产出高质量、可追溯、符合规范的 spec 文档。
