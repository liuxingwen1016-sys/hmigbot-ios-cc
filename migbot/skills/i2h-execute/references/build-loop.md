<!-- when: 编译检查点派发 hmos-builder agent + placeholder 回填时加载 -->
<!-- topics: 编译闭环, hmos-builder agent, placeholder 回填, trigger 白名单 6 类, 升级诊断, 构建操作纪律 -->

# 编译修复流程细节

## 宿主编译检查点

在真实入口已经接线且本批代码写入结束时运行。复用现有目标项目构建命令及依赖缓存，输出原始日志和聚合诊断。

```bash
python3 .claude/skills/i2h-execute/scripts/host_build_checkpoint.py \
  --project-root . --log spec/execution/host-build.log \
  --out spec/execution/host-build.json -- ./hvigorw assembleHap --mode module
```

退出 0 表示 Hvigor 成功且前后生产源码摘要一致，1 表示编译或签名失败，2 表示宿主访问、工具或结果不确定。源摘要变动时，以无并发写入的同一快照重跑。宿主交接日志需要绑定输入摘要。此命令只输出诊断，正式构建验收和迁移账本沿用原有入口。

需要把签名包与现有 Stage 1 / Verify 设备取证接线时，在已授权宿主执行以下命令。构建命令应产出或更新所选 HAP，SDK 验签和设备安装成功后才发布交接。

```bash
python3 .claude/skills/i2h-execute/scripts/host_build_checkpoint.py \
  --project-root . --log spec/execution/host-build.log --out spec/execution/host-build.json \
  --scope spec/execution/stage1-visual/scope.json --signed-hap "$HAP_PATH" \
  --java "$JAVA_BIN" --sign-tool "$HAP_SIGN_TOOL_JAR" \
  --hdc "$HDC_BIN" --device "$APPROVED_DEVICE" --bundle "$APPROVED_BUNDLE" \
  -- ./hvigorw assembleHap --mode module
```

`spec/verify/host-installation.json` 索引正式 Stage 1 可消费的 build/install 证据，绑定当前生产源码、范围、签名 HAP、设备和已确认的应用版本。原始日志与阶段正式输入均受摘要保护。设备测试执行者继续使用相应的原生到态、视觉、单测及行为契约。宿主回执本身不代表上述测试通过，生产 App 身份仍由 CHECK-2 校验。可在无设备权限的会话执行 `--project-root . --check-installation` 复算。
每次派发先读[统一执行策略](../../../references/execution-policy.md)（项目安装后读 `.migbot/runtime/references/execution-policy.md`）。阶段上限与任务剩余预算共同约束实际循环，同一根因沿用会话；连续两轮无新证据或无进展时换策略，不能用重派重置。

body 只留四句：派发 Agent `hmos-builder`（最多 20 轮）→ agent 返回结构化报告（PASS/FAIL）→ PASS 后主线程按 trigger 白名单回填 placeholder → FAIL 时调 arkts-knowledge-verifier 升级诊断。完整流程图与 trigger 6 类判定在此。

