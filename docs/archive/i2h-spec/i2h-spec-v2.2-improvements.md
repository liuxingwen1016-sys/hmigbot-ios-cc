# i2h-spec v2.2 改进说明

**改进时间**: 2024-11-03  
**版本**: v2.1 → v2.2  
**改进原因**: 用户反馈实际生成的产物存在 3 个问题

---

## 🔍 发现的问题

### 问题 1: 没生成 feature-base.md
- **现象**: 执行 i2h-spec 后没有生成 `spec/baseline/feature-base.md`
- **原因**: SKILL.md 中有步骤但执行时被跳过
- **影响**: 共享基础设施分散在各 feature spec 中，重复描述

### 问题 2: 生成了无用的 placeholder 文件
- **现象**: 生成了大量 `feat_XXX_placeholder.md` 文件
- **原因**: feature-index 列出了很多功能，但没真实实现就生成了 placeholder
- **影响**: 产物混乱，无用文件干扰

### 问题 3: 验收标准太简单（核心问题）
- **现象**: 验收标准只有 2-5 个，内容笼统
- **对比**: Android 版本有 12-20 个详细的 AC
- **原因**: 模板示例不够详细，没有强调"穷举"要求

---

## ✅ 已修复的内容

### 修复 1: 强化 feature-base.md 生成

**更新**: `SKILL.md` Step C4

**改进内容**：
- 明确执行时机：所有 feature spec 生成完成后
- 详细的提取步骤（8 个方面）
- 验证内容完整性

### 修复 2: 禁止生成 placeholder 文件

**更新**: `SKILL.md` Step C3 和 Step C5

**改进内容**：

Step C3 新增约束：
```markdown
**关键约束**：
- **只生成真实功能的 spec**，不生成 placeholder 文件
- ❌ 不生成 `feat_XXX_placeholder.md` 文件
```

Step C5 新增检查：
```markdown
**Findings 报告**：
- 生成了 placeholder 文件 → `SPEC.PLACEHOLDER_FILE_GENERATED`（精确类，blocking）
```

### 修复 3: 强化验收标准穷举要求（核心修复）

**更新**: `templates/feature-spec-template.md`

**改进内容**：

#### 3.1 明确 AC 原子性 + 穷举铁律

```markdown
### AC 原子性 + 穷举铁律（无论 complexity）

`## 验收标准` 必须**始终位于主文件**，每条 `- [ ]` 必须**原子且可断言**。

**核心要求**：
1. **原子性**：每条 AC 独立可测
2. **穷举性**：必须穷举所有可枚举的分支——"少而精"是 anti-pattern
   - 每种功能单独成 AC
   - 每个 UI 元素单独成 AC
   - 每种错误路径单独成 AC
3. **可追溯**：每条 AC 带稳定 ID，精确追溯到源码
```

#### 3.2 提供详细的穷举示例

新增 20 个 AC 的完整示例（数据存储功能）：
- 初始化（3 个 AC）
- CRUD - 创建（5 个 AC）
- CRUD - 读取（5 个 AC）
- CRUD - 更新（4 个 AC）
- CRUD - 删除（3 个 AC）
- 关系管理（2 个 AC）
- UI 集成（3 个 AC）
- 错误处理（2 个 AC）

#### 3.3 提高 AC 数量最低要求

| 复杂度 | 改进前 | 改进后 |
|--------|-------|-------|
| simple | ≥ 5 个 | ≥ 8 个 |
| medium | ≥ 8 个 | ≥ 15 个 |
| complex | ≥ 12 个 | ≥ 25 个 |
| very_complex | ≥ 15 个 | ≥ 30 个 |

#### 3.4 在 SKILL.md 中强化要求

Step C3 新增：
```markdown
**穷举要求**（验收标准）：
1. **CRUD 完整性**：每个操作单独成 AC
2. **UI 元素穷举**：每个按钮、列表、输入框单独成 AC
3. **错误路径穷举**：每种错误情况单独成 AC
4. **关系管理**：每种关系操作单独成 AC
5. **集成验证**：每个 UI 集成点单独成 AC
```

Step C5 新增检查：
```markdown
- [ ] 验收标准数量符合最低要求
      (simple ≥8, medium ≥15, complex ≥25, very_complex ≥30)
- [ ] 每个 AC 都有完整格式（`源: → 标: | 判: | 真:`）

**Findings 报告**：
- 验收标准数量不足 → `SPEC.AC_INSUFFICIENT`（精确类，blocking）
- AC 格式不完整 → `SPEC.AC_FORMAT_INVALID`（精确类，blocking）
```

---

## 📊 对比：改进前 vs 改进后

### 验收标准示例对比

**改进前**（不符合要求）：
```markdown
## 验收标准
- [ ] F001-AC01 CRUD 操作正常工作
- [ ] F001-AC02 数据持久化成功
- [ ] F001-AC03 UI 正确显示
```
**问题**：笼统、不可测试、没有穷举

**改进后**（符合要求）：
```markdown
## 验收标准

### 初始化
- [ ] F001-AC01 应用启动时 BrewStore 自动初始化数据库
      `源:BrewStore.init() → 标:BrewStore.init(context)`
      `判:contract | ModelContainer 创建成功`
      `真:App/Data/BrewStore.swift:45`

- [ ] F001-AC02 数据库文件创建在正确位置
      `源:ModelContainer(schema) → 标:getRdbStore(config)`
      `判:data | 数据库文件存在于 files/cuike.db`
      `真:App/Data/BrewStore.swift:48`

### CRUD - 创建
- [ ] F001-AC03 addBean() 成功插入新咖啡豆记录
      `源:BrewStore.addBean(_:) → 标:BrewStore.addBean(bean)`
      `判:contract | 返回插入的 BeanRecord`
      `真:App/Data/BrewStore.swift:120`

... (共 25+ 个 AC)
```
**优势**：原子、可测试、完整穷举、精确追溯

---

## 🎯 预期效果

### 下次执行 i2h-spec 后

1. ✅ **生成 feature-base.md**
   - 统一说明共享基础设施
   - 避免重复描述

2. ✅ **不生成 placeholder 文件**
   - 只生成真实功能的 spec
   - 产物清晰

3. ✅ **验收标准详细且完整**
   - simple 功能：8+ 个 AC
   - medium 功能：15+ 个 AC
   - complex 功能：25+ 个 AC
   - 每个 AC 原子、可测试、可追溯

---

## 📝 修改的文件

1. `migbot/skills/i2h-spec/SKILL.md`
   - Step C3: 强化验收标准要求
   - Step C4: 详细的 feature-base 生成步骤
   - Step C5: 新增验证检查

2. `migbot/skills/i2h-spec/templates/feature-spec-template.md`
   - 重写"验收标准"段落
   - 新增 AC 原子性 + 穷举铁律
   - 提供详细的 20 个 AC 示例
   - 提高 AC 数量最低要求

---

## ✅ 验证清单

下次执行 i2h-spec 后，验证：

- [ ] `spec/baseline/feature-base.md` 存在且内容完整
- [ ] 没有 `feat_XXX_placeholder.md` 文件
- [ ] 每个 feature spec 的 AC 数量符合最低要求
- [ ] 每个 AC 格式完整（`源: → 标: | 判: | 真:`）
- [ ] AC 内容具体、原子、可测试

---

**改进完成时间**: 2024-11-03  
**版本**: v2.2  
**改进者**: Claude Opus 5.5
