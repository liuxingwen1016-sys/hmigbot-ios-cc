# e057f48 模态视觉链路增量移植：逐文件原因（R2独立复审修订版R3，供复审）

基线：`e057f483540fd98d36d1541bbfecb00a36b6b4e3`，远端`main_ui_optimize`。候选分支`patch/modal-visual-e057-20261124-review`。这是从远端提交按需摘取的增量，不是把本机latest整树覆盖上去。原工作区和未提交改动不转移、不stash/reset，线上已有文件不删除。

本次仅引入窗口/活动原生模态的视觉验收、截图与原树摘要和Stage1重放、测试/文档。`uitest_scenario.py`和`layout_from_step`未移植，acceptance_plan.py及行为合同实现未改，G0生产/汇总格式未改。

## 上一份补丁为什么会删除48个文件（原因补充与纠正）

**上一份包 `hmigbot-ios-cc-patch-e057f48-local20261120.zip` 已标记停用，不用于本次增量移植。** 它的清单类型是 `EXACT_LOCAL_FROZEN_SNAPSHOT_DELTA`，目标是让线上e057f48副本精确等于本机 `local.20261120-modal-cover-sheet` 冻结快照。生成时将“线上存在、本地目标快照不存在”的文件集合直接当作删除清单，因此产生48项删除。

这里要分清“为什么会被列为删除”和“是否有充分理由删除”：前者是上述整树快照差集算法；后者没有成立。我没有逐项证明这48个文件已废弃、被等价替代或不再被调用，也没有为它们作能力下线决定。**本地冻结版缺少某文件，不等于线上文件无用。把存在版本分叉的本地快照当作线上完整替代品，是上一包生成策略的问题。** 原说明虽然列了48项删除和精确同步风险，却没有明确解释这一根因，这是说明遗漏。

旧包的780项回归通过只能证明其目标快照上所运行的测试通过；由于测试集本身也被删改，不能据此证明被删除的线上能力得到保留。旧包780项与新包744项不是同一测试集合，不能按数量判断能力退步或进步。

上一包仅生成了本地补丁，没有将这些删除应用或推送到线上仓库，也未删除原工作区、latest或转换项目中的对应文件。本次从e057f48按需摘取模态视觉改动，**13修改、12新增、0删除；下面48个文件全部保留且与e057f48摘要相同**。旧压缩包保持原字节和原SHA，仅作为历史证据；其同目录README/CHANGES与DEPRECATED说明已提示停用，解压出的旧README仍是历史原文，不能当作当前使用建议。

### 已确认的Android清理与iOS替换

**之前确实做过“清理旧Android检查、改为原生iOS实现”，这一成果仍然有效。** “未证明48项存在等价替代”只针对上一份补丁的删除集合，不表示此前没有进行Android到iOS的替换。应分别看待：

| 事项 | 已核对的证据与处理 |
|---|---|
| 旧Android UI交付二进制改为Python iOS门禁 | P34安装验证已记录旧Execute二进制目录移除；ui_delivery_gate.py与ui_stage1_gate.py在e057f48基线中已经是Python，且与旧包目标快照字节相同 |
| CHECK-5旧Android Oracle/未来适配说明清理 | 本次check5-behavior-verify.md保留前139行既有原生行为合同，删除后半段过时说明，链接原生模态视觉合同 |
| 上一份整树同步包删除48项线上文件 | 删除项包含原生iOS字体、本地化、Swift声明、实际安装包身份校验，以及共享任务路由/预算与测试 |

核对不只看文件名：上一包同时从ui_evidence.py移除了scan_localizations、scan_fonts、scan_themes的调用及对应输出，从ios_runtime_capture.py移除了实际安装包身份/摘要的前后校验。对同一份通用合成夹具执行资源采集，e057f48保留实现输出1条xcstrings本地化记录、1条字体注册和1份主题，旧包目标快照不再输出这三个字段。新模态观察/场景记录文件不能等价替代这些源分析能力。该局部A/B并非完整转换或真机验收，也不表示48项已逐一做完整功能复测。

历史依据：P34的codex-validation.md“发布安装与实测”及p34-release-receipt.json；代码依据：e057f48原提交、旧包PATCH-MANIFEST.json及本地冻结快照。本次零删除策略保留线上能力，同时继续接入原生iOS模态视觉与清理过时Android说明，不会把旧Android二进制重新装回去。

### 删除项影响范围（明确区分代码、说明和测试）

