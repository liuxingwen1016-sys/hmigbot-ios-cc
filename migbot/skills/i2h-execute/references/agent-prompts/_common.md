# Agent 派发 Prompt — 公共规则（所有派发点必读）

> 本文件是 `agent-prompts/` 下各单段 prompt 的**公共前置规则**。
> 派发任一 worker 时，**先 Read 本文件 + 对应单段文件**两个即构成完整派发规范。


## §0 执行纪律

### 0.1 单写者原则

**规则**: 每个文件在同一时刻只能有一个 agent 写入。

**实施**:
- Batch/Group closer 返回 `writeback manifest`
- 主线程调用 `scripts/apply_writeback.py` 统一落盘
- **禁止** worker 直接写入已有文件

**例外**: 新创建的文件可以直接写入

### 0.2 资源直写原则

**规则**: 资源文件允许直接写入（幂等操作）

**允许直写**:
- `entry/src/main/resources/**/*` (图片、字符串、配置)
- 资源文件是幂等的，多次写入结果相同

**禁止直写**:
- `.ets` 代码文件
- `module.json5` 配置文件
- `main_pages.json` 页面配置

### 0.3 占位符规则

#### 占位符格式

```typescript
// PLACEHOLDER: <kind> | <reason> | <context>
throw new Error('PLACEHOLDER: <kind>');
```

#### 7 种 kind

| Kind | 说明 | 何时使用 |
|------|------|---------|
| **TBD** | To Be Determined | 设计未定，需要后续决策 |
| **STUB** | Stub | 接口桩，等待实现 |
| **DEFER** | Deferred | 延迟到后续 Stage |
| **SLICE-N** | Slice N | 等待 Slice N 实现 |
| **UPSTREAM** | Upstream | 等待上游 Base 层实现 |
| **COMPLEX** | Complex | 复杂逻辑，需要专门处理 |
| **UNKNOWN** | Unknown | 未知情况，需要调查 |

#### 占位符示例

```typescript
// ❌ 错误：没有说明
throw new Error('Not implemented');

// ✅ 正确：完整说明
// PLACEHOLDER: SLICE-3 | 搜索功能 | 等待 Slice 3 实现搜索 API 调用
throw new Error('PLACEHOLDER: SLICE-3');
```

#### 占位符登记

**所有占位符必须登记**到 `spec/execution/placeholder-registry.json`:

```json
{
  "version": "2.0",
  "placeholders": [
    {
      "id": "PH-001",
      "kind": "SLICE-3",
      "file": "entry/src/main/ets/viewmodels/SearchViewModel.ets",
      "line": 45,
      "reason": "搜索功能",
      "context": "等待 Slice 3 实现搜索 API 调用",
      "owner_stage": "execute",
      "created_at": "2024-11-03T10:30:00Z"
    }
  ]
}
```


## §1 占位符填充纪律

### 1.1 占位符回填时机

| Stage | 回填范围 |
|-------|---------|
| **Stage 2 Base** | 回填 kind=UPSTREAM 的占位符 |
| **Stage 3 Slice N** | 回填 kind=SLICE-N 的占位符 |
| **FV-1** | 回填剩余的 TBD/DEFER 占位符 |

### 1.2 回填方式

**通过 writeback manifest**:

```json
{
  "fills": [
    {
      "placeholder_id": "PH-001",
      "file": "entry/src/main/ets/viewmodels/SearchViewModel.ets",
      "line_range": [45, 48],
      "new_content": "return await this.searchService.search(keyword);"
    }
  ]
}
```

**主线程应用**:
```bash
python3 scripts/apply_writeback.py <manifest> --project-root .
```


## §2 Brief 产出规则

### 2.1 Brief 必须字段

每个 worker 返回的 brief 必须包含：

```markdown
# Brief: <任务名称>

## 任务信息
- Task ID: <task_id>
- Stage: <stage_number>
- Worker: <worker_type>
- Status: PASS / FAIL / BLOCKED

## 执行统计
- 开始时间: <timestamp>
- 结束时间: <timestamp>
- 耗时: <duration>

## 产出文件
- <file_path_1> (新建 / 修改)
- <file_path_2> (新建 / 修改)

## 占位符
- 新增: <count> 个
- 回填: <count> 个
- 详见: spec/execution/placeholder-registry.json

## 依赖
- 依赖的 Base: <base_ids>
- 依赖的 Slice: <slice_ids>

## 问题和风险
- <问题描述 1>
- <问题描述 2>

## 下一步
- <下一步行动>
```

### 2.2 Brief 命名规范

