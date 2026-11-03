<!-- when: 开始生成 spec 产物时加载 -->
<!-- topics: 目录结构、文件命名规则、产物清单 -->

# i2h-spec 产物结构与命名规范

## 1. 完整目录结构

```
spec/
├── .i2h/                           # 中间产物和运行数据
│   ├── project-skeleton.json      # Phase A: 项目骨架
│   ├── info-plist-analysis.json   # Phase A: Info.plist 分析
│   ├── resources-inventory.json   # Phase A: 资源清单
│   ├── phase-a-report.md          # Phase A: 总结报告
│   ├── open-findings.json         # Findings 追踪
│   └── spec-run/                  # 运行时数据
│       └── gate-ledger.json       # 门禁记录
│
├── baseline/                       # 最终产物（核心输出）
│   ├── ui-manifest.md             # Phase B: UI 总清单
│   ├── feature-index.md           # Phase C: 功能索引
│   ├── spec-complete.txt          # 完成标记
│   │
│   ├── ui/                        # Phase B: 分页 UI Spec
│   │   ├── page_0001_HomeView.md
│   │   ├── page_0002_SettingsView.md
│   │   └── ...
│   │
│   ├── features/                  # Phase C: 分功能 Spec
│   │   ├── feat_001_data_storage.md
│   │   ├── feat_002_navigation.md
│   │   └── ...
│   │
│   └── ui-snapshots/              # Phase A: 页面元数据
│       ├── page_0001_HomeView/
│       │   ├── meta.json          # 页面元数据（脚本骨架 + LLM 补充）
│       │   └── screenshot.png     # （可选）截图
│       └── page_0002_SettingsView/
│           └── meta.json
│
├── decision-ledger.md              # 决策记录（门禁放行、技术选型等）
│
└── ref/                            # （可选）参考文档
    ├── ios-spec.md                # iOS 原始需求文档（用户提供）
    └── design-notes.md            # 设计说明（用户提供）
```

## 2. 命名规则

### 页面 ID 命名

**格式**：`page_NNNN_ClassName`

**规则**：
- `NNNN`：4 位数字，从 0001 开始递增
- `ClassName`：iOS 源码中的实际类名（SwiftUI View 或 UIKit ViewController）
- 不区分 SwiftUI/UIKit，共用序列

**示例**：
- `page_0001_HomeView`
- `page_0002_SettingsView`
- `page_0012_ScanViewController`

**禁止**：
- ❌ `page_1_HomeView`（数字必须 4 位）
- ❌ `page_0001_home_view`（必须使用原始类名）
- ❌ `frag_0001_DetailFragment`（不使用 frag_ 前缀）

### 功能 ID 命名

**格式**：`FXXX`

**编号范围**：
- `F001-F099`: 核心业务功能
- `F100-F199`: 系统集成功能
- `F200-F299`: 辅助功能

**示例**：
- `F001` — 数据存储
- `F002` — 导航路由
- `F101` — 相机扫描
- `F102` — 通知服务

### 文件命名

**UI Spec 文件**：
- `spec/baseline/ui/page_NNNN_ClassName.md`

**Feature Spec 文件**：
- `spec/baseline/features/feat_XXX_feature_name.md`
- `feature_name` 使用小写下划线分隔

**元数据文件**：
- `spec/baseline/ui-snapshots/page_NNNN_ClassName/meta.json`

## 3. 必需产物清单

### Phase A 产物

- [ ] `spec/.i2h/project-skeleton.json` — 项目骨架
- [ ] `spec/.i2h/info-plist-analysis.json` — Info.plist 分析
- [ ] `spec/.i2h/resources-inventory.json` — 资源清单
- [ ] `spec/.i2h/phase-a-report.md` — Phase A 总结
- [ ] `spec/baseline/ui-snapshots/page_NNNN_*/meta.json` — 每个页面的元数据（至少 1 个）

### Phase B 产物

- [ ] `spec/baseline/ui-manifest.md` — UI 总清单
- [ ] `spec/baseline/ui/page_NNNN_*.md` — 每个页面的详细 spec（至少 1 个）

### Phase C 产物

- [ ] `spec/baseline/feature-index.md` — 功能索引
- [ ] `spec/baseline/features/feat_XXX_*.md` — 每个功能的详细 spec（至少 1 个）

### 完成标记

- [ ] `spec/baseline/spec-complete.txt` — 最终完成标记

### 决策记录

- [ ] `spec/decision-ledger.md` — 所有决策和门禁放行记录

## 4. 文件格式规范

### meta.json 格式

```json
{
  "page_id": "page_0001",
  "view_name": "HomeView",
  "file_path": "Cuike/Views/HomeView.swift",
  "type": "SwiftUI View",
  "complexity": "medium",
  "line_count": 80,
  "confidence": "high",
  
  "properties": [
    {
      "name": "beanStore",
      "wrapper": "@ObservedObject",
      "type": "BeanStore",
      "has_default": false
    }
  ],
  
  "ui_structure": {
    "container": "VStack",
    "depth": 3,
    "key_components": ["List", "NavigationLink", "Button"]
  },
  
  "interactions": [
    {
      "type": "navigation",
      "trigger": "NavigationLink tap",
      "target": "BeanDetailView"
    }
  ],
  
  "conversion_strategy": {
    "converter": "template",
    "auto_conversion_rate": 0.85,
    "manual_adjustments": ["Sheet presentation", "Navigation binding"]
  },
  
  "ios_source_anchors": {
    "primary_file": "Cuike/Views/HomeView.swift",
    "related_files": ["Cuike/Models/Bean.swift"],
    "key_symbols": ["HomeView.body", "BeanStore.fetchBeans()"]
  }
}
```

