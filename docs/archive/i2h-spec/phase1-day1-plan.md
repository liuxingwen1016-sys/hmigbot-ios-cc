# Phase 1 Day 1 执行计划: toolkit-fact-tree.json 生成

**目标**: 创建能够生成符合原版规范的 `spec/toolkit-fact-tree.json` 的实现

**时间**: 2024-11-03  
**优先级**: P0 (最高)

---

## 📊 现状分析

### 当前问题

1. **ios-fact-tree skill 存在但不合规**
   - 位置: `migbot/skills/ios-fact-tree/skill.md`
   - 输出: `ios-facts.json` (不符合规范)
   - 格式: 自定义格式，不兼容 hmigbot 原版

2. **i2h-spec 未调用 ios-fact-tree**
   - 在 `i2h-spec/SKILL.md` 中没有找到对 ios-fact-tree 的调用
   - Phase A 只做了基础的源码扫描，未生成 fact-tree

3. **toolkit-fact-tree.json 完全缺失**
   - iOS 版本 (Cuike01) 的 spec/ 目录中不存在此文件
   - 这是最致命的问题，影响整个下游流程

### 原版标准 (JetSnackHarmony)

```json
{
  "$schema_version": 1,
  "schema_version": 1,
  "app": {
    "package": "com.example.jetsnack",
    "launcher_short": "MainActivity",
    "launcher_activity": "com.example.jetsnack.ui.MainActivity",
    "min_sdk": null,
    "target_sdk": null
  },
  "source": {
    "toolkit": "compose-fact-tree",
    "generator": {
      "skill": "compose-fact-tree",
      "script_version": "1.0.0"
    },
    "android_root": "/path/to/android",
    "generated_at": "2026-11-03T04:57:31.322691Z",
    "resolution_notes": "..."
  },
  "pages": [
    {
      "id": "MainActivity",
      "type": "Activity",
      "screen_kind": "page",
      "fq_class": "com.example.jetsnack.ui.MainActivity",
      "package": "com.example.jetsnack.ui",
      "label": "Jetsnack",
      "purpose": null,
      "uncertain": false,
      "source": "launcher_activity",
      "android_file": "app/src/main/java/.../MainActivity.kt",
      "layout_file": null,
      "harmony_target": "pages/mainactivity/Index",
      "logical_feature_id": "compose.ui",
      "route": null,
      "is_start_destination": true,
      "contains": ["MainContainer"],
      "shows_dialogs": [],
      "components": [],
      "navigation": {
        "inbound": [],
        "outbound": [],
        "unresolved_hints": []
      },
      "preconditions": [],
      "inbound_triggers": [...]
    }
  ],
  "fragments": [],
  "dialogs": [...],
  "features": [...],
  "navigation": {...},
  "stats": {...}
}
```

---

## 🎯 实施策略

### 方案选择

根据 `references-integration-analysis.md` 和 `swift-syntax-guide.md` 的建议，采用**实用主义方案**：

**Phase 1.1: 简化版实现 (Bash + grep)** ✅ 推荐
- 快速实现，2-4 小时
- 适合大多数场景
- 无外部依赖

**Phase 1.2: 增强版实现 (可选，SwiftSyntax)** 🟡 可选
- 精准解析，4-8 小时
- 适合复杂项目
- 需要 Xcode 工具链

**决策**: 先实现 Phase 1.1，如果需要再添加 Phase 1.2

---

## 📋 实施步骤

### Step 1: 修改 i2h-spec/SKILL.md

在 Phase A 中添加 fact-tree 生成步骤。

**位置**: `migbot/skills/i2h-spec/SKILL.md` - Phase A

**添加内容**:

