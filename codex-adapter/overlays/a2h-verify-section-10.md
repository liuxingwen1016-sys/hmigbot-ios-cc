## 10. 收尾：盘库 + 上报本阶段用量

verify 成功产出 `spec/verify-report.md` 后，作为本 skill 的最后一步执行（纯本地 Bash，**忽略退出码、绝不阻断**）。**两条命令的先后顺序有意义，不要调换**：

```bash
# 1. 代码行数盘库（LOC 事实）→ code-lines.json
.migbot/bin/a2h-codex count-lines

# 2. 标记本阶段水位
.migbot/bin/a2h-codex mark-stage a2h-verify
```

- **`count-lines`** 统计 Android / HarmonyOS 两侧的代码行数。verify 通过即迁移完成，此刻两侧代码都已就位，是行数盘库的第一个有效时点——而 `$a2h-init` 那次盘库跑在迁移之前，HarmonyOS 侧尚不存在（记为 `null`）。缺了这一次，一个只跑到 verify、不跑 retrospect 的迁移会永远停在"已完成、HarmonyOS 0 行"。a2h-retrospect 结尾还会再盘一次（覆盖同一 run 的 fact），两次都跑不会重复计数。
- **`mark-stage a2h-verify`** 写出本阶段的 stage-marks fact 与 sentinel。这个水位就是**服务端判定"迁移已完成"的唯一依据**（Codex 没有 CC 的 finalize 上传）——所以它必须排在 `count-lines` 之后：完成状态一旦落库，看板就会开始展示这个 app 的行数，行数得先就位。token / subagent / skill 维度的用量由生命周期 hook 上传的会话记录在服务端解析归因，供性能看板（5002）的事件时间轴使用；本步不自行采集用量。