```
spec/execution/briefs/
├── stage1-batch-001-brief.md
├── stage2-base-001-brief.md
├── stage3-slice-001-brief.md
└── stage4-fv-brief.md
```


## §3 资源处理

### 3.1 资源引用规范

**iOS 资源** → **HarmonyOS 资源**:

| iOS 资源 | HarmonyOS 资源 |
|---------|---------------|
| `UIImage(named: "icon")` | `$r('app.media.icon')` |
| `UIColor(named: "primary")` | `$r('app.color.primary')` |
| `NSLocalizedString("key")` | `$r('app.string.key')` |

### 3.2 资源缺失处理

**发现资源缺失时**:

1. **记录到 brief**:
```markdown
## 资源缺失
- app.media.icon_search (iOS: search_icon.png)
- app.color.text_secondary (iOS: textSecondary)
```

2. **调用资源 sweep**:
```bash
python3 scripts/sweep_resources.py \
  --project-root . \
  --ios-root <ios_path> \
  --missing-list <list_file>
```

3. **资源 sweep 自动转换**:
- 读取 iOS 资源
- 转换为 HarmonyOS 格式
- 写入 `entry/src/main/resources/`


## §4 编译与验证

### 4.1 编译触发时机

| 阶段 | 编译门 | 触发条件 |
|------|-------|---------|
| **Stage 2 末尾** | Base-7 | Base 层全部完成 |
| **Stage 3 末尾** | Stage 3 集中门 | 所有 Group 完成 |
| **FV-2** | 终态全量编译 | FV-1 收尾完成 |

### 4.2 编译命令

**不在 worker 内部编译**，由主线程统一调用：

```bash
# 调用 hmos-builder skill
Skill({
  skill: "hmos-builder",
  args: "--caller i2h-execute --stage-hint <hint> --round 1"
})
```

### 4.3 结构审计

**调用 arkts-structural-closure**:

```bash
# Stage 骨架审计
Skill({
  skill: "arkts-structural-closure",
  args: "mode=stage target=<stage_number>"
})

# Group 结构验证
Skill({
  skill: "arkts-structural-closure",
  args: "mode=group target=<group_id>"
})
```


## §5 错误处理

### 5.1 任务失败处理

**任务失败时**:

1. **记录到 brief**:
```markdown
## 任务失败
- Status: FAIL
- 错误类型: <error_type>
- 错误信息: <error_message>
- 失败文件: <file_path>
- 失败位置: <line_number>
```

2. **返回 partial writeback**:
- 已完成的部分写入 writeback manifest
- 未完成的部分标记为 BLOCKED

3. **主线程决策**:
- 重试 (max 3 次)
- 降级 (标记为 PLACEHOLDER)
- 阻断 (报告用户)

### 5.2 依赖缺失处理

**发现依赖缺失时**:

```markdown
## 依赖缺失
- Base-3: NetworkService (BLOCKED)
- Base-5: PreferencesManager (BLOCKED)

## 行动
- 标记当前任务为 BLOCKED
- 等待依赖完成后重试
```


## §6 iOS 特定规则

### 6.1 iOS 组件映射

| iOS 组件 | HarmonyOS 组件 |
|---------|---------------|
| `UIViewController` | `@Component struct XxxPage` |
| `UIView` | `@Component struct XxxView` |
| `UITableView` | `List` + `ListItem` |
| `UICollectionView` | `Grid` + `GridItem` |
| `UILabel` | `Text` |
| `UIButton` | `Button` |
| `UITextField` | `TextInput` |
| `UIImageView` | `Image` |

### 6.2 生命周期映射

| iOS 生命周期 | HarmonyOS 生命周期 |
|------------|-------------------|
| `viewDidLoad` | `aboutToAppear` |
| `viewWillAppear` | `onPageShow` |
| `viewDidAppear` | `onPageShow`（延迟） |
| `viewWillDisappear` | `onPageHide` |
| `viewDidDisappear` | `onPageHide`（延迟） |

### 6.3 状态管理映射

| iOS 模式 | HarmonyOS 模式 |
|---------|---------------|
| `@State` / `@Published` | `@Trace` (ObservedV2) |
| `@Binding` | `@Param` |
| `@ObservedObject` | `@ObservedV2 class` |
| `@EnvironmentObject` | `@Provider` + `@Consumer` |


## §7 ArkTS 严格模式规则

### 7.1 禁止的语法