这里说的是**如果应用上一份旧补丁，会实际删掉什么**。删除实现会让工具包失去相应代码或入口；删除测试只表示少了自动检查，不能直接推断功能已经坏了；删除说明则表示少了使用合同或模板接入说明。这三种后果不能混写。

| 分类 | 删除文件组成 | 已确认的具体变化 | 结论边界 |
|---|---|---|---|
| Claude任务路由、累计预算、agent与安装 | 6个执行/配置/agent文件、2份说明、2个测试，共10个 | 删除run_claude_task.py任务入口、execution_policy.py路由策略、claude_task_guard.py累计预算程序、策略JSON和2个agent定义；安装器还撤掉相关运行时及agent复制接线。旧包不再交付线上这套统一任务路由与累计预算实现。 | 新增模态视觉/场景记录文件不承担任务路由或累计预算；未发现对应替代入口。 |
| 流水线阶段marker合法性测试 | 1个测试 | 删除test_marker_stage_validation.py，少了该文件中的阶段标记合法性自动回归。 | 这一项删除的是测试；不能据此说marker生产程序也被删除或已失效。 |
| Execute批准清单与源绑定 | 3个实现、10个测试，共13个 | 删除ui_inventory_resolution.py派生执行清单入口、ios_inventory_resolution.py源证据/清单校验库、ios_swift_declaration_scope.py声明解析库及10个测试。原来这条“用批准清单和Swift源证据生成、校验执行清单”的入口不再随包提供。 | 可以确认原入口和检查代码被移除；本轮没有对Execute所有剩余入口逐项复测，不能把它夸大成整个Execute不可用。 |
| Plan需求、依赖、覆盖与续跑 | 1个实现、5个测试，共6个 | 删除validate_plan_schema1.py独立校验入口，以及文件匹配、schema-1续跑、依赖、宿主UI清单与Plan结构的5个测试文件。少了该校验入口和这些自动回归。 | Plan还有其他生产代码。是否覆盖了被删入口的全部检查条件，本轮未逐项核实；不能直接断言整个Plan覆盖/续跑功能消失。 |
| Spec声明、资源和安装包身份 | 5个实现、5个测试，共10个 | 删除Swift声明、字体、本地化、主题与实际安装包身份的5个iOS实现及5个测试；相关调用也被移除。已执行的局部A/B确认：旧包资源采集不再输出xcstrings明细、字体注册和主题字段；截图前后实际安装包身份校验及build_binding记录也从采集代码撤下。 | 资源输出差异已实测；安装身份校验撤下已核对代码。本轮未重跑完整iOS采集或全部Spec流程。 |
| iOS真机实际安装包探针 | 5个源码/头文件、1份说明、1个测试，共7个 | 删除可选DEBUG探针、bundle摘要核心、macOS校验CLI、接入说明和测试。旧包不再提供这套iOS真机安装包摘要取证模板。 | 这是可选真机取证模板；删除它不等于模拟器采集或所有iOS取证都不可用。 |
| Plan/UI覆盖测试 | 1个测试 | 删除tests/test_plan_ui_coverage.py，少了这一组Plan/UI覆盖自动回归。 | 这一项删除的是测试；生产覆盖校验是否变化需要另看实现，不能从测试文件被删直接下结论。 |

**“没有验证等价替代”的准确意思：** 对需要替换的旧入口，应指出新入口在哪、谁调用它，并用相同输入验证原来会拒绝的错误仍被拒绝、原来会输出的必要信息仍被保留。此前没有给这48项逐一完成这套对应验证。因此不能用“旧Android文件换成新iOS文件”概括整批删除，也不能反过来声称这48项删除已经造成所有对应功能故障。

当前增量补丁不执行上述48项删除，原文件及字节均保留；表中是旧包的影响分析，不是当前补丁的故障清单。

### 48项逐文件标记

每项的共同成因都是“线上存在、本地冻结快照缺失，被精确同步机械列为删除”，并非已审核通过的功能下线。逐项对应如下；本次状态均为保留且字节不变，SHA证据见 `preservation.json`。

