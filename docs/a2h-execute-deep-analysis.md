# Android 原版 a2h-execute 深度分析与 iOS 版本对比

**日期**: 2024-11-03  
**分析目标**: 理解 a2h-execute 的完整执行流程、调用的所有资源  
**对比对象**: hmigbot-ios/i2h-execute v2.0

---

## 📊 总体架构对比

| 维度 | Android 原版 (a2h-execute) | iOS 版本 (i2h-execute v2.0) | 对齐度 |
|------|---------------------------|----------------------------|--------|
| **文件结构** | skill.md + references/ + scripts/ + templates/ | skill.md | ⚠️ 20% |
| **代码行数** | 605 行 (skill.md) | ~1,100 行 (SKILL.md) | ✅ 182% |
| **References** | 18 个文件 | 0 个 | ❌ 0% |
| **Scripts** | 28 个脚本 | 0 个 | ❌ 0% |
| **Templates** | 1 个模板 | 0 个 | ❌ 0% |
| **Agent Prompts** | 8 个 (拆分) | 0 个 | ❌ 0% |

---

## 🔍 Android 原版完整执行流程

### Stage 0: UI 前置产物与环境校验

#### 调用的 Skills

1. **后台环境预热（并行）**
   - `hmos_fix_build_errors` (环境段)
     - env-doctor (检查 local.properties)
     - ohpm install
     - hvigorw --sync
     - daemon 预热 (assembleHap，结果丢弃)

2. **资源转换和校验**
   - `arkts-app-identity` (scope=dev-identity)
     - 落地 app_name
     - 落地 versionName
     - 落地图标

#### 调用的 References

1. **`references/stage-0-resources.md`** ⭐⭐⭐⭐⭐ (MUST 加载)
   - 资源校验规则
   - static-v1 vs legacy 分流

2. **`references/resource-facts-handoff.md`** (仅 static-v1)
   - 资源事实交接契约

#### 调用的 Scripts

1. **资源转换相关**
   - 批量资源转换 (Android → HarmonyOS)
   - 资源保真检查

#### 门控

1. **HARD-GATE**: 资源闭包和保真检查
   - 全部 `$r(...)` 引用可解析或显式 MISSING_xxx
   - static-v1: 校验目标输入、资源事实、选定页面证据
   - 失败 → 阻断进入 Stage 1

---

### Stage 1: UI Pipeline

#### 调用的 Skills

1. **`a2h-activity-converter`** ⭐⭐⭐⭐⭐
   - 页面转换 (Android Activity/Fragment → HarmonyOS ArkTS)
   - 每个页面一个 converter

2. **`a2h-closer` (mode=batch)** ⭐⭐⭐⭐⭐
   - Batch 收尾 subagent
   - 资源 sweep
   - 布局尺寸复核
   - 产生 writeback manifest

3. **`a2h-migration-worker`**
   - S1-W 最小接线施工

4. **`arkts-structural-closure` (mode=stage target=1)** ⭐⭐⭐⭐⭐
   - Stage 1 骨架审计

5. **`arkts-visual-verify` (可选，用户选择)** ⭐⭐⭐⭐
   - S1-V 双端视觉检查
   - scope=stage1_wired

6. **`hmos-builder`** (可选，S1-V 需要时)
   - 生成 Stage 1 验证 HAP
   - 不替代 Base-7 编译门

#### 调用的 References

1. **`references/stage1-dispatch.md`** ⭐⭐⭐⭐⭐ (MUST 加载)
   - converter 上下文加载
   - 槽位控制
   - 空信封重派
   - 停滞回收规则

2. **`references/runtime-snapshot-handoff.md`** ⭐⭐⭐⭐⭐
   - 运行时快照交接契约
   - runtime_required / source_only / progressive 模式

3. **`references/entry-navigation-setup.md`** ⭐⭐⭐⭐⭐ (MUST 加载)
   - 入口装配流程
   - Navigation 外壳模板
   - main_pages.json 规则

4. **`references/agent-prompts/1-converter.md`** ⭐⭐⭐⭐⭐ (MUST 加载)
   - converter 派发模板

5. **`references/agent-prompts/2-batch-closer.md`** ⭐⭐⭐⭐⭐ (MUST 加载)
   - batch closer 派发模板