```typescript
// ❌ 禁止: as unknown as
const value = json.id as unknown as string;

// ✅ 正确: 使用构造函数
const value = String(json.id);

// ❌ 禁止: as const
const COLORS = ['red', 'blue'] as const;

// ✅ 正确: 明确类型
const COLORS: string[] = ['red', 'blue'];

// ❌ 禁止: 对象字面量（无明确类型）
return { id: '123', name: 'test' };

// ✅ 正确: 先创建实例
const obj = new MyClass();
obj.id = '123';
obj.name = 'test';
return obj;

// ❌ 禁止: 类型索引访问
type Color = typeof COLORS[number];

// ✅ 正确: 枚举类型
type Color = 'red' | 'blue';

// ❌ 禁止: @BuilderParam 在方法参数
@Builder
MyBuilder(@BuilderParam content: () => void) {}

// ✅ 正确: @BuilderParam 在成员属性
@BuilderParam content: () => void;

@Builder
MyBuilder() {
  this.content();
}
```

### 7.2 常见 API 修正

```typescript
// ❌ 错误: SymbolGlyph.fontColor 需要数组
SymbolGlyph($r('sys.symbol.house'))
  .fontColor($r('app.color.primary'))

// ✅ 正确: 使用数组
SymbolGlyph($r('sys.symbol.house'))
  .fontColor([$r('app.color.primary')])
```


## §8 Forward Reference

### 8.1 前向引用规则

**允许前向引用的情况**:

```typescript
// ✅ 允许: 引用后续 Slice 的接口
interface SearchService {
  search(keyword: string): Promise<SearchResult>;
}

// PLACEHOLDER: SLICE-3 | SearchService 实现
class SearchServiceStub implements SearchService {
  async search(keyword: string): Promise<SearchResult> {
    throw new Error('PLACEHOLDER: SLICE-3');
  }
}
```

### 8.2 接口契约

**定义接口契约**:

```typescript
// entry/src/main/ets/interfaces/ISearchService.ets
export interface ISearchService {
  search(keyword: string): Promise<SearchResult>;
}

// 在 Base 层定义接口
// 在 Slice 3 实现接口
```


## §9 执行检查清单

### 9.1 Worker 完成前检查

- [ ] 所有新文件已创建
- [ ] 所有占位符已登记到 `placeholder-registry.json`
- [ ] Brief 已生成（包含所有必须字段）
- [ ] Writeback manifest 已生成（如有修改）
- [ ] 资源引用已检查（无缺失或已记录）
- [ ] 没有直接写入已有代码文件
- [ ] 遵循 ArkTS 严格模式规则
- [ ] 错误处理已完整

### 9.2 Closer 完成前检查

- [ ] 所有 worker 产出已整合
- [ ] 跨文件接线已完成
- [ ] 资源 sweep 已执行
- [ ] 占位符回填已处理
- [ ] Writeback manifest 已生成
- [ ] Brief 已生成
- [ ] 结构审计已通过（group closer）


## §10 HarmonyOS 知识应用

### 10.1 读取知识库

**在 Stage 2 末尾加载**:

```bash
# 主线程加载知识库
Skill({ skill: "arkts-knowledge-verifier", args: "mode=get-rules" })
Skill({ skill: "arkts-component-builder", args: "mode=get-patterns" })

# 生成: spec/execution/harmonyos-knowledge.json
```

### 10.2 应用知识库

**Worker 内部应用**:

```typescript
// 读取知识库
const knowledge = JSON.parse(
  fs.readFileSync('spec/execution/harmonyos-knowledge.json', 'utf-8')
);

// 应用 ArkTS 规则
const rules = knowledge.arkts_rules.rules;

// 检查是否违反规则
for (const rule of rules) {
  if (code.includes(rule.wrong)) {
    // 替换为正确写法
    code = code.replace(rule.wrong, rule.correct);
  }
}
```


## §11 总结

**核心原则**:

1. ✅ **单写者**: 通过 writeback manifest 统一落盘
2. ✅ **占位规则**: 7 种 kind，必须登记
3. ✅ **资源直写**: 资源文件允许直接写入
4. ✅ **Brief 产出**: 每个 worker 必须产出 brief
5. ✅ **错误处理**: 失败时返回 partial writeback
6. ✅ **ArkTS 规范**: 严格遵循 ArkTS 规则
7. ✅ **知识应用**: 使用 HarmonyOS 知识库

**执行流程**:

```
1. 读取 _common.md + 对应派发 prompt
2. 理解任务上下文
3. 执行任务（遵循所有规则）
4. 产出 brief
5. 产出 writeback manifest（如有修改）
6. 登记占位符
7. 返回主线程
```