| 上一包列为删除的文件 | 为什么被列为删除 | 涉及能力/回归 | 本次处理 |
|---|---|---|---|
| `migbot/agents/i2h-diagnostic-expert.md` | 本地目标快照缺失；未确认废弃或等价替代 | Claude任务路由、累计预算、agent定义及安装/测试 | 保留，SHA不变 |
| `migbot/agents/i2h-source-indexer.md` | 本地目标快照缺失；未确认废弃或等价替代 | Claude任务路由、累计预算、agent定义及安装/测试 | 保留，SHA不变 |
| `migbot/bin/scripts/pipeline/tests/test_marker_stage_validation.py` | 本地目标快照缺失；未确认废弃或等价替代 | 流水线阶段marker合法性测试 | 保留，SHA不变 |
| `migbot/config/README.md` | 本地目标快照缺失；未确认废弃或等价替代 | Claude任务路由、累计预算、agent定义及安装/测试 | 保留，SHA不变 |
| `migbot/config/execution-policy.json` | 本地目标快照缺失；未确认废弃或等价替代 | Claude任务路由、累计预算、agent定义及安装/测试 | 保留，SHA不变 |
| `migbot/references/execution-policy.md` | 本地目标快照缺失；未确认废弃或等价替代 | Claude任务路由、累计预算、agent定义及安装/测试 | 保留，SHA不变 |
| `migbot/scripts/claude_task_guard.py` | 本地目标快照缺失；未确认废弃或等价替代 | Claude任务路由、累计预算、agent定义及安装/测试 | 保留，SHA不变 |
| `migbot/scripts/execution_policy.py` | 本地目标快照缺失；未确认废弃或等价替代 | Claude任务路由、累计预算、agent定义及安装/测试 | 保留，SHA不变 |
| `migbot/scripts/run_claude_task.py` | 本地目标快照缺失；未确认废弃或等价替代 | Claude任务路由、累计预算、agent定义及安装/测试 | 保留，SHA不变 |
| `migbot/scripts/test_execution_install.py` | 本地目标快照缺失；未确认废弃或等价替代 | Claude任务路由、累计预算、agent定义及安装/测试 | 保留，SHA不变 |
| `migbot/scripts/test_execution_policy.py` | 本地目标快照缺失；未确认废弃或等价替代 | Claude任务路由、累计预算、agent定义及安装/测试 | 保留，SHA不变 |
| `migbot/skills/i2h-execute/scripts/lib/ios_inventory_resolution.py` | 本地目标快照缺失；未确认废弃或等价替代 | Execute批准清单、源绑定及对应门禁/测试 | 保留，SHA不变 |
| `migbot/skills/i2h-execute/scripts/lib/ios_swift_declaration_scope.py` | 本地目标快照缺失；未确认废弃或等价替代 | Execute批准清单、源绑定及对应门禁/测试 | 保留，SHA不变 |
| `migbot/skills/i2h-execute/scripts/tests/test_authority_strict.py` | 本地目标快照缺失；未确认废弃或等价替代 | Execute批准清单、源绑定及对应门禁/测试 | 保留，SHA不变 |
| `migbot/skills/i2h-execute/scripts/tests/test_central_authority_validation.py` | 本地目标快照缺失；未确认废弃或等价替代 | Execute批准清单、源绑定及对应门禁/测试 | 保留，SHA不变 |
| `migbot/skills/i2h-execute/scripts/tests/test_current_authority_chain.py` | 本地目标快照缺失；未确认废弃或等价替代 | Execute批准清单、源绑定及对应门禁/测试 | 保留，SHA不变 |
| `migbot/skills/i2h-execute/scripts/tests/test_frozen_source_alternative_binding.py` | 本地目标快照缺失；未确认废弃或等价替代 | Execute批准清单、源绑定及对应门禁/测试 | 保留，SHA不变 |
| `migbot/skills/i2h-execute/scripts/tests/test_indentation_defect.py` | 本地目标快照缺失；未确认废弃或等价替代 | Execute批准清单、源绑定及对应门禁/测试 | 保留，SHA不变 |
| `migbot/skills/i2h-execute/scripts/tests/test_native_integration_honest.py` | 本地目标快照缺失；未确认废弃或等价替代 | Execute批准清单、源绑定及对应门禁/测试 | 保留，SHA不变 |
| `migbot/skills/i2h-execute/scripts/tests/test_phase_a_final_obligations.py` | 本地目标快照缺失；未确认废弃或等价替代 | Execute批准清单、源绑定及对应门禁/测试 | 保留，SHA不变 |
| `migbot/skills/i2h-execute/scripts/tests/test_source_only_defects.py` | 本地目标快照缺失；未确认废弃或等价替代 | Execute批准清单、源绑定及对应门禁/测试 | 保留，SHA不变 |
| `migbot/skills/i2h-execute/scripts/tests/test_source_only_flow.py` | 本地目标快照缺失；未确认废弃或等价替代 | Execute批准清单、源绑定及对应门禁/测试 | 保留，SHA不变 |
| `migbot/skills/i2h-execute/scripts/tests/test_source_only_g1.py` | 本地目标快照缺失；未确认废弃或等价替代 | Execute批准清单、源绑定及对应门禁/测试 | 保留，SHA不变 |
| `migbot/skills/i2h-execute/scripts/ui_inventory_resolution.py` | 本地目标快照缺失；未确认废弃或等价替代 | Execute批准清单、源绑定及对应门禁/测试 | 保留，SHA不变 |
| `migbot/skills/i2h-plan/scripts/tests/test_feat_glob_fix.py` | 本地目标快照缺失；未确认废弃或等价替代 | Plan依赖、覆盖、续跑及清单校验/测试 | 保留，SHA不变 |
| `migbot/skills/i2h-plan/scripts/tests/test_pipeline_resume_schema1.py` | 本地目标快照缺失；未确认废弃或等价替代 | Plan依赖、覆盖、续跑及清单校验/测试 | 保留，SHA不变 |
| `migbot/skills/i2h-plan/scripts/tests/test_plan_dependency_checks.py` | 本地目标快照缺失；未确认废弃或等价替代 | Plan依赖、覆盖、续跑及清单校验/测试 | 保留，SHA不变 |
| `migbot/skills/i2h-plan/scripts/tests/test_ui_delivery_host_validation.py` | 本地目标快照缺失；未确认废弃或等价替代 | Plan依赖、覆盖、续跑及清单校验/测试 | 保留，SHA不变 |
| `migbot/skills/i2h-plan/scripts/tests/test_validate_plan_schema1.py` | 本地目标快照缺失；未确认废弃或等价替代 | Plan依赖、覆盖、续跑及清单校验/测试 | 保留，SHA不变 |
| `migbot/skills/i2h-plan/scripts/validate_plan_schema1.py` | 本地目标快照缺失；未确认废弃或等价替代 | Plan依赖、覆盖、续跑及清单校验/测试 | 保留，SHA不变 |
| `migbot/skills/i2h-spec/scripts/ios_declaration_scope.py` | 本地目标快照缺失；未确认废弃或等价替代 | Spec声明、资源保真与安装身份校验/测试 | 保留，SHA不变 |
| `migbot/skills/i2h-spec/scripts/ios_fonts.py` | 本地目标快照缺失；未确认废弃或等价替代 | Spec声明、资源保真与安装身份校验/测试 | 保留，SHA不变 |
| `migbot/skills/i2h-spec/scripts/ios_installed_identity.py` | 本地目标快照缺失；未确认废弃或等价替代 | Spec声明、资源保真与安装身份校验/测试 | 保留，SHA不变 |
| `migbot/skills/i2h-spec/scripts/ios_localizations.py` | 本地目标快照缺失；未确认废弃或等价替代 | Spec声明、资源保真与安装身份校验/测试 | 保留，SHA不变 |
| `migbot/skills/i2h-spec/scripts/ios_theme.py` | 本地目标快照缺失；未确认废弃或等价替代 | Spec声明、资源保真与安装身份校验/测试 | 保留，SHA不变 |
| `migbot/skills/i2h-spec/scripts/tests/test_declaration_scoping.py` | 本地目标快照缺失；未确认废弃或等价替代 | Spec声明、资源保真与安装身份校验/测试 | 保留，SHA不变 |
| `migbot/skills/i2h-spec/scripts/tests/test_ios_runtime_capture_batch_binding.py` | 本地目标快照缺失；未确认废弃或等价替代 | Spec声明、资源保真与安装身份校验/测试 | 保留，SHA不变 |
| `migbot/skills/i2h-spec/scripts/tests/test_ios_runtime_capture_binding.py` | 本地目标快照缺失；未确认废弃或等价替代 | Spec声明、资源保真与安装身份校验/测试 | 保留，SHA不变 |
| `migbot/skills/i2h-spec/scripts/tests/test_native_skeleton_consumers.py` | 本地目标快照缺失；未确认废弃或等价替代 | Spec声明、资源保真与安装身份校验/测试 | 保留，SHA不变 |
| `migbot/skills/i2h-spec/scripts/tests/test_resource_fidelity.py` | 本地目标快照缺失；未确认废弃或等价替代 | Spec声明、资源保真与安装身份校验/测试 | 保留，SHA不变 |
| `migbot/skills/ios_fast_traverse/templates/physical-bundle-probe/I2HBundleHashCore.h` | 本地目标快照缺失；未确认废弃或等价替代 | iOS实际安装包探针、摘要及对应测试/说明 | 保留，SHA不变 |
| `migbot/skills/ios_fast_traverse/templates/physical-bundle-probe/I2HBundleHashCore.m` | 本地目标快照缺失；未确认废弃或等价替代 | iOS实际安装包探针、摘要及对应测试/说明 | 保留，SHA不变 |
| `migbot/skills/ios_fast_traverse/templates/physical-bundle-probe/I2HBundleProbe.h` | 本地目标快照缺失；未确认废弃或等价替代 | iOS实际安装包探针、摘要及对应测试/说明 | 保留，SHA不变 |
| `migbot/skills/ios_fast_traverse/templates/physical-bundle-probe/I2HBundleProbe.m` | 本地目标快照缺失；未确认废弃或等价替代 | iOS实际安装包探针、摘要及对应测试/说明 | 保留，SHA不变 |
| `migbot/skills/ios_fast_traverse/templates/physical-bundle-probe/README.md` | 本地目标快照缺失；未确认废弃或等价替代 | iOS实际安装包探针、摘要及对应测试/说明 | 保留，SHA不变 |
| `migbot/skills/ios_fast_traverse/templates/physical-bundle-probe/i2h_bundle_hash_cli.m` | 本地目标快照缺失；未确认废弃或等价替代 | iOS实际安装包探针、摘要及对应测试/说明 | 保留，SHA不变 |
| `migbot/skills/ios_fast_traverse/templates/physical-bundle-probe/test_bundle_hash_core.py` | 本地目标快照缺失；未确认废弃或等价替代 | iOS实际安装包探针、摘要及对应测试/说明 | 保留，SHA不变 |
| `tests/test_plan_ui_coverage.py` | 本地目标快照缺失；未确认废弃或等价替代 | Plan/UI覆盖回归 | 保留，SHA不变 |