6. **`references/agent-prompts/_common.md`** ⭐⭐⭐⭐⭐ (MUST 加载)
   - 公共占位规则
   - 单写者纪律
   - 资源直写纪律

7. **`references/stage1-wiring.md`** ⭐⭐⭐⭐⭐ (MUST 加载)
   - S1-W 最小接线规则
   - strict_wiring 契约

8. **`references/brief-schemas.md` §1** ⭐⭐⭐⭐
   - batch brief schema

9. **`references/ui-integration-1030.md`** (full-ui-v2 模式)
   - 完整 UI 交付模式

10. **`references/ui-delivery-contract.md`** (full-ui-v2 模式)
    - UI 交付契约

11. **`references/layout-fidelity.md`** (full-ui-v2 模式)
    - 布局保真规则

12. **`references/stage1-gate-policy.md`** ⭐⭐⭐⭐
    - Stage 1 门禁失败处理策略

#### 调用的 Scripts

1. **`scripts/validate_runtime_snapshots.py`** ⭐⭐⭐⭐⭐
   - 验证运行时快照完整性
   - 参数: `--project-root <project> --pages-file <batch.json> --ui-facts-policy <mode>`

2. **`scripts/sweep_resources.py`** ⭐⭐⭐⭐⭐
   - 资源 sweep (残量兜底)
   - grep 所有 `$r('app.<type>.<name>')` 引用
   - 校验 SVG 可渲染性
   - 调用 `android2hmos_resources_convert` 补齐缺失资源

3. **`scripts/layout_dims_gate.py`** ⭐⭐⭐⭐
   - 源布局尺寸复核
   - 检查 dp/sp 值是否落进代码

4. **`scripts/apply_writeback.py`** ⭐⭐⭐⭐⭐
   - 应用 writeback manifest
   - 落盘 brief + 翻账本
   - 幂等可重放

5. **`scripts/stage1_reachability.py`** ⭐⭐⭐⭐
   - S1-W 接线可达性检查
   - 参数: `--project-root <project> --wiring-manifest <manifest> --output-json spec/execution/stage1_reachability.json`

6. **`scripts/stage1_preview.py`** ⭐⭐⭐
   - S1-P Preview 接线脚本

7. **`scripts/ui_stage1_gate.py`** ⭐⭐⭐⭐
   - S1-V 门禁检查
   - 参数: `--project-root <project> --wiring-dir spec/execution/wiring --output-json spec/execution/ui-stage1-gate.json`

8. **`scripts/stage1_visual_scope.py`** ⭐⭐⭐⭐
   - S1-V 视觉比较范围
   - 参数: `--project-root <project> --wiring-dir spec/execution/wiring --out spec/execution/stage1-visual-scope.json`

9. **`scripts/stage1_visual_report.py`** ⭐⭐⭐
   - 生成 S1-V 比较报告

#### 门控

1. **S1-R 资源校验 (HARD-GATE)**
   - 资源闭包未落地 → 按门禁分类处置
   - 保真检查失败 → 按门禁分类处置

2. **S1-G Batch writeback (HARD-GATE)**
   - writeback manifest 必产
   - apply 成功才进入下一 Batch

3. **S1-W 接线可达性 (HARD-GATE)**
   - 选定目标不可达 → 阻断

4. **骨架审计 (HARD-GATE)**
   - `arkts-structural-closure` (mode=stage target=1)
   - FAIL → 按分类处置 (精确类修过 / 推断类记账放行)

5. **S1-V 视觉检查 (可选，用户选择)**
   - choice=run: 构建、安装、比较
   - choice=skip: 记录 SKIP，不阻断
   - visual_blocked: 升级后才进 Stage 2

---

### Stage 2: Feature Base

#### 调用的 Skills

1. **`a2h-migration-worker`** ⭐⭐⭐⭐⭐ (Base 任务)
   - Base-1: Models
   - Base-2: Database
   - Base-3: Network
   - Base-4: Events
   - Base-5: Preferences
   - Base-6: 公共组件库

2. **`hmos-builder`** ⭐⭐⭐⭐⭐ (Base-7)
   - CALLER=a2h-execute
   - STAGE_HINT=stage-2-base-7
   - ROUND=1
   - 最多 20 轮自动修复
   - **这是 Stage 1 + Stage 2 的首道编译门**

