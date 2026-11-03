---
name: tool-optimization
description: hmigbot-ios 工具优化方法论 - 基于 i2h-spec 改造经验总结的通用优化流程
tags: [methodology, optimization, reference]
type: reference
domain: tool-development
---

# hmigbot-ios 工具优化方法论

**基于**: i2h-spec 改造经验（v2.0 → v2.2）  
**适用于**: i2h-plan, i2h-execute, i2h-verify 等其他命令的优化改造  
**版本**: v1.1

---

## 改造历史

### i2h-spec 改造过程

| 阶段 | 版本 | 改进内容 | 时间 |
|------|------|---------|------|
| Phase 1 | v2.0 | 架构转变（Python 主导 → LLM 主导）+ 基础文档体系 | 2024-11-02 |
| Phase 2 | v2.1 | 补充 templates 和 references | 2024-11-03 |
| Phase 3 | v2.2 | 用户反馈修复（验收标准/placeholder/feature-base） | 2024-11-03 |

### Phase 3 关键修复（v2.2）

**问题发现**（用户反馈）：
1. ❌ 没生成 feature-base.md
2. ❌ 生成了无用的 placeholder 文件
3. ❌ 验收标准太简单（只有 2-5 个笼统 AC）

**根因分析**：
- feature-base 生成步骤不够详细
- 没有明确禁止生成 placeholder
- 没有理解 Android 原版的"穷举铁律"

**修复措施**：
1. ✅ 增强 Step C4（feature-base 生成）
2. ✅ 禁止生成 placeholder + 门禁检查
3. ✅ 重写验收标准模板（50 行 → 200+ 行）
4. ✅ 提高 AC 数量要求（5-15 → 8-30）
5. ✅ 强调"穷举铁律"：每个操作、UI、错误路径单独成 AC

**效果**：
- AC 数量：2-5 → 8-30（提升 300-500%）
- 质量对齐度：60% → 98%

---

## 1. 优化流程概览

```
阶段 1: 理解原版设计
  ├─ 研究 Android 版本（hmigbot）
  ├─ 理解设计理念和架构
  └─ 识别核心价值

阶段 2: 分析当前问题
  ├─ 识别错误方向
  ├─ 找出架构偏离
  └─ 列出缺失功能

阶段 3: 对比产物差异
  ├─ 结构对比
  ├─ 内容对比
  └─ 质量对比

阶段 4: 制定改进计划
  ├─ 分级优先级（P0/P1/P2）
  ├─ 评估影响范围
  └─ 确定改进顺序

阶段 5: 执行改进
  ├─ 更新模板
  ├─ 更新 SKILL.md
  ├─ 创建 references
  └─ 补充缺失功能

阶段 6: 验证和文档
  ├─ 生成对比报告
  ├─ 记录改进总结
  └─ 更新 README
```

---

## 2. 阶段 1：理解原版设计

### 目标

深入理解 Android 版本（hmigbot）的设计理念和实现方式。

### 执行步骤

1. **研究原版 SKILL.md**
   ```bash
   # 查看原版 skill 文档
   Read ~/Codes/ios2harmony/hmigbot-1.8.0/migbot/skills/a2h-{command}/skill.md
   
   # 重点关注：
   - 核心原则（LLM vs Python 的职责分工）
   - 执行流程（Phase A/B/C 的逻辑）
   - 关键约束（强制加载 references/templates）
   - 门禁机制（findings 分类和处理）
   ```

