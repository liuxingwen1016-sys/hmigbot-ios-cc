---
name: i2h-execute
description: iOS→HarmonyOS 代码迁移执行引擎（Pipeline 第三步）：按 plan 自动生成代码、编译验证、自动修复，确保可构建的 HarmonyOS 应用
tags: [pipeline, migration, code-generation]
type: pipeline
domain: migration
version: 2.0
---

# i2h-execute

**Pipeline 第三步**：执行实际的代码转换，生成可编译的 HarmonyOS 应用。

## 🎯 定位

基于 `i2h-spec` 生成的规格和 `i2h-plan` 生成的计划，自动完成：
1. **代码生成** — 将 iOS 代码转换为 HarmonyOS ArkTS 代码
2. **编译验证** — 确保生成的代码能够编译通过
3. **自动修复** — 自动修复常见的编译错误

```
i2h-spec → i2h-plan → i2h-execute（本 skill）
                          │
                          ├─ Stage 0: 环境准备
                          ├─ Stage 1: Spec 解析与理解
                          ├─ Stage 2: Feature 详细设计
                          ├─ Stage 3: 代码生成
                          ├─ Stage 4: 编译验证与自动修复 ✨ 新增
                          └─ Stage 5: 最终报告
```

---

## 📋 启动检查

### 前置条件

检查 pipeline 产物：

| 文件 | 说明 | 缺失处理 |
|------|------|---------|
| `spec/baseline/spec-index.md` | i2h-spec 生成的规格索引 | 提示先运行 `/i2h-spec` |
| `spec/baseline/plans/execution-plan.md` | i2h-plan 生成的执行计划 | 提示先运行 `/i2h-plan` |
| `spec/baseline/features/` | Feature 详细规格目录 | 提示先运行 `/i2h-spec` |

### 环境检查

```bash
# 检查 DevEco Studio 是否安装
[ -d "/Applications/DevEco-Studio.app" ] || echo "请安装 DevEco Studio"

# 检查 HarmonyOS 项目是否初始化
[ -f "build-profile.json5" ] || echo "请先初始化 HarmonyOS 项目"

# 检查必要的 skills 是否可用
ls -la ~/.claude/migbot/skills/hmos_fix_build_errors/ || echo "缺少编译修复 skill"
ls -la ~/.claude/migbot/skills/arkts-knowledge-verifier/ || echo "缺少知识验证 skill"
```

---

## 1. Stage 0: 环境准备

### Step 0.1: 验证工作环境

```bash
# 读取配置
IOS_PATH=$(grep "ios_project_path" spec/.i2h/config.json | cut -d'"' -f4)
HOS_PATH=$(pwd)
DEVECO_PATH="/Applications/DevEco-Studio.app/Contents"

# 验证路径
echo "iOS 项目: $IOS_PATH"
echo "HarmonyOS 项目: $HOS_PATH"
echo "DevEco Studio: $DEVECO_PATH"
```

### Step 0.2: 创建执行目录

```bash
# 创建执行域目录
mkdir -p spec/execution/{source-understanding,conversion-reports,briefs,autofix-log}

# 创建占位注册表
cat > spec/execution/placeholder-registry.json << 'EOF'
{
  "version": "2.0",
  "placeholders": [],
  "last_updated": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
}
EOF
```

### Step 0.3: 环境预热（并行后台）

**目标**: 预热编译环境，避免首次编译冷启动

启动后台预热任务：

```bash
# 派发后台 agent 进行环境预热
Agent({
  description: "Environment prewarm",
  prompt: """
  执行环境预热任务（后台并行，不阻塞主流程）：
  
  1. 检查 local.properties 中的 hwsdk.dir
  2. 运行 ohpm install 安装依赖
  3. 预热 hvigor daemon（assembleHap）
  
  预热构建结果丢弃，不记录，不 gate。
  """
})
```

**不等待完成** — 后台并行进行

### Step 0.4: 读取执行计划

```bash
# 读取 execution-plan.md
PLAN_FILE="spec/baseline/plans/execution-plan.md"

# 提取关键信息
TOTAL_FEATURES=$(grep -c "^### F-" "$PLAN_FILE")
TOTAL_PAGES=$(grep "Total pages:" "$PLAN_FILE" | cut -d':' -f2 | tr -d ' ')

echo "📊 执行计划统计:"
echo "  - 功能数: $TOTAL_FEATURES"
echo "  - 页面数: $TOTAL_PAGES"
```

### Step 0.5: 冻结 iOS 固定几何 scale（有目标 presentation 时）

如果执行输入已经记录了目标逻辑宽度和 iOS runtime Accessibility JSON，先生成
`spec/execution/layout-scale.json`：

```bash
python3 .claude/skills/i2h-execute/scripts/layout_scale.py \
  --ios-accessibility-json <ios-accessibility.json> \
  --target-logical-width-vp <target_width_vp> \
  --out spec/execution/layout-scale.json
```

转换器只将该 scale 用于有共同设计宽度证据的固定几何量。字体、动态内容、安全区、系统栏和百分比布局不继承该 scale。目标宽度缺失时保留源数值，并把归一化列为待验证项。

### Stage 0 完成标记

```
✅ Stage 0 完成:
  - 工作环境已验证
  - 执行目录已创建
  - 环境预热已启动（后台）
  - 执行计划已加载
```

创建 `spec/execution/stage0-complete.txt`

---

## 2. Stage 1: Spec 解析与理解

### Step 1.1: 读取 Feature Specs

**目标**: 深入理解每个 feature 的需求

```bash
# 读取所有 feature specs
for feature_file in spec/baseline/features/F-*.md; do
  feature_id=$(basename "$feature_file" .md)
  
  echo "📖 读取 $feature_id"
  
  # 提取关键信息
  # - 功能描述
  # - iOS 实现位置
  # - HarmonyOS 映射
  # - 验收标准
  # - 技术依赖
done
```

### Step 1.2: 源码理解（complex features）

**对于 complex features**，需要深入理解源码：

```typescript
// 读取 iOS 源码
const iosSourcePath = feature.ios_implementation.file
const iosCode = fs.readFileSync(iosSourcePath, 'utf-8')

// 生成源码理解文档
const sourceUnderstanding = `
# ${featureId} 源码理解

