# i2h-plan Scripts

i2h-plan 辅助脚本集合，用于自动化校验 plan 产物的格式和完整性。

## 脚本列表

### 1. lint_plan_coverage.py - 覆盖率校验（核心）

**功能**：执行 SKILL.md §7 定义的 12 项覆盖率校验

**检查项**：
- ✅ P0 功能覆盖率 = 100%
- ✅ P1 功能覆盖率 ≥ 80%
- ✅ UI 页面覆盖率 = 100%
- ✅ Placeholder trigger 白名单率 = 100%
- ✅ Complex Slice anchor 完整率 = 100%
- ✅ 对接点归属率 = 100%
- ✅ 组件嵌入归属率 = 100%
- ✅ 数据链路层扇出完整率 = 100%
- ✅ 骨架审计预演（WARN）
- ✅ 分层校验 5 项
- ✅ 功能分组校验
- ✅ 跨切片接线归属检测

**用法**：
```bash
python3 lint_plan_coverage.py <project_root>

# 示例
python3 lint_plan_coverage.py ~/Projects/Cuike02
```

**退出码**：
- 0: 所有校验通过
- 1: 有阻断级别的失败
- 2: 有警告（非阻断）

**输出示例**：
```
🔍 开始 i2h-plan 覆盖率校验...

================================================================================

📊 覆盖率校验结果

================================================================================

✅ P0 功能覆盖率
   覆盖率: 4/4 (100.0%)
   阈值: 100%

✅ P1 功能覆盖率
   覆盖率: 2/2 (100.0%)
   阈值: 80%

✅ UI 页面覆盖率
   覆盖率: 7/7 (100.0%)
   阈值: 100%

✅ Placeholder trigger 白名单率
   覆盖率: 0/0 (100.0%)
   ⚠️  警告:
      - 无 placeholder-registry.md（无占位）

================================================================================

✅ 通过: 12
❌ 失败: 0 (阻断: 0, 警告: 0)

🎉 所有校验通过！
```

---

### 2. lint_ui_plan.py - UI Plan 专项校验

**功能**：检查 ui-plan.md 的格式和内容正确性

**检查项**：
- ✅ 文件格式（Markdown 表格）
- ✅ 必填字段（序号、页面、iOS 来源、owning_slice）
- ✅ owning_slice 格式（裸 F-ID）
- ✅ 批次分配合理性（无 size-1 批次）
- ✅ 结算检查点存在
- ✅ Summary 统计正确
- ✅ 与 ui-manifest 交叉校验

**用法**：
```bash
python3 lint_ui_plan.py <project_root>
```

**输出示例**：
```
🔍 检查 ui-plan.md...

================================================================================

❌ 错误:

1. Batch 3 只有 1 个页面（size-1 批次）
   💡 建议: 应并入前一批次末尾

2. owning_slice 格式错误: Feature F001 (序号 0005) (行 28)
   💡 建议: 应为裸 F-ID 格式（如 F001），而非 'Feature F001'

================================================================================

❌ 发现 2 个错误，0 个警告
   请修复错误后重新运行
```

---

### 3. lint_feature_plan.py - Feature Plan 专项校验