3. **`arkts-structural-closure` (mode=stage target=2)** ⭐⭐⭐⭐⭐
   - Stage 2 骨架审计
   - 扫描范围: Stage 2 git diff 改动的 .ets + stage2_brief.md
   - 重点抓 Base signature 桩 `throw ...'Slice N'`

#### 调用的 References

1. **`references/agent-prompts/3-worker.md`** ⭐⭐⭐⭐⭐ (MUST 加载)
   - Base worker 派发模板

2. **`references/agent-prompts/_common.md`** ⭐⭐⭐⭐⭐ (MUST 加载)
   - 公共占位规则

3. **`references/build-loop.md`** ⭐⭐⭐⭐⭐ (MUST 加载)
   - 编译派发流程
   - placeholder 回填
   - 构建操作纪律 (cache / checkpoint / CLI→IDE 降级)

4. **`references/brief-schemas.md` §2** ⭐⭐⭐⭐
   - stage2_brief schema

#### 调用的 Scripts

无 (主线程直写 stage2_brief.md)

#### 门控

1. **Base-7 编译门 (HARD-GATE)** ⭐⭐⭐⭐⭐
   - `hmos-builder` BUILD_STATUS=PASS → 继续
   - BUILD_STATUS=FAIL (20 轮用完) → **阻断** (唯一停点)
   - 这是 Android 原版的**第 1 道编译门**

2. **骨架审计 (HARD-GATE)**
   - `arkts-structural-closure` (mode=stage target=2)
   - 精确类 FAIL → 必须修过才进 Stage 3
   - 推断类 FAIL → 记账放行

3. **任务完成检查 (HARD-GATE)**
   - 任务行未 PASS → 下一组不启动
   - Base-7 未 PASS → 阻断 Stage 3

---

### Stage 3: Feature Slices

#### 调用的 Skills

1. **`a2h-migration-worker`** ⭐⭐⭐⭐⭐ (Slice worker)
   - 每个 slice 1 个 worker
   - Step 3a: UI 补充 (如需要，调用 `a2h-activity-converter`)
   - Step 3b: ViewModel + 状态管理
   - Step 3c: 数据层接入
   - Step 3d: 页内接线

2. **`a2h-activity-converter`** (Step 3a 按需)
   - 补充缺失的 UI 页面

3. **`a2h-closer` (mode=group)** ⭐⭐⭐⭐⭐
   - group-closer 收尾 subagent
   - 跨文件接线
   - 资源 sweep
   - **结构 fix-forward** (自调 `arkts-structural-closure` mode=group，≤3 轮)
   - 产生 writeback manifest

4. **`arkts-structural-closure` (mode=group)** ⭐⭐⭐⭐⭐
   - group-closer 内部调用
   - 自修 ≤3 轮直到 CONVERGED
   - 非收敛才冒泡到主线程

5. **`hmos-builder`** ⭐⭐⭐⭐⭐ (Stage 3 集中门)
   - CALLER=a2h-execute
   - STAGE_HINT=stage-3-gate
   - ROUND=1
   - 最多 20 轮自动修复
   - **这是 Android 原版的第 2 道编译门**

6. **`arkts-structural-closure` (mode=stage target=3)** ⭐⭐⭐⭐⭐
   - Stage 3 骨架审计

#### 调用的 References

1. **`references/agent-prompts/4-slice-worker.md`** ⭐⭐⭐⭐⭐ (MUST 加载)
   - slice worker 派发模板
   - Step 3a/3b/3c/3d 一份 prompt

2. **`references/agent-prompts/8-group-closer.md`** ⭐⭐⭐⭐⭐ (MUST 加载)
   - group-closer 派发模板

3. **`references/agent-prompts/_common.md`** ⭐⭐⭐⭐⭐ (MUST 加载)
   - 公共占位规则

4. **`references/brief-schemas.md` §3/§4** ⭐⭐⭐⭐
   - group brief schema
   - writeback manifest schema

5. **`references/phase-a-ondemand.md`** ⭐⭐⭐
   - Phase A 按需触发机制

#### 调用的 Scripts