## 核心类和职责
- ViewModel: ${viewModelName} — 管理${功能}状态
- Model: ${modelName} — ${数据模型说明}
- Service: ${serviceName} — ${业务逻辑说明}

## 数据流
${iosDataFlow}

## 关键方法
${iosKeyMethods}

## 技术要点
${iosTechPoints}
`

// 写入源码理解文档
fs.writeFileSync(
  `spec/execution/source-understanding/${featureId}-source-notes.md`,
  sourceUnderstanding
)
```

### Step 1.3: 生成 Stage 1 Brief

```markdown
# Stage 1: Spec 解析与理解 — Brief

## 统计
- 总功能数: ${totalFeatures}
- Simple features: ${simpleCount}
- Complex features: ${complexCount}
- 生成源码理解文档: ${complexCount} 个

## Feature 列表
| Feature ID | 名称 | 复杂度 | 源码理解 |
|-----------|------|--------|---------|
| F-001 | 数据存储 | Complex | ✅ |
| F-002 | 网络请求 | Simple | - |
| ... | ... | ... | ... |

## 下一步
进入 Stage 2: Feature 详细设计
```

写入 `spec/execution/briefs/stage1-spec-understanding.md`

### Stage 1 完成标记

创建 `spec/execution/stage1-complete.txt`

---

## 3. Stage 2: Feature 详细设计 + HarmonyOS 知识加载 ✨

### Step 2.1: 生成 Feature 详细设计

**目标**: 为每个 feature 生成详细的实现设计

对每个 feature：

```typescript
// 生成详细设计文档
const featureDesign = {
  feature_id: 'F-001',
  name: '数据存储',
  
  // HarmonyOS 实现方案
  harmonyos_implementation: {
    // ViewModel
    viewmodel: {
      class_name: 'DataStorageViewModel',
      file: 'entry/src/main/ets/viewmodels/DataStorageViewModel.ets',
      responsibilities: ['管理数据状态', '处理用户操作'],
      state_properties: [
        { name: 'items', type: 'BeanRecord[]', initial: '[]' }
      ],
      methods: [
        { name: 'addItem', params: ['item: BeanRecord'], returns: 'void' },
        { name: 'deleteItem', params: ['id: string'], returns: 'void' }
      ]
    },
    
    // Model
    model: {
      class_name: 'BeanRecord',
      file: 'entry/src/main/ets/models/BeanRecord.ets',
      properties: [
        { name: 'id', type: 'string' },
        { name: 'name', type: 'string' },
        { name: 'createdAt', type: 'Date' }
      ],
      methods: [
        { name: 'fromJSON', params: ['json: object'], returns: 'BeanRecord' },
        { name: 'toJSON', params: [], returns: 'object' }
      ]
    },
    
    // Repository
    repository: {
      class_name: 'LocalStorageRepository',
      file: 'entry/src/main/ets/repositories/LocalStorageRepository.ets',
      methods: [
        { name: 'save', params: ['item: BeanRecord'], returns: 'Promise<void>' },
        { name: 'load', params: [], returns: 'Promise<BeanRecord[]>' },
        { name: 'delete', params: ['id: string'], returns: 'Promise<void>' }
      ]
    }
  },
  
  // 数据流
  data_flow: 'UI → ViewModel → Repository → Preferences',
  
  // 依赖
  dependencies: {
    harmonyos_apis: ['@ohos.data.preferences'],
    base_components: ['Base-1: Models', 'Base-5: Preferences'],
    third_party: []
  }
}

// 写入设计文档
fs.writeFileSync(
  `spec/execution/designs/feature-${featureId}-design.json`,
  JSON.stringify(featureDesign, null, 2)
)
```

### Step 2.2: 加载 HarmonyOS 专业知识 ✨✨✨

**⭐ 核心改进：防止生成错误代码**

**目标**: 确保 Stage 3 代码生成使用正确的 ArkTS 规则和 HarmonyOS API

```bash
echo "📚 加载 HarmonyOS 专业知识..."

# 1. 加载 ArkTS 严格模式规则
Skill({
  skill: "arkts-knowledge-verifier",
  args: "mode=get-rules output=spec/execution/arkts-rules.json"
})

# 2. 加载组件构建规范
Skill({
  skill: "arkts-component-builder",
  args: "mode=get-patterns output=spec/execution/component-patterns.json"
})

# 3. 加载 HarmonyOS API 规范（可选，如果有对应 skill）
if [ -f ~/.claude/migbot/skills/hmos-api-reference ]; then
  Skill({
    skill: "hmos-api-reference",
    args: "mode=get-api-specs output=spec/execution/api-specs.json"
  })
fi

echo "✅ HarmonyOS 知识已加载"
```

**加载的知识内容**:

```json
// spec/execution/arkts-rules.json
{
  "version": "2.0",
  "rules": [
    {
      "rule_id": "R001",
      "name": "禁止 as unknown as",
      "description": "ArkTS 不支持 'as unknown as' 类型转换",
      "wrong": "json.id as unknown as string",
      "correct": "String(json.id)",
      "category": "type-conversion"
    },
    {
      "rule_id": "R002",
      "name": "禁止 as const",
      "description": "ArkTS 不支持 'as const' 常量断言",
      "wrong": "const COLORS = ['red'] as const",
      "correct": "const COLORS: string[] = ['red']",
      "category": "const-assertion"
    },
    {
      "rule_id": "R003",
      "name": "对象字面量需明确类型",
      "description": "返回对象时必须先创建实例",
      "wrong": "return { id: '123', name: 'test' }",
      "correct": "const obj = new MyClass(); obj.id = '123'; return obj",
      "category": "object-literal"
    },
    {
      "rule_id": "R004",
      "name": "禁止类型索引访问",
      "description": "不支持 typeof array[number] 类型",
      "wrong": "type Color = typeof COLORS[number]",
      "correct": "type Color = 'red' | 'blue' | 'green'",
      "category": "indexed-access"
    },
    {
      "rule_id": "R005",
      "name": "@BuilderParam 只能用于成员属性",
      "description": "@BuilderParam 不能用于方法参数",
      "wrong": "@Builder MyBuilder(@BuilderParam content: () => void) {}",
      "correct": "@BuilderParam content: () => void",
      "category": "builder-param"
    }
  ],
  "api_corrections": [
    {
      "api": "SymbolGlyph.fontColor",
      "wrong": ".fontColor($r('app.color.primary'))",
      "correct": ".fontColor([$r('app.color.primary')])",
      "reason": "需要数组类型"
    },
    {
      "api": "bindSheet",
      "note": "title 参数类型是 SheetTitleOptions，不是 string"
    }
  ]
}
```

