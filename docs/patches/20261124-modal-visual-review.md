# 模态视觉R3：独立复审发现与合并验证记录

## 结论与方法

本次不是重跑R2自带用例后宣布通过。先从交付ZIP取出补丁，在新的e057f483540fd98d36d1541bbfecb00a36b6b4e3副本应用；新增针对正式入口的边界测试，再在另一临时副本上对原R2运行同样13项测试。**原R2：11失败、2通过；补修后：13通过。** 原始R2 ZIP、R2候选及原工作区未改，复审没有使用独立模型或应用设备，属于新副本、新反例和实际安装入口的独立代码/合同复审。

完整原始日志保留在本机工具维护记录中，不随运行时安装。仓库内保存[机器验证摘要](20261124-modal-visual-validation.json)，回归用例均在migbot测试目录内，可按下列命令复现。

## 确认的问题与修复

| 编号 | 原R2实际问题 | 补修 | 回归证据 |
|---|---|---|---|
| R01 / P1 | 已安装finalize可把scope改为schema-1并删除pairs，绕过项目当前批准谓词；prepare也继续生成待采集清单 | 由项目当前批准清单/严格配置选择合同；prepare和finalize均比对权威scope，降级结构不能切回标签路径 | test_installed_finalize_cannot_downgrade_schema_to_remove_current_predicates；test_installed_prepare_rejects_scope_downgrade_with_structured_report |
| R02 / P1 | 采集汇总在图像被换掉后重算SHA而继续PASS；不要求采集时绑定摘要；字符串前缀允许../逃出本次目录 | 严格case要求原采集图像SHA并复核原件格式/摘要；路径解析后仍须在本次目录 | test_installed_finalize_rejects_image_replacement_after_first_summary；test_installed_finalize_requires_images_bound_at_capture；test_installed_finalize_cannot_escape_current_capture_directory |
| R03 / P1 | finalize接收另一scope的安装回执、把BLOCKED场景的遗留图提升为PASS，且可混合两个设备 | 核对当前scope摘要；只接收成功到态的严格case；同组HAP/设备必须一致 | test_installed_finalize_rejects_install_receipts_from_other_scope；test_installed_finalize_does_not_promote_blocked_case_with_old_artifacts；test_installed_finalize_keeps_multiple_pairs_on_one_installation |
| R04 / P2 | 严格活动层过滤误删状态栏诊断需要的完整树上下文，将原本CLIPPED变成UNAVAILABLE；同时把原显示视口改为窗口边界 | 活动层只约束语义锚点；状态栏诊断继续读完整原树；坐标保留原显示视口 | test_strict_relationship_keeps_raw_status_bar_audit；test_strict_layer_filter_preserves_original_coordinate_viewport |
| R05 / P2 | 安装身份日志JSON为数组时，AttributeError逃出正式capture-index，不能形成正常阻断报告 | 严格安装身份/HAP结构错误转换为ValueError，由既有正式门禁按BLOCKED处理 | test_malformed_install_identity_is_blocked_not_an_uncaught_exception |

没有降低阈值、删断言或靠放宽focus/模态规则消除失败。R2既有case夹具仅补充采集图像时已经知道的SHA字段；原有断言不改。当前schema-2批准scope不完整时仍可准备部分证据，但不能汇总PASS；无当前schema-2批准清单的schema-1旧项目继续按原规则读取。

## 原五项修复在正式入口的覆盖

| 原要求 | 复审位置与结果 |
|---|---|
| 前后同一批准谓词/弹层变化 | R2检查点与writer/回放的原反例全部保留；无前树不能写严格回执，同包同route弹层出现或消失不能通过 |
| 实际HAP安装包绑定 | capture-index、正式visual/smoke均沿用三方包名/安装日志复核；新增坏身份结构的阻断。finalize额外补上scope和安装cohort一致性 |
| Windows CI | 原三平台矩阵及通用测试保留；POSIX路由/预算与旧G0安装组有runner.os条件。新独立CLI测试用sys.executable运行Python安装入口，不依赖fcntl或POSIX假CLI；Windows/Linux本轮未实跑 |
| smoke/汇总/关系一致 | 新测试在实际安装目录连续跑capture-index→assemble→visual archive及smoke，有效证据先PASS，然后缺图/换图时三入口均返回阻断；finalize独立反例已补修；活动层匹配仍拒绝底层控件 |
| Plan空值 | 原R2缺失/null/非列表测试保留，并实际从安装后的ui_delivery.py validate --require-runtime-plan验证结构化缺项错误 |

## 线上能力与验证范围

