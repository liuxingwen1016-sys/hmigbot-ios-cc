---
name: claude-session-stats
description: 通用代码行数统计原语。任何需要 LoC 对比的 agent 都应该调用 `.migbot/bin/a2h count-loc`，而不是在 LLM 里现写解析逻辑。token / 工具 / 子代理用量不再由本地解析——生命周期 hook 上传会话切片后由服务端推导。a2h-retrospect 的主 agent 是其典型调用方，但本 skill 不绑定 a2h 业务，可被任何流水线复用。
metadata:
  type: util
  domain: generic
  tags:
  - util
  - stats
  - telemetry
---
# claude-session-stats

## 1. 为什么需要这个 skill

任何需要做"回顾 / 上报 / 度量"的流程都要回答两类问题：

1. **代码量**：某个目录下，每种文件类型有多少行？
2. **会话消耗**：本次 Codex 会话烧了多少 token、调用了几次工具 / Skill / 子代理？

如果让 agent 每次进 retrospect 都现写 Python / bash 解析，会有三个问题：
- 每次几百 token 浪费在重复推导上；
- 字段命名、JSON 形状每次都漂；
- 解析 jsonl 时遗漏 `usage.cache_*` 之类的字段是常见 bug。

代码量这件事固化成 `.migbot/bin/a2h count-loc` 一个子命令，agent 只需要 `Bash` 调一行，确定性输出 JSON。会话消耗不再在本地解析：生命周期 hook 自动上传会话切片，token / 工具 / 子代理用量由服务端从切片推导（看板 5002 可查）。

## 2. 提供的原语

### `a2h count-loc <dir> [--ext ext1,ext2,...] [--json]`

走 `<dir>` 下所有匹配扩展名的文件，按扩展名汇总行数。

- `<dir>` 不存在不报错，输出 `{"exists":false,"total":0}`，方便 agent 直接管道。
- 默认扩展名列表覆盖 Android / HarmonyOS / ArkTS / JVM 构建文件：`java,kt,xml,gradle,kts,properties,json,yaml,yml,proto,arkt,ts,ets`。需要别的就传 `--ext rs,go,py`。
- 优先用 `ripgrep`（`rg`）扫，没有就降级到 `find + wc`。
- 不读 `.migbot/config.json`，不假设双端结构。要做"Android vs HarmonyOS"这种业务对比，由调用方分别跑两次自行 diff。

JSON 形状：
```json
{
  "dir": "src/main",
  "exists": true,
  "total": 12345,
  "by_ext": { "java": 8000, "kt": 4000, "xml": 345 }
}
```

## 3. 怎么用

### 在 agent 流程里调用

```bash
# 代码量对比（Android 一侧）
.migbot/bin/a2h count-loc "$android_path" --json > /tmp/android-loc.json

# 代码量对比（HarmonyOS 一侧）
.migbot/bin/a2h count-loc "$harmonyos_path" --json > /tmp/harmonyos-loc.json
```

## 4. 边界

**这个 skill 不做：**
- 不上传任何数据到服务器（上传由生命周期 hook 与各 stage skill 的 `mark-stage` / `count-lines` 负责）；
- 不写 `.migbot/metrics/`（调用方拿到 stdout JSON 自己决定怎么落盘）；
- 不假设双端代码结构、不假设业务 schema。

**这个 skill 是无副作用的纯计算原语**，可以放心被任意流程 / agent / 脚本调用。

## 5. 退出码

| 退出码 | 含义 |
|---|---|
| 0  | 成功（包括 count-loc 目标目录不存在的情况，仍输出空 JSON） |
| 64 | 用法错误：缺参数 / 未知 flag / 未知子命令 |