```json
// spec/execution/component-patterns.json
{
  "version": "2.0",
  "patterns": [
    {
      "pattern_id": "P001",
      "name": "基础组件",
      "template": "@Component\nstruct MyComponent {\n  build() {\n    Column() {}\n  }\n}"
    },
    {
      "pattern_id": "P002",
      "name": "状态管理组件",
      "template": "@ComponentV2\nstruct MyComponent {\n  @Local state: string = ''\n}"
    }
  ]
}
```

### Step 2.3: 合并知识库

```bash
# 合并所有知识到一个文件
cat > spec/execution/harmonyos-knowledge.json << 'EOF'
{
  "version": "2.0",
  "loaded_at": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "arkts_rules": $(cat spec/execution/arkts-rules.json),
  "component_patterns": $(cat spec/execution/component-patterns.json),
  "api_specs": $(cat spec/execution/api-specs.json 2>/dev/null || echo '{}')
}
EOF

echo "✅ HarmonyOS 知识库已合并"
```

### Step 2.4: 生成 Stage 2 Brief

```markdown
# Stage 2: Feature 详细设计 + HarmonyOS 知识加载 — Brief

## 统计
- 生成设计文档: ${featureCount} 个
- 加载 ArkTS 规则: ${ruleCount} 条
- 加载组件模式: ${patternCount} 个
- 加载 API 规范: ${apiCount} 个

## HarmonyOS 知识库
- ArkTS 严格模式规则: spec/execution/arkts-rules.json
- 组件构建规范: spec/execution/component-patterns.json
- API 规范: spec/execution/api-specs.json
- 合并知识库: spec/execution/harmonyos-knowledge.json

## 关键规则
- ❌ 禁止 as unknown as → ✅ 使用构造函数
- ❌ 禁止 as const → ✅ 使用明确类型
- ❌ 对象字面量 → ✅ 先创建实例
- ❌ 类型索引访问 → ✅ 使用枚举类型
- ❌ @BuilderParam 在参数 → ✅ 成员属性

## 下一步
进入 Stage 3: 代码生成（使用 HarmonyOS 知识）
```

写入 `spec/execution/briefs/stage2-feature-design.md`

### Stage 2 完成标记

创建 `spec/execution/stage2-complete.txt`

---

## 4. Stage 3: 代码生成（使用 HarmonyOS 知识）✨

### Step 3.1: 加载知识库

**在生成任何代码之前，先加载知识库**:

```typescript
// 读取 HarmonyOS 知识库
const knowledge = JSON.parse(
  fs.readFileSync('spec/execution/harmonyos-knowledge.json', 'utf-8')
)

// 提取规则
const arktsRules = knowledge.arkts_rules.rules
const componentPatterns = knowledge.component_patterns.patterns
const apiSpecs = knowledge.api_specs

console.log(`✅ 已加载 ${arktsRules.length} 条 ArkTS 规则`)
console.log(`✅ 已加载 ${componentPatterns.length} 个组件模式`)
```

### Step 3.2: 按 Feature 生成代码

**对每个 feature 按优先级顺序生成**:

```typescript
for (const feature of executionPlan.features) {
  console.log(`🔨 生成 ${feature.feature_id}: ${feature.name}`)
  
  // 读取详细设计
  const design = JSON.parse(
    fs.readFileSync(`spec/execution/designs/feature-${feature.feature_id}-design.json`)
  )
  
  // 生成文件
  await generateModel(feature, design, arktsRules)
  await generateViewModel(feature, design, arktsRules)
  await generateRepository(feature, design, arktsRules)
  await generateUI(feature, design, arktsRules, componentPatterns)
  
  // 记录生成结果
  generationResults.push({
    feature_id: feature.feature_id,
    status: 'generated',
    files: design.harmonyos_implementation.files
  })
}
```

### Step 3.3: 应用 ArkTS 规则生成代码

**⭐ 核心改进：生成符合 ArkTS 规范的代码**

#### 3.3.1 Model 代码生成

```typescript
function generateModel(feature, design, arktsRules) {
  const model = design.harmonyos_implementation.model
  
  // 应用规则 R001: 禁止 as unknown as
  // 应用规则 R003: 对象字面量需明确类型
  
  const code = `
export class ${model.class_name} {
  ${model.properties.map(p => `${p.name}: ${p.type}`).join('\n  ')}
  
  constructor() {
    ${model.properties.map(p => `this.${p.name} = ${getDefaultValue(p.type)}`).join('\n    ')}
  }
  
  // ✅ 正确：使用构造函数进行类型转换
  static fromJSON(json: Record<string, Object>): ${model.class_name} {
    const obj = new ${model.class_name}()
    obj.id = String(json['id'])  // ✅ 使用 String() 而不是 as unknown as
    obj.name = String(json['name'])
    obj.createdAt = new Date(Number(json['createdAt']))
    return obj
  }
  
  // ✅ 正确：先创建对象再返回
  toJSON(): Record<string, Object> {
    const json: Record<string, Object> = {}
    json['id'] = this.id
    json['name'] = this.name
    json['createdAt'] = this.createdAt.getTime()
    return json
  }
}
  `.trim()
  
  fs.writeFileSync(model.file, code)
  console.log(`  ✅ 生成 Model: ${model.file}`)
}
```

#### 3.3.2 ViewModel 代码生成

```typescript
function generateViewModel(feature, design, arktsRules) {
  const viewmodel = design.harmonyos_implementation.viewmodel
  
  // 应用规则 R002: 禁止 as const
  // 应用规则 R004: 禁止类型索引访问
  
  const code = `
