# 重要说明：Skill 修改的同步机制

## 问题发现

在本次会话中发现了一个关键问题：

**修改位置**: `/Users/liuxingwen/DevecoStudioProjects/Cuike01/.claude/skills/i2h-verify/skill.md`  
**源码位置**: `/Users/liuxingwen/Codes/ios2harmony/hmigbot-ios/migbot/skills/i2h-verify/SKILL.md`

修改只在运行时目录，没有自动同步回源码仓库！

---

## 目录结构说明

### 源码仓库（hmigbot-ios）

```
/Users/liuxingwen/Codes/ios2harmony/hmigbot-ios/
└── migbot/
    └── skills/
        ├── i2h-spec/SKILL.md
        ├── i2h-plan/SKILL.md
        ├── i2h-execute/SKILL.md
        ├── i2h-verify/SKILL.md      ← 源码
        └── i2h-retrospect/SKILL.md
```

### 运行时目录（Cuike01 项目）

```
/Users/liuxingwen/DevecoStudioProjects/Cuike01/
└── .claude/
    └── skills/
        ├── i2h-spec/skill.md
        ├── i2h-plan/skill.md
        ├── i2h-execute/skill.md
        ├── i2h-verify/skill.md      ← 运行时副本（本次修改在这里）
        └── i2h-retrospect/skill.md
```

**注意文件名差异**:
- 源码: `SKILL.md`（大写）
- 运行时: `skill.md`（小写）

---

## 安装流程

当运行 `./install.sh --project /path/to/project --ios /path/to/ios` 时：

```bash
1. 读取 hmigbot-ios/migbot/skills/*/SKILL.md
2. 复制到 project/.claude/skills/*/skill.md
3. 创建 .migbot/config.json
```

**关键点**: 这是**单向复制**，修改运行时文件**不会自动回源码**！

---

## 同步机制（重要！）

### 开发 Skill 时的正确流程

#### ❌ 错误做法
```
1. 修改 Cuike01/.claude/skills/i2h-verify/skill.md
2. 测试通过
3. 忘记同步回源码
4. 下次安装到其他项目时，还是旧版本！
```

#### ✅ 正确做法

**方案 1: 直接修改源码**（推荐）
```bash
1. 修改 hmigbot-ios/migbot/skills/i2h-verify/SKILL.md
2. 重新安装到测试项目
   cd hmigbot-ios
   ./install.sh --project /path/to/Cuike01 --ios /path/to/cuike-ios
3. 测试验证
4. 提交 Git
```

**方案 2: 修改后同步回源码**（本次采用）
```bash
1. 修改 Cuike01/.claude/skills/i2h-verify/skill.md
2. 测试通过
3. 同步回源码:
   cp Cuike01/.claude/skills/i2h-verify/skill.md \
      hmigbot-ios/migbot/skills/i2h-verify/SKILL.md
4. 提交 Git
```

**方案 3: 创建符号链接**（高级）
```bash
# 开发阶段，让运行时目录直接指向源码
ln -s /path/to/hmigbot-ios/migbot/skills/i2h-verify \
      /path/to/Cuike01/.claude/skills/i2h-verify
```

---

## 本次会话的同步

### 已完成的同步

```bash
# 同步命令
cp /Users/liuxingwen/DevecoStudioProjects/Cuike01/.claude/skills/i2h-verify/skill.md \
   /Users/liuxingwen/Codes/ios2harmony/hmigbot-ios/migbot/skills/i2h-verify/SKILL.md

# Git 提交
git add migbot/skills/i2h-verify/SKILL.md
git commit -m "feat: 同步 i2h-verify 的完整修改到源码仓库"
```

### 验证

```bash
# 文件大小对比
Cuike01/.claude/skills/i2h-verify/skill.md:  22,480 字节
hmigbot-ios/migbot/skills/i2h-verify/SKILL.md: 22,480 字节
✅ 已同步
```

---

## 未来会话的注意事项

### 下次修改 Skill 时

1. **明确修改位置**: 
   - 开发测试 → Cuike01/.claude/skills/
   - 源码管理 → hmigbot-ios/migbot/skills/

2. **及时同步**: 
   - 测试通过后立即同步回源码
   - 提交 Git 前检查是否已同步

3. **验证一致性**:
   ```bash
   diff -q Cuike01/.claude/skills/xxx/skill.md \
           hmigbot-ios/migbot/skills/xxx/SKILL.md
   ```

4. **文档说明**: 
   - 在 commit message 中说明是否已同步
   - 在 HANDOVER.md 中说明修改位置

---

## 检查清单

在提交代码前，检查：

- [ ] 运行时的修改是否已同步回源码？
- [ ] 文件大小是否一致？
- [ ] Git status 是否包含源码文件？
- [ ] commit message 是否说明了同步？

---

## 影响范围

### 本次会话的修改

**已同步的文件**:
- ✅ i2h-verify/SKILL.md (22,480 字节)

**未修改的文件**（无需同步）:
- i2h-spec/SKILL.md
- i2h-plan/SKILL.md
- i2h-execute/SKILL.md
- i2h-retrospect/SKILL.md

---

## 建议：下次优化 i2h-spec

**直接修改源码**，避免再次遗忘同步：

```bash
# 1. 修改源码
vim /Users/liuxingwen/Codes/ios2harmony/hmigbot-ios/migbot/skills/i2h-spec/SKILL.md

# 2. 重新安装
cd /Users/liuxingwen/Codes/ios2harmony/hmigbot-ios
./install.sh --project /Users/liuxingwen/DevecoStudioProjects/Cuike01 \
             --ios /Users/liuxingwen/Codes/ios2harmony/cuike-ios

# 3. 测试验证（在 Cuike01 中运行 /i2h-spec）

# 4. 提交 Git
git add migbot/skills/i2h-spec/SKILL.md
git commit -m "..."
```

这样可以避免忘记同步的问题！

---

**创建时间**: 2024-11-02  
**重要性**: ⭐⭐⭐⭐⭐  
**下次会话**: 务必遵循正确流程