1. **`scripts/apply_writeback.py`** ⭐⭐⭐⭐⭐
   - 应用 group writeback manifest
   - 落盘 brief + 翻账本

2. **`scripts/verify_slice_wiring.py`** ⭐⭐⭐⭐⭐ (C2 机械判定)
   - 接线完成性机械判定
   - 调用方页面存在 + handler 已接 + target 被实例化

#### 门控

1. **组内 writeback (HARD-GATE)**
   - writeback manifest 必产
   - apply 成功才放行下一个 closer

2. **接线完成性 (HARD-GATE)**
   - `verify_slice_wiring.py` C2 机械判定
   - 未完成 → BLOCKED

3. **结构验证 (HARD-GATE)**
   - 普通组: structural CONVERGED
   - 末组: 可 defer 到 FV-1
   - STALLED/REGRESSED/EXHAUSTED → 主线程介入

4. **Stage 3 集中编译门 (HARD-GATE)** ⭐⭐⭐⭐⭐
   - `hmos-builder` (STAGE_HINT=stage-3-gate)
   - 组内无编译，错误累积至此一次结清
   - **这是 Android 原版的第 2 道编译门**

5. **骨架审计 (HARD-GATE)**
   - `arkts-structural-closure` (mode=stage target=3)
   - 通过后进入 FV-1

6. **ESCALATED 比例检查**
   - >10% → 按 gate-handling 记「未达标放行」
   - 不阻断继续

---

### Stage 4: Final Structural Closure (FV)

#### 调用的 Skills

1. **`a2h-closer` (mode=final)** ⭐⭐⭐⭐⭐
   - FV-1 收尾 subagent
   - 内部调用 `arkts-structural-closure` (mode=pipeline target=final)
   - 产生 writeback-final.json

2. **`arkts-structural-closure` (mode=pipeline target=final)** ⭐⭐⭐⭐⭐
   - FV-1 全工程兜底
   - 独立一次性 loop
   - CONVERGED → 产生 writeback-final.json

3. **`hmos-builder`** ⭐⭐⭐⭐⭐ (FV-2 终态全量编译)
   - CALLER=a2h-execute
   - STAGE_HINT=fv-final-build
   - ROUND=1
   - 最多 20 轮自动修复
   - **这是 Android 原版的第 3 道编译门**

4. **`arkts-ui-verifier`** (可选，用户明确要求)
   - 运行时交互冒烟
   - verify_only 模式

#### 调用的 References

1. **`references/brief-schemas.md` §3/§4** ⭐⭐⭐⭐
   - final brief schema

#### 调用的 Scripts

1. **`scripts/audit_interaction_candidates.py`** ⭐⭐⭐
   - 交互候选审查 (非门控)
   - 参数: `--project-root <project>`

2. **`scripts/apply_writeback.py`** ⭐⭐⭐⭐⭐
   - 应用 final writeback manifest
   - 落盘 brief + 补翻 defer 末组

3. **`scripts/build_writeback.py`** ⭐⭐⭐⭐
   - 读取 FV-1 剩余 FAIL
   - 剔除实现文件相交的末组 slice

#### 门控

1. **FV-1 收尾 evidence (HARD-GATE)** ⭐⭐⭐⭐⭐
   - 必产: `loops-final-structural-closure.json` (final_state == PASS)
   - 必产: `final_structural_closure_brief.md`
   - 缺失 → 重跑一次
   - 仍缺失 → 管线类工具缺口
   - final_state ≠ PASS → 按 gate-handling 记「未达标放行」

2. **FV-2 终态全量编译 (HARD-GATE)** ⭐⭐⭐⭐⭐
   - `hmos-builder` (STAGE_HINT=fv-final-build)
   - 必须为真实构建 (不能是 `all tasks up-to-date` 空转)
   - **这是 Android 原版的第 3 道编译门**
   - **进 a2h-verify 前的最后 gate**

---

### Stage 5: 迁移报告生成

#### 调用的 Scripts

1. **`scripts/lint_execute_coverage.py`** ⭐⭐⭐⭐⭐
   - 终态认领结算
   - 参数: `--project-root . --final`
   - 检出点: `EXECUTE.REQUIREMENT_UNCLAIMED`