基线仍为e057f48。13修改、12新增、0删除；上一包48个线上文件保持原SHA。原任务路由、累计预算、agent安装、Execute批准清单/source_only、Plan索引/覆盖与Spec源/资源/身份检查及已有测试均保留。G0/G1及行为录制实现未改，uitest_scenario.py与layout_from_step仍未移植。

全量回归、旧G0/G1、全文件摘要及正反向应用结果见同目录机器验证摘要。macOS实际运行；Windows/Linux保留CI配置但NOT_RUN，不用配置检查代替实跑。原R3复审时未更新latest或合入；本记录随main_ui_optimize的集成提交发布。合并不自动升级本机latest或任何真实转换工程，临时验证副本均在使用后清理。工具测试通过不等同于Cuike等应用设备验收通过。

## 重跑本次工具验证

CI使用Python3.11，本机验证使用Python3.12.1。安装pytest/Pillow/ImageHash后，在工具仓库执行：

```bash
python -m pytest -q migbot/skills/i2h-spec/scripts/tests
python -m pytest -q migbot/skills/i2h-plan/scripts/tests
python -m pytest -q migbot/skills/i2h-execute/scripts/tests
python -m pytest -q migbot/skills/i2h-verify/scripts/tests
python -m unittest migbot.scripts.test_install_runtime -v
python tests/test_e2e_i2h_fixture.py -v
python -m unittest tests/test_marker_contract.py -v
python tests/test_plan_ui_coverage.py -v
```

macOS/Linux另外执行POSIX组：

```bash
python migbot/scripts/test_execution_policy.py -v
python migbot/scripts/test_execution_install.py -v
python migbot/scripts/test_modal_visual_upgrade.py -v
```

重点独立用例：`migbot/skills/i2h-execute/scripts/tests/test_modal_visual_independent_review.py`，实际安装到临时合成项目后调用正式Python入口；不访问Cuike等实例或真实设备。

## 合并后的远端CI适配

首个集成提交455faca触发的远端CI已实际运行：Windows在Plan覆盖测试因cp1252控制台编码失败；Linux的Verify静态分析子进程未产生JSON，原工作流未声明安装ripgrep；macOS任务在启动前报告macos-14-arm64-us-default不受支持。原始日志作为本机工具维护证据保留。

接续修复不删测试、不降低断言：

- `.github/workflows/ios-contracts.yml`：使用受支持的macos-latest，显式安装/检查ripgrep，统一PYTHONUTF8与PYTHONIOENCODING，保留三平台矩阵、通用回归及POSIX分组规则。
- `migbot/skills/i2h-verify/scripts/ios_static_analyzer.py`：用shutil.which查找程序，按rg --json解析文件/行号，避免Windows盘符冒号被拆错；rg非0/1退出、超时或畸形事件返回工具错误，不冒充零违规。
- `migbot/skills/i2h-verify/scripts/tests/test_ios_static_analyzer.py`：保留原3项规则测试，新增Windows路径、无匹配、搜索故障和缺依赖的4项回归；子进程无JSON时显示stderr首因。
- 中英文README与验证摘要同步说明依赖、平台和新增能力；R3原773项记录保留为历史，接续本机完整回归共777项。

macOS镜像依据：[GitHub官方退役公告](https://github.com/actions/runner-images/issues/13518)。远端修复后的最终状态以对应集成提交的Actions运行结果为准。

Windows第二轮CI进一步确认：安装回归内部的acceptance_plan测试通过-I创建了新的Python子进程，隔离模式会忽略环境变量，因此此前job级UTF-8设置不会自动传下去。接续为acceptance_plan、pipeline_timing和visual_worklist测试中的隔离调用显式添加-X utf8；保留-I隔离和全部原断言，不改验收生产规则。

## 当前支持范围与线程隔离

按维护者最新要求，以macOS为当前必要验收平台。保留Windows/Linux实现、测试和手动入口，但不继续把这些平台兼容性作为发布阻塞。默认push/PR只跑macOS合同组；workflow_dispatch的cross_platform=true可附加Windows/Linux，且continue-on-error仅用于这两个可选平台。macOS仍失败即失败，不放宽工具自身的验收断言。

Windows隔离子进程UTF-8启动修正作为已有测试配置保留，不宣称已重新通过Windows。此前修正后的macOS/Linux远端检查已通过，Windows安装升级检查曾失败，原始状态如实保留。

本轮修改限于独立的合并工作副本和维护者已授权更新的线上main_ui_optimize；原工作区、其他候选未提交改动、实际应用项目和latest均不改动，也未取消其他线程/设备任务。
