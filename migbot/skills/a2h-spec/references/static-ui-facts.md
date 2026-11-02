<!-- when: ui_facts_policy=static-v1 或 static-v1-shadow 时加载 -->
# 静态 UI 事实分支

模式缺省为 legacy。static-v1-shadow 的输出目录为 spec/.a2h/ui-facts-shadow/baseline，
供比对和计时；static-v1 为 spec/baseline。旧合成器和 legacy Gate B 保留。

## Phase A

先固定一个 target。无 Gradle 执行、网络下载或设备采集。
仅使用常规 sourceSets 和字面量依赖的项目可静态推导：

    python3 <skills>/android-ui-graph-builder/scripts/target_input.py resolve \
      --android-root "$ANDROID_SRC" --project-root "$PROJECT_ROOT" \
      --module app --variant debug --build-type debug --static-literals

自定义 flavor/sourceSets、约定插件或动态 DSL 使用导出/审核后的显式 JSON：

    python3 <skills>/android-ui-graph-builder/scripts/target_input.py resolve \
      --android-root "$ANDROID_SRC" --project-root "$PROJECT_ROOT" \
      --resolved-input <reviewed-model.json>

模型沿用 feat/ht_analysis 的 target-input schema。source_sets 按低到高 priority，
明确列 source_dirs/res_dirs/asset_dirs/manifest。每个 flavor dimension 恰好选择一个 flavor。
dependencies 为精确 group/artifact/version，可附 path/sha256/source，禁止动态版本。
同 GAV 多个缓存副本同 hash 可复用，不同 hash 阻断。
外链资源在 allowed_symlink_targets 明确列 path/sha256；无法解析退出 2，生成 decision card，
禁止隐式退回全 flavor 扫描。target resolver 不执行自定义 Gradle 代码。

A1 的既有页面清单/优先级作为 --pages 输入，保持 page_NNNN_ClassName 和 batch-plan ID：

    [{"page_id":"page_0001_MainActivity","activity":"com.example.MainActivity","priority":"P0"}]

未传 pages 时优先复用既有 meta.json ID，再做继承发现；A1 仍需处理 SDK 壳和 skip 决策。
Dialog 从同 scope 的完整 inventory 提取，按 layout owner 落 dialog-snapshots，
不进入 page batch；PreferenceScreen 直接读 res/xml，无 layout 也可生成事实。

    python3 <skills>/a2h-spec/scripts/ui_facts.py prepare \
      --policy static-v1 --project-root "$PROJECT_ROOT" \
      --target-input spec/.a2h/target-input.json --pages <pages.json>

--preview-config 可传 theme_mode、orientation、locale、density、api；
默认 light/port/source-default/density=candidates。候选不伪装成已选择配置。
存在 w/sw/h 等布局 qualifier 时可明确 width_dp/smallest_width_dp/height_dp；
未提供时保留 configuration_required，不固定手机宽度或随意选择 base。
主题按 manifest、首屏 setTheme 参数及实际源码调用/返回分支解析，不使用样式名或工具类名推断。
不确定的分支由 source_theme_selection_required 决策项处理；审核后可在 pages 的 theme 字段
指定源中实际存在的 style ref。light/dark 是资源配置变体，不是对任意 style 名的语义猜测。
--gradle-cache 可指定 modules-2/files-2.1 路径，只读 model 中精确坐标的 AAR。
--apk-enrichment 只解码 reference_packages 中固定 hash 的 APK，不构建或下载。
APK 身份由 package/version/hash 核对；无 Java 或身份不确定记 unresolved。
source/AAR 是主事实，obfuscated 名不猜测。

产物：

- res-index/{values,drawables,usage,design-tokens}.json：资源定义、覆盖链、Drawable 描述、使用表、身份保留的 tokens。
- ui-snapshots/<page>/{meta,visual,fixture}.json、view.xml：结构、值/来源链、首屏数据候选；`visual.json` / `fixture.json` 是可选增强输入，缺失不阻断真机快照或页面迁移。
- templates/*.json：列表 item-type 模板，runtime_instance=false，不进入主 view.xml。
- dialog-snapshots/<owner>/：同样的事实族，按宿主页/共享正文引用。
- res-index/decision-cards.json：未解析事项；res-index/handoff.json：execute 消费边界。
- visual-facts.md：脚本可读投影（可选）；`facts-manifest.json`、`visual-facts.md`、`view.static.xml` 的缺失或陈旧只产生 warning，不作为硬门。

view.xml 始终 synthesized=true，bounds 为空；visual-key 与 nodes.node_key 对应。
解包 DataBinding、展开 include/merge、保留 include 覆盖；未充气 ViewStub 保留引用。
ViewBinding 名由实际 layout 名及 DataBinding data.class 反查，自定义 binding 类不要求 Binding 后缀。
UI 子类、列表和分页容器从继承链及方法契约识别，任意业务类名均可，不要求 Fragment/Adapter 后缀。
Fragment 子页树通过 composition 关联。source-only 不表示运行时几何已确认。

## Phase B

B2 保留原模板必填章节。新 sidecar 数值由脚本决定，worker 不得重写。
代码覆盖、初始子组件、selector/level 输入、自定义绘制等未静态确定事项逐项给
source_refs 和 disposition。常量绘制可 script_resolved；数据/视图尺寸/循环/动画/交互
相关绘制需要引用源码的 interpretation。

worker 只写自己的 spec 和 spec/.a2h/ui-facts-decisions/<batch_id>.json：

    {"pages":{"page_0001_MainActivity":{"obligations":[{
      "id":"<obligation id>","disposition":"preview_policy",
      "owner":"Slice 1 Step 3c","policy_ref":"<source-backed policy>",
      "preview_value":0,"source_refs":[{"file":"<absolute Android source>","line":123}]
    }]}}}

disposition 为 resolved/script_resolved/preview_policy/deferred/not_applicable。
首屏事项不能 deferred；preview_policy 要 owner/policy_ref；解释不修改原资源值。
各 batch 由主线程合并，重复 ownership 报错。

B2-join 重新 prepare，传相同 pages + --decisions 目录，然后：

    python3 <skills>/a2h-spec/scripts/ui_facts.py render --baseline spec/baseline
    python3 <skills>/a2h-spec/scripts/ui_facts.py lint --baseline spec/baseline \
      --target-input spec/.a2h/target-input.json --project-root "$PROJECT_ROOT" --require-specs

render 只替换标记内的视觉事实/设计令牌块，保留 worker 正文。
lint 检查 target/hash、P0 首屏义务、引用、投影、页面 spec 和 manifest。
--project-root 登记 open-findings.json 的 spec/ui_facts section，不关闭其他 linter finding。
只有修复后重跑才传 --after-repair；普通检查不推进修复轮次。

## Execute 交接

优先级为 selected-state code override → resolved visual fact → usage token →
有 provenance 的 partial-source 读取 → unresolved。Material 默认必须来自固定 AAR。
dp/dip textSize 保留原单位，目标 vp；sp 目标 fp。
FONT_DP_AS_FP 在 SDK 构建和 font-scale fixture 通过前仅 review。
展示数据登记 preview-fixture，不计为业务接线完成；registry row 和消费规则见
[ui-facts-handoff.md](ui-facts-handoff.md)。

默认开启依赖 V2 回归、D3/D4/D8 消费落地和外部 V5 A/B。
截图/渲染对比只在 post-execute 验证工具中使用，不回填 spec 数值。

验证命令、泛化用例和已知边界见 [ui-facts-validation.md](ui-facts-validation.md)。