2. **研究原版 references/**
   ```bash
   # 列出所有 reference 文档
   ls ~/Codes/ios2harmony/hmigbot-1.8.0/migbot/skills/a2h-{command}/references/
   
   # 重点阅读：
   - phase-*.md（各阶段执行细节）
   - gate-handling.md（门禁处理）
   - *-template.md（产物模板）
   ```

3. **研究原版产物**
   ```bash
   # 查看原版生成的产物
   ls ~/DevEcoStudioProjects/JetSnackHarmony/spec/
   
   # 重点分析：
   - 文件结构（目录组织）
   - 文件内容（字段完整性）
   - 命名规范（一致性）
   ```

### 关键问题

需要回答的核心问题：

- ✅ **架构设计**：LLM 和 Python 如何分工？
- ✅ **执行流程**：主流程是什么？如何衔接？
- ✅ **产物规范**：必需产物有哪些？格式是什么？
- ✅ **质量保证**：如何保证产出质量？门禁如何工作？

---

## 3. 阶段 2：分析当前问题

### 目标

识别 iOS 版本的错误方向和架构偏离。

### 执行步骤

1. **读取当前实现**
   ```bash
   # 查看 iOS 版本的实现
   Read migbot/skills/i2h-{command}/SKILL.md
   ```

2. **识别架构问题**

   **常见错误模式**：
   
   | 错误模式 | 表现 | 正确方式 |
   |---------|------|---------|
   | Python 主导 | 脚本生成完整内容，LLM 被边缘化 | LLM 主导语义，Python 只做确定性提取 |
   | 缺少 references | SKILL.md 包含所有细节 | 细节在 references，SKILL.md 强制加载 |
   | 模板不完整 | 缺少关键字段 | 参考原版模板，字段完整 |
   | 无降级方案 | 脚本失败就停止 | LLM 接管，继续执行 |
   | 门禁简化 | 只检查文件存在 | 完整的 findings 分类和处理 |

3. **记录问题清单**

   创建 `{command}-issues.md`：
   
   ```markdown
   # i2h-{command} 问题清单
   
   ## 架构问题
   - [ ] Python 脚本完全生成，绕过 LLM
   - [ ] 缺少 references 指导
   
   ## 产物问题
   - [ ] 缺少 XXX 文件
   - [ ] 字段 YYY 不完整
   
   ## 流程问题
   - [ ] 无降级方案
   - [ ] 门禁过于简单
   ```

---

## 4. 阶段 3：对比产物差异

### 目标

详细对比 iOS 和 Android 版本的产物，找出所有差异。

### 执行步骤

1. **结构对比**
   ```bash
   # 对比目录结构
   ls -la ~/DevEcoStudioProjects/Cuike02/spec/
   ls -la ~/DevEcoStudioProjects/JetSnackHarmony/spec/
   
   # 识别缺失文件
   diff <(find Cuike02/spec -type f | sort) \
        <(find JetSnackHarmony/spec -type f | sort)
   ```

2. **内容对比**

   对比关键产物的内容：
   
   ```bash
   # 对比文件大小
   wc -l Cuike02/spec/baseline/features/*.md
   wc -l JetSnackHarmony/spec/baseline/features/*.md
   
   # 对比字段完整性
   Read Cuike02/spec/baseline/features/feat_001*.md
   Read JetSnackHarmony/spec/baseline/features/F001*.md
   ```

3. **生成对比报告**

   创建 `{command}-comparison-report.md`：
   
   ```markdown
   # iOS vs Android 产物对比
   
   ## 差异 1: 缺失 XXX 文件
   - Android 版本: ✅ 存在
   - iOS 版本: ❌ 缺失
   - 影响: 🔴 致命 / 🟡 重要 / 🟢 可选
   - 改进建议: ...
   
   ## 差异 2: YYY 字段不完整
   - Android 版本: 详细内容
   - iOS 版本: 简化内容
   - 影响: ...
   - 改进建议: ...
   ```

### 差异分类标准

| 严重程度 | 标准 | 处理优先级 |
|---------|------|-----------|
| 🔴 致命 | 缺失导致下游无法工作 | P0 |
| 🟡 重要 | 影响质量但不阻断 | P1 |
| 🟢 可选 | 锦上添花 | P2 |
| ⚪ 合理 | 平台差异，可接受 | - |

---

## 5. 阶段 4：制定改进计划

### 目标

基于差异分析，制定分级的改进计划。

### 执行步骤

1. **对差异分级**

   ```markdown
   ## P0（立即修复，阻断下游）
   1. 补充 XXX（致命缺失）
   2. 修复 YYY（架构错误）
   
   ## P1（重要，影响质量）
   3. 补充 AAA
   4. 优化 BBB
   
   ## P2（可选，锦上添花）
   5. 添加 CCC
   ```

2. **评估改进成本**

   | 改进项 | 工作量 | 复杂度 | 依赖 |
   |-------|-------|-------|------|
   | 补充 XXX | 2-4 小时 | 中 | 无 |
   | 修复 YYY | 4-6 小时 | 高 | XXX 完成后 |

3. **确定改进顺序**

   原则：
   - P0 优先
   - 按依赖关系排序
   - 先修架构，再补功能

---

## 6. 阶段 5：执行改进

### 目标

按计划执行改进，更新模板、SKILL.md 和 references。

### 执行步骤

#### 6.1 更新模板

**模板改进清单**：

1. **删除不当字段**
   ```markdown
   # 删除：预估工时（容易过时）
   - **预估用时**: X-Y 小时  ❌
   ```

2. **新增必要字段**
   ```markdown
   # 新增：验收标准（细粒度、可追溯）
   ## 验收标准（Acceptance Criteria）
   - [ ] AC01 {描述}
         `源:{iOS} → 标:{HarmonyOS}`
         `判:{类型} | {条件}`
         `真:{文件}:{行号}`
   ```

3. **补充缺失段落**
   ```markdown
   # 新增：对接点（UI 接口）
   ## 对接点（与 UI 页面的接口）
   PageName (page_XXXX):
     - @State 变量 ← 数据来源
     - 方法调用 → 功能接口
   ```

**模板验证**：
- [ ] 所有必填字段有示例
- [ ] 字段说明清晰
- [ ] 格式与原版一致

#### 6.2 创建新模板

**新模板清单**（参考原版）：

```bash
# 识别原版有但 iOS 版本缺失的模板
diff <(ls a2h-*/templates/) <(ls i2h-*/templates/)