import { ${design.harmonyos_implementation.model.class_name} } from '../models/${design.harmonyos_implementation.model.class_name}'

@ObservedV2
export class ${viewmodel.class_name} {
  ${viewmodel.state_properties.map(p => `@Trace ${p.name}: ${p.type} = ${p.initial}`).join('\n  ')}
  
  // ✅ 正确：使用明确类型而不是 as const
  private readonly VALID_STATUSES: string[] = ['pending', 'completed']  // ✅ string[] 而不是 as const
  
  ${viewmodel.methods.map(m => `
  ${m.name}(${m.params.join(', ')}): ${m.returns} {
    // Implementation
  }
  `).join('\n')}
}
  `.trim()
  
  fs.writeFileSync(viewmodel.file, code)
  console.log(`  ✅ 生成 ViewModel: ${viewmodel.file}`)
}
```

#### 3.3.3 UI 组件代码生成

```typescript
function generateUI(feature, design, arktsRules, componentPatterns) {
  const ui = design.harmonyos_implementation.ui
  
  // 应用规则 R005: @BuilderParam 只能用于成员属性
  // 应用 API 修正：SymbolGlyph.fontColor 需要数组
  
  const code = `
import { ${design.harmonyos_implementation.viewmodel.class_name} } from '../viewmodels/${design.harmonyos_implementation.viewmodel.class_name}'

@ComponentV2
export struct ${ui.component_name} {
  @Local viewModel: ${design.harmonyos_implementation.viewmodel.class_name} = new ${design.harmonyos_implementation.viewmodel.class_name}()
  
  // ✅ 正确：@BuilderParam 用于成员属性
  @BuilderParam customContent: () => void = this.defaultContent
  
  // ✅ 正确：@Builder 函数不带 @BuilderParam 参数
  @Builder
  defaultContent() {
    Text('Default content')
  }
  
  build() {
    Column() {
      // ✅ 正确：SymbolGlyph.fontColor 使用数组
      SymbolGlyph($r('sys.symbol.house'))
        .fontColor([$r('app.color.primary')])  // ✅ 数组类型
        .fontSize(24)
      
      List() {
        ForEach(this.viewModel.items, (item: BeanRecord) => {
          ListItem() {
            this.customContent()  // 使用 @BuilderParam
          }
        })
      }
    }
  }
}
  `.trim()
  
  fs.writeFileSync(ui.file, code)
  console.log(`  ✅ 生成 UI: ${ui.file}`)
}
```

### Step 3.4: 生成入口文件和配置

`spec/baseline/ui-delivery-approved.json` 中每个 unit 的 `output.file` 与 `output.symbol` 是交付契约。生成器必须按该路径和符号落盘，不能用 `pages/Index.ets` 替代规格指定的根页面。模板若要求 `Index.ets` 作为 `EntryAbility` 入口，则 `Index.ets` 只负责导入并转发 `RootView`，实际根组件仍位于 `pages/RootView.ets`。在构建前检查 approved units 的 output 文件和符号均存在，路径不一致时阻断执行。

```typescript
// 生成 Index.ets
generateIndexFile()

// 生成 main_pages.json
generateMainPages()

// 更新 module.json5
updateModuleConfig()

// 更新 EntryAbility
updateEntryAbility()
```

### Step 3.5: 生成 Stage 3 Brief

```markdown
# Stage 3: 代码生成 — Brief

## 统计
- 生成功能: ${featureCount} 个
- 生成文件: ${fileCount} 个
- 代码行数: ${lineCount} 行

## 生成详情
| Feature | Model | ViewModel | Repository | UI | 状态 |
|---------|-------|-----------|-----------|----|----|
| F-001 | ✅ | ✅ | ✅ | ✅ | 完成 |
| F-002 | ✅ | ✅ | ✅ | ✅ | 完成 |
| ... | ... | ... | ... | ... | ... |

## 应用的 ArkTS 规则
- ✅ 禁止 as unknown as：使用构造函数 (${r001Count} 处)
- ✅ 禁止 as const：使用明确类型 (${r002Count} 处)
- ✅ 对象字面量：先创建实例 (${r003Count} 处)
- ✅ 类型索引：使用枚举类型 (${r004Count} 处)
- ✅ @BuilderParam：成员属性 (${r005Count} 处)

## 下一步
进入 Stage 4: 编译验证与自动修复
```

写入 `spec/execution/briefs/stage3-code-generation.md`

### Stage 3 完成标记

创建 `spec/execution/stage3-complete.txt`

---

## 5. Stage 4: 编译验证与自动修复 ✨✨✨

**⭐⭐⭐ 核心改进：自动编译验证和修复，消除手动修复时间**

### Step 4.1: 首次编译验证 🚪

**目标**: 发现所有编译错误

```bash
echo "🔨 Stage 4: 编译验证与自动修复"
echo "正在编译项目..."

# 调用 hmos_fix_build_errors skill
Skill({
  skill: "hmos_fix_build_errors",
  args: "--project-root $HOS_PATH --deveco-path $DEVECO_PATH --mode unsigned --max-iterations 20"
})
```

**hmos_fix_build_errors 执行流程**:

```
1. 环境检查
   ├─ 检查 local.properties
   ├─ 检查 DevEco Studio 路径
   └─ 检查项目结构

2. 首次编译
   ├─ 运行 hvigorw assembleHap
   ├─ 收集编译错误
   └─ 解析错误类型

3. 自动修复循环（最多 20 次）
   ├─ 分类错误
   ├─ 应用修复策略
   ├─ 重新编译
   └─ 验证修复

4. 生成报告
   ├─ 修复统计
   ├─ HAP 文件信息
   └─ 剩余问题（如有）
```

### Step 4.2: 常见错误的自动修复策略

**hmos_fix_build_errors 内置的修复策略**:

#### 修复策略 1: as unknown as 错误

```typescript
// 错误特征
// ERROR: Type assertion 'as unknown as' is not supported in ArkTS

// 自动修复
before: json.id as unknown as string
after:  String(json.id)

before: data.value as unknown as number
after:  Number(data.value)
```

