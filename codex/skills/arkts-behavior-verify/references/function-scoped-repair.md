<!-- when: reviewing setting repair resources or executing a setting repair worker -->
<!-- topics: method-body scope, shared state, pre-edit intent, bounded overlap, publication backpressure -->

# 设置方法体的有限并发

新运行复用 Baseline/Quick 的真实源码审查，允许 setting 通道内同文件的独立方法体在隔离副本中并行。interaction 同文件与跨通道同文件仍按文件串行。没有新增逐批复核 Agent，主会话只执行原生发布命令，不承担业务补丁合并。旧运行不热迁移。

## 审查时声明

先完成 `repair_read_set` 的完整文件读集，再为预计只修改已有方法体的 setting 添加可选 `function_scope`。涉及新增字段、import、签名、构造、生命周期、共享状态机或不明确依赖时留空；仍可走原有文件级修复。

```json
{
  "complete": true,
  "basis": "实际读到的调用者、状态与副作用为何独立",
  "unknown_dependencies": [],
  "resources_read": ["state:qualified-owner.field"],
  "resources_write": ["effect:qualified-operation"],
  "read_regions": [],
  "write_regions": []
}
```

`resources_*` 使用规范的全限定共享状态、偏好键、事件、缓存和副作用身份；相同资源不能按功能名换个别名。纯函数可以为空，但必须有实际证据。修改读取方式、订阅、调用方契约或共同状态时应声明冲突，不能仅以“不同方法”判断独立。

用 `python <skill>/scripts/function_scope.py --root <HMOS> --path <relative> --signature "Owner::method(): Type {"` 提取精确 region；输出含 `path/signature/body_sha256/context_sha256`，无需手算哈希。read_regions 包含所读的相关方法体，write_regions 包含预计修改的方法体。文件读集中的某个文件没有 region 时仍按整文件读。写入文件必须全部有 write_regions；一个原生 batch 内全部 setting 都有有效声明才启用。

当前仅支持单行签名的已有命名方法体。方法头、字段、import 及其他非方法体字节受保护；嵌套模板插值、歧义 slash、歧义签名和不支持的语法自动退回文件串行。声明封存在原审查 sidecar，注册时自动聚合，不能从路径/方法名自动推断完整性。

## Worker 编辑前与发布

1. 使用 claim 的精确 `required_reading`、packet、worker_root 和 draft_path。先读 packet 中本批已封存的 findings/consumer 锚点，校验当前源码；未变化的事实与 SDK 定位直接复用，变化的依赖才重新追踪。逐项结论和副作用自查仍不可继承，不必再做一遍全量 Baseline 搜索或逐角色进度叙述。
2. 编辑前写树外 intent JSON：`{ "setting-key": ["planned/relative/path.ets"] }`，覆盖每个 key（不改的 key 填空数组）。运行 claim 给出的 `edit_intent_command_prefix` 加 `--edit-intent <JSON>`。原生 check 在编辑前检查每个 key 的 edit_paths，整批 ownership 不等于每项都有权限。方法体并发模式下，未登记 intent 的实际修改会被拒绝。
3. 有 native `function_contract` 时，只修改声明的方法体。check/submit 检查真实差异；发布再次检查依赖方法与文件结构、三方合并、原生草稿及 CAS。文本合并成功不产生语义通过；仍为 STATIC_UNVERIFIED，不替代集中编译。
4. 同文件最多两批组成一个窗口，窗口收口前不滚动加入第三批。草稿排队仍保留窗口；至少两份可发布结果积压时暂停新领取，先发布。等待 interaction 收口的早期 setting 草稿不计入全局可发布队列，避免阻塞其前置点击批。
5. `FUNCTION_SCOPE_EXCEEDED`：原 worker 撤回声明外修改，或停写并等待同文件同伴先完成，再 refresh 原批进入文件串行。`FUNCTION_DEPENDENCY_CHANGED`/文本冲突：同样定向修正或 refresh，不新增 reviewer，不重跑 Baseline。refresh 保留原 agent/token，归档旧稿，使用新副本和新 draft；原有 refresh 次数上限不变。两个同伴都无法发布时，用现有 fail 如实记录不可闭合批以释放窗口，不能互相无限等待。

这条通道依赖 reviewer 的完整性声明；机械检查验证实际范围、源码版本和合并，不证明业务独立。无法作出可靠声明就保留文件串行。

## 分包与指标

先按共享 writer/逻辑组聚合，再统计分组间仍重复的写入路径为热点。仅把完全不含这些热点的独立小组在原条目/路径上限内合并；热点组不附带无关工作。保留 exactly-once、foundation 例外与原生 ownership。

比较总阶段耗时、平均执行并发、可发布队列、refresh/失败与同文件并发窗口数。静态模拟和单测能证明调度/保护行为，不能宣称真实模型耗时已大幅下降。若需要修改公共状态，就合并/串行相关任务，不通过追加集中复核来追求执行槽满载。
