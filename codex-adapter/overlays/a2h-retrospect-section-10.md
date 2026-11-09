## 10. 数据采集与上报

**本节是 a2h-retrospect 的必跑收尾步骤**：§7 回顾报告产出 ≠ skill 完成。报告写出来之后必须紧接着把下面两条命令跑完，skill 才算真正结束。

**【硬约束】严禁**用 Write / Edit / NotebookEdit 工具直接创建或修改 `.migbot/metrics/` 下任何文件——所有产物必须由下列 `.migbot/bin/a2h-codex` 命令作为副产物生成。手工伪造文件等于把假数据上报给服务端。

> 全程由**主 agent** 在当前会话里直接调 Bash，**不要派发 subagent**。

原始 transcript 通道现在是自动的：Codex 生命周期 hook 会上传会话切片，服务端据此重新解析出用量数据。因此本步只剩两条命令（每条都是纯本地 Bash，不需要 LLM 推理）：

```bash
# 1. 代码行数对比（LOC 事实）→ code-lines.json
.migbot/bin/a2h-codex count-lines

# 2. 收尾：标记 retrospect 阶段，写出 <project>/retrospect.done sentinel
.migbot/bin/a2h-codex mark-stage a2h-retrospect
```

**步骤说明**

- **#1** `count-lines` 产出 Android / HarmonyOS 两侧按文件类型的行数，并记录 `android_app_name` / `harmonyos_app_name`。其中 `file_type:"total"` 为**核心代码行数**——仅累加源码与 UI/资源（`.java/.kt/.xml/.ets/.ts/.arkt/.proto`），已排除构建/依赖配置（`gradle/kts/properties/json/yaml/yml`）与文档（`.md/.txt` 本就不在统计列表内）；各配置类型仍保留独立的 per-type 记录，仅不计入 `total`。
- **#2** `mark-stage a2h-retrospect` 写出本阶段的 stage-marks fact，并落下 `.migbot/metrics/<project>/retrospect.done` sentinel（命令会剥掉 `a2h-` 前缀）——**这个 sentinel 就是 `$a2h-run` 用来判定 retrospect 阶段完成的 marker**。受授权门控、尽力而为，忽略退出码、绝不阻断。