### spec-complete.txt 格式

```
i2h-spec completed at 2024-11-03T15:30:00Z
UI pages: 11
Features: 5
Findings: 0 blocking, 2 deferred
Next: Run /i2h-plan to generate execution plan
```

## 5. 产物验证

### 文件存在性检查

所有必需产物必须存在：

```bash
# 检查脚本示例
required_files=(
  "spec/baseline/ui-manifest.md"
  "spec/baseline/feature-index.md"
  "spec/baseline/spec-complete.txt"
)

for file in "${required_files[@]}"; do
  if [[ ! -f "$file" ]]; then
    echo "ERROR: Missing required file: $file"
    exit 1
  fi
done
```

### 内容完整性检查

关键字段必须非空：

```python
# 检查 meta.json 示例
required_fields = [
    "page_id", "view_name", "file_path", 
    "type", "complexity", "confidence"
]

for field in required_fields:
    if not meta.get(field):
        raise ValueError(f"Missing required field: {field}")
```

### 命名一致性检查

页面 ID 必须在所有产物中保持一致：

- `meta.json` 中的 `page_id`
- UI Spec 文件名中的 `page_NNNN`
- `ui-manifest.md` 中的引用

## 6. 与原版 a2h-spec 的对应关系

| 原版 (Android) | iOS 版本 | 说明 |
|---------------|---------|------|
| `toolkit-fact-tree.json` | `project-skeleton.json` | 项目骨架 |
| `ui-snapshots/page_NNNN/view.xml` | `ui-snapshots/page_NNNN/meta.json` | 页面元数据（iOS 无 view.xml）|
| `ui-manifest.md` | `ui-manifest.md` | UI 总清单（相同）|
| `feature-index.md` | `feature-index.md` | 功能索引（相同）|
| `api-inventory/` | （暂不实现） | API 清单（Phase 2+）|
| `plans/slices/` | （由 i2h-plan 生成） | 执行切片（下一阶段）|

## 7. 产物用途

### 下游消费者

| 产物 | 消费者 | 用途 |
|------|--------|------|
| `ui-manifest.md` | i2h-plan | 生成 UI 转换计划 |
| `ui/page_*.md` | i2h-execute | 指导页面转换 |
| `feature-index.md` | i2h-plan | 生成功能实现计划 |
| `features/feat_*.md` | i2h-execute | 指导功能实现 |
| `ui-snapshots/*/meta.json` | i2h-execute | 运行时数据源 |
| `decision-ledger.md` | i2h-verify | 验证决策合理性 |

### 人工阅读

所有 `.md` 文件都应该：
- 可读性强（使用 Markdown 格式）
- 结构清晰（使用标题层次）
- 内容完整（不用 TODO 占位）
- 便于追溯（包含源文件引用）

## 8. 清理和归档

### 临时文件

以下文件仅用于运行时，可在完成后清理：

- `spec/.i2h/spec-run/` — 运行时数据
- `spec/.i2h/*-report.md` — 中间报告（可选保留）

### 永久保留

以下文件必须永久保留：

- `spec/baseline/` — 所有最终产物
- `spec/decision-ledger.md` — 决策记录
- `spec/.i2h/open-findings.json` — Findings 追踪

## 9. 版本控制

### 应提交到 git

```
spec/baseline/
spec/decision-ledger.md
spec/ref/  （如果用户提供）
```

### 可忽略

```
spec/.i2h/spec-run/
spec/.i2h/*-report.md
spec/baseline/ui-snapshots/*/screenshot.png  （可选）
```

### .gitignore 建议

```gitignore
# i2h-spec 临时文件
spec/.i2h/spec-run/
spec/.i2h/phase-*-report.md

# 可选的截图（体积大）
spec/baseline/ui-snapshots/**/*.png
```

## 10. 质量标准

### 必需达到的标准

- ✅ 所有必需文件存在
- ✅ 关键字段非空（不用 TODO）
- ✅ 文件路径已验证存在
- ✅ 页面 ID 命名一致
- ✅ 复杂度评估合理

### 优秀的标准

- ⭐ 代码示例丰富
- ⭐ 风险评估详细
- ⭐ 依赖关系清晰
- ⭐ 迁移策略可操作
- ⭐ 决策有充分理由

## 11. 故障排查

### 产物缺失

如果发现产物缺失：

1. 检查 Phase 是否正常完成
2. 查看 `open-findings.json` 是否有阻断
3. 检查 decision-ledger.md 是否有异常决策

### 格式错误

如果发现格式错误：

1. 检查是否遵循模板规范
2. 使用 linter 验证格式
3. 手动修复或重新生成

### 数据不一致

如果发现页面 ID 不一致：

1. 以 `meta.json` 为准
2. 更新其他文件中的引用
3. 重跑覆盖率审计