2. **`scripts/gate_ledger.py check`** ⭐⭐⭐⭐⭐ (from a2h-spec)
   - 检查放行条目成立性
   - 参数: `--project-root . --android-root <安卓工程根>`
   - 退出 1 → 有放行条目不成立

#### 调用的 Templates

1. **`templates/migration-report-template.md`** ⭐⭐⭐⭐⭐
   - 迁移报告模板
   - 含: 总览 / Stage 详情 / Skill 使用统计 / 覆盖记录 / 产出文件清单 / FAILED 列表 / 页面状态汇总 / 最终编译 / Final Structural Closure

#### 门控

1. **认领结算 (HARD-GATE)**
   - `lint_execute_coverage.py --final`
   - REQUIREMENT_UNCLAIMED → 决策卡上报

2. **放行条目校验 (HARD-GATE)**
   - `gate_ledger.py check`
   - 有不成立的条目 → 先改正

---

## 🎯 核心 Skills 调用统计

| Skill | 调用次数 | 调用阶段 | 重要性 |
|-------|---------|---------|--------|
| **`hmos-builder`** | 3-4 次 | Base-7 / Stage 3 集中门 / FV-2 / S1-V(可选) | ⭐⭐⭐⭐⭐ |
| **`arkts-structural-closure`** | 5+ 次 | Stage 1/2/3 骨架审计 / group fix-forward / FV-1 | ⭐⭐⭐⭐⭐ |
| **`a2h-activity-converter`** | N 次 | Stage 1 页面转换 / Stage 3 UI 补充 | ⭐⭐⭐⭐⭐ |
| **`a2h-migration-worker`** | N 次 | Stage 2 Base 任务 / Stage 3 Slice worker | ⭐⭐⭐⭐⭐ |
| **`a2h-closer`** | N 次 | batch / group / final 收尾 | ⭐⭐⭐⭐⭐ |
| **`arkts-app-identity`** | 1 次 | Stage 0 资源落地 | ⭐⭐⭐⭐ |
| **`arkts-visual-verify`** | 0-1 次 | S1-V (用户选择) | ⭐⭐⭐⭐ |
| **`arkts-ui-verifier`** | 0-1 次 | FV 后交互冒烟 (用户要求) | ⭐⭐⭐ |

---

## 📂 核心 References 统计

| Reference | 被引用次数 | 重要性 | 用途 |
|-----------|-----------|--------|------|
| **`agent-prompts/_common.md`** | 每次派发 | ⭐⭐⭐⭐⭐ | 公共占位规则、单写者纪律 |
| **`build-loop.md`** | 每次编译 | ⭐⭐⭐⭐⭐ | 构建纪律 |
| **`brief-schemas.md`** | 每个 Stage | ⭐⭐⭐⭐⭐ | brief 和 writeback manifest schema |
| **`stage1-dispatch.md`** | Stage 1 | ⭐⭐⭐⭐⭐ | converter 派发规则 |
| **`entry-navigation-setup.md`** | Stage 1 | ⭐⭐⭐⭐⭐ | 入口装配 |
| **`stage1-wiring.md`** | S1-W | ⭐⭐⭐⭐⭐ | 接线规则 |
| **`stage-0-resources.md`** | Stage 0 | ⭐⭐⭐⭐⭐ | 资源校验 |
| **`agent-prompts/1-converter.md`** | N 次 | ⭐⭐⭐⭐⭐ | converter 派发模板 |
| **`agent-prompts/2-batch-closer.md`** | N 次 | ⭐⭐⭐⭐⭐ | batch closer 派发模板 |
| **`agent-prompts/3-worker.md`** | N 次 | ⭐⭐⭐⭐⭐ | Base worker 派发模板 |
| **`agent-prompts/4-slice-worker.md`** | N 次 | ⭐⭐⭐⭐⭐ | slice worker 派发模板 |
| **`agent-prompts/8-group-closer.md`** | N 次 | ⭐⭐⭐⭐⭐ | group-closer 派发模板 |
| **`runtime-snapshot-handoff.md`** | Stage 1 | ⭐⭐⭐⭐⭐ | 快照交接 |
| **`stage1-gate-policy.md`** | Stage 1 失败时 | ⭐⭐⭐⭐ | 根因处置 |
| **`execution-discipline.md`** | 启动时 | ⭐⭐⭐⭐ | 决策铁律 |
| **`ui-integration-1030.md`** | full-ui-v2 | ⭐⭐⭐ | 完整 UI 模式 |
| **`ui-delivery-contract.md`** | full-ui-v2 | ⭐⭐⭐ | UI 交付契约 |
| **`layout-fidelity.md`** | full-ui-v2 | ⭐⭐⭐ | 布局保真 |

