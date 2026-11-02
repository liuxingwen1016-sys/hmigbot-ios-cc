<!-- when: planning or executing an interaction/domain batch -->
<!-- topics: current interaction engine, domain discovery, isolated repair, runtime boundaries -->

# 点击 adapter：使用完整当前引擎

完整定义保存在 [点击引擎入口](../engines/interaction/ENTRY.md)。首次进入点击流程读取该文件；下列领域协议按阶段加载。

| 阶段 | 协议 |
|---|---|
| 初始化/结果 | [流程](../engines/interaction/references/fast-workflow-protocol.md)、[结果](../engines/interaction/references/fast-result-contract.md)、[预检](../engines/interaction/references/preflight-protocol.md) |
| Baseline/Quick 计划 | [Review 提速](../engines/interaction/references/review-efficiency-protocol.md)、[adapter 发现](../engines/interaction/references/adapter-discovery.md)、[adapter 契约](../engines/interaction/references/adapter-contract.md) |
| Baseline | [紧凑审查](../engines/interaction/references/compact-review-protocol.md) |
| 异步/共享服务 | [依赖审查](../engines/interaction/references/effect-dependency-review.md) |
| Repair 计划 | [组织](../engines/interaction/references/repair-organization-protocol.md)、[共享修复](../engines/interaction/references/shared-repair-protocol.md) |
| Repair 执行 | [修复](../engines/interaction/references/fast-repair-protocol.md)、[原生直接发布](../engines/interaction/references/direct-repair-protocol.md)、[统一直接发布](direct-repair-protocol.md) |
| Quick | [快速审查](../engines/interaction/references/quick-review-protocol.md) |
| 用户授权目标验收 | [真机与独立验收](../engines/interaction/references/runtime-validation-protocol.md) |

涉及回调、订阅或共享 writer 的入口，按[效果反馈与副作用](effect-feedback-safety.md)审查返回路径和重复副作用；ENTRY_CHECK_ONLY 同样核对本入口与公共补丁的实际关系，不能继承其它入口的安全结论。

常规 Baseline、已启用的 Quick 和 direct Repair 均支持默认六槽，按[全局并发口径](unified-dispatch.md#concurrency-contract)与设置共用额度；不用原生 Review dispatcher 再创建额外槽。原生 `validate-draft → publish → merge → quality-check`、affinity catalog、scope、SDK 声明、真实根因、九角色与证据哈希全部保持。新 Repair 使用 direct：全部执行槽用于修复，无逐批 reviewer，原生隔离 dispatcher 冻结 worker_root；停写 submit 后主会话确定性 publish，再补位。同文件 writer 锁跨待发布队列保留。依赖变化/受影响项在 full-repair 交唯一一次独立 Quick，默认模式只保留审计证据，均不制造语义通过。worker 只编辑返回的 `worker_root` 下绝对路径，并运行原生 `check`。误改私有副本可 refresh/fail；正式源码异常只按可验证 before/after journal 精确恢复，保留哈希、diff 与恢复证据。无可靠归因的外部修改保护原字节并报告 blocker，不直接用旧 snapshot 覆盖。单批可安全封存的失败继续补位。


organization 使用当前源码路径级候选和显式 target_mapping 裁决；不同 callable/anchor 可证明共同根因，但必须逐入口保留结果。Quick 消费 direct publication 的依赖变化与 affected entries，仍覆盖全部 Baseline FIX_REQUIRED，不把自动合并当成已修复。

新统一运行各阶段点击优先；每个已启用修复轮次允许按[补位协议](repair-overlap.md)提前执行有完整独立性证据的设置批，设置正式发布仍等待点击收口；没有提前初始化时才在交接处 rebase 设置 manifest。使用原生新 dispatcher 的领取/attach 握手、[CC 独立上下文映射](unified-dispatch.md#claude-code-host-mapping)、固定树外 `draft_path`、整批自动 `required_scope_target`、发布摘要与正则字面量误报修正。统一层不另写领域推导器，只消费原生冻结检查域并归一化显式参数；不能缩小原生领域保护或将发布摘要当作完整审查证据。

scope hazard 是提示，不是确诊。下载完成顺序的审查必须区分局部待提交对象中的 `COMPLETED` 参数与已发布状态/terminal map/数据库回读；前者不自动构成过早终态。只有可达消费者能在提交前观察到成功时才确认该缺陷；无法证明时保留原生 `NO_DEFECT/UNRESOLVED` 的 SHA 绑定裁决，不为清零修改合法状态构造。

媒体控制逐入口、事件和状态分支核对命令身份。播放保留平台状态序列、返回后播放条、点击重开、展开状态 3 秒稳定及当前媒体 identity。下载保留匹配 task 的真实 callback、最终非空文件、提交后数据库回读、下载列表及后置动作；注册日志、截图、文件存在、UI 局部布尔值都不能单独证明完成。

仅对当前源码能力启用域规则，不强加 AVPlayer/request.agent 到普通点击或未知框架。SDK 支持的 BACKGROUND、cache 相对 saveas 不是缺陷；mkdir throws 清单也不是可达性证明。修复 app-owned 静态断点并把真实网络/设备条件列为 runtime gap，不能因缺真机证据跳过确定的空 callback/禁用门。

独立验收在封存结果之外生成矩阵、before/after、observations/report，真实控件点击与 task/entity 身份证据逐行对应；没有执行的项保留 NOT_TESTED/BLOCKED。失败只报告，不能开启第三轮、重装绕过或回写原封存结果。

点击固定使用[核心候选](../engines/interaction/references/candidate-policy.md)，CLI 不接受候选模式参数。热点 writer 按原生协议；提前 Quick 通过[统一性能入口](behavior-performance.md)协调两域，不能绕过全局名额和剩余 writer 检查。
