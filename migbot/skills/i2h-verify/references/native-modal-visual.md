# 原生模态视觉取证与回放

本合同只处理Stage1视觉到态。`native_scenario_evidence.py`在本补丁中仅包含原生窗口/状态观察，不带v2场景记录器；`uitest_scenario.py`与`layout_from_step`留待后续补丁。CHECK-5继续使用线上原有合同。

## 批准谓词与兼容边界

在批准UI清单`verification_states`中为每个严格状态提供`target_observation`，经原Plan批准/Execute权威链消费，不绕过执行派生清单、source_only或验证回执。例：

```json
{"bundle":"com.example.demo","page_path":"pages/Root","present":[{"id":"editorName"}],"absent":[{"id":"errorDialog"}]}
```

`present`每项须在活动层恰好匹配一个可见控件，`absent`默认检查整个前台窗口。基础页存在可弹出的**自定义Stack**浮层时，须把该浮层标志列为absent；原生模态会自动排除底层present，不能据此推断所有自绘浮层顺序。允许单个`within:{"ancestor":{"id":"editorForm"}}`：祖先必须在活动层唯一，present/absent同时限制为它的后代，祖先自身不算后代。布尔字段仅接受true/false或字符串"true"/"false"。

已批准谓词本身就启用该pair的严格回放；即使回执删除observation也不会回退。若项目明确要求**所有**视觉状态严格验证，在已授权阶段断点将`.migbot/config.json`的`native_visual_observation`设为`native-page-state-v2`，此时任何状态缺少批准谓词都阻断。禁止在运行采集器中临时修改谓词。

旧清单无该字段且未启用严格配置时，旧格式视觉回执继续按旧合同处理，身份来自runner声明，**不是严格状态证据**，不得据其宣称模态排他或补写新observation。G0及其归档、source_only、需求/覆盖索引、预算和安装合同不受此开关影响。安装升级不自动给旧工程开启严格模式，也不改写批准清单。

## 窗口与活动模态

仅接受顶层唯一focused应用窗口，其bundle和非空原生pagePath须匹配；树根envelope的pagePath、其他应用窗口、不同hostWindowId、隐藏子树、UIExtensionComponent不参与。所有消费者使用同一严格focus解析，重复聚焦窗口或畸形focus拒绝。

单条嵌套模态链取最内层。多个独立模态仅在下述已知形状可消歧：SheetPage直属不同SheetWrapper；wrapper和page自身focus一致；与其并列的ModalPage持有自身focus；所有分支容器拥有同一个已记录、非空的直接父节点；至少一条Sheet分支且恰好一条focus=true。文档顺序、zIndex、普通子控件focus或“哪个层恰好满足期望”都不能决定活动层。缺标志、冲突标志、未知/折叠父节点、Dialog混合等保持未验证，错误附有界模态定位摘要，不复制自由文本。

## 截图与原树绑定

严格采集调用`capture_checkpoint(..., target_observation=pair["target_observation"])`，其中pair必须来自本轮当前批准清单。`is_ready`是额外业务条件，不能替代批准谓词。截图前两者均通过才拍；截图后对同一包、同一路由重新执行**同一个批准谓词**，同时核对活动层身份连续，才调用正式到态回调。即使相同控件ID在底层仍存在，截图后弹层出现或消失也拒绝。

回调的签名为`record_arrival(name, tree, *, pre_capture_tree)`；将`pre_capture_tree`原样传入`write_visual_arrival(..., pre_capture_tree=pre_capture_tree)`，使用已保存的截图后原树作为layout。严格writer未拿到截图前原树时拒绝写回执，不允许只检查截图后状态。writer将截图前树保存为到态回执同目录的`*.before.json`，记录`pre_capture_tree`引用和`pre_capture_observation`；截图后继续记录`page_state_observation`、`observed_window`和语义声明。`observe_state.active_layer`是本次原树的活动原生层类型/记录索引（无模态为null），只用于前后连续性，不能当作跨次采集的稳定页面ID。