后续增量补丁不再以本地冻结快照覆盖线上树；如确需删除受控文件，应逐项列明调用方、替代实现或下线理由及回归证据，不能仅凭本地不存在或测试总数通过作决定。

## 每个文件为什么变（R2独立复审修订，R3）

| 文件 | 类型 | 变更原因与保留边界 |
|---|---|---|
| `.github/workflows/ios-contracts.yml` | 修改 | 保留三平台矩阵和全部原有通用测试；路由/累计预算与POSIX安装升级测试仅macOS/Linux执行，Windows仍执行通用契约、Plan/Execute/Verify与新增模态回归；不声称未运行的平台已通过。 |
| `docs/patches/20261123-modal-visual-port.md` | 新增 | 在原逐文件说明中加入独立复审修订原因、范围和原包保留说明；25个文件逐项解释。保留48项删除与Android清理的历史区分。 |
| `fixtures/modal-visual/e057f48-g0-pass.json` | 新增 | 保存e057f48原安装器与原prepare/complete/aggregate_g0实际产生的通用合成G0 PASS及25份原始工件摘要，用于无网络、跨安装位置的升级兼容回归；不是Cuike实例或人工构造PASS标记。 |
| `migbot/scripts/test_modal_visual_upgrade.py` | 新增 | 安装候选工具到包含旧G0归档的工程，检查配置、App/Spec、原归档字节不变，G0重新汇总及G1通过；另在实际安装路径检验共享观察器拒绝后台控件，并确认线上agent/任务路由仍安装。 |
| `migbot/skills/i2h-execute/references/ios-visual-acceptance.md` | 修改 | 为既有Stage1视觉流程链接新模态合同，明确底层标志和树根route不构成上层到态，G0/清单权威/source_only不变。 |
| `migbot/skills/i2h-execute/scripts/lib/ios_stage1_progress.py` | 修改 | 让正式smoke识别新的declared/page_state_observation身份，再交原_arrival复算原树；保留旧smoke格式和全部设备/HAP/冷启动/覆盖约束，避免只改最终归档却在smoke误拒或漏验。 |
| `migbot/skills/i2h-execute/scripts/lib/ios_stage1_scope.py` | 修改 | 在已存在的线上权威清单读取后，只把批准行的target_observation校验并传入冻结视觉pair；inventory_path/load_inventory及source_only链原样保留。 |
| `migbot/skills/i2h-execute/scripts/lib/ios_stage1_visual_gate.py` | 修改 | 保留R2前后原树/图像/安装身份严格回放；把畸形HAP或bm身份JSON的结构错误转换为可报告的ValueError，使capture-index/最终归档阻断，避免AttributeError逃出正式门禁。 |
| `migbot/skills/i2h-execute/scripts/lib/ios_ui_relationships.py` | 修改 | 严格语义控件匹配仍仅在活动层；独立复审恢复使用完整原树执行原有状态栏诊断，防止CLIPPED退化UNAVAILABLE。原始视口与证据SHA保持，诊断节点不能参与活动层锚点补齐。 |
| `migbot/skills/i2h-execute/scripts/lib/stage1_capture_scope.py` | 修改 | 独立复审补修：按当前批准项目选择合同，prepare/finalize均拒绝scope降级或删谓词；严格case必须已成功到态、绑定采集时图像SHA和当前run内原件，拒绝换图/目录穿越；安装回执绑定当前scope且全组同HAP/设备。允许保留不完整scope的准备/缺项诊断，但不能汇总PASS。无批准schema-2的旧schema-1路径保留。 |
| `migbot/skills/i2h-execute/scripts/tests/test_modal_visual_chain.py` | 新增 | 保留R2全部正反例，只为严格capture summary夹具补充由采集原件产生的harmony_png_sha256，不改期望断言；覆盖同状态多pair、前后模态、安装包名、smoke换图与最终回放。 |
| `migbot/skills/i2h-execute/scripts/tests/test_modal_visual_independent_review.py` | 新增 | 新增13项独立复审测试。实际安装后跑prepare/finalize、capture-index、assemble、visual archive、smoke与Plan CLI；原R2重放11失败2通过，修订后13通过，验证scope/截图/状态/安装cohort和既有状态栏/视口没有漏接或被过滤掉。 |
| `migbot/skills/i2h-execute/scripts/ui-delivery-runtime.json` | 修改 | 保留原受控文件集合，刷新本次实际变化的受控库摘要（含关系检查），确保干净安装交付新字节；不改变安装策略。 |
| `migbot/skills/i2h-plan/scripts/native_scenario_evidence.py` | 新增 | 保留原生窗口/模态状态观察和前后活动层连续性；活动层投影优先保留原始显示视口，避免只筛节点却改变坐标尺度；无行为录制和layout_from_step。 |
| `migbot/skills/i2h-plan/scripts/tests/test_modal_cover_sheet_resolution.py` | 新增 | 覆盖SheetPage与ModalPage并列时的正反例及within/absent作用域，阻止按遍历顺序、zIndex、子节点focus或期望谓词选择“碰巧能过”的层。 |
| `migbot/skills/i2h-plan/scripts/tests/test_modal_focus_resolution.py` | 新增 | 覆盖多个SheetWrapper/SheetPage兄弟分支的唯一自身focus、嵌套链、背景排除、顺序无关以及缺标志/未知父节点等拒绝；诊断有界且不泄露自由文本。 |
| `migbot/skills/i2h-plan/scripts/tests/test_modal_plan_null_compat.py` | 新增 | 新增旧清单verification_states缺失/null不崩溃、非列表类型错误和require_runtime_plan严格结构化缺项错误的回归。 |
| `migbot/skills/i2h-plan/scripts/tests/test_native_scenario_evidence.py` | 新增 | 保留原生观察的基础正反例：真实布尔/字符串等价，拒绝1/0、异包/异窗口/UIExtension以及同route错状态，验证新纯观察器。 |
| `migbot/skills/i2h-plan/scripts/ui_delivery.py` | 修改 | 保留线上权威/需求/覆盖实现，仅增加可选原生谓词校验，并先确认verification_states为列表再遍历；缺失/null兼容旧清单，非列表及运行时严格缺项返回结构化错误。 |
| `migbot/skills/i2h-verify/SKILL.md` | 修改 | 仅清理过时Android Oracle与未来调用参数说明，保留五CHECK及原生行为路径并链接模态视觉合同；没有开启新行为记录器、修改分母或改变验收放行。 |
| `migbot/skills/i2h-verify/references/check5-behavior-verify.md` | 修改 | 保留现有原生UITest、AC、Hypium、场景续跑和报告合同；移除后半段过时的“整个iOS CHECK-5未来支持/Android Oracle”长说明，补缺原生证据时如实DEFERRED。 |
| `migbot/skills/i2h-verify/references/native-modal-visual.md` | 新增 | 补充严格采集汇总的图像SHA、状态、当前scope和同安装要求，并区分活动层语义匹配与完整原树的状态栏诊断/坐标，说明无谓词旧合同继续兼容。 |
| `migbot/skills/i2h-verify/scripts/tests/test_modal_visual_checkpoint.py` | 新增 | 覆盖前台窗口/focus、同包同route截图后弹层出现/消失、弱业务条件不能跳过批准谓词、严格回调获得前树等通用合成回归。 |
| `migbot/skills/i2h-verify/scripts/uitest_action.py` | 修改 | 前台判定统一复用本安装目录的纯观察器，支持严格bool/string且拒绝重复聚焦或畸形focus；新增实际observed_window/focused_page_matches，保留原动作定位API和CLI提示，不移植无关触感持久化或记录器逻辑。 |
| `migbot/skills/i2h-verify/scripts/uitest_checkpoint.py` | 修改 | 严格capture_checkpoint接受本轮批准谓词，截图前后均执行同一谓词并核对活动层连续；通过后回调提供截图前原树。writer要求并保存前后原树/观察，不能只看截图后状态；旧非严格调用维持原签名行为。 |

