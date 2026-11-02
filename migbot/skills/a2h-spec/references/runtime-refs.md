# 新项目的运行时引用契约

本契约用于新的空项目。保留 canonical snapshot ID；不迁移历史复制产物。

## 存储与身份

snapshot 的 view.xml 始终是静态合成树，meta.view_xml_origin=static_synthetic。
PNG 与运行时 XML 保存在 spec/.a2h/android-fast-traverse/<run_id>/android_traverse_screenshots/。
<run> 是 run_id 容器，<out> 是其固定产物目录；--run 接受两者，run_id 始终取容器名。
每个 snapshot 的 runtime-refs.json 使用 path_base=spec，文件引用是 {path, sha256}；
必须将整个 spec/ 与采集目录一起保留、导出。不得存绝对 run_root、复制截图或覆盖静态树。

以 snapshot meta.activity（源码完整类名）和 capture meta.activity_info.resumed_activity
规范化对应。安装 applicationId 与源码 namespace 分开保存。目录名称、序号、
aft.kind 和标签不能充当页面或语义状态身份。混淆 resource-id 不能关联源码符号 ID。

## Spec 的操作顺序

1. ui_pipeline.py preflight 返回 ready 后才能派发分析任务。
2. 静态 facts、canonical 页面清单和 target-input 就位。
3. 调用新版 android_fast_traverse inspect/profile/run/report；profile、review 位于 <out>/_aft/input/，同一 <out> 的 run 自动续跑。
4. 生成对应草稿：

~~~sh
python3 <a2h-spec>/scripts/promote_android_fast_traverse.py \
  --project-root <project> --run <project>/spec/.a2h/android-fast-traverse/<run_id> \
  --draft --output <project>/spec/.a2h/runtime-mapping.json
~~~

5. 主线程根据源码、click_path、trigger_element、标签、Tab 索引和完整 XML 解析结果，
   将 captures 分组为语义状态；处理宿主组件、重复实例、滚动帧、未采原因。
   草稿中的 semantic_review_required 必须经过实际审阅后移除或置 false。
   capture 名字生成的 state_id 只是候选，不能把所有 MainActivity captures 当成不同页面。
6. 提交引用：

~~~sh
python3 <a2h-spec>/scripts/promote_android_fast_traverse.py \
  --project-root <project> --run <run> \
  --mapping <project>/spec/.a2h/runtime-mapping.json \
  --output <project>/spec/.a2h/runtime-mapping-receipt.json
~~~

## 映射输入（schema_version=3）

pages 必须覆盖所有 canonical snapshot 恰好一次。一个页面可以对应多个 capture；
一个 capture 可为宿主与子组件提供证据，原文件仍只有一份。

~~~json
{
  "schema_version": 3,
  "pages": [
    {
      "page_id": "page_0003_MainActivity",
      "states": [
        {
          "state_id": "weather",
          "source_page_ids": ["page_0010_MainActivity", "manual_0041_MainActivity"],
          "review": "已核对天气 Tab；第二 capture 是同一状态的列表实例"
        },
        {
          "state_id": "forecast",
          "source_page_ids": ["manual_0068_MainActivity"],
          "review": "点击预报 Tab 后的运行时内容"
        }
      ]
    },
    {
      "page_id": "page_0026_WeatherLineActivity",
      "states": [],
      "host_bindings": [
        {
          "state_id": "forecast",
          "host_page_id": "page_0003_MainActivity",
          "host_state_id": "forecast",
          "source_component": "example.WeatherLineFragment",
          "source_refs": [{"file": "<实际 Android 源文件>", "line": 123}],
          "region_px": [0, 100, 1080, 2100],
          "review": "源码确认宿主展示等价内容；不是独立 Activity 被采到"
        }
      ]
    }
  ]
}
~~~

示例 ID 和 region 必须替换为本次实际证据；数组中仍需列出其他页面。

## 零映射

没有 states 和 host_bindings 时必须有 zero_mapping={status,reason,source_refs?}。
status 可为 mapping_pending、pending_capture、condition_unmet、channel_hidden、
source_unreachable、external_callback、headless、source_only。
条件、隐藏、不可达、回调和 headless 分类必须附实际源码引用。
它们描述证据状态，不自动排除交付范围，也不证明实现完成。
已有 states 或 host_bindings 时禁止再写整页 zero_mapping。部分未采状态写
state_gaps=[{state_id,status,reason,source_refs}]，ID 不得与已采状态重复，必须有实际源码引用。
Execute 只接受该记录机械派生的 fallback；“progressive pending”等任意文本不构成替代依据。

progressive 必须逐页登记未采原因；runtime_required 的可见 UI 必须有运行时状态。
headless/external_callback 只验证其行为与路由，不要求不存在的独立截图。
source_only 由 ui_pipeline gate 初始化空引用，后续可用源码替代实现，视觉结果保持 BLOCKED。

## 真实 XML 与下游

runtime_view.py 是标准解析入口，完整解析原文件并绑定 SHA256。禁止单行大 XML 直接 Read，
禁止每个 Converter 临时自写解析器或按源码 resource-id 搜索混淆后的运行时树。

~~~sh
python3 <a2h-spec>/scripts/runtime_view.py --xml <runtime.xml> --density <实际 factor> \
  --out <derived-tree.json>
~~~

真实树提供当前帧结构、文本、bounds、交互属性、重复列表实例；样式、隐藏分支和动态逻辑
由静态事实及源码补充，自绘外观由 PNG 检查。不同状态不能拼成同时显示的树。
宿主生成外壳、容器和导航；子组件使用 reviewed region 内的树，不重复生成宿主栏。
使用实际 density，不默认 3x。没有 bounds 表示未知，静态 clickable=false 不证明无源码事件。

B2 worker 必须读取本页引用及标准解析摘要；B2-join prepare/render 只刷新静态产物，
不改 runtime-refs.json 或 traversal。Gate B 检查完整引用图、身份、PNG/XML 配对及哈希。

所有 PNG/XML 路径跟随 index.json；有效帧可位于 _aft/revisions/，不能假定 PAGE_ID/screenshot.png 是最新版。
runs[].run_root 相对 spec/ 指向容器，output_root 指向固定产物目录；单帧 png/xml/meta 引用仍相对 spec/，不复制帧。
