<!-- when: Phase A 调用确定性脚本生成 meta.json 骨架 / 合成 view.xml 时加载 -->
<!-- topics: synthesize_meta_json, synthesize_view_xml, scaffold 模式, enrich 模式, 合成 view.xml 特征 -->

# Phase A 确定性脚本调用

Phase A 用 android-ui-graph-builder 的两个脚本做确定性提取：`synthesize_meta_json.py`（scaffold 生骨架 / enrich 补字段）与 `synthesize_view_xml.py`（无 UIAutomator dump 时从 layout XML 合成 view.xml）。

Dialog 先运行：

```bash
python3 .claude/skills/a2h-spec/scripts/prepare_dialog_artifacts.py \
  --project-root "$PROJECT_ROOT" --android-root "$ANDROID_SRC" --prepare-all
```

该命令生成确定性 inventory，并按唯一 `layout_owner_fqn` 写
`spec/baseline/dialog-snapshots/`。页面脚本调用不变；批量调用 `synthesize_meta_json.py` 时传
`--dialog-inventory spec/.a2h/spec-run/dialog-inventory.json`，使 page type 与 coverage 共用同一继承闭包。
Phase B 写 index 前先运行 `a2h-spec/scripts/dialog_index.py --skeleton`；hashed keys、source FQN、
call sites、hosts 和 snapshot ref 必须原样采用脚本输出，不得手抄或改写。

## Step A2a 确定性骨架生成（scaffold 模式）

对每个 Activity/Fragment，先运行确定性脚本生成 meta.json 骨架：

```bash
python3 .claude/skills/android-ui-graph-builder/scripts/synthesize_meta_json.py \
  $ANDROID_SRC \
  --activity {fully_qualified_class_name} \
  --page-id {page_id} \
  --output spec/baseline/ui-snapshots/{page_dir}/meta.json \
  --mode scaffold \
  --package {package}
```

脚本自动提取：`layout_sources`、`menu_sources`、`fragment_tags`、`style_sources`、`recycler_item_layouts`、`navigation_targets`。LLM 需补充的字段以默认占位值标记（`label=""`、`confidence="medium"`、`dynamic_menus={}`、`navigation_mode="UNKNOWN"` 等）。

## Step A3 合成 view.xml（无 UIAutomator dump 时）

1. 确认 meta.json 中 `layout_sources` 已填充（来自 Step A2 分析结果）
2. 调用合成脚本：
   ```bash
   python3 .claude/skills/android-ui-graph-builder/scripts/synthesize_view_xml.py \
     $ANDROID_SRC \
     --layouts "{meta.json.layout_sources 逗号拼接}" \
     --menus "{meta.json.menu_sources 逗号拼接}" \
     --resolve-strings \
     --resolve-styles \
     --output spec/baseline/ui-snapshots/page_NNNN_XxxActivity/view.xml \
     --package {AndroidManifest 中的 package 属性}
   ```
3. 脚本输出结果处理：
   - 成功 → 在 meta.json 中标记 `"view_xml_synthesized": true`，confidence 维持 `medium`
   - 失败 → confidence 降为 `low`，meta.json 标记 `"view_xml_synthesized": false`，记录失败原因，不阻塞后续 Phase
4. view.xml 合成后，运行 enrich 模式补充 `clickable_elements`（从 view.xml 提取）：
   ```bash
   python3 .claude/skills/android-ui-graph-builder/scripts/synthesize_meta_json.py \
     $ANDROID_SRC \
     --activity {fully_qualified_class_name} \
     --page-id {page_id} \
     --output spec/baseline/ui-snapshots/{page_dir}/meta.json \
     --mode enrich \
     --existing spec/baseline/ui-snapshots/{page_dir}/meta.json \
     --view-xml spec/baseline/ui-snapshots/{page_dir}/view.xml \
     --package {package}
   ```

合成版 view.xml 特征：
- 根元素 `<hierarchy synthesized="true">` 标识为合成版
- `bounds` 属性始终为空（无运行时坐标数据）
- `class` 为全限定类名，`resource-id` 为 `{package}:id/{name}` 格式
- `clickable`/`enabled`/`scrollable` 等从 XML 属性取值，无则用 Android 默认值
- 递归处理 `<include>` 和 `<merge>` 标签

---

## Step A3 源码映射可靠性规则（`layout_sources` / `style_sources` 填充与验证）

脚本 scaffold 出的路径字段由 LLM 校验补全；下列规则是 meta.json 写入前的**强制**口径。

**源码映射可靠性规则**：

`layout_sources` 填充规则：
- **必须**包含主 layout（来自 `setContentView` / `inflate`）
- **必须**包含所有 `<include>` 传递引用的 layout
- 路径**必须**相对于 `$ANDROID_SRC`（如 `app/src/main/res/layout/activity_main.xml`）
- 生成后逐路径验证：确认 `$ANDROID_SRC/{path}` 实际存在
- 不存在的路径 → 从列表移除并输出警告

`style_sources` 填充规则：
- 始终包含「标准三件套」（如果存在）：`values/styles.xml`, `values/themes.xml`, `values/colors.xml`
- 包含 layout XML 中 `style="@style/xxx"` 引用的具体文件
- 包含 Activity 在 AndroidManifest 中声明的 `android:theme` 对应文件
- 包含 `values-night/` 等变体目录下的对应文件（如果存在）

验证步骤（meta.json 写入前必须执行）：
1. 逐路径检查 `$ANDROID_SRC/{path}` 是否存在
2. 路径不存在 → 从列表移除 + 输出警告（不降级 confidence）
3. 所有路径验证完毕后写入 meta.json
