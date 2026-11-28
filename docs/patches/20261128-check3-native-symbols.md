# CHECK-3 显式原生符号与活动源导航增量

源码基线为 c919b99，包含 11 月 26 日流程交接修复。本变更只属于工具，通用合成回归不包含应用实例原件；更新仓库源码不会自动替换其他项目的安装。

| 文件 | 变更原因与行为 |
| --- | --- |
| scripts/lib/ios_ui_relationships.py | 增加显式符号身份、父按钮及页签约束；重复组消歧后仍按4pt测量；限制批准的源导航为唯一主窗口中的独立后继容器，防止宿主/外部窗口混入；补逐对说明校验；默认模式保留旧页签语义。 |
| scripts/lib/ios_stage1_visual_gate.py | 正式视觉门禁重放新选项及其完整证据，拒绝改标记、删字段、篡改绑定和伪造PASS；独立外观证据保持必需。 |
| scripts/tests/test_ios_native_symbol_anchors.py | 用通用合成树覆盖正例、语义冲突、裁剪/背景/按钮错配、重复歧义、6pt失败、源窗口/模态身份、空标签、旧模式兼容以及门禁重放篡改。 |
| scripts/ui-delivery-runtime.json | 刷新实际变动的两个库文件摘要，保持原安装校验条目与覆盖范围。 |
| references/ui-delivery-contract.md | 说明显式启用条件、源导航绑定、拒绝条件及旧项目兼容范围。 |
| 本说明 | 记录逐文件理由、验收命令与发布边界。 |

表中 scripts/references 路径均相对 migbot/skills/i2h-execute。
没有删除线上文件，48项保护清单保持不变；已有脚本、测试与CI均保留。
源导航模式在证据不充分时保持未验证，不推测页面身份。新符号模式不会生成或修改应用图标。

## 验收与使用

通过正常 migbot/scripts/migbot-install.py 安装后，从 .claude/skills/i2h-execute/scripts/
调用 ui_relationships.py；按批准范围显式传入 --native-symbol-anchors、
--native-control-roles，必要时传 --audit-viewport --tab-bar-id 和
--approved-source-navigation。Stage1 仍使用原正式入口与独立外观审核。

macOS 全量 848 项合同回归通过，0 失败/跳过；其中本文件对应 23 项新增通用回归。最终安装版 63 项相关测试、14 项独立 CLI 检查通过；干净安装、保留配置升级、旧 G0/G1 和旧关系回执兼容检查通过。独立安装检查单列，不与全量回归重复相加。

复跑相关回归：

```bash
python3 -B -m pytest -q \
  migbot/skills/i2h-execute/scripts/tests/test_ios_native_symbol_anchors.py \
  migbot/skills/i2h-execute/scripts/tests/test_ios_ui_relationships.py \
  migbot/skills/i2h-execute/scripts/tests/test_ios_stage1_visual_gate.py
python3 -B -m pytest -q migbot/scripts/test_modal_visual_upgrade.py
```

全量分组命令见 `.github/workflows/ios-contracts.yml`。Windows/Linux保留覆盖，本轮未实跑。应用工程、采集数据和本机日志不随此工具源码提交，工具测试不能代替应用完整Verify。

在新符号模式中，同名重复按钮可按真实或明确声明的页签内部/非页签上下文分组，源与目标在该分组中各自唯一时才配对；同区多候选保持未决，不用位置或控件 ID 猜按钮。旧模式不启用此消歧。