#### 修复策略 2: Object Literal 错误

```typescript
// 错误特征
// ERROR: Object literal must have explicit type

// 自动修复
before: return { id: '123', name: 'test' }
after:  const obj = new MyClass()
        obj.id = '123'
        obj.name = 'test'
        return obj
```

#### 修复策略 3: as const 错误

```typescript
// 错误特征
// ERROR: 'as const' assertion is not supported

// 自动修复
before: const COLORS = ['red', 'blue'] as const
after:  const COLORS: string[] = ['red', 'blue']

before: type Color = typeof COLORS[number]
after:  type Color = 'red' | 'blue'
```

#### 修复策略 4: @BuilderParam 错误

```typescript
// 错误特征
// ERROR: @BuilderParam can only be used on member properties

// 自动修复
before: @Builder MyBuilder(@BuilderParam content: () => void) {}
after:  @BuilderParam content: () => void
        
        @Builder MyBuilder() {
          this.content()
        }
```

#### 修复策略 5: SymbolGlyph API 错误

```typescript
// 错误特征
// ERROR: Type mismatch: expected 'ResourceColor[]', found 'ResourceColor'

// 自动修复
before: .fontColor($r('app.color.primary'))
after:  .fontColor([$r('app.color.primary')])
```

### Step 4.3: 修复循环执行

```typescript
let iteration = 1
let maxIterations = 20
let remainingErrors = []

while (iteration <= maxIterations) {
  console.log(`\n🔄 修复轮次 ${iteration}/${maxIterations}`)
  
  // 1. 编译项目
  const buildResult = await runBuild()
  
  if (buildResult.success) {
    console.log(`✅ 编译成功！`)
    break
  }
  
  // 2. 解析错误
  const errors = parseBuildErrors(buildResult.output)
  console.log(`发现 ${errors.length} 个错误`)
  
  // 3. 分类错误
  const categorizedErrors = categorizeErrors(errors)
  
  // 4. 应用修复
  let fixedCount = 0
  for (const error of categorizedErrors) {
    if (await applyFix(error)) {
      fixedCount++
    }
  }
  
  console.log(`修复了 ${fixedCount} 个错误`)
  
  // 5. 检查是否还有可修复的错误
  if (fixedCount === 0) {
    console.log(`⚠️ 无法继续自动修复`)
    remainingErrors = errors
    break
  }
  
  iteration++
}
```

### Step 4.4: 生成编译报告

```markdown
# Stage 4: 编译验证与自动修复 — Brief

## 最终状态
${buildStatus === 'success' ? '✅ 编译成功' : '❌ 编译失败'}

## 统计
- 初始错误数: ${initialErrors}
- 修复轮次: ${iterations}
- 最终错误数: ${finalErrors}
- 修复成功率: ${((initialErrors - finalErrors) / initialErrors * 100).toFixed(1)}%

## 修复详情
| 轮次 | 错误数 | 修复类型 | 修复数 | 耗时 |
|------|-------|---------|-------|------|
| 1 | 47 → 35 | Object Literal | 12 | 2min |
| 2 | 35 → 28 | as unknown as | 7 | 1.5min |
| 3 | 28 → 23 | as const | 5 | 1min |
| 4 | 23 → 20 | @BuilderParam | 3 | 1min |
| 5 | 20 → 18 | SymbolGlyph API | 2 | 1min |
| ... | ... | ... | ... | ... |
| 14 | 3 → 0 | Indexed Access | 3 | 1min |

## 错误分类统计
| 错误类型 | 数量 | 修复成功 | 修复率 |
|---------|------|---------|-------|
| Object Literal | 20 | 20 | 100% |
| as unknown as | 10 | 10 | 100% |
| SymbolGlyph API | 5 | 5 | 100% |
| @BuilderParam | 3 | 3 | 100% |
| Indexed Access | 2 | 2 | 100% |
| 其他 | 7 | 7 | 100% |
| **总计** | **47** | **47** | **100%** |

## HAP 产物
${buildStatus === 'success' ? `
- 文件路径: ${hapPath}
- 文件大小: ${hapSize}
- SHA256: ${hapSha256}
` : '无（编译失败）'}

## 剩余问题
${remainingErrors.length > 0 ? `
⚠️ 以下问题需要人工处理：

${remainingErrors.map(e => `- ${e.file}:${e.line} — ${e.message}`).join('\n')}
` : '无'}

## 下一步
进入 Stage 5: 最终报告生成
```

写入 `spec/execution/briefs/stage4-build-verification.md`

### Step 4.5: 编译失败处理

**如果 20 轮后仍有错误**:

```bash
if [ ${finalErrors} -gt 0 ]; then
  echo "❌ 编译失败：${finalErrors} 个错误未修复"
  echo "详细错误信息："
  cat spec/execution/autofix-log/round-20/remaining-errors.txt
  
  echo ""
  echo "📝 建议："
  echo "1. 查看错误详情: spec/execution/autofix-log/"
  echo "2. 手动修复剩余错误"
  echo "3. 运行 'hvigorw assembleHap' 验证"
  echo "4. 考虑报告给工具开发团队"
  
  # 记录到迁移报告
  echo "## ⚠️ 编译警告" >> spec/migration-report.md
  echo "自动修复后仍有 ${finalErrors} 个错误需要人工处理。" >> spec/migration-report.md
fi
```

### Stage 4 完成标记

创建 `spec/execution/stage4-complete.txt`

---

## 6. Stage 5: 最终报告生成

### Step 5.1: 汇总执行统计

```typescript
const executionStats = {
  // Stage 统计
  stages: {
    stage0: { duration: '2min', status: 'completed' },
    stage1: { duration: '15min', status: 'completed' },
    stage2: { duration: '25min', status: 'completed' },
    stage3: { duration: '25min', status: 'completed' },
    stage4: { duration: '15min', status: 'completed' }
  },
  
  // 代码统计
  code: {
    features: totalFeatures,
    files: totalFiles,
    lines: totalLines
  },
  
  // 编译统计
  build: {
    initial_errors: initialErrors,
    final_errors: finalErrors,
    fix_iterations: iterations,
    fix_success_rate: `${((initialErrors - finalErrors) / initialErrors * 100).toFixed(1)}%`
  },
  
  // 时间统计
  time: {
    total_duration: '82min',
    estimated_duration: '120min',
    time_saved: '38min'
  }
}
```

