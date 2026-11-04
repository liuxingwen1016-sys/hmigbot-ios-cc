# Brief 和 Writeback Manifest Schemas

**用途**: 定义所有 brief 和 writeback manifest 的标准格式  
**加载时机**: 派发 worker 前 / 应用 writeback 前

---

## §1 Brief Schemas

### 1.1 通用 Brief 格式

所有 brief 必须包含以下字段：

```markdown
# Brief: <任务名称>

## 任务信息
- Task ID: <task_id>
- Stage: <stage_number>
- Worker: <worker_type>
- Status: PASS | FAIL | BLOCKED

## 执行统计
- 开始时间: <ISO8601_timestamp>
- 结束时间: <ISO8601_timestamp>
- 耗时: <duration_in_minutes> 分钟

## 产出文件
- <file_path_1> (新建 | 修改, <line_count> 行)
- <file_path_2> (新建 | 修改, <line_count> 行)

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

### 1.2 Stage 1 Batch Brief

```markdown
# Brief: Batch <batch_id> 收尾

## 任务信息
- Batch ID: <batch_id>
- Pages: <page_list>
- Worker: batch-closer
- Status: PASS | FAIL

## 执行统计
- 开始时间: <timestamp>
- 结束时间: <timestamp>
- 耗时: <duration>

## Converter 汇总
- <PageName1>: PASS (<line_count> 行代码)
- <PageName2>: PASS (<line_count> 行代码)
- 总计: <count> 个页面，<total_lines> 行代码

## 资源 Sweep
- 转换图片: <count> 个
- 转换颜色: <count> 个
- 转换字符串: <count> 个
- 失败: <count> 个

## 布局复核
- <PageName1>: PASS | WARN | FAIL
- <PageName2>: PASS | WARN | FAIL

## 入口装配（首个 Batch）
- ✅ main_pages.json 已创建
- ✅ Index.ets Navigation 外壳已创建
- ✅ EntryAbility 已更新

## Writeback Manifest
- 文件: <manifest_path>
- 操作数: <count> 个 (创建 <n>, 修改 <n>, 回填 <n>)

## 占位符
- 回填: <count> 个
- 剩余: <count> 个

## 依赖验证
- Base-1 (Models): ✅ 已就绪 | ⏸️ 待实现
- Base-3 (Network): ✅ 已就绪 | ⏸️ 待实现

## 问题和风险
- <问题列表>

## 下一步
- 主线程应用 writeback manifest
- 进入下一个 Batch 或 Stage 2
```

### 1.3 Stage 2 Base Brief

```markdown
# Brief: Base-<n> <base_name>

## 任务信息
- Task ID: base-<n>
- Base: Base-<n> (<base_name>)
- Worker: base-worker
- Status: PASS | FAIL

## 执行统计
- 开始时间: <timestamp>
- 结束时间: <timestamp>
- 耗时: <duration>

## 产出文件
- <file_path_1> (新建, <line_count> 行)
- <file_path_2> (新建, <line_count> 行)

## iOS → HarmonyOS 映射
- <iOS_concept> → <HarmonyOS_concept>

## 占位符
- 新增: <count> 个（通常为 0，Base 层无占位符）

## 依赖
- 无（Base 层无依赖）

## 问题和风险
- <问题列表>

## 下一步
- 等待其他 Base 完成
- 等待 Base-7 编译门
```

### 1.4 Stage 3 Group Brief

```markdown
# Brief: Group-<n> 收尾

## 任务信息
- Group ID: group-<n>
- Slices: <slice_list>
- Worker: group-closer
- Status: PASS | FAIL

## 执行统计
- 开始时间: <timestamp>
- 结束时间: <timestamp>
- 耗时: <duration>

## Slice 汇总
- Slice-<n>: PASS (<line_count> 行代码)
- 总计: <count> 个 Slice，<total_lines> 行代码

## 跨文件接线
- <ViewModel1> ←→ <Service1>: ✅ 已连接 | ❌ 失败

## 资源 Sweep
- 转换: <count> 个
- 失败: <count> 个

## 结构 Fix-Forward
- 初始 FAIL: <count> 个
- 轮次 1: <n1> → <n2>
- 轮次 2: <n2> → <n3>
- 最终状态: CONVERGED | STALLED | REGRESSED | EXHAUSTED

## Writeback Manifest
- 文件: <manifest_path>
- 操作数: <count> 个

## 占位符
- 回填: <count> 个
- 剩余: <count> 个

## 问题和风险
- <问题列表>

## 下一步
- 主线程应用 writeback
- 进入下一个 Group
```

### 1.5 FV Final Brief

```markdown
# Brief: FV-1 最终收尾