```python
def record(name, tree, *, pre_capture_tree):
    write_visual_arrival(spec_root, arrival_path, pair=pair,
        capture_run_id=run_id, device_id=device_id,
        screenshot=image_path, layout=layout_path, matched_tree=tree,
        pre_capture_tree=pre_capture_tree,
        build_receipt=build_path, install_receipt=install_path)

capture_checkpoint(name, bundle=pair["target_observation"]["bundle"],
    read_layout=read_layout, is_ready=is_ready, capture_image=capture_image,
    approved_images=approved_images, record_arrival=record,
    target_observation=pair["target_observation"])
```

严格回放重新读取前后原树和图像，并校验所有摘要、同一批准谓词与活动层。缺截图或截图字节被替换时，正式smoke、capture-index和最终归档都阻断。旧无谓词、未启用严格配置的回执仍按原规则读取；不得给旧回执补造截图前证据来宣称严格通过。

## 安装身份与入口一致性

严格pair使用线上原安装回执格式：install包含`bundle`、`version_code`、`hap_path/hap_sha256`、`device_id`及`install_log`/`identity_log`引用（路径相对工程根）。回放读取当前构建HAP的module.json、成功安装日志和bm dump身份日志；批准谓词包名、实际唯一前台窗口包名与该HAP实际安装包名必须相等。安装身份或日志缺失、错包名、版本不符均阻断，即使设备和各文件摘要有效。旧版非严格回执不新增这些要求。

采集汇总对于schema-2从当前批准清单重建scope并逐字典核对，按`pair_id`取谓词；同页同状态多个pair分别取各自批准谓词并要求完整覆盖。传入scope删除谓词、漏pair、重复pair或把一个pair的观察套给另一个pair均阻断。严格case还要带当前run内的截图前树与观察，不能退回标签判定。

严格控件关系检查复用同一活动层解析，只在唯一前台窗口的活动层内匹配控件，保留原树摘要和原始窗口坐标；被遮挡底层、其他窗口和隐藏子树不再补足缺失的目标控件。无谓词的旧关系检查保持原规则。Plan的verification_states缺失或null在非严格旧清单仍可读取；运行时严格校验返回结构化缺项错误，非列表输入返回结构化类型错误。

截图与原树摘要证明文件身份及同次检查点前后状态稳定，不证明图像语义完全等价；图像仍须独立外观审核。legacy无谓词回执不会被升级成严格证据。未到态保持缺失，不能拿期望文件名、批准pair标签或树根route当作观测结果。

## 回归入口

- Plan：`test_native_scenario_evidence.py`、`test_modal_focus_resolution.py`、`test_modal_cover_sheet_resolution.py`。
- Verify：`test_modal_visual_checkpoint.py`，覆盖实际窗口、严格focus及截图后状态变化。
- Execute：`test_modal_visual_chain.py`，覆盖取证、摘要篡改、活动层回放及禁止严格模式回退。
- 安装升级：`test_modal_visual_upgrade.py`，读取e057f48原始工具产生的合成G0 PASS归档，不伪造或重写原归档。

这些是通用合成夹具，无Cuike等实例代码、截图或数据，不代表应用完成设备验收。

## 独立复审补充：采集汇总与原有诊断

严格采集case在记录原图时就保存`harmony_png_sha256`（可直接沿用write_visual_arrival生成的对应frame摘要），finalize只校验，不得在图被替换后重新计算摘要再放行。case状态仅READY/PASS/DIFF进入严格证据校验；PENDING/BLOCKED/FAIL及遗留图像不能被升级成成功。原件（含截图前树）必须解析在本次capture_dir内，不能用../或符号链接落到其他目录。

prepare和finalize都以当前批准清单/配置选择合同，而不是信任传入scope的schema_version；更换schema或删除pairs不能回到标签路径。build/install回执要与当前scope摘要绑定，整个汇总必须同一HAP和设备。实际scope尚不完整时仍可准备并保留已知pair的采集信息，但最终状态不允许PASS。旧schema-1且没有当前schema-2批准清单/严格配置的流程继续按原规则处理。

语义锚点仅在活动层匹配；原有状态栏诊断仍从完整原始树读取系统状态栏和前台应用，活动层过滤不应让已知CLIPPED变成UNAVAILABLE。坐标投影保留原始显示视口，不改为活动窗口的偏移边界；完整原树诊断不能替代活动层控件匹配。畸形安装身份对象应形成结构化阻断，不能让异常逃出验收入口。
