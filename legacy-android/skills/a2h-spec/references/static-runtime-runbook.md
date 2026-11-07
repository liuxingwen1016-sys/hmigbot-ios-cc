# 新空项目 static-v1 + traverse 的运行顺序

源码路径确认后先运行：

~~~sh
python3 <a2h-spec>/scripts/ui_pipeline.py preflight --project-root <project>
~~~

needs_selection 时主线程调用宿主询问工具；不派发 Phase 0/参考分析/B-API。
完整已提供选择直接 configure；缺一项只问缺项。实际答复后 configure，再确认 ready：

~~~sh
python3 <a2h-spec>/scripts/ui_pipeline.py configure --project-root <project> \
  --facts static-v1 --runtime progressive --reason "<实际用户选择>"
~~~

建立并验证 spec/.a2h/target-input.json，固定 variant/source sets/资源身份。
按 static-ui-facts.md 运行 ui_facts.py prepare --policy static-v1。
静态页面身份与三源事实就位后，按 android_fast_traverse Skill 运行 inspect/profile/run/report；
产物固定在 <run>/android_traverse_screenshots，profile/review 放其 _aft/input；同一产物目录自动续跑至 completed/completed_with_gaps。

按 [runtime-refs.md](./runtime-refs.md) draft→review→promote，保留全部原始 PNG/XML，
生成每页引用，不复制证据。B2 worker 消费引用与共享解析摘要后生成 page specs。
B2-join 再 prepare/render/lint，只更新静态文件，不覆盖引用。

~~~sh
python3 <a2h-spec>/scripts/ui_pipeline.py gate --project-root <project> \
  --pages-file <canonical-pages.json> --run <run> --pending <progressive-pending.json>
~~~

runtime_required 不传 pending；source_only 不传 run，gate 创建空引用。
Gate B 通过后正常进入后续 Spec/Plan 审批。Plan 生成 stage1-ui-delivery.json，
Execute 冻结 ui-inputs 并按组件/状态生成、装配和验证，详见
[UI delivery contract](../../a2h-execute/references/ui-delivery-contract.md)。
