<!-- when: 派发 Stage 2 Base worker（a2h-migration-worker，Base 层任务）时加载本段 + _common.md -->
<!-- topics: Stage 2 Base worker prompt, Base 层任务, 占位规则 -->

# §3. Stage 2 Base worker prompt（a2h-migration-worker）

> 公共占位规则 §2.1 见 [`_common.md`](./_common.md)，派发时一并 Read。

```
Agent(
  prompt="你正在执行 Android→HarmonyOS 迁移 Base 层任务（执行时序 Phase 0）。

  任务: {task_name}
  描述: {task_description}
  详细信息: {task_details}

  使用 Skill: {suggested_skills}
  输入来源: {task_input_source}
  输出位置: {task_output_path}

  Android 源码路径: {android_source_dir}
  HarmonyOS 项目路径: {harmony_project_dir}

  验收标准:
  {task_acceptance_criteria}

  占位规则：合法占位的 marker 形态与 kind 枚举权威定义在
  `a2h-plan/templates/placeholder-registry-template.md`。Base worker 阶段常用 kind:
  - `forward-ref`：Base signature 桩（如 `throw ApiException(...)`），登记 `resolve_by=Slice {N} Step 3c`
  - `thirdparty-sdk`：三方 SDK 占位 + 白名单 trigger_condition
  - `resource-pending-asset`：fallback 资产 + `trigger=<resource-id> 就绪`
  - 需要他 Base 任务的产出但尚不存在（同组并行时常见）：只写本任务 output 目录，以接口 / 类型桩 + `// FWD-REF: P-B{N}-{seq}` 登记 `kind=forward-ref`，trigger 用白名单 `<file-path> 实现 <symbol>`；禁止写入他任务 output 目录、禁止自建替代实现
  所有占位 6 字段齐全；其余写法（自由 TODO 注释 / console.info('TODO:...') / 空回调 / 资源 value 含未登记 [TODO:...]）一律禁止。",

  subagent_type="hmigbot:a2h-migration-worker"
)
```