### Step 5.2: 生成迁移报告

```markdown
# iOS → HarmonyOS 迁移执行报告

**项目**: ${projectName}
**执行时间**: ${executionTime}
**总耗时**: ${totalDuration}

---

## 📊 执行总览

### 成功指标
- ✅ 代码生成完成
- ✅ 编译验证通过
- ✅ HAP 文件生成成功

### 统计数据
| 指标 | 数值 |
|------|------|
| 功能数 | ${totalFeatures} |
| 页面数 | ${totalPages} |
| 生成文件 | ${totalFiles} |
| 代码行数 | ${totalLines} |
| 初始错误 | ${initialErrors} |
| 最终错误 | ${finalErrors} |
| 修复成功率 | ${fixSuccessRate} |

---

## 🎯 Stage 执行详情

### Stage 0: 环境准备
- 耗时: 2 分钟
- 状态: ✅ 完成
- 产物:
  - 执行目录已创建
  - 环境预热已完成
  - 执行计划已加载

### Stage 1: Spec 解析与理解
- 耗时: 15 分钟
- 状态: ✅ 完成
- 产物:
  - 源码理解文档: ${complexFeatureCount} 个
  - Spec 解析报告: spec/execution/briefs/stage1-spec-understanding.md

### Stage 2: Feature 详细设计 + HarmonyOS 知识加载
- 耗时: 25 分钟
- 状态: ✅ 完成
- 产物:
  - Feature 设计文档: ${featureCount} 个
  - ArkTS 规则: ${arktsRuleCount} 条
  - 组件模式: ${componentPatternCount} 个
  - 知识库: spec/execution/harmonyos-knowledge.json

### Stage 3: 代码生成
- 耗时: 25 分钟
- 状态: ✅ 完成
- 产物:
  - Model 文件: ${modelCount} 个
  - ViewModel 文件: ${viewModelCount} 个
  - Repository 文件: ${repositoryCount} 个
  - UI 组件: ${componentCount} 个

### Stage 4: 编译验证与自动修复
- 耗时: 15 分钟
- 状态: ✅ 完成
- 统计:
  - 初始错误: ${initialErrors}
  - 修复轮次: ${iterations}
  - 最终错误: ${finalErrors}
  - HAP 文件: ${hapPath}

---

## 🔧 修复详情

### 错误分类统计
| 错误类型 | 数量 | 修复成功 | 修复率 |
|---------|------|---------|-------|
| Object Literal | 20 | 20 | 100% |
| as unknown as | 10 | 10 | 100% |
| SymbolGlyph API | 5 | 5 | 100% |
| @BuilderParam | 3 | 3 | 100% |
| Indexed Access | 2 | 2 | 100% |
| 其他 | 7 | 7 | 100% |
| **总计** | **47** | **47** | **100%** |

### 修复轮次详情
查看完整修复日志: spec/execution/briefs/stage4-build-verification.md

---

## 📦 产物清单

### 核心文件
- 入口: entry/src/main/ets/pages/Index.ets
- 配置: entry/src/main/module.json5
- 页面列表: entry/src/main/resources/base/profile/main_pages.json

### Models
${modelFiles.map(f => `- ${f}`).join('\n')}

### ViewModels
${viewModelFiles.map(f => `- ${f}`).join('\n')}

### Repositories
${repositoryFiles.map(f => `- ${f}`).join('\n')}

### UI Components
${componentFiles.map(f => `- ${f}`).join('\n')}

### HAP 文件
- 路径: ${hapPath}
- 大小: ${hapSize}
- SHA256: ${hapSha256}

---

## ⏱️ 性能对比

### 本次执行 vs 优化前
| 指标 | 优化前 | 本次执行 | 改进 |
|------|--------|---------|------|
| 初始错误 | 47 个 | < 10 个 | ✅ 79% |
| 手动修复时间 | 60 分钟 | 0 分钟 | ✅ 100% |
| 总执行时间 | 120 分钟 | 82 分钟 | ✅ 32% |
| 成功率 | 50% | 95% | ✅ 90% |

---

## 📋 下一步

1. **运行验证**: `hvigorw assembleHap`
2. **安装测试**: 在 HarmonyOS 设备/模拟器上安装 HAP
3. **功能测试**: 验证各功能是否正常工作
4. **继续 Pipeline**: 运行 `/i2h-verify` 进行详细验证

---

## 📚 相关文档

- 执行计划: spec/baseline/plans/execution-plan.md
- Stage Briefs: spec/execution/briefs/
- 修复日志: spec/execution/autofix-log/
- HarmonyOS 知识库: spec/execution/harmonyos-knowledge.json

---

**生成时间**: ${new Date().toISOString()}
**工具版本**: i2h-execute v2.0
**执行人**: Claude Opus 5.5
```

写入 `spec/migration-report.md`

### Step 5.3: 清理临时文件

```bash
# 清理临时文件（可选）
# rm -rf spec/execution/designs/
# rm -rf spec/execution/arkts-rules.json
# rm -rf spec/execution/component-patterns.json
# rm -rf spec/execution/api-specs.json
```

### Stage 5 完成标记

在生成 Stage 5 marker 前，必须先完成执行覆盖率账本收口。Closer 应将本轮实际执行的
packet intent 写入 `spec/execution/writeback/`，然后用确定性脚本展开
`spec/.i2h/plan-coverage.json` 中对应 packet 的 `requirement_ids` 和 digest，最后运行
`apply_writeback.py` 生成 `spec/.i2h/impl-claims.json`：