```markdown
### Step A3.5: 生成 toolkit-fact-tree.json

调用 ios-fact-tree (改造版) 生成项目结构分析：

\`\`\`bash
# 生成 toolkit-fact-tree.json
# 这是下游所有 skill 依赖的核心数据源
python3 .migbot/bin/scripts/ios/generate_fact_tree.py \
  --ios-root "$IOS_ROOT" \
  --output "$SPEC_DIR/toolkit-fact-tree.json"
\`\`\`

**输出**: `spec/toolkit-fact-tree.json`

**包含**:
- app 元信息 (bundle ID, 启动入口)
- pages 数组 (所有 SwiftUI Views 和 UIKit VCs)
- navigation 图谱 (导航关系)
- features 聚类 (功能分组)
- dialogs 清单 (sheet, alert, popover)
- stats 统计信息

**验证**:
- [ ] 文件存在且 >= 500 行
- [ ] schema_version = 1
- [ ] pages 数组非空
- [ ] 每个 page 有 id, type, fq_class
- [ ] navigation 对象存在
```

### Step 2: 创建 Python 脚本

**文件**: `.migbot/bin/scripts/ios/generate_fact_tree.py`

**核心功能**:
1. 扫描 iOS 项目结构
2. 识别 SwiftUI Views 和 UIKit ViewControllers
3. 分析导航关系
4. 生成符合规范的 JSON

**参考**:
- `references/ios-0.14.1-iOS技能与说明/skills/ios-fact-tree/SKILL.md`
- `migbot/skills/i2h-spec/references/swift-syntax-guide.md`
- 原版 `compose-fact-tree` 的输出格式

### Step 3: 实现脚本 (简化版)

使用 Bash + Python 混合方式，快速实现基本功能。

### Step 4: 测试验证

在 Cuike01 项目上运行并验证输出。

### Step 5: 更新 i2h-spec 调用链

确保 i2h-spec 正确调用并验证 fact-tree 生成。

---

## 🔧 技术实现

### 实现思路

