# scripts/ — 与 ArkTs-Core 的同步工具

本目录是 **migbot 仓库维护者**的内部工具，用于把上游 ArkTs-Core 的 skill 同步进来。
插件使用者不需要关心这里。

---

## 先做一次性设置

克隆仓库后执行两条命令，之后所有脚本都能直接跑：

```bash
# 1. 启用 pre-commit 提示（改到共享 skill 时提醒回推上游）
git config core.hooksPath .githooks

# 2. 告诉脚本你本机的 ArkTs-Core 在哪
git config migbot.coreRoot /path/to/ArkTs-Core
```

两条都写在 `.git/config` 里，**不随仓库分发**，所以每个人都要各自执行一次。
第 1 条尤其容易漏——不设置的话 hook 文件虽然在仓库里，git 也不会调用它。

---

## 背景：skills/ 有两类来源

| 来源 | 数量 | 真相源 | 改动后 |
|---|---|---|---|
| ArkTs-Core | 71 | **上游** | **必须回推上游**，否则下次同步被覆盖 |
| migbot 独有 | 16 | 本仓 | 直接改即可 |

migbot-only 的是 `claude-session-stats`、`migbot-increment-*`、`rq-*`、
`arkts-webview-manager`、`mod-design`、`prd-generator`、`tdd-enforcer` 等。
完整清单见 [`.githooks/core-skills.manifest`](../.githooks/core-skills.manifest)。

**为什么"回推"这件事要专门强调**：migbot 依赖的打点、构建护栏、frontmatter 引号
曾被上游整版同步覆盖 **3 次**（v1.1.2 / v1.2.1 / v1.2.2）。其中 v1.2.1 声明恢复
却漏掉了 `arkts-component-builder`，因为当时 CI 只断言 8 处上报调用，护栏和引号
不在其中。现在这些内容已内置到 ArkTs-Core，两侧各有一道防线：

- **上游** `scripts/ci/check-migbot-contract.sh` — 谁删掉契约，PR 就红
- **本仓** `.githooks/pre-commit` — 改了共享 skill 就提醒回推

---

## 脚本

### `sync-skills-from-core.sh` — 同步上游产物

```bash
# 先在 ArkTs-Core 侧完成构建
cd <ArkTs-Core>/build/script-compression
python3 scripts/run.py --no-build --no-verify

# 回到 migbot，先看会改什么
./scripts/sync-skills-from-core.sh --dry-run

# 确认无误后执行
./scripts/sync-skills-from-core.sh
```

同步完会自检 14 条契约（8 条上报 + 2 条授权门控 + 4 条护栏）和全量 frontmatter
可解析性，任一不过即非零退出。

**为什么不直接 `cp -r`** —— 三条约束都来自实际踩过的坑：

1. **绝不用 `--delete`**。migbot 那 16 个独有 skill 上游没有，带 `--delete`
   会全部删光。
2. **平台完整性闸门**。不带 `--delete` 意味着只更新 dist 里有的平台，缺失平台的
   二进制原地保留 ⇒ 同一 skill 在 macOS 和 Windows 跑不同版本。缺平台直接拒绝；
   确知只发单平台可加 `--allow-partial-platform`。
3. **stub 退化闸门**。分发的 `.py` 应是 26 行 launcher stub（真实逻辑编译在
   `bin/<平台>/_entry.dist/` 里）。若 dist 里是明文源码而本仓是 stub，说明该
   skill 这次没编译进去——覆盖会泄露源码，并与残留的 `_entry.bin` 版本错配。
   曾有一次用缺少 `_artifacts` 的仓跑 `--no-build`，组装出的残缺产物把 31 个
   已编译 stub 换回了源码。

### `gen-core-manifest.sh` — 重新生成共享清单

```bash
./scripts/gen-core-manifest.sh
```

上游新增/删除 skill，或 migbot 调整分发范围后跑一次。清单决定 pre-commit hook
对哪些 skill 提示回推。

### `lib/resolve-core.sh` — 路径解析（被上面两个 source）

按 **命令行参数 → `ARKTS_CORE_ROOT` 环境变量 → `git config migbot.coreRoot`**
的优先级解析 ArkTs-Core 位置，并校验目标确实是该仓库。路径因人而异，故不写死在
仓库里。

---

## 改了共享 skill 之后

pre-commit 会提示，按提示回推上游即可：

```bash
cd <ArkTs-Core>
# 把改动应用到 arkts-skills/skills/<name>/
bash scripts/ci/check-migbot-contract.sh   # 回推后自检
```

仅本地实验、不打算保留的改动可以忽略提示（hook 不阻断提交），或用
`SKIP_CORE_SYNC_CHECK=1 git commit ...` 跳过。

---

## 相关文档

- [`docs/skills-telemetry-instrumentation.md`](../docs/skills-telemetry-instrumentation.md)
  — 打点的完整规范，§3 是逐 skill 可直接粘贴的原文，§5 是整版替换后的重应用 checklist
- [`.githooks/core-skills.manifest`](../.githooks/core-skills.manifest) — 共享 skill 清单