---

## 🔧 核心 Scripts 统计

| Script | 调用次数 | 重要性 | 用途 |
|--------|---------|--------|------|
| **`apply_writeback.py`** | N 次 | ⭐⭐⭐⭐⭐ | 落盘 brief + 翻账本 |
| **`sweep_resources.py`** | N 次 | ⭐⭐⭐⭐⭐ | 资源 sweep |
| **`verify_slice_wiring.py`** | N 次 | ⭐⭐⭐⭐⭐ | 接线完成性判定 |
| **`lint_execute_coverage.py`** | 多次 + final | ⭐⭐⭐⭐⭐ | 认领结算 |
| **`validate_runtime_snapshots.py`** | Stage 1 前 | ⭐⭐⭐⭐⭐ | 快照验证 |
| **`stage1_reachability.py`** | S1-W 收口 | ⭐⭐⭐⭐ | 接线可达性 |
| **`layout_dims_gate.py`** | Batch 收尾 | ⭐⭐⭐⭐ | 布局尺寸复核 |
| **`ui_stage1_gate.py`** | S1-V 前 | ⭐⭐⭐⭐ | S1-V 门禁 |
| **`stage1_visual_scope.py`** | S1-V 前 | ⭐⭐⭐⭐ | S1-V 范围 |
| **`build_writeback.py`** | FV-1 后 | ⭐⭐⭐⭐ | 剔除未收敛 slice |
| **`stage1_visual_report.py`** | S1-V 后 | ⭐⭐⭐ | 视觉报告 |
| **`stage1_preview.py`** | S1-P | ⭐⭐⭐ | Preview 接线 |
| **`audit_interaction_candidates.py`** | FV-1 前 | ⭐⭐⭐ | 交互候选 |

---

## 🚪 关键门控总结

### 编译门 (3 道)

1. **Base-7 编译门** (Stage 1+2 完成后)
   - `hmos-builder` (STAGE_HINT=stage-2-base-7)
   - 最多 20 轮自动修复
   - 失败 → **阻断** (唯一停点)

2. **Stage 3 集中门** (Stage 3 所有 group 完成后)
   - `hmos-builder` (STAGE_HINT=stage-3-gate)
   - 最多 20 轮自动修复
   - 组内无编译，错误累积至此

3. **FV-2 终态全量编译** (FV-1 完成后)
   - `hmos-builder` (STAGE_HINT=fv-final-build)
   - 最多 20 轮自动修复
   - **进 a2h-verify 前的最后 gate**

### 结构审计门 (4+ 道)

1. **Stage 1 骨架审计**
   - `arkts-structural-closure` (mode=stage target=1)

2. **Stage 2 骨架审计**
   - `arkts-structural-closure` (mode=stage target=2)

3. **Stage 3 骨架审计**
   - `arkts-structural-closure` (mode=stage target=3)

4. **group 结构验证** (每个 group)
   - `arkts-structural-closure` (mode=group)
   - group-closer 内部调用，≤3 轮 fix-forward

5. **FV-1 全工程兜底**
   - `arkts-structural-closure` (mode=pipeline target=final)
   - 独立一次性 loop

### 其他关键门控

1. **Stage 0 资源校验** (HARD-GATE)
2. **S1-R 资源校验** (HARD-GATE)
3. **Batch writeback** (HARD-GATE, 每个 batch)
4. **接线完成性** (HARD-GATE, 每个 group)
5. **认领结算** (HARD-GATE, final)
6. **放行条目校验** (HARD-GATE, final)

---

## 🆚 iOS 版本 (i2h-execute v2.0) 对比

### ✅ 已实现