## 任务信息
- Worker: final-closer
- Status: PASS | FAIL

## 执行统计
- 开始时间: <timestamp>
- 结束时间: <timestamp>
- 耗时: <duration>

## 结构收敛
- 初始 FAIL: <count> 个
- 最终 FAIL: <count> 个
- 迭代次数: <count>
- 最终状态: CONVERGED | STALLED

## Writeback Manifest
- 文件: spec/execution/writeback/final-writeback.json
- 操作数: <count> 个

## 占位符
- 回填: <count> 个
- 剩余: <count> 个（标记为 DEFER）

## 问题和风险
- <问题列表>

## 下一步
- 主线程应用 writeback
- 执行 FV-2 终态全量编译
```

---

## §2 Writeback Manifest Schema

### 2.1 基本结构

```json
{
  "version": "2.0",
  "batch_id": "batch-001",
  "group_id": "group-001",
  "timestamp": "2024-11-03T10:30:00Z",
  "operations": [
    {
      "type": "create | modify | delete | fill_placeholder",
      "file": "<file_path>",
      "content": "<full_content>",
      "changes": [],
      "placeholder_id": "<ph_id>",
      "line_range": [<start>, <end>],
      "new_content": "<content>"
    }
  ],
  "resources": {
    "images": ["<resource_name>"],
    "colors": ["<color_name>"],
    "strings": ["<string_key>"]
  },
  "stats": {
    "total_operations": 10,
    "creates": 5,
    "modifies": 3,
    "deletes": 0,
    "fills": 2
  }
}
```

### 2.2 操作类型

#### 2.2.1 create（创建新文件）

```json
{
  "type": "create",
  "file": "entry/src/main/ets/pages/NewPage.ets",
  "content": "import { ... }\n\n@Entry\n@ComponentV2\nexport struct NewPage {\n  ...\n}"
}
```

#### 2.2.2 modify（修改已有文件）

```json
{
  "type": "modify",
  "file": "entry/src/main/ets/pages/HomePage.ets",
  "changes": [
    {
      "line_range": [45, 48],
      "old_content": "  .width(78)\n  .height(78)",
      "new_content": "  .width(80)\n  .height(80)  // 布局复核修正"
    },
    {
      "line_range": [120, 125],
      "old_content": "// TODO: implement search",
      "new_content": "const results = await this.viewModel.search(keyword);"
    }
  ]
}
```

#### 2.2.3 delete（删除文件，罕见）

```json
{
  "type": "delete",
  "file": "entry/src/main/ets/temp/TempFile.ets",
  "reason": "临时文件，不再需要"
}
```

#### 2.2.4 fill_placeholder（回填占位符）

```json
{
  "type": "fill_placeholder",
  "placeholder_id": "PH-005",
  "file": "entry/src/main/ets/viewmodels/HomeViewModel.ets",
  "line_range": [32, 35],
  "old_content": "// PLACEHOLDER: SLICE-2 | 数据加载\nthrow new Error('PLACEHOLDER: SLICE-2');",
  "new_content": "this.isLoading = true;\ntry {\n  const data = await this.networkService.get('/api/beans');\n  this.items = data.map(json => BeanRecord.fromJSON(json));\n} finally {\n  this.isLoading = false;\n}"
}
```

### 2.3 资源记录

```json
{
  "resources": {
    "images": [
      "icon_home.png",
      "icon_search.png",
      "background.png"
    ],
    "colors": [
      "text_primary",
      "text_secondary",
      "background"
    ],
    "strings": [
      "home_title",
      "search_placeholder",
      "error_network"
    ]
  }
}
```

---

## §3 Placeholder Registry Schema

### 3.1 结构

```json
{
  "version": "2.0",
  "placeholders": [
    {
      "id": "PH-001",
      "kind": "TBD | STUB | DEFER | SLICE-N | UPSTREAM | COMPLEX | UNKNOWN",
      "file": "<file_path>",
      "line": <line_number>,
      "reason": "<short_reason>",
      "context": "<detailed_context>",
      "owner_stage": "execute",
      "created_at": "<ISO8601_timestamp>",
      "filled_at": "<ISO8601_timestamp>",
      "status": "OPEN | FILLED | DEFERRED"
    }
  ],
  "stats": {
    "total": 10,
    "open": 5,
    "filled": 3,
    "deferred": 2
  },
  "last_updated": "<ISO8601_timestamp>"
}
```

### 3.2 占位符生命周期

```
创建（Converter/Worker）
  ↓ status: OPEN
等待依赖完成
  ↓
回填（Closer）
  ↓ status: FILLED