```
派发 Agent hmos-builder（CALLER=<上游>, STAGE_HINT=<阶段>, ROUND=<轮次>）
  │
  ├─ agent 内部：build-fix 循环（最多 20 轮，原始日志留在磁盘，context 只加载当前根因诊断切片）
  │
  ├─ agent 返回结构化报告（BUILD_STATUS / ITERATIONS / FILES_CHANGED / [PASS]HAP_OUTPUT / [FAIL]REMAINING_ERRORS+DIAGNOSIS）
  │
  ├─ [可选] 本轮 ERRORS_FIXED_TOTAL >= 5 时:
  │   ├─ 主线程调用 i2h-retrospect --incremental
  │   ├─ 分析本轮错误模式
  │   ├─ 新模式写入 skill references
  │   └─ 后续 task 立即受益
  │
  ├─ BUILD_STATUS=PASS → 主线程执行占位符回填:
  │   ├─ 读取 spec/placeholder-registry.md
  │   ├─ 对每个 status=pending 的条目:
  │   │   ├─ 解析 trigger_condition 自动判定（白名单 7 类）:
  │   │   │   ├─ `D-{N} chosen`           → grep "D-{N}.*chosen" spec/migration-decisions.md
  │   │   │   ├─ `<file-path> 实现 <symbol>` → grep -n "<symbol>" <file-path>
  │   │   │   ├─ `<业务类别> SDK 入仓`     → 按 trigger 实际指定的检测方式查（新 skill 入仓 / 私仓 har / 官方适配文档 / 团队决策记录等任一形式满足即可）
  │   │   │   ├─ `<api-endpoint> 上线`     → grep "<api-endpoint>" entry/src/main/ets/network/
  │   │   │   ├─ `<resource-id> 就绪`      → grep "<resource-id>" entry/src/main/resources/（同时覆盖 resource-pending-asset：fallback 资产被真实资产替换后命中）
  │   │   │   ├─ `Slice {N} Step {3c|3d}`  → `kind=forward-ref` 专用：检测 location 文件已无 `// FWD-REF:` marker（即接线已完成）
  │   │   │   └─ `Slice {N} Step 3a 确认`  → `kind=forward-ref-uncertain` 专用：Slice N Step 3a worker 报告 `uncertain_regions_resolved[]` 含本 P-ID（execute 主线程更新 status）
  │   │   ├─ trigger 命中 → status: pending → due，发出 hilog warning + 写迁移报告
  │   │   ├─ trigger 未命中 → status 维持 pending
  │   │   ├─ status=due 时尝试回填: 目标已实现 → 回填真实代码 + status → resolved
  │   │   └─ 回填失败（仍找不到实现） → status: due → fired，记入告警清单
  │   └─ 回填后如有代码变更 → 再次派发 hmos-builder（ROUND+=1）验证
  │
  ├─ BUILD_STATUS=PASS + 回填完成 → SUCCESS
  │
  └─ BUILD_STATUS=FAIL（阶段上限/累计预算内仍失败） → 升级处理:
      ├─ 主线程读 agent 返回的 REMAINING_ERRORS + DIAGNOSIS → 调 arkts-knowledge-verifier 诊断
      ├─ verifier 给出 patch 建议 → 主线程派 worker（按 fixer_layer 分轨）应用 patch
      ├─ 有剩余预算时沿用原根因会话与 TASK_ID 派发 hmos-builder（ROUND+=1） → 编译通过 → SUCCESS
      └─ 仍失败 → 标记 FAILED（按调用方阶段规则处理）
```


## 构建操作纪律（hmos_fix_build_errors / hmos-builder 的任何构建 subagent 必须遵守）

### Cache Cleanliness

- 首编后所有构建默认**增量**（热 daemon、不 clean）；仅命中腐坏征兆（<1s 空退 / 00303208×2）按 hmos_fix_build_errors 安全阀 `--stop-daemon` 处置。
- `hvigorw clean` 最多执行 **1 次**。禁止 `rm -rf entry/build`（会破坏 hvigor daemon 增量状态）。
- `ohpm install` 只在构建循环开始前执行一次，不在循环内部重复执行。

### Checkpoint 与提交

- 每次真实 `BUILD SUCCESSFUL` 后记录日志路径、退出码、源码/HAP 摘要和修复轮次。按当前任务已有授权，在相应验收完成后批量提交；不要求每次成功都单独提交。
- linter 回改时先检查当前 diff 和真实诊断，定位根因；保留用户已有修改，不用 `git checkout -- <file>` 覆盖文件。

### CLI 构建降级策略

出现以下情况时禁止继续 CLI 构建，必须**升级到 IDE 构建**：
- `hvigorw` 在 <1 秒内退出且无编译错误行 → Daemon 僵死，重试 1 次后仍失败则升级
- SDK 路径错误 `00303208`/`00303217` 连续出现 2 次 → 升级
- `module.json5` 语法损坏（`00305008`）连续出现 2 次 → 升级且禁止手动修改 module.json5
- 单个文件被 linter 回改超过 3 次 → 升级，由 IDE 环境验证最终状态

### 降级时输出

```
构建环境已不稳定，无法继续 CLI 构建验证。
请在 DevEco Studio IDE 中 Build → Build HAP(s) 验证项目完整性。
```
