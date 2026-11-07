# Project Status

**更新日期**: 2026-11-06  
**基线**: `hmigbot-1.8.0`（Android → HarmonyOS）  
**目标**: iOS → HarmonyOS（ArkTS）

## 当前结论

仓库已经完成主要 i2h Skill 的文档和骨架改造，具备继续工程化的基础。当前结论是“可审计的开发基线”，不是“已通过端到端验收的生产工具”。

## 阶段状态

| 阶段 | 当前状态 | 证据 | 主要限制 |
|---|---|---|---|
| i2h-spec | 文档与模板已形成 | `migbot/skills/i2h-spec/` | 依赖若干未落地的 helper/ledger 脚本，需补存在性门禁 |
| i2h-plan | indexed-v1 计划规范和 linter 已有 | `migbot/skills/i2h-plan/` | `/i2h-run` 仍检查旧 JSON 标记，需统一产物契约 |
| i2h-execute | 编排规范、资源/writeback 工具和二进制包装器已在仓库 | `migbot/skills/i2h-execute/` | Python 测试不能直接导入包装器，部分依赖模块缺失 |
| i2h-verify | 静态分析、身份解析、截图对比工具可运行 | `migbot/skills/i2h-verify/` | CHECK-5 明确 deferred；真实设备端到端验证尚未形成 CI |
| i2h-retrospect | 报告模板和指标流程已有 | `migbot/skills/i2h-retrospect/` | 模板仍含 Cuike 示例硬编码，必须改成运行时数据 |

## 已验证事实

- `./install.sh` 可以把命令、Skill、脚本和 `spec/` 骨架复制到临时 HarmonyOS 工程。
- 安装结果没有生成 `.migbot/bin/i2h` 或 `.migbot/bin/i2h-tool`，因此依赖它们的命令当前不能视为可用。
- `i2h-verify/scripts/ios_static_analyzer.py` 和 `ios_config_parser.py` 能在本地样例上运行并输出 JSON。
- `i2h-execute/scripts/tests/` 当前无法通过标准 unittest 入口运行：测试导入二进制 launcher，且部分被导入模块不存在。

## 近期优先级

1. 补齐或移除 `i2h` / `i2h-tool` 运行时入口，并让安装脚本做安装后 smoke test。
2. 统一 i2h-spec、i2h-plan、i2h-execute、i2h-verify 的产物路径和完成标记。
3. 把编译二进制包装器和可测试 Python 实现分离，恢复 execute 测试。
4. 补齐 `gate_ledger.py`、`build-dependencies.json` 指向的 helper，或将缺口显式降级为 DEFERRED。
5. 在 Cuike 和一个最小 UIKit/SwiftUI fixture 上跑完整 spec → plan → execute → verify，记录真实编译与行为证据。