```bash
INTENT=$(find spec/execution/writeback -name '*intent*.json' -type f | sort | tail -1)
if [ -z "$INTENT" ]; then
  echo "BLOCKED: execute packet intent is missing; cannot claim requirements"
  exit 1
fi
python3 .claude/skills/i2h-execute/scripts/build_writeback.py "$INTENT" \
  --project-root . \
  --out spec/execution/writeback/writeback-final.json
python3 .claude/skills/i2h-execute/scripts/apply_writeback.py \
  spec/execution/writeback/writeback-final.json --project-root .
python3 .claude/skills/i2h-execute/scripts/lint_execute_coverage.py .
```

`impl-claims.json` 缺失、claim 数量不足或 packet digest 不一致时，Stage 5 必须保持
BLOCKED，不能只写 `stage5-complete.txt`。这条门禁防止生成代码已经落盘但 366 条
requirement 没有任何可追溯实现声明的情况。

在写入 Stage 5 marker 前，针对 iOS 源码中识别到的系统能力运行确定性平台门禁：

```bash
python3 .claude/skills/i2h-execute/scripts/capability_gate.py \
  --project-root . \
  --output-json spec/execution/capability-gate.json
```

该门禁检查 F101 CAMERA/OCR、F102 LiveForm 与通知降级、F103 FormExtension 服务卡片、
F104 `ohos.ability.shortcuts` metadata 和 `shortcuts.json`。`PARTIAL` 或 `BLOCKED` 必须
保留具体 capability finding，不能写成 Stage 5 PASS。系统宿主行为仍需真机或模拟器证据，
静态 profile 通过不能替代添加、刷新和点击回路。

如果 `spec/baseline/ui-delivery-approved.json` 中包含 `source_obligations`，在写入
Stage 5 marker 前还必须运行一次确定性的 UI 事实门禁：

```bash
python3 .claude/skills/i2h-execute/scripts/ui_obligation_gate.py \
  --project-root . \
  --output-json spec/execution/ui-obligation-gate.json
```

该门禁检查固定底部主动作没有落入 `Scroll`、Form Picker 没有被 chip 替代、toolbar
search 没有退化成首屏内联输入框，以及 Chart 仍保留折线和数据点结构。失败时必须修复
产物或保留具体 finding，不能把 prompt 中已声明的 source obligation 当成已实现。

创建 `spec/execution/stage5-complete.txt` 作为 **schema-2 JSON marker**。
在 `spec/migration-report.md` 和
`spec/execution/ui-state-ownership.json` 最终写入后，按照
[i2h-plan 的 marker-contract.md](../i2h-plan/references/marker-contract.md)
调用 `marker_contract.write_marker()`，传入 `stage="i2h-execute"`、当前
`target_input_sha256` 和上述报告/receipt 的实际路径。必须保留
`mode="static-only"` 及报告中的 `DEFERRED` 证据（如果没有真实构建/设备），
不要创建纯文本完成标记，也不要把 marker 自身作为 artifact。Stage 0–4
的内部记录可以继续使用各自的执行日志；`/i2h-run` 只消费 Stage 5 的
canonical marker 加 migration report。

---

## 7. 最终输出

### 7.1: 控制台输出

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  🎉 i2h-execute 执行完成
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 执行统计:
  - 总耗时: 82 分钟
  - 生成文件: 65 个
  - 代码行数: 2,500 行
  - 初始错误: 47 个
  - 最终错误: 0 个
  - 修复成功率: 100%

✅ 编译状态: 成功
📦 HAP 文件: build/default/outputs/default/entry-default-unsigned.hap

📋 详细报告: spec/migration-report.md

🚀 下一步:
  1. 查看迁移报告: cat spec/migration-report.md
  2. 验证编译: hvigorw assembleHap
  3. 安装测试: 在设备上安装 HAP
  4. 继续 Pipeline: /i2h-verify

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### 7.2: 返回数据

```json
{
  "status": "success",
  "execution_time": "82min",
  "statistics": {
    "features": 4,
    "files": 65,
    "lines": 2500,
    "initial_errors": 47,
    "final_errors": 0,
    "fix_success_rate": "100%"
  },
  "output": {
    "report": "spec/migration-report.md",
    "hap": "build/default/outputs/default/entry-default-unsigned.hap",
    "briefs": "spec/execution/briefs/"
  },
  "next_steps": [
    "查看迁移报告",
    "验证编译",
    "安装测试",
    "运行 /i2h-verify"
  ]
}
```

---

## 8. 错误处理

### 8.1: Stage 失败处理

```typescript
try {
  await executeStage(stageNumber)
} catch (error) {
  console.error(`❌ Stage ${stageNumber} 执行失败: ${error.message}`)
  
  // 记录错误
  fs.writeFileSync(
    `spec/execution/stage${stageNumber}-error.txt`,
    `${error.message}\n${error.stack}`
  )
  
  // 回滚（如果需要）
  if (stageNumber >= 3) {
    console.log(`🔄 回滚 Stage ${stageNumber} 的修改...`)
    await rollbackStage(stageNumber)
  }
  
  // 生成错误报告
  generateErrorReport(stageNumber, error)
  
  throw error
}
```

### 8.2: 编译失败处理

参见 Stage 4 Step 4.5

### 8.3: 技能调用失败处理

```typescript
try {
  await Skill({ skill: "hmos_fix_build_errors", args: "..." })
} catch (error) {
  console.error(`❌ Skill 调用失败: ${error.message}`)
  
  // 降级策略：手动编译
  console.log(`⚠️ 降级为手动编译验证`)
  
  const buildResult = await execSync('hvigorw assembleHap')
  
  if (buildResult.status !== 0) {
    console.error(`❌ 编译失败，需要人工介入`)
    generateManualFixGuide(buildResult.stderr)
  }
}
```

---

## 9. 部分执行支持

### 9.1: 触发方式

```bash
# 完整执行
/i2h-execute

# 只执行特定 Stage
/i2h-execute --stage 3

# 从特定 Stage 开始
/i2h-execute --from-stage 2

# 重新执行失败的 Stage
/i2h-execute --retry-failed
```

### 9.2: 断点续跑

```typescript
// 检查已完成的 Stage
const completedStages = []
for (let i = 0; i <= 5; i++) {
  if (fs.existsSync(`spec/execution/stage${i}-complete.txt`)) {
    completedStages.push(i)
  }
}

console.log(`已完成的 Stage: ${completedStages.join(', ')}`)

// 从下一个 Stage 开始
const nextStage = Math.max(...completedStages, -1) + 1
console.log(`从 Stage ${nextStage} 继续执行`)
```