| 功能 | Android 原版 | iOS v2.0 | 对齐度 |
|------|-------------|----------|--------|
| **文档结构** | 605 行 | ~1,100 行 | ✅ 182% |
| **Stage 划分** | 0/1/2/3/FV | 0/1/2/3/4/5 | ✅ 类似 |
| **编译验证** | 3 道编译门 | 1 道 (Stage 4) | ⚠️ 33% |
| **知识加载** | 无 | ✅ Stage 2 | ✅ 优于原版 |

### ❌ 缺失（关键）

#### 1. References (0/18) ❌❌❌

**缺失的关键 References**:

1. **agent-prompts/** (0/8) — ⭐⭐⭐⭐⭐
   - `_common.md` — 公共占位规则、单写者纪律
   - `1-converter.md` — converter 派发模板
   - `2-batch-closer.md` — batch closer 派发模板
   - `3-worker.md` — Base worker 派发模板
   - `4-slice-worker.md` — slice worker 派发模板
   - `8-group-closer.md` — group-closer 派发模板

2. **核心规范文档** (0/10)
   - `build-loop.md` — ⭐⭐⭐⭐⭐ 构建纪律
   - `brief-schemas.md` — ⭐⭐⭐⭐⭐ brief schema
   - `stage1-dispatch.md` — ⭐⭐⭐⭐⭐ 派发规则
   - `entry-navigation-setup.md` — ⭐⭐⭐⭐⭐ 入口装配
   - `stage1-wiring.md` — ⭐⭐⭐⭐⭐ 接线规则
   - `stage-0-resources.md` — ⭐⭐⭐⭐⭐ 资源校验
   - `runtime-snapshot-handoff.md` — ⭐⭐⭐⭐⭐ 快照交接
   - `stage1-gate-policy.md` — ⭐⭐⭐⭐ 根因处置
   - `execution-discipline.md` — ⭐⭐⭐⭐ 决策铁律
   - `resource-facts-handoff.md` — ⭐⭐⭐⭐ 资源交接

**影响**: 
- 没有标准化的派发模板
- 没有占位规则和单写者纪律
- 没有构建纪律
- 没有接线规则

#### 2. Scripts (0/28) ❌❌❌

**缺失的关键 Scripts**:

1. **账本管理** (0/3) — ⭐⭐⭐⭐⭐
   - `apply_writeback.py` — 落盘 brief + 翻账本
   - `build_writeback.py` — 剔除未收敛 slice
   - `lint_execute_coverage.py` — 认领结算

2. **资源处理** (0/1) — ⭐⭐⭐⭐⭐
   - `sweep_resources.py` — 资源 sweep

3. **接线验证** (0/2) — ⭐⭐⭐⭐⭐
   - `verify_slice_wiring.py` — 接线完成性判定
   - `stage1_reachability.py` — 接线可达性

4. **快照和门禁** (0/4) — ⭐⭐⭐⭐
   - `validate_runtime_snapshots.py` — 快照验证
   - `layout_dims_gate.py` — 布局尺寸复核
   - `ui_stage1_gate.py` — S1-V 门禁
   - `stage1_visual_scope.py` — S1-V 范围

**影响**:
- 无法自动管理账本
- 无法验证接线完成性
- 无法进行资源 sweep
- 无法验证快照完整性

#### 3. Agent 派发机制 ❌❌❌

**Android 原版**:
```python
# 派发 converter (MUST 加载 references)
Read('references/agent-prompts/1-converter.md')
Read('references/agent-prompts/_common.md')
Agent({
  description: "页面转换",
  prompt: f"{converter_template}\n{page_context}"
})

# 派发 batch closer (MUST 加载 references)
Read('references/agent-prompts/2-batch-closer.md')
Read('references/agent-prompts/_common.md')
Agent({
  description: "Batch 收尾",
  prompt: f"{closer_template}\n{batch_context}"
})
```

**iOS v2.0**:
```typescript
// ❌ 没有标准化的派发模板
// ❌ 没有强制加载 references
// ❌ 直接内联 prompt（不稳定、不一致）
```

#### 4. 编译门数量 ⚠️

**Android 原版**: 3 道编译门
1. Base-7 (Stage 1+2 完成后)
2. Stage 3 集中门
3. FV-2 终态全量编译

**iOS v2.0**: 1 道编译门
- Stage 4 编译验证

**问题**: 缺少 Base-7 和 Stage 3 集中门

#### 5. 结构审计机制 ❌

**Android 原版**: 5+ 道结构审计
1. Stage 1 骨架审计
2. Stage 2 骨架审计
3. Stage 3 骨架审计
4. group 结构验证 (每个 group，≤3 轮 fix-forward)
5. FV-1 全工程兜底

**iOS v2.0**: 0 道
- 完全缺失

#### 6. Closer 机制 ❌❌❌

**Android 原版**: 3 种 closer
1. `a2h-closer` (mode=batch) — Batch 收尾
2. `a2h-closer` (mode=group) — group 收尾
3. `a2h-closer` (mode=final) — FV 收尾

**iOS v2.0**: 0 个
- 完全缺失

#### 7. Writeback 协议 ❌❌❌

**Android 原版**:
```python
# closer 产生 writeback manifest
closer 返回 writeback manifest

# 主线程 apply
python3 scripts/apply_writeback.py <manifest> --project-root .

# 幂等可重放
崩溃恢复 = 重跑 apply
```

**iOS v2.0**: 无
- 完全缺失

---

## 🎯 iOS 版本急需补充的内容

### P0 (必须补充)

1. **References: agent-prompts/** ⭐⭐⭐⭐⭐
   - `_common.md` — 公共规则
   - converter / worker / closer 派发模板
   
2. **References: build-loop.md** ⭐⭐⭐⭐⭐
   - 构建纪律

3. **Scripts: apply_writeback.py** ⭐⭐⭐⭐⭐
   - 账本管理

4. **Scripts: sweep_resources.py** ⭐⭐⭐⭐⭐
   - 资源 sweep

5. **3 道编译门** ⭐⭐⭐⭐⭐
   - Base-7
   - Stage 3 集中门
   - FV-2

### P1 (强烈建议)

6. **References: brief-schemas.md** ⭐⭐⭐⭐
   - brief schema

7. **Scripts: verify_slice_wiring.py** ⭐⭐⭐⭐
   - 接线验证

8. **Closer 机制** ⭐⭐⭐⭐
   - batch / group / final

9. **结构审计** ⭐⭐⭐⭐
   - 调用 `arkts-structural-closure`

10. **References: stage1-wiring.md** ⭐⭐⭐⭐
    - 接线规则

### P2 (建议)

11. **References: 其他规范文档**
    - stage1-dispatch.md
    - entry-navigation-setup.md
    - stage-0-resources.md
    - 等

12. **Scripts: 其他工具脚本**
    - validate_runtime_snapshots.py
    - layout_dims_gate.py
    - 等

---

## 📝 总结

### Android 原版的核心优势

1. **完整的 references 体系** — 18 个规范文档
2. **丰富的 scripts 工具** — 28 个自动化脚本
3. **3 道编译门** — 多重质量保障
4. **5+ 道结构审计** — 全面的代码审查
5. **标准化的 agent 派发** — 8 个派发模板
6. **完善的 closer 机制** — 单写者纪律
7. **writeback 协议** — 幂等可重放
8. **接线完成性判定** — 机械判定，零回填

### iOS v2.0 的差距

1. **references: 0/18** ❌❌❌
2. **scripts: 0/28** ❌❌❌
3. **编译门: 1/3** ⚠️
4. **结构审计: 0/5+** ❌❌❌
5. **agent 派发: 无标准化** ❌❌❌
6. **closer 机制: 0/3** ❌❌❌
7. **writeback 协议: 无** ❌❌❌

### 建议

**立即行动**:
1. 补充 P0 内容（agent-prompts / build-loop / apply_writeback / sweep_resources / 3 道编译门）
2. 参考 Android 原版创建 references/
3. 参考 Android 原版创建 scripts/
4. 实现 closer 机制
5. 实现 writeback 协议

**评估重写**:
- 当前 v2.0 的文档虽然详细（1,100 行），但缺少关键的支撑体系
- 建议参考 Android 原版的架构，而不仅仅是 SKILL.md
- references/ 和 scripts/ 是执行的关键支撑，不可或缺

---

**生成时间**: 2024-11-03  
**分析人**: Claude Opus 5.5  
**状态**: ✅ 深度分析完成
