# tool-optimization Skill 使用指南

## Skill 位置

```
~/Codes/ios2harmony/hmigbot-ios/migbot/skills/tool-optimization/SKILL.md
```

## 在其他会话中调用

### 方法 1: 使用相对路径（推荐）

如果你在 `hmigbot-ios` 项目目录下：

```bash
# 在 Codex 中
Read migbot/skills/tool-optimization/SKILL.md
```

### 方法 2: 使用绝对路径

```bash
# 在任何会话中
Read ~/Codes/ios2harmony/hmigbot-ios/migbot/skills/tool-optimization/SKILL.md
```

### 方法 3: 使用 Skill 调用（如果配置了）

```bash
# 如果 hmigbot-ios 的 skills 已加载
/tool-optimization
```

## 典型使用场景

### 场景 1: 开始优化新命令

```
我：现在要优化 i2h-plan，参考 tool-optimization skill

模型:
1. Read ~/Codes/ios2harmony/hmigbot-ios/migbot/skills/tool-optimization/SKILL.md
2. 执行阶段 1：理解原版设计（研究 a2h-plan）
3. ...
```

### 场景 2: 遇到问题时查阅

```
我：i2h-plan 生成的产物有问题，怎么排查？

模型:
1. Read tool-optimization skill § 13 经验教训
2. 对比 Android 版本产物
3. 检查是否理解了设计理念
4. ...
```

### 场景 3: 验证改进效果

```
我：i2h-plan 改进完成，如何验证？

模型:
1. Read tool-optimization skill § 13.6 验证的重要性
2. 执行代码审查（静态）
3. 实际执行（动态）
4. 用户验证（真实场景）
```

## Skill 内容概览

### 核心流程（6 阶段）

```
1. 理解原版设计
   └─ 研究 Android 版本的 SKILL.md, references, 产物

2. 分析当前问题
   └─ 识别架构偏离、功能缺失

3. 对比产物差异
   └─ 生成详细对比报告

4. 制定改进计划
   └─ P0/P1/P2 分级

5. 执行改进
   └─ 更新模板、SKILL.md、references

6. 验证和文档
   └─ 实际执行 + 用户反馈
```

### 关键章节

- **§1-6**: 核心优化流程（必读）
- **§7**: 阶段 5 执行改进的详细步骤
- **§8**: 关键经验总结（常见陷阱）
- **§13**: 经验教训（v2.2 补充，包含用户反馈案例）
- **§14**: 总结和成功因素

### 重要经验（§13 新增）

1. **用户反馈的重要性** - 实际执行才能发现问题
2. **理解设计理念** - 不只复制格式，要理解为什么
3. **门禁检查的完整性** - 检查"有什么"也检查"没有什么"
4. **分阶段改进** - 快速迭代，不追求一次完美
5. **模板的详细程度** - 要有完整示例，不只格式说明
6. **验证的重要性** - 代码审查 + 实际执行 + 用户验证

## 快速参考

### 对比 Android 版本产物

```bash
# 查看 Android 版本产物
ls -la ~/DevEcoStudioProjects/JetSnackHarmony/spec/

# 查看 iOS 版本产物
ls -la ~/DevEcoStudioProjects/Cuike02/spec/

# 对比文件数量
diff <(cd JetSnackHarmony/spec && find . -type f | sort) \
     <(cd Cuike02/spec && find . -type f | sort)
```

### 检查产物质量

```bash
# 检查是否有 placeholder 文件
ls spec/baseline/features/*_placeholder.md 2>/dev/null

# 检查验收标准数量
for f in spec/baseline/features/feat_*.md; do
  ac_count=$(grep -c "^- \[ \] F[0-9]\+-AC[0-9]\+" "$f")
  echo "$f: $ac_count AC"
done
```

## 注意事项

1. **每次改进都要对比原版** - 不要重新发明轮子
2. **必须实际执行验证** - 不能只看代码
3. **欢迎用户反馈** - 这是最真实的验证
4. **记录改进过程** - 生成对比报告和改进总结
5. **持续迭代** - 根据反馈不断改进

## 更新历史

- v1.0 (2024-11-03): 基于 i2h-spec v2.0-v2.1 改造经验
- v1.1 (2024-11-03): 补充 v2.2 修复经验（§13 经验教训）

---

**维护**: 每次改进后更新此 skill，记录经验教训  
**路径**: `~/Codes/ios2harmony/hmigbot-ios/migbot/skills/tool-optimization/SKILL.md`
