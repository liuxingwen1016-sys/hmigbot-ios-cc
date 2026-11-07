# 1030 与完整 UI 交付模式

Plan 审批的 `stage1-ui-delivery.json` 使用 schema 2、`delivery_contract=full-ui-v2`、
`visual_policy=required`。这是完整交付的独立入口；未采用该契约的 1030 冒烟/Preview 流程
保留原来的 S1-V 用户选择。后者的 SKIP 不满足完整 UI 契约。

## 生成与装配

1. 按源码审阅唯一组件、真实 states、shell/content/overlay 责任、宿主 ROI、正式/Preview 到达、
   toolchain、presentation、state_setup。整页组合验证单列 owner 和 implementation_units。
   运行 `ui_delivery.py review` 后按 1030 的审批规则批准最终清单，使用实际用户或 default-policy
   决策引用；保留审批来源，不能把自动决策标成用户确认。
2. Spec 使用 schema 3 mapping 和 runtime-refs，原始 PNG/XML 保留在 run。
   `ui_delivery_inputs.py --project-root <project> --inventory <inventory>` 冻结输入，
   `validate_runtime_snapshots.py --project-root <project>` 校验 packet。
3. 并发、空信封和停滞回收 MUST READ stage1-dispatch.md，复用①–④、⑥–⑦；⑤逐批 closer 在本模式改为全量 G0 后统一 closer。
   每单元 `ui_dispatch.py prepare` 的 prompt 全文进入派发；明确输入身份、摘要与图片路径。
   源码决定布局，runtime 选状态并验证；读取 source layout obligations、代表帧/必需扩展帧及共享解析树。
   原始代码和报告写完立即 complete 保存 G0，检查失败也保留首次结果，修复使用新 attempt。
4. 所有生成批完成后 `stage1_acceptance.py --kind g0` 汇总原始输出，再由一个 closer 按完整
   inventory 装配；保留 1030 的 route-root、wrapper/typed params、资源及源尺寸复核规则。
   Batch 仅调度生成，不在中间批改写原始输出。writeback `stage1.phase=assembled` 只表示 STRUCTURAL_ONLY。
5. 静态装配后归档 G1，运行 ui_stage1_gate；它在有 frozen index 时路由到完整交付检查。
   无 index 的旧模式继续使用 1030 的显式 wiring bindings、entry 与 Preview 检查。

## 构建、实际到达与 S1-V

生成 `stage1_visual_scope.py --project-root <project> --out <scope>`；完整模式返回
`scope=stage1_delivery` 的 pairs，来自批准清单的全部 required states/regions/frames，包含缺基线项。
旧 `scope=stage1_wired` 的 units/pages 不混入本报告；交给原 stage1_capture_scope 处理。

Stage 1 验证包由 hmos-builder 以 STAGE_HINT=stage-1-ui-delivery、MAX_ITER=1、--build-only
执行一次真实构建。Execute 的验收账本计数：初次构建加最多两轮修复，视觉同样初次加最多两轮。
构建修复改变代码后必须重建；不在一次回执内隐藏额外循环。

两个模式使用 stage1_contract.source_digest：覆盖 AppScope、各模块 src/main、构建/依赖配置和
hvigorfile。构建/安装回执继续使用 1030 字段：kind=build/install、status=PASS、unit_id、
source_sha256、hap_sha256；build 有项目相对 hap_path，install 有实际 device_id。
完整模式额外绑定 scope_sha256。可复用同次实际构建/HAP，为不同 unit 保存各自回执，不逐单元重编。
所有报告内文件引用使用相对 spec/ 的 {path,sha256}，回执内 hap_path 使用项目相对路径。

每个 arrival_receipt 记录 pair_id、arrival_mode、state_setup、presentation、build_receipt、
install_receipt、device_id、capture_run_id、observed_page_id、observed_state_id、landing_evidence。
只有实际观察到该页/状态才成功；安装成功不能代替到达。截图/dump 保存到
spec/execution/stage1-visual/<capture_run_id>/，不能使用旧 run 路径或其他设备的图片。
每 comparison 使用 ui_relationships 复算顺序、靠边、重叠和间距，并绑定独立 appearance_report。
正式与 Preview 到达分开；宿主 shell 不代替正文区域比较，composition 验证不认领正文实现。

## 收口与 1030 门禁处置

恢复先运行 `stage1_acceptance.py --kind next`，结果缺步骤是 NOT_RUN，有证据的前置失败才是 BLOCKED。
--kind compile/visual 保存有界轮次，--kind summary 汇总；完整完成 writeback 使用
stage1.phase=complete 和冻结 scope，build/apply_writeback 在落任何 brief 前重算。
G0 缺失、源码/包/设备/状态不匹配、逐状态结果缺失、视觉未通过时不能 stage1_complete=true。

1030 的 gate-handling、放行记账、导航修复和后续业务验收保留。新增门禁在 gate-registry 登记，
精确格式/哈希/SDK 成员与推断式布局检查分开。流程放行不改变原始 FAIL/BLOCKED，也不生成视觉 PASS。
完整模式必须尝试 S1-V 并逐项记录；允许按 1030 规则带问题继续时，使用 assessed 结果及 ledger 决策，
stage1_complete 仍为 false。不能用旧模式的 SKIP、自由文本理由、批次 brief PASS 或 git import 统计替代它。

新工程不迁移旧实验副本。1030 旧映射/回执 API 的回归测试与完整模式的测试均须保留；
1to1 按整个 skill 替换，必须带齐共享 helpers 和 dependencies，不能只复制 SKILL.md。