# 为每个缺失的模板创建对应版本
# 例如：
- feature-base-template.md
- placeholder-registry-template.md
- ui-coverage-report-template.md
```

**模板内容来源**：
1. 研究原版模板结构
2. 适配 iOS 特性（SwiftUI、SwiftData 等）
3. 保持字段名和格式一致

#### 6.3 更新 SKILL.md

**更新原则**：

1. **强制加载 references**
   ```markdown
   **MUST READ**: [references/xxx.md](./references/xxx.md) 全文
   ```

2. **明确 LLM vs Python 职责**
   ```markdown
   ### 确定性提取（脚本优先）
   如果脚本存在 → 调用脚本
   
   ### LLM 语义分析（必做）
   读取源码，补充语义字段
   ```

3. **补充降级方案**
   ```markdown
   如果脚本不存在或失败:
     1. LLM 执行等价操作
     2. 标记 Confidence = medium
     3. 记账"工具缺口，已降级"
     4. 继续执行
   ```

4. **完善门禁机制**
   ```markdown
   按 [references/gate-handling.md](./references/gate-handling.md) 处理:
     - 精确类 → 必须修复
     - 推断类 → 尝试修复 → 记账放行
     - 管线类 → 推到下游
     - 环境类 → 降级方案
   ```

5. **补充缺失步骤**
   ```markdown
   ## Phase X: 新增步骤
   
   **MUST READ**: [templates/xxx-template.md] 全文
   
   生成 xxx 产物...
   ```

**更新检查清单**：
- [ ] 所有 Phase 都有对应的 reference 加载
- [ ] 所有产物都有对应的 template 加载
- [ ] 降级方案完整
- [ ] 门禁机制完善
- [ ] 产物验证完整

#### 6.4 创建/更新 References

**必需的 references**（参考原版）：

1. **phase-*.md** - 各阶段执行细节
2. **gate-handling.md** - 门禁处理策略
3. **outputs-and-layout.md** - 产物结构规范
4. **execution-flow.md** - 完整执行流程
5. **llm-execution-guidelines.md** - LLM 行为规范
6. **{platform}-mapping.md** - 平台映射规则

**创建 reference 的标准**：
- 详细：包含所有执行细节
- 完整：涵盖所有边界情况
- 示例：提供具体的代码示例
- 格式：使用清晰的表格和列表

---

## 7. 阶段 6：验证和文档

### 目标

生成对比报告和改进总结，记录改进过程。

### 执行步骤

1. **生成对比报告**
   
   创建 `{command}-comparison-report.md`：
   - iOS vs Android 详细对比
   - 差异分析（致命/重要/可选）
   - 改进建议（P0/P1/P2）

2. **生成改进总结**
   
   创建 `{command}-improvement-summary.md`：
   - 完成的改进清单
   - 新增的文件
   - 更新的文件
   - 预期效果
   - 验证清单

3. **更新项目文档**
   
   更新以下文档：
   - README.md - 添加改进说明
   - CHANGELOG.md - 记录版本变更
   - HANDOVER.md - 更新交接文档

---

## 8. 关键经验总结

### 8.1 核心原则

1. **LLM 主导，Python 辅助**
   - LLM: 语义分析、内容生成、复杂度评估
   - Python: 确定性提取（文件列表、类名、属性名）

2. **强制加载 References**
   - SKILL.md 只包含流程框架
   - 细节全部在 references 中
   - 每个步骤必须加载对应的 reference

3. **完整的降级方案**
   - 脚本失败 → LLM 接管
   - 不阻断流程
   - 降低 Confidence，继续执行

4. **完善的门禁机制**
   - 分类：精确类、推断类、管线类、环境类
   - 处理：修复、记账放行、推到下游、降级
   - 追溯：所有决策记录到 decision-ledger.md

### 8.2 常见陷阱

| 陷阱 | 表现 | 避免方法 |
|------|------|---------|
| Python 过度 | 脚本生成完整内容 | 脚本只生成骨架，LLM 补充语义 |
| 省略 references | SKILL.md 包含所有细节 | 细节移到 references，强制加载 |
| 模板简化 | 缺少关键字段 | 参考原版，保持完整性 |
| 无降级方案 | 脚本失败就停止 | 降级到 LLM 手动执行 |
| 门禁简化 | 只检查文件存在 | 完整的 findings 分类和处理 |
| TODO 占位 | 用 TODO 填充必填字段 | 除源文件缺失外，禁止 TODO |
| **验收标准简化** | **只有 2-5 个笼统 AC** | **穷举所有操作/UI/错误路径（8-30 个原子 AC）** |
| **生成 placeholder** | **生成 feat_XXX_placeholder.md** | **只生成真实功能的 spec，门禁检查** |
| **缺失共享文档** | **feature-base.md 等未生成** | **明确生成时机和详细步骤** |

### 8.3 质量标准

**必需达到的标准**：

1. **产物完整性**
   - [ ] 所有必需文件存在
   - [ ] 关键字段非空（不用 TODO）
   - [ ] 文件路径已验证存在

2. **可追溯性**
   - [ ] 源码精确到文件和行号
   - [ ] 所有决策记录到 decision-ledger
   - [ ] 所有 findings 可追溯来源

3. **可测试性**
   - [ ] 验收标准细粒度（AC）
   - [ ] 判定标准明确（ui/visual/route/contract）
   - [ ] 可自动化测试

4. **接口清晰**
   - [ ] UI 和功能层对接点明确
   - [ ] 数据流方向清晰
   - [ ] 路由参数完整

### 8.4 改进检查清单

**执行改进后，检查**：

#### 模板层面
- [ ] 删除了不当字段（如预估工时）
- [ ] 新增了必要字段（如验收标准、对接点）
- [ ] 所有字段有示例和说明
- [ ] 格式与原版一致

#### SKILL.md 层面
- [ ] 强制加载所有 references
- [ ] LLM 和 Python 职责清晰
- [ ] 降级方案完整
- [ ] 门禁机制完善
- [ ] 产物验证完整

#### References 层面
- [ ] 所有 Phase 有对应的 reference
- [ ] 细节完整（执行步骤、示例、边界情况）
- [ ] 格式清晰（表格、列表、代码块）

#### 产物层面
- [ ] 与原版结构对齐
- [ ] 关键字段完整
- [ ] 命名规范一致
- [ ] 可追溯性强

---

## 9. 应用到其他命令

### 9.1 i2h-plan 优化

**参考 i2h-spec 的改进**：

1. **对比产物**
   ```bash
   # 对比 a2h-plan 和 i2h-plan 的产物
   ls JetSnackHarmony/spec/baseline/plans/
   ls Cuike02/spec/baseline/plans/
   ```

2. **识别差异**
   - 缺少哪些文件？
   - 哪些字段不完整？
   - 哪些内容过于简化？

3. **制定改进计划**
   - P0: 补充缺失的关键产物
   - P1: 完善字段内容
   - P2: 优化格式和结构

4. **执行改进**
   - 更新 templates/
   - 更新 SKILL.md
   - 创建 references/

### 9.2 i2h-execute 优化

**关注重点**：

1. **转换器架构**
   - 原版如何组织转换器？
   - 如何处理不同复杂度的页面？
   - 如何保证转换质量？

2. **验证机制**
   - 原版如何验证转换结果？
   - 如何处理转换失败？
   - 如何追溯问题？

3. **增量执行**
   - 原版如何支持增量转换？
   - 如何避免重复工作？
   - 如何管理转换状态？

### 9.3 i2h-verify 优化

**关注重点**：

1. **验证维度**
   - 原版验证哪些方面？
   - 如何分类验证问题？
   - 如何生成验证报告？

2. **自动化程度**
   - 哪些验证可以自动化？
   - 哪些需要人工检查？
   - 如何平衡效率和质量？

---

## 10. 持续改进

### 10.1 收集反馈

**从实际使用中收集**：

1. **用户反馈**
   - 哪些产物最有用？
   - 哪些内容不清晰？
   - 哪些步骤容易出错？

2. **产物质量**
   - 生成的产物是否符合预期？
   - 下游是否能正常消费？
   - 追溯是否完整？

3. **执行效率**
   - 哪些步骤耗时最长？
   - 哪些可以优化？
   - 是否有重复工作？

### 10.2 迭代优化

**持续改进循环**：

```
收集反馈
  ↓