**功能**：检查 feature-plan.md、base-plan.md 和 slices/*.md 的格式和内容正确性

**检查项**：
- ✅ indexed-v1 格式（plan_format 标记）
- ✅ Base 层 stub 正确（指向 base-plan.md）
- ✅ Slice 索引 ↔ slice 文件一一对应
- ✅ Slice 文件三铁律（调度表、只读、不持有占位）
- ✅ wires 账本结构正确
- ✅ cross_slice_edits 无双登
- ✅ FV 任务存在（FV-1 和 FV-2）
- ✅ base-plan.md 只读态

**用法**：
```bash
python3 lint_feature_plan.py <project_root>
```

**输出示例**：
```
🔍 检查 feature-plan.md 和相关文件...

================================================================================

❌ 错误:

1. [readonly] slice 文件不应包含 checkbox [slice-02-F002.md:45]
   💡 建议: slice 文件应为只读态，移除 - [ ]

2. [format] Base 层不应展开任务行 [feature-plan.md:23]
   💡 建议: Base 层任务应在 base-plan.md 中，索引只保留 stub

================================================================================

❌ 发现 2 个错误，0 个警告
   请修复错误后重新运行
```

---

### 4. gate_plan_complete.py - 完成门禁

**功能**：在 i2h-plan 完成时执行最终门禁检查

**检查项**：
- ✅ 所有必需文件存在
- ✅ 所有 HARD-GATE 校验通过
- ✅ 无 blocking findings
- ✅ grill #2 已完成
- ✅ 覆盖率指标达标

**用法**：
```bash
python3 gate_plan_complete.py <project_root>
```

**输出示例**：
```
🚪 i2h-plan 完成门禁检查

================================================================================

📋 门禁检查结果:

✅ ✅ ui-plan.md 存在
   spec/baseline/plans/ui-plan.md

✅ ✅ feature-plan.md 存在
   spec/baseline/plans/feature-plan.md

✅ ✅ base-plan.md 存在
   spec/baseline/plans/base-plan.md

✅ ✅ coverage-matrix.md 存在
   spec/baseline/plans/coverage-matrix.md

✅ ✅ slices/ 目录包含 4 个文件
   找到 4 个 slice 文件

✅ ✅ feature-plan.md 使用 indexed-v1 格式
   检测到 plan_format: indexed-v1

✅ ✅ Final Verification 任务完整
   包含 FV-1 和 FV-2

✅ ✅ P0 功能覆盖率 = 100%
   4/4 (100%)

✅ ✅ UI 页面覆盖率 = 100%
   7/7 (100%)

✅ ✅ 无 blocking findings
   总 findings: 0，无阻断级别

✅ ✅ grill #2 已完成
   decision-ledger.md 包含 3 条决策

================================================================================

统计: 11 通过, 0 失败 (阻断: 0, 警告: 0)

🎉 门禁通过: 所有检查通过，可以进入 i2h-execute！

✅ 完成标记已创建: spec/baseline/plans/complete.txt
```

---

## 使用场景

### 场景 1: 开发阶段快速迭代

```bash
# 修改 plan 后立即验证
cd migbot/skills/i2h-plan/scripts
./lint_plan_coverage.py ~/Projects/MyApp

# 2-3 秒内得到反馈
❌ P0 功能覆盖率: 3/4 (75%)
   缺失: F004
```

### 场景 2: 分步校验

```bash
# 1. 先检查 UI Plan
./lint_ui_plan.py ~/Projects/MyApp

# 2. 再检查 Feature Plan
./lint_feature_plan.py ~/Projects/MyApp

# 3. 最后运行完整覆盖率校验
./lint_plan_coverage.py ~/Projects/MyApp

# 4. 全部通过后执行门禁
./gate_plan_complete.py ~/Projects/MyApp
```

### 场景 3: CI/CD 集成

```bash
#!/bin/bash
# check_plan.sh

PROJECT_ROOT=$1
SCRIPT_DIR="migbot/skills/i2h-plan/scripts"

echo "开始 plan 质量检查..."

# 运行所有检查
python3 $SCRIPT_DIR/lint_ui_plan.py "$PROJECT_ROOT" || exit 1
python3 $SCRIPT_DIR/lint_feature_plan.py "$PROJECT_ROOT" || exit 1
python3 $SCRIPT_DIR/lint_plan_coverage.py "$PROJECT_ROOT" || exit 1
python3 $SCRIPT_DIR/gate_plan_complete.py "$PROJECT_ROOT" || exit 1

echo "✅ Plan 质量检查通过！"
```

### 场景 4: pre-commit hook

```bash
#!/bin/bash
# .git/hooks/pre-commit

# 只在修改了 plan 文件时运行检查
if git diff --cached --name-only | grep -q "spec/baseline/plans/"; then
    echo "检测到 plan 文件修改，运行校验..."
    python3 migbot/skills/i2h-plan/scripts/lint_plan_coverage.py .
    if [ $? -ne 0 ]; then
        echo "❌ Plan 校验失败，阻止提交"
        exit 1
    fi
fi
```

---

## 脚本 vs LLM 校验对比

| 维度 | Python 脚本 | LLM 校验 |
|------|-----------|---------|
| **速度** | 2-3 秒 ⚡ | 2-3 分钟 🐌 |
| **准确性** | 100%（机械规则）✅ | 95%+（可能遗漏）⚠️ |
| **成本** | 免费 💰 | Token 消耗 💸 |
| **可重复性** | 100% ✅ | 可能不同 ⚠️ |
| **CI/CD 集成** | 原生支持 ✅ | 不支持 ❌ |
| **批量处理** | 支持 ✅ | 不支持 ❌ |

---

## 错误排查

### 问题 1: ModuleNotFoundError

**错误**：
```
ModuleNotFoundError: No module named 'dataclasses'
```

**解决**：
```bash
# Python 3.6 需要安装 dataclasses
pip3 install dataclasses

# 或升级到 Python 3.7+
```

### 问题 2: Permission denied

**错误**：
```
Permission denied: ./lint_plan_coverage.py
```

**解决**：
```bash
# 添加可执行权限
chmod +x *.py
```

### 问题 3: 路径不存在

**错误**：
```
❌ 错误: 目录不存在: /path/to/project
```

**解决**：
```bash
# 使用绝对路径
python3 lint_plan_coverage.py /absolute/path/to/project

# 或相对路径（从脚本目录）
python3 lint_plan_coverage.py ../../../Cuike02
```

---

## 依赖要求

- Python 3.7+
- 标准库（无需额外安装）：
  - pathlib
  - re
  - json
  - dataclasses
  - datetime

---

## 贡献指南

### 添加新的检查项

1. 在对应的 linter 类中添加 `_check_xxx()` 方法
2. 在 `run()` 或 `run_all_checks()` 中调用
3. 更新 README 文档

### 示例：添加新检查

```python
def _check_custom_rule(self):
    """检查自定义规则"""
    # 实现检查逻辑
    if condition_failed:
        self._add_error(
            'category',
            "错误描述",
            file='file.md',
            line=123,
            suggestion="修复建议"
        )
```

---

## 许可证

MIT License

---

**最后更新**: 2024-11-03  
**版本**: v1.0