---

## 10. 性能优化

### 10.1: 并行执行

```typescript
// Feature 生成可以并行
await Promise.all(
  features.map(feature => generateFeature(feature))
)

// 文件生成可以并行
await Promise.all([
  generateModels(),
  generateViewModels(),
  generateRepositories(),
  generateUI()
])
```

### 10.2: 增量执行

```typescript
// 检查文件是否已存在
if (fs.existsSync(targetFile)) {
  const lastModified = fs.statSync(targetFile).mtime
  const sourceModified = fs.statSync(sourceFile).mtime
  
  if (lastModified > sourceModified) {
    console.log(`⏭️ 跳过 ${targetFile}（已是最新）`)
    return
  }
}

// 生成文件
await generateFile(sourceFile, targetFile)
```

---

## 11. 调试支持

### 11.1: 详细日志

```bash
# 启用详细日志
export I2H_DEBUG=true
/i2h-execute

# 日志输出位置
tail -f spec/execution/i2h-execute.log
```

### 11.2: 中间产物保留

```bash
# 保留所有中间产物
export I2H_KEEP_TEMP=true
/i2h-execute

# 中间产物位置
ls -la spec/execution/designs/
ls -la spec/execution/autofix-log/
```

---

## 12. 与 Android 原版对齐

### 12.1: 架构对齐

| 维度 | Android 原版 | iOS 版本 | 对齐度 |
|------|-------------|---------|-------|
| Stage 数量 | 4 个 | 5 个 | 125% |
| 编译门 | 3 道 | 1 道 | 33% → 100%（v2.0） |
| 自动修复 | ✅ 有 | ❌ 无 → ✅ 有（v2.0） | 100% |
| 知识加载 | ❌ 无 | ✅ 有（v2.0） | 优于原版 |

### 12.2: 产物对齐

| 产物 | Android 原版 | iOS 版本 |
|------|-------------|---------|
| 迁移报告 | ✅ | ✅ |
| Stage Briefs | ✅ | ✅ |
| HAP 文件 | ✅ | ✅ |
| 修复日志 | ✅ | ✅ |
| 知识库 | ❌ | ✅ (新增) |

---

## 13. 质量保证

### 13.1: 自动化检查

```bash
# Stage 完成后自动检查
check_stage_output() {
  local stage=$1
  
  # 检查 brief 文件
  [ -f "spec/execution/briefs/stage${stage}-*.md" ] || return 1
  
  # 检查完成标记
  [ -f "spec/execution/stage${stage}-complete.txt" ] || return 1
  
  # 检查产物
  case $stage in
    3) [ -d "entry/src/main/ets/" ] || return 1 ;;
    4) [ -f "build/default/outputs/default/*.hap" ] || return 1 ;;
  esac
  
  return 0
}
```

### 13.2: 质量门禁

```bash
# Stage 4 必须编译成功才能继续
if [ ${finalErrors} -gt 0 ]; then
  echo "❌ 编译失败，阻断 Pipeline"
  exit 1
fi

# HAP 文件必须存在
if [ ! -f "${hapPath}" ]; then
  echo "❌ HAP 文件不存在，阻断 Pipeline"
  exit 1
fi
```

---

## 14. 成功标准

### 14.1: 必须达成

- ✅ 所有 Stage 执行完成
- ✅ 代码生成成功（所有 feature）
- ✅ 编译验证通过（0 个错误）
- ✅ HAP 文件生成成功
- ✅ 迁移报告生成完整

### 14.2: 强烈建议

- ✅ 初始错误 < 10 个
- ✅ 修复成功率 > 90%
- ✅ 总耗时 < 90 分钟
- ✅ HarmonyOS 知识库已加载

### 14.3: 可选目标

- ⭐ 初始错误 < 5 个
- ⭐ 修复成功率 = 100%
- ⭐ 总耗时 < 80 分钟
- ⭐ 所有代码符合 ArkTS 规范

---

## 15. 常见问题

### Q1: 为什么需要 Stage 4 编译验证？

**A**: 基于真实项目（Cuike03）发现的问题：
- 原版 i2h-execute 生成代码后直接声称完成
- 实际有 47 个编译错误
- 用户需要手动修复 60 分钟
- 添加 Stage 4 可以自动修复，节省时间

### Q2: 为什么需要加载 HarmonyOS 知识？

**A**: 基于错误分析：
- 43% 的错误是因为不知道 ArkTS 不支持对象字面量
- 21% 的错误是因为使用了 `as unknown as`
- 11% 的错误是因为不了解 HarmonyOS API 规范
- 加载知识可以从源头避免生成错误代码

### Q3: 自动修复的成功率如何？

**A**: 基于 Cuike03 项目：
- 初始错误: 47 个
- 经过 14 轮修复：全部修复
- 预期成功率: 90-95%
- 常见错误（Object Literal、as unknown as）有确定性修复策略

### Q4: 如果自动修复失败怎么办？

**A**: 
1. 查看详细错误日志: `spec/execution/autofix-log/`
2. 查看修复报告: `spec/execution/briefs/stage4-build-verification.md`
3. 手动修复剩余错误
4. 反馈给工具开发团队

### Q5: 与 Android 原版相比有什么改进？

**A**:
1. ✅ 新增 Stage 2 知识加载（Android 原版没有）
2. ✅ 新增 Stage 4 编译验证（对齐 Android 的 3 道编译门）
3. ✅ 集成自动修复循环（最多 20 次迭代）
4. ✅ 生成详细的修复报告

---

## 收尾：上报阶段用量

```bash
# 标记 i2h-execute 阶段完成
.migbot/bin/i2h mark-stage i2h-execute
```

---

## 可选资源增量协议

`scripts/resource_delta.py` 提供 task-owned OpenHarmony 资源增量的初始化、提交和原子合并。它通过 preimage hash 和锁拒绝并发冲突，默认不替换 `sweep_resources.py`，只有明确声明资源 scope 的任务才可使用。
