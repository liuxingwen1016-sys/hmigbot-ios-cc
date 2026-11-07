# Project Status

**更新日期**: 2026-11-06  
**基线**: `hmigbot-1.8.0`（Android → HarmonyOS）  
**目标**: iOS → HarmonyOS（ArkTS）

## 当前结论

仓库已经完成主要 i2h Skill 的文档和骨架改造，具备继续工程化的基础。当前结论是“可审计的开发基线”，不是“已通过端到端验收的生产工具”。

## 阶段状态

| 阶段 | 当前状态 | 证据 | 主要限制 |
|---|---|---|---|
| i2h-spec | 文档、模板、静态 UI/资源证据和最小 gate ledger 已形成 | `migbot/skills/i2h-spec/` | 真实 simulator 状态、dialog 枚举和完整 detector registry 仍待补齐 |
| i2h-plan | indexed-v1 计划规范、linter 和 schema-2 UI delivery 脚本已有 | `migbot/skills/i2h-plan/` | 需把 delivery inventory 接入完整 `/i2h-run` fixture |
| i2h-execute | 编排规范、资源/writeback 工具和依赖清单已在仓库 | `migbot/skills/i2h-execute/` | Python 测试仍不能直接导入打包 launcher，需拆分可导入实现 |
| i2h-verify | 静态分析、身份解析、截图对比工具可运行 | `migbot/skills/i2h-verify/` | CHECK-5 明确 deferred；真实设备端到端验证尚未形成 CI |
| i2h-retrospect | 报告模板和指标流程已有 | `migbot/skills/i2h-retrospect/` | 模板仍含 Cuike 示例硬编码，必须改成运行时数据 |

## 已验证事实

- `./install.sh` 和 `migbot/install.sh --ios ...` 可以把命令、Skill、脚本、`spec/` 骨架以及 `.migbot/bin/i2h`、`i2h-tool`、`i2h-bootstrap` 复制到临时 HarmonyOS 工程。
- 三个运行时入口已实跑 `validate`、`count-lines`、`mark-stage`；事实只写本地可审计 JSON，不宣称远程上传成功。
- `ui_evidence.py` 已在 Cuike iOS 项目上生成 22 个视图、资源索引和统一 `target_input_sha256`。
- `i2h-verify/scripts/ios_static_analyzer.py` 和 `ios_config_parser.py` 能在本地样例上运行并输出 JSON。
- `i2h-execute/scripts/tests/` 当前无法通过标准 unittest 入口运行：测试导入二进制 launcher，且部分被导入模块不存在。

## 近期优先级

1. 把编译二进制包装器和可测试 Python 实现分离，恢复 execute 测试。
2. 扩展 gate ledger 的 iOS registry，并把 schema-2 UI delivery 接入完整 `/i2h-run` fixture。
3. 接入依赖就绪调度器、超时/停滞回收和真实 HOST_MAX 运行时记录。
4. 在 Cuike 和一个最小 UIKit/SwiftUI fixture 上跑完整 spec → plan → execute → verify，记录真实编译与行为证据。
