---
description: 验证配置并运行 hvigorw assembleHap 编译鸿蒙项目
allowed-tools: Bash(.migbot/bin/i2h-tool *), Bash(.migbot/bin/i2h *)
---

## 目标

编译鸿蒙项目以验证迁移结果。

## 步骤

### 1. 验证配置

运行 `.migbot/bin/i2h-tool validate` 检查所有必需路径。

如果返回 `{ok:false}`：
- 向用户列出每个失败项
- 建议运行 `/i2h-init` 修复路径
- 停止

### 2. 运行构建

运行 `.migbot/bin/i2h-tool build` 编译项目。

实时流式输出到用户。

报告最终退出码：
- 退出 0: ✅ 构建成功
- 非零: ❌ 构建失败

### 3. 报告 token 用量

运行 `Bash: .migbot/bin/i2h mark-stage i2h-build` 记录此阶段的 token 用量。

这是尽力而为且需要用户同意的 — 忽略其退出状态（永远不影响构建结果）。

### 4. 显示构建产物

如果构建成功，显示 HAP 文件位置：
```
✅ 构建成功

HAP 文件: entry/build/default/outputs/default/entry-default-unsigned.hap

下一步:
  - 安装: hdc install <hap-file>
  - 运行: hdc shell aa start -a EntryAbility -b <bundle-name>
```

如果构建失败，显示错误摘要并建议下一步：
```
❌ 构建失败

常见问题:
  1. 缺少依赖: 检查 oh-package.json5
  2. 语法错误: 查看上面的错误日志
  3. 路径问题: 重新运行 /i2h-init

详细错误日志: entry/build/default/cache/default/*/compiler.log
```
