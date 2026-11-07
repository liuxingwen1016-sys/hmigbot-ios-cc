# hmigbot-ios 实现审计

**审计日期**: 2026-11-06  
**参考基线**: `../hmigbot-1.8.0`  
**审计方式**: 阅读过程文档、对照原版目录、检查引用路径、执行安装 smoke test、执行 Python 编译和 verify 脚本 smoke test。

## 结论

当前工程已经形成 iOS 迁移的设计骨架，但还没有形成可证明的端到端闭环。最大风险不是单个映射规则，而是“文档声称的流水线”和“实际可执行入口、产物路径、测试模块”之间存在断裂。

## P0：必须先修复

| 问题 | 证据 | 影响 | 修复方案 |
|---|---|---|---|
| 运行时入口缺失（已修复） | 旧版安装结果只有 `.migbot/bin/scripts/`；本轮已新增可移植 `migbot/bin/i2h`、`i2h-tool`、`i2h-bootstrap` 并由安装器复制/校验 | 旧问题会导致 `/i2h-build`、各阶段 `mark-stage`、`count-lines` 无法执行；当前已有本地事实和阶段 marker | 保留 Python 入口作为 Claude Code 兼容真源；安装 smoke test 必须继续覆盖三个入口 |
| 流水线完成标记曾经不一致，已完成文档修正 | 本轮已将 `migbot/commands/i2h-run*.md` 改为读取 `spec/baseline/plans/complete.txt`；仍缺端到端 marker 测试 | 修正前会重复执行 plan 或误判阶段未完成；当前风险转为“没有回归测试保护” | 保留 indexed-v1 Markdown 为唯一格式，给五个阶段各写最小 completion-marker fixture，并在 CI 验证恢复逻辑 |
| execute 测试不可导入 | `migbot/skills/i2h-execute/scripts/*.py` 多数是导向 `_entry.bin` 的 launcher；测试直接 `import build_writeback`、`stage1_*`，会触发进程替换；`stage1_contract`、`stage1_wiring_checks` 等模块不在源码目录 | 标准 unittest 无法启动，无法证明门禁脚本行为 | 把业务实现放入 `lib/` 或 `impl/` 可导入模块，launcher 只负责 CLI；把测试依赖模块纳入源码；CI 同时测源码模式和打包模式 |

## P1：完成主链前必须处理

| 问题 | 证据 | 影响 | 修复方案 |
|---|---|---|---|
| execute 依赖清单指向不存在文件（已修复） | 已新增 `i2h-spec/scripts/ui_evidence.py`、`runtime_view.py` 与 `i2h-plan/scripts/ui_delivery.py`、`source_layout.py`、`ui_state_ownership.py`，并补充契约测试 | 资源证据、schema-2 UI delivery 和源码布局义务现在有可运行输入；完整设备闭环仍需真实工程验证 | 继续把 manifest 路径检查纳入 CI，禁止新增悬空依赖 |
| gate ledger 只有最小 iOS 实现 | 已新增 `i2h-spec/scripts/gate_ledger.py`，支持 classify/check/release、unknown/exact/hard 规则阻断和 verify-focus 输出；尚未覆盖原版全部 detector 汇总 | verify 可以读取并拒绝明显不安全放行，但不能把它当作原版完整门禁注册表 | 继续扩展 iOS gate registry 和 detector 证据校验，补 malformed/open-findings 回归 |
| i2h-spec helper 名称和安装目录不一致（已修复） | Phase A 现在由 `i2h-spec/scripts/ui_evidence.py` 生成骨架和资源事实；7 个 iOS Skill 已统一为 Claude Code 规范的 `SKILL.md` | 不再依赖不存在的 `ios-project-scanner`/`ios-view-analyzer` 路径；LLM 语义补充仍需按文档执行 | 继续增加 existence gate 和失败 findings，避免脚本故障被静默降级 |
| 资源转换仍需扩大闭包覆盖（部分修复） | 已新增 `resources-inventory`→`res-index` 生成器；resource worker 已支持全部声明图片变体、PDF/SVG、暗黑色彩、重复文件名和多语言记录；SF Symbols、Storyboard 关联和完整引用闭包仍未完全落地 | 页面生成前能发现更多资源缺口，但不能把当前索引当作完整资源等价证明 | 将 `usage` unresolved、SF Symbols 和 Storyboard 依赖接入 Gate B/Stage 0，并补真实项目回归 |
| execute 的阶段模型与原版契约混杂 | 当前 `i2h-execute/SKILL.md` 采用“Spec 解析 → Feature 设计 → 代码生成 → 编译”的 5 段叙述，但 references 和原版契约要求 Stage 0/1/2/3、Base-7、Stage 3 gate、FV-2 | 主流程、计划模板和验证门的语义不一致，无法判断哪个阶段负责什么 | 选定一个正式状态机；建议保留原版 Stage 0/1/2/3 + FV 结构，将 iOS 语义映射写到各 Stage，而不是另起一套阶段名 |
| verify 的“生产就绪”结论没有真实端到端证据 | `docs/archive/i2h-verify/i2h-verify-production-ready.md` 写“生产就绪”，但 CHECK-5 明确 deferred，CHECK-3 依赖设备，审计未发现真实 iOS→HarmonyOS 全流程记录 | 用户会把脚本可运行误解为迁移结果可交付 | 将状态改为“工具脚本可用、端到端待验证”；补真实项目安装、编译、截图、行为和回归证据后再升级 |