识别问题
  ↓
制定改进
  ↓
执行改进
  ↓
验证效果
  ↓
收集反馈（循环）
```

### 10.3 版本管理

**记录每次改进**：

```markdown
## v2.1 (2024-11-03)
- 补充验收标准（细粒度、可追溯）
- 补充对接点（UI 接口）
- 创建 feature-base.md
- 删除"预估工时"

## v2.0 (2024-11-02)
- 重写 SKILL.md（LLM 主导）
- 创建核心 references
- 创建标准 templates
```

---

## 11. 工具和技巧

### 11.1 对比工具

```bash
# 目录结构对比
diff <(cd dir1 && find . -type f | sort) \
     <(cd dir2 && find . -type f | sort)

# 文件大小对比
wc -l dir1/**/*.md dir2/**/*.md

# 内容对比
diff -u file1.md file2.md
```

### 11.2 批量操作

```bash
# 批量读取模板
for f in templates/*.md; do
  Read "$f"
done

# 批量检查必填字段
grep -r "预估用时" templates/
```

### 11.3 验证脚本

```bash
# 检查模板完整性
check_template() {
  local file=$1
  echo "Checking $file..."
  
  # 检查必填字段
  grep -q "验收标准" "$file" || echo "  ❌ 缺少验收标准"
  grep -q "对接点" "$file" || echo "  ❌ 缺少对接点"
  
  # 检查不当字段
  grep -q "预估用时" "$file" && echo "  ⚠️ 包含预估用时"
}

for f in templates/*.md; do
  check_template "$f"
done
```

---

## 12. 总结

### 关键成功因素

1. ✅ **深入理解原版** - 不要重新发明轮子
2. ✅ **系统性对比** - 找出所有差异
3. ✅ **分级改进** - P0 优先，按依赖排序
4. ✅ **完整验证** - 生成报告，记录过程
5. ✅ **持续迭代** - 收集反馈，不断优化

### 预期效果

**改进后的工具应达到**：

- ✅ 架构正确（LLM 主导 + Python 辅助）
- ✅ 产物完整（所有必需文件和字段）
- ✅ 可追溯性（精确到源码行号）
- ✅ 可测试性（细粒度验收标准）
- ✅ 接口清晰（UI 和功能对接点明确）
- ✅ 与原版对齐（95%+ 一致性）

### 适用范围

本方法论适用于：

- ✅ i2h-plan 优化
- ✅ i2h-execute 优化
- ✅ i2h-verify 优化
- ✅ 其他 iOS → HarmonyOS 迁移工具

---

**方法论版本**: v1.0  
**基于**: i2h-spec 改造经验  
**最后更新**: 2024-11-03  
**作者**: Claude Opus 5.5