移除占位符
```

**DEFERRED 状态**:
- FV-1 后仍未回填
- 标记为 DEFERRED
- 记录到迁移报告

---

## §4 编译报告 Schema

### 4.1 Base-7 编译报告

```markdown
# Base-7 编译报告

## 编译信息
- Stage Hint: stage-2-base-7
- 轮次: 14
- 状态: PASS | FAIL

## 统计
- 初始错误: 47 个
- 最终错误: 0 个
- 修复成功率: 100%
- 总耗时: 28 分钟

## 修复详情
| 轮次 | 错误数 | 修复类型 | 修复数 | 耗时 |
|------|-------|---------|-------|------|
| 1 | 47 → 35 | Object Literal | 12 | 2min |
| 2 | 35 → 28 | as unknown as | 7 | 1.5min |
| ... | ... | ... | ... | ... |
| 14 | 3 → 0 | SymbolGlyph API | 3 | 1min |

## 错误分类统计
| 错误类型 | 数量 | 修复成功 | 修复率 |
|---------|------|---------|-------|
| Object Literal | 20 | 20 | 100% |
| as unknown as | 10 | 10 | 100% |
| SymbolGlyph API | 5 | 5 | 100% |
| @BuilderParam | 3 | 3 | 100% |
| Indexed Access | 2 | 2 | 100% |
| 其他 | 7 | 7 | 100% |

## HAP 产物
- 文件路径: build/default/outputs/default/entry-default-unsigned.hap
- 文件大小: 2.5 MB
- SHA256: abc123...

## 剩余问题
无

## 日志文件
spec/execution/build-logs/base-7-round-{01-14}.log
```

### 4.2 降级报告

```markdown
# 构建降级报告

## 降级信息
- 触发时间: <timestamp>
- 触发原因: Daemon 僵死
- 失败轮次: 2 次

## 降级建议
⚠️ 构建环境已不稳定，无法继续 CLI 构建验证。
请在 DevEco Studio IDE 中执行 Build → Build HAP(s) 验证项目完整性。

## 日志
spec/execution/build-logs/degraded.log
```

---

## §5 验证规则

### 5.1 Brief 验证

**必须字段检查**:

```python
def validate_brief(brief_path: str) -> bool:
    content = read_file(brief_path)
    
    required_sections = [
        "# Brief:",
        "## 任务信息",
        "## 执行统计",
        "## 产出文件",
        "## 占位符",
        "## 问题和风险",
        "## 下一步"
    ]
    
    for section in required_sections:
        if section not in content:
            print(f"❌ 缺少必须章节: {section}")
            return False
    
    return True
```

### 5.2 Writeback Manifest 验证

**格式检查**:

```python
def validate_writeback(manifest_path: str) -> bool:
    manifest = json.load(open(manifest_path))
    
    # 检查版本
    if manifest.get('version') != '2.0':
        return False
    
    # 检查操作
    for op in manifest.get('operations', []):
        if op['type'] not in ['create', 'modify', 'delete', 'fill_placeholder']:
            return False
        
        if 'file' not in op:
            return False
    
    return True
```

---

## §6 使用示例

### 6.1 生成 Brief

```typescript
// Worker 内部
const brief = `
# Brief: HomePage 转换

## 任务信息
- Task ID: page-001
- Stage: 1
- Worker: converter
- Status: PASS

## 执行统计
- 开始时间: ${startTime}
- 结束时间: ${endTime}
- 耗时: ${duration} 分钟

...
`;

fs.writeFileSync('spec/execution/briefs/stage1-page-001-brief.md', brief);
```

### 6.2 生成 Writeback Manifest

```typescript
// Closer 内部
const manifest = {
  version: '2.0',
  batch_id: 'batch-001',
  timestamp: new Date().toISOString(),
  operations: [
    {
      type: 'create',
      file: 'entry/src/main/ets/pages/Index.ets',
      content: indexContent
    },
    {
      type: 'modify',
      file: 'entry/src/main/ets/pages/HomePage.ets',
      changes: [
        {
          line_range: [45, 48],
          old_content: '...',
          new_content: '...'
        }
      ]
    }
  ],
  stats: {
    total_operations: 2,
    creates: 1,
    modifies: 1
  }
};

fs.writeFileSync(
  'spec/execution/writeback/batch-001-writeback.json',
  JSON.stringify(manifest, null, 2)
);
```

### 6.3 应用 Writeback

```bash
# 主线程调用脚本
python3 scripts/apply_writeback.py \
  spec/execution/writeback/batch-001-writeback.json \
  --project-root .
```

---

**版本**: 1.0  
**更新时间**: 2024-11-03  
**适用**: i2h-execute 所有 brief 和 writeback
