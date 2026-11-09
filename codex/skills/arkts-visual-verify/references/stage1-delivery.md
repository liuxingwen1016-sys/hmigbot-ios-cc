# Stage 1 delivery 的受限视觉检查

调用参数 scope=stage1_delivery scope_manifest=<path> mode=capture_compare fix=none。
先加载 a2h-execute/references/ui-delivery-contract.md；该模式不走默认双端遍历队列。
新 schema 2 还须读取 layout-fidelity.md。所有 scope pairs 和 composition verification pairs 都在分母中；
组合验证 owner 不自动拥有子组件实现。保持 presentation/state_setup，与实际 arrival_receipt 逐项一致。

scope.pairs 是冻结的 required-state 分母，使用明确 pair_id/page_id/state_id，
Android 输入来自 android_frames[].png/xml/parsed 的 {path,sha256}（path 相对 spec/）。
直接复用这些文件，不复制到 screenshots/android，不按目录名字推断对应。
保留同一状态的所有 required frames；host child 只比较 region_px 内内容。
代表帧和 required_expansion 必须比较，其余 optional_frames 按需展开。working_png 是本区域裁剪图；
原图 png/xml 为来源，比较时按 region_px 对齐 HarmonyOS 对应区域，不把局部坐标当屏幕坐标。
逐帧一致性、滚动内容和状态切换都需核对；density 使用实际 frame 值。

主线程派 hmos-builder 构建当前来源包，记录 source_sha256/HAP hash，安装同一 HAP。
保持真实业务条件；arrival_mode=preview 只通过受控验证 host 展示正式组件。
由批次多模态 agent 读取引用 PNG 与对应 HarmonyOS PNG/dump，主线程读取结果摘要。
先运行 a2h-execute/scripts/ui_relationships.py（实际密度/区域），按文字、角色和唯一语义上下文
检查顺序、靠边、重叠、间距；不要按混淆资源 ID 匹配。匹配不确定保持 UNRESOLVED。
图片复核补充外观、图标、背景/canvas，不能替代关系脚本。
所有实际操作产生来源回执；设备/签名/前置缺失保留 BLOCKED 原因，不能删除 pair。

结果保存在 spec/execution/stage1-visual，比较报告绑定 scope_sha256，
pairs 每项包含 pair_id、arrival_mode、verdict、arrival_receipt 和 comparisons。
comparisons 必填 comparison_id、android_png_sha256、android_region_px，以及相对 spec/ 的 harmony_png/harmony_xml 哈希对象。
同一原图的不同区域必须分别有 comparison，不能只按 PNG hash 对账。
PASS/FAIL 都保留输入图像和实际到达收据；BLOCKED 写 reason。
schema 2 每个 comparison 还须绑定 appearance_report（{path,sha256}），内容有相同 comparison_id 和
verdict；PASS 必须关系脚本复算 PASS 且外观报告 PASS。构建 receipt 须绑定实际 HAP 文件和摘要，采用 1030 typed receipts；详见 ui-integration-1030.md。
BLOCKED 使用 scope 原有分类，或 DEVICE_UNAVAILABLE/SIGNING_UNAVAILABLE/BUILD_FAILED/
ARRIVAL_FAILED/RELATIONSHIP_UNRESOLVED 加对应 evidence；未运行不能用自由文本冒充阻断。
正式到达与 Preview 到达分别统计，均不自动声称业务接入完成。

返回比较报告供 stage1_acceptance.py 归档，不启动本 Skill 的默认 visual-fixer。
Execute 最多进行两轮修复并保留 round-0；本模式不改页面 verified 状态。
缺强制 G0 归档或脚本失败时 BLOCKED，不得宣称 Stage 1 完成。最终结果由 stage1_acceptance.py --kind summary 汇总。

arrival_receipt 还须绑定 device_id、capture_run_id、observed_page_id/state_id 和 landing_evidence；图/dump 必须在本次 spec/execution/stage1-visual/<run>/ 中。stage1_acceptance 使用与 1030 相同的源码摘要和实际 HAP 校验，不能把 installed 当作 ready。