## 旧版与严格视觉的区别

带批准`target_observation`的pair必须重读原树并校验活动层，不能通过删除新字段退回标签。项目要求全量严格时，在阶段断点明确启用`native_visual_observation: native-page-state-v2`，缺批准谓词即阻断。旧清单未启用时继续保留旧格式历史回放，但身份仍属runner声明，不能声称获得了严格模态证据。升级不自动改写批准范围或旧回执。

## 明确保留的线上能力

上一份patch列为删除的48文件全部保留且字节不变，包括Claude任务路由、累计预算、agent安装；Execute中央批准清单/执行派生清单、source_only和严格源绑定；Plan需求索引、依赖/覆盖校验；Spec Swift声明、本地化、字体、主题和模拟器实际安装身份检查。原安装器、G0归档/读取/汇总和acceptance_plan实现未改，CI原步骤未删除。可从本补丁变更集和随交付的preservation.json独立复核。

## 验证入口

```bash
python -m pip install pytest==8.3.5 packaging==24.2 pluggy==1.5.0 iniconfig==2.0.0
python migbot/scripts/test_execution_policy.py -v
python migbot/scripts/test_execution_install.py -v
python migbot/scripts/test_modal_visual_upgrade.py -v
python -m unittest migbot.scripts.test_install_runtime -v
python tests/test_e2e_i2h_fixture.py -v
python -m unittest tests/test_marker_contract.py -v
python tests/test_plan_ui_coverage.py -v
python -m pytest -q migbot/skills/i2h-spec/scripts/tests
python -m pytest -q migbot/skills/i2h-plan/scripts/tests
python -m pytest -q migbot/skills/i2h-execute/scripts/tests
python -m pytest -q migbot/skills/i2h-verify/scripts/tests
```

本轮独立复审发现、五项请求的正式入口映射和平台实测状态见INDEPENDENT-REVIEW.md；完整结果、补丁从e057f48应用/回滚/解包校验及各文件SHA见VERIFICATION.md/verification.json。旧G0夹具由原工具实际生成，升级测试只读重放原归档；通用合成测试不是应用真机或完整迁移通过证明。本次没有更新本机latest、没有覆盖任何进行中的转换项目，也没有push。

## 合并后的文档入口

本变更随main_ui_optimize的R3集成提交发布。仓库根README.md/README_CN.md逐项说明能力，独立复审与测试复现入口见[复审记录](20261124-modal-visual-review.md)，平台与本机回归数据见[验证摘要](20261124-modal-visual-validation.json)。原补丁交付目录的完整日志作为本机工具维护证据保留，不与应用工程或门禁状态混用。

## 远端CI接续修正

合并后追加的跨平台依赖、UTF-8、runner与静态分析JSON解析修复详见[复审记录的CI适配段](20261124-modal-visual-review.md#合并后的远端ci适配)。原25项R3移植清单保留为原补丁记录；接续提交另含静态分析器及其既有测试文件的修正，未删除线上文件。
