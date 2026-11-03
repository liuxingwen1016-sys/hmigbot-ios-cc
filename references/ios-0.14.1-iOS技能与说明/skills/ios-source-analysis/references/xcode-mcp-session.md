# Xcode MCP 正式采集通道

已选择 MCP 后，`source-analysis` 自动执行工程访问前检和实际取证。沿用已有选择，不重复弹授权；本客户端不打开工程、不批准 agent/目录、不改变系统设置。

## 工程访问契约

1. 读取当次工具列表与 schema，按实际名称选择 `XcodeListTargets`／`ListTargets`，参数绑定已选源 project/workspace。枚举返回真实目标，优先使用当前转换已选 target；未选时仅在列表完整且只有一个非测试、非扩展、非 aggregate 目标时确定，否则报告缺上下文，不选第一个。
2. 使用真实 target 调用 `GetTargetBuildSettings`；返回 target 必须一致且 settings 非空。缺枚举工具时只允许使用已确认的原生 target 并记录缺口。缺构建设置能力时不能声称正式工程访问成功。
3. 授权错误立即记 `auth_required`，停止本轮 MCP 分支，不换 session/PID 重试授权，不自动申请新批准。独立 Apple CLI 分析继续，依赖 MCP 的证据保持阻塞。
4. 通过后按当前工具实际采集 targets、已选 target 的 build settings、schemes；文档搜索仅作适用主题的可选补充。各调用保存实际参数、schema、原响应、源码和 fact 绑定；不会因没有 DocumentationSearch 放弃工程取证。

只在当前转换范围内采集，不默认读取工作区全部目标。输入缺字段、返回 malformed/empty、重复或截断目标、不同 target 响应分别失败，不从自由文本猜 target 或构造空参数假探测。

## 会话与恢复

`spec/ref/ios-mcp-session.json` 保存源根、选定 project/workspace/target、provider、command、PID/session、上次状态及收据。session_id 不是授权凭证；复用仍重新探测当前访问。源、目标或服务身份改变不继承授权。它是连接配置，不是业务语义或 PASS 凭证。

已有同范围 `auth_required` 时，普通续跑直接返回原阻塞，不连接、不重复申请。实际 agent/工程授权由开发者在宿主处理；确认处理后显式执行 `source-analysis --project <target> --mcp-recheck`。低层 `mcp-query` 的对应显式重检为 `--recheck-authorization`。这些参数只允许重查，不能批准权限或跳过只读边界；不要将重检永久写进自动续跑脚本。配置支持布尔 `mcp_recheck`，仅用于明确的一次恢复请求。

自动发现优先尝试已保存连接，其次实际运行的实例及默认服务。传输错误可在共享总预算内尝试其他候选；任一候选返回授权错误就停止，不通过换身份绕过。所有尝试单独记录，后台错误不能冒充另一实例的结果。

## 状态和产物

- 通道 `success`：必需工程访问和已选目标取证通过；可选能力缺失/失败保留 `partial`、`gaps`、`failures`，不丢弃有效证据。
- `auth_required`：MCP 阶段 `blocked`，明确需要所选 Xcode agent/工程授权；已取得的局部证据保留，不能据此认定整个通道成功。
- `not_available`／`failed`：MCP 阶段 `completed_with_fallback`，单列具体原因及 CLI 替代，不当作 MCP 完成。
- `source-analysis` 的 `needs_review` 表示规格候选待审；即使 CLI 工作完成，也不抹掉 MCP blocked。查看 `mcp_channel`、`stages` 和 `progress.blocked`，不能仅据命令退出 0 认定 MCP 或 Spec 通过。

`spec/ref/analysis-runs/AR-*/mcp-result.json` 保存通道结果；`mcp-discovery*/`、`mcp-query-session/` 保存 transcript/stderr/timings；`spec/ref/mcp-runs/MCP-*/artifact.json` 通过既有 ios-mcp-index 绑定事实和原响应摘要。错误不写成功索引。MCP 响应仅为 `tool_response`，不自动升级为 compiler_binding 或 runtime 证明。

## schema、等待和边界

只调用已公布的源读白名单，拒绝 mutating 声明和未知必填参数。需要 tabIdentifier 时读取当前只读窗口上下文，唯一绑定所选源；没有可核验上下文就保留缺口，不自动开工程。旧 XcodeListWindows 仅在官方 bridge 且 advertised readOnlyHint=true 时作为上下文读取。

initialize 默认 30 秒，tools/list 和 tools/call 默认各 60 秒；每次发现/查询操作总上限 180 秒，多候选发现共用预算。显式 server JSON 可配置 timeouts.connect/discover/call/overall。超时取消并关闭自有 stdio 进程组，保留原始日志，不无限等待；不会终止用户 Xcode。

状态命令只反映当前进程可见性，服务开关不等于工程授权。隔离协议夹具验证契约、实际调用和状态消费；不等于真实 Apple 工程集成。未指定独立测试工程时，不拿正在转换的应用作维护测试。
