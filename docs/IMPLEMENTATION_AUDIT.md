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
| 流水线完成标记曾经不一致，已完成文档修正 | `migbot/commands/i2h-run*.md` 使用 indexed-v1 marker；`tests/test_e2e_i2h_fixture.py` 已覆盖五阶段 marker、前置依赖和恢复顺序 | 当前本地恢复语义有回归保护；完整 Claude 编排仍需 CI/真实工程验证 | 保留 indexed-v1 Markdown 为唯一格式，将 fixture 接入 CI，并为旧路径提供显式兼容解析 |
| execute 测试不可导入（已修复） | `i2h-execute/scripts/lib/` 现提供可导入实现，顶层脚本变为 import-safe launcher shim；`stage1_contract`、`stage1_wiring_checks` 等兼容模块已纳入源码 | 标准 unittest 已可启动并验证门禁行为；真实打包二进制仍需跨平台运行 | 保留 launcher 的 bundled-binary 优先策略；CI 在 macOS ARM64/Windows x64 复跑同一套源码测试和最小 smoke |

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
| 缺少跨平台 CI（最小 fixture 已补） | `tests/test_e2e_i2h_fixture.py` 覆盖 SwiftUI/UIKit 混合输入、资源哈希、delivery ownership、五阶段 marker 恢复和 static-only/DEFERRED 边界；尚未接入 CI | 本地可回归静态契约，真实设备和 DevEco 行为仍需实机 | 将 fixture 接入 CI，并在 macOS ARM64/Windows x64 运行同一套命令；设备/编译缺失只能记录 DEFERRED |
| 安装白名单仍混入 Android 命名（已修复） | 安装器已移除 `a2h-join`；主插件只复制 i2h/iOS/ArkTS 入口，旧 a2h runtime 随 legacy plugin 保存 | 新安装不再把历史 Android 工具带入 iOS 项目 | 继续对通用 ArkTS 能力中的 Android 语境做逐项中性化，避免 description 抢路由 |
| 直接 plugin-dir 会发现旧 Android skills（已修复） | 17 个 `a2h-*`/`android-*` Skill、旧增量命令、Android agents 与 `a2h` runtime 已移至根目录 `legacy-android` sibling plugin；主 `migbot/skills` 不再包含这些目录 | iOS 自然语言路由不会加载历史 Android pipeline；需要旧链时必须显式加载兼容插件 | 主插件与 legacy 插件分别执行 `claude plugin validate --profile directory --strict`；ArkTS 通用能力中仍有少量 Android 语境参考，后续按 iOS 证据模型逐项中性化 |

## 已执行的验证

- `python3 -m py_compile`：i2h-spec/plan/execute/verify/retrospect 下 Python 文件语法通过。
- `./install.sh` 和 `migbot/install.sh --ios ...` 临时工程 smoke test：安装返回 0，`.migbot/bin/i2h`、`i2h-tool`、`i2h-bootstrap` 均可执行；`validate`、`count-lines`、`mark-stage` 已实跑。
- `python3 -m unittest discover -s migbot/skills/i2h-spec/scripts/tests`：2 个 gate-ledger 契约测试通过；`i2h-plan` 契约测试 5 个通过；资源转换测试 2 个通过；调度器测试 3 个通过。
- `ios_static_analyzer.py` 在 `CuikeHarmony` 上运行成功，得到 0 ERROR、3 WARN；这证明脚本能运行，不证明迁移结果完整。
- `ios_config_parser.py` 在 Cuike iOS 项目上运行成功，能读取 Info.plist 和 AppIcon；Bundle ID/版本仍是构建变量，不能直接当作最终身份通过。
- execute 测试入口已修复：`python3 -m unittest discover -s migbot/skills/i2h-execute/scripts/tests -p 'test_*.py'` 当前 93/93 通过；离线 E2E fixture 也已通过。

## 修复验收顺序

1. 运行时入口和安装 smoke test；
2. 计划/阶段产物契约统一；
3. execute 源码实现与测试恢复；
4. gate ledger 和依赖 manifest 完整性；
5. 最小 fixture 的完整五阶段运行；
6. Cuike + UIKit/混合项目真实编译、设备和回归；
7. 最后才更新 README、CHANGELOG 和生产状态。