## P2：质量和维护问题

| 问题 | 证据 | 影响 | 修复方案 |
|---|---|---|---|
| 根目录文档互相矛盾 | 旧文档同时出现 40%、75%、90%、100% 和“生产就绪”；已归档的 `FINAL_100_PERCENT.md` 没有验证证据 | 接手者无法判断当前状态 | 保留历史原文但全部归档；根目录只保留当前文档，所有数字写明来源和范围 |
| README_CN 引用不存在命令 | 旧版列出 `/i2h-privacy` 和 `/i2h-privacy-zh`，仓库没有对应 command | 新用户会执行失败 | 已从当前 README_CN 移除；若需要隐私检查，新增独立 Skill 后再加入入口 |
| retrospect 模板含 Cuike 硬编码 | `migbot/skills/i2h-retrospect/SKILL.md` 的代码规模、页面数、自动转换率和时间是固定示例 | 任意项目都会生成虚假报告 | 全部改为从 manifest、git diff、编译日志和 verify 报告读取；无数据时输出 `UNKNOWN/DEFERRED` |
| 历史报告把估算写成事实 | `CUIKE_*`、`FINAL_*`、`docs/i2h-*-production-ready.md` 中大量使用“100%”“生产级”“预计达成” | 评估结果失真 | 用“历史原型估算”“设计目标”“已验证”三种标签；禁止无证据的通用指标 |
| 缺少跨平台 CI 和最小 fixture | 当前没有看到覆盖 install → spec → plan → execute → verify 的可重复 CI | 回归只能靠人工和模型记忆 | 增加最小 SwiftUI、UIKit 混合、资源和失败门禁 fixture；在 macOS ARM64/Windows x64 运行同一套命令 |
| 安装白名单仍混入 Android 命名 | `migbot-install.py` 仍安装 `a2h-join` 等旧命名工具 | 语义混乱，后续维护者难以知道是否平台相关 | 将真正通用的工具改成中性命名；保留兼容别名时在 manifest 中标注来源和适用范围 |
| 直接 plugin-dir 会发现旧 Android skills | Claude Code 会扫描 `migbot/skills/` 下所有 `SKILL.md`；安装器白名单已主要限制为 i2h/iOS/ArkTS，但插件目录仍包含 `a2h-*`/`android-*` 历史 skill | iOS 迁移自然语言触发时可能被旧 Android skill 抢路由 | 后续拆分 `hmigbot-ios` 与 Android 参考包，或使用 Claude Code 支持的显式组件清单；当前保留目录是为了不破坏旧 references |

## 已执行的验证

- `python3 -m py_compile`：i2h-spec/plan/execute/verify/retrospect 下 Python 文件语法通过。
- `./install.sh` 和 `migbot/install.sh --ios ...` 临时工程 smoke test：安装返回 0，`.migbot/bin/i2h`、`i2h-tool`、`i2h-bootstrap` 均可执行；`validate`、`count-lines`、`mark-stage` 已实跑。
- `python3 -m unittest discover -s migbot/skills/i2h-spec/scripts/tests`：2 个 gate-ledger 契约测试通过；`i2h-plan` 契约测试 5 个通过；资源转换测试 2 个通过；调度器测试 3 个通过。
- `ios_static_analyzer.py` 在 `CuikeHarmony` 上运行成功，得到 0 ERROR、3 WARN；这证明脚本能运行，不证明迁移结果完整。
- `ios_config_parser.py` 在 Cuike iOS 项目上运行成功，能读取 Info.plist 和 AppIcon；Bundle ID/版本仍是构建变量，不能直接当作最终身份通过。
- execute 测试入口仍未修复：`unittest discover` 会被 `build_writeback.py` 等打包 launcher 的参数解析接管；这仍是下一轮必须拆分 `lib/` 实现与 CLI launcher 的 P0。

## 修复验收顺序

1. 运行时入口和安装 smoke test；
2. 计划/阶段产物契约统一；
3. execute 源码实现与测试恢复；
4. gate ledger 和依赖 manifest 完整性；
5. 最小 fixture 的完整五阶段运行；
6. Cuike + UIKit/混合项目真实编译、设备和回归；
7. 最后才更新 README、CHANGELOG 和生产状态。