```python
#!/usr/bin/env python3
"""
generate_fact_tree.py - 生成 iOS 项目的 toolkit-fact-tree.json

输出格式完全对齐 hmigbot 原版 (compose-fact-tree)
"""

import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

def main():
    # 1. 解析命令行参数
    ios_root = parse_args()
    
    # 2. 扫描项目结构
    project_info = scan_project_structure(ios_root)
    
    # 3. 识别 SwiftUI Views
    swiftui_views = scan_swiftui_views(ios_root)
    
    # 4. 识别 UIKit ViewControllers
    uikit_vcs = scan_uikit_viewcontrollers(ios_root)
    
    # 5. 合并为 pages 数组
    pages = build_pages_array(swiftui_views, uikit_vcs, project_info)
    
    # 6. 分析导航关系
    navigation = analyze_navigation(pages, ios_root)
    
    # 7. 识别 dialogs (sheet, alert, popover)
    dialogs = identify_dialogs(ios_root)
    
    # 8. 聚类 features
    features = cluster_features(pages)
    
    # 9. 组装 fact-tree
    fact_tree = {
        "$schema_version": 1,
        "schema_version": 1,
        "app": project_info['app'],
        "source": {
            "toolkit": "ios-fact-tree",
            "generator": {
                "skill": "ios-fact-tree",
                "script_version": "1.0.0"
            },
            "ios_root": str(ios_root),
            "generated_at": datetime.utcnow().isoformat() + 'Z',
            "resolution_notes": f"iOS project: {len(pages)} pages, {len(dialogs)} dialogs"
        },
        "pages": pages,
        "fragments": [],  # iOS 没有 Fragment 概念
        "dialogs": dialogs,
        "features": features,
        "navigation": navigation,
        "stats": calculate_stats(pages, dialogs, features)
    }
    
    # 10. 输出 JSON
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(fact_tree, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Generated toolkit-fact-tree.json: {len(pages)} pages, {len(dialogs)} dialogs")
    
def scan_swiftui_views(ios_root: Path) -> List[Dict]:
    """扫描所有 SwiftUI View"""
    views = []
    
    # 使用 grep 查找 SwiftUI View 定义
    result = subprocess.run([
        'grep', '-r', '--include=*.swift',
        '-E', r'struct\s+\w+\s*:\s*View',
        str(ios_root)
    ], capture_output=True, text=True)
    
    for line in result.stdout.splitlines():
        # 解析: 文件路径:行号:内容
        match = re.match(r'([^:]+):(\d+):(.*)', line)
        if match:
            file_path, line_num, content = match.groups()
            
            # 提取 struct 名称
            view_match = re.search(r'struct\s+(\w+)', content)
            if view_match:
                view_name = view_match.group(1)
                views.append({
                    'name': view_name,
                    'file': file_path,
                    'line': int(line_num),
                    'type': 'SwiftUI'
                })
    
    return views

def build_pages_array(swiftui_views, uikit_vcs, project_info) -> List[Dict]:
    """构建符合规范的 pages 数组"""
    pages = []
    
    # 处理 SwiftUI Views
    for idx, view in enumerate(swiftui_views, 1):
        page = {
            "id": view['name'],
            "type": "SwiftUI",
            "screen_kind": "page",
            "fq_class": f"{project_info['app']['package']}.{view['name']}",
            "package": project_info['app']['package'],
            "label": view['name'],  # 简化版：使用名称作为 label
            "purpose": None,
            "uncertain": False,
            "source": "swiftui_view",
            "ios_file": view['file'].replace(str(ios_root) + '/', ''),
            "layout_file": None,
            "harmony_target": f"pages/{view['name'].lower()}/Index",
            "logical_feature_id": infer_feature_from_path(view['file']),
            "route": None,
            "is_start_destination": (idx == 1),  # 第一个作为启动页（简化版）
            "contains": [],
            "shows_dialogs": [],
            "components": [],
            "navigation": {
                "inbound": [],
                "outbound": [],
                "unresolved_hints": []
            },
            "preconditions": [],
            "inbound_triggers": []
        }
        pages.append(page)
    
    # 处理 UIKit ViewControllers
    for vc in uikit_vcs:
        page = {
            "id": vc['name'],
            "type": "UIKit",
            "screen_kind": "page",
            "fq_class": f"{project_info['app']['package']}.{vc['name']}",
            # ... 类似结构
        }
        pages.append(page)
    
    return pages
```

---

## ⏱️ 时间估算

| 步骤 | 时间 | 说明 |
|------|------|------|
| Step 1: 修改 i2h-spec | 30 分钟 | 添加调用步骤 |
| Step 2: 设计脚本架构 | 30 分钟 | 确定函数结构 |
| Step 3: 实现核心功能 | 2-3 小时 | 扫描、解析、生成 |
| Step 4: 测试验证 | 1 小时 | 在 Cuike01 上测试 |
| Step 5: 文档更新 | 30 分钟 | 更新说明文档 |
| **总计** | **4.5-5.5 小时** | |

---

## ✅ 验收标准

### 必须满足

- [ ] `spec/toolkit-fact-tree.json` 存在
- [ ] 文件大小 >= 500 行
- [ ] schema_version = 1
- [ ] app 对象包含 package, launcher_short
- [ ] pages 数组非空，至少包含所有 SwiftUI Views
- [ ] 每个 page 有必需字段: id, type, fq_class, package
- [ ] navigation 对象存在
- [ ] features 数组非空
- [ ] stats 对象包含统计信息

### 格式兼容性

- [ ] 与原版 JetSnackHarmony 的 toolkit-fact-tree.json 结构一致
- [ ] 可以被下游 skill (a2h-spec) 正确读取
- [ ] JSON 格式正确，可以被 jq 解析

---

## 📝 下一步

完成 Day 1 后，继续 Day 2: api-inventory/ 生成。

**Day 1 成功标志**: 
- ✅ toolkit-fact-tree.json 生成
- ✅ 通过验收标准
- ✅ 在 Cuike01 项目上成功运行

---

**创建时间**: 2024-11-03  
**状态**: 计划就绪，待执行
