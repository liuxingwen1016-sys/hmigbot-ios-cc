<!-- when: 需要确认 a2h-spec 产出落点 / 目录布局 / 增量演进产出路径时加载（Gate B / Gate C 摘要核对、下游 skill 排障、产出完整性自查）-->
<!-- topics: 初始迁移产出表, 完整目录结构, 增量演进产出, spec/baseline 布局, spec/.a2h 布局 -->

# a2h-spec 产出清单与目录布局

本文是 a2h-spec 全部产出的**落点权威**：初始迁移逐 Phase 产出表、`spec/` 完整目录树、增量演进产出路径。
SKILL.md 各 Step 只写「产出什么」，「落在哪、目录长什么样」一律以本文为准。

### 初始迁移产出

| 阶段 | 产出 | 路径 | 说明 |
|------|------|------|------|
| Phase 0（仅 `$MULTI_MODULE`） | 模块依赖骨架 | `spec/baseline/module-dep-graph.json` | P0.1 脚本提取的跨模块 DAG + seam 签名 |
| Phase 0（仅 `$MULTI_MODULE`） | 跨模块契约 | `spec/baseline/cross-module-contracts.md` | P0.2 LLM 补充的 seam 语义契约 |
| Phase A | UI 快照数据 | `spec/baseline/ui-snapshots/page_NNNN_XxxActivity/` | 三源数据（view.xml + meta.json + screenshot.png） |
| Phase A | Dialog 结构快照 | `spec/baseline/dialog-snapshots/dlgsnap_<hash>_<LayoutOwner>/` | 非页面 Dialog 的 meta/view 结构证据；Variant 复用 owner snapshot |
| Phase A | Dialog 确定性清单 | `spec/.a2h/spec-run/dialog-inventory.json` | source-only 分母、继承/host/layout owner/匿名实例事实 |
| Phase B | UI 总览 | `spec/baseline/ui-manifest.md` | 页面清单 + 全局约定 + 状态生命周期 |
| Phase B | Dialog 索引 sidecar | `spec/.a2h/spec-run/dialog-index.json` | 固定十列表的机器解析结果；execute 共用 |
| Phase C | Dialog 闭合报告 | `spec/.a2h/spec-run/dialog-closure-report.json` | `lint_coverage.py`（含 `--report-only`）经 `dialog_closure.py` 原子写出：逐行 status、summary、inventory/index digest；auditor 唯一输入 |
| Phase B | UI 分页 Spec | `spec/baseline/ui/page_NNNN_XxxActivity.md` | 每页溯源 + 结构 + 状态接口 + 导航 |
| Phase B（B-API 轨） | API 清单 | `spec/baseline/api-inventory/{raw_apis.json, api-inventory.json, api-inventory.md}` | android-api-inventory 子 agent 产出（分支 C 输入源模式），供 Phase C 消费 |
| Phase C | 功能总览 | `spec/baseline/feature-index.md` | 功能清单 + 依赖图 |
| Phase C | 基础设施 Spec | `spec/baseline/feature-base.md` | 数据模型 + DB + 网络 + 事件 + 偏好 + 公共组件库 |
| Phase C | 功能分 Spec | `spec/baseline/features/F00x-xxx.md` | 每功能自包含 Spec（顶部 complexity/tier/depth + AC 带 `源→标` + `判:`/`真:` 追踪）|
| Phase C | 功能 addenda（可选形态） | `spec/baseline/features/F00x-xxx.<slug>.md` | 证据义务（required_addenda）的**两种等价兑现之一**；另一种是主文件同名章节（不产文件、不登记）。section 溢出时才必须拆 sibling（C4.6e 收口）|
| Phase C（C4.6b） | 源码覆盖报告 | `spec/baseline/source-coverage-report.md` | 源码侧 ownership 审计 + 多子仓 seam 审计段 |
| Phase C（C4.6b，可选） | 四层覆盖报告 | `spec/feature-coverage-report.md` | 外部 arkts-feature-coverage-auditor 产出 |
| Phase C（C4-pre） | 证据画像 | `spec/baseline/feature-profiles.json` | 每功能的行为信号 + `file:line` 证据 + 必备义务种类 |
| Phase C（C4-pre） | 复杂度诊断 | `spec/baseline/complexity-metrics.json` | decision_count / 密度 / split 建议——**不参与门禁** |
| Phase C（C4.6f） | 待办 findings | `spec/.a2h/open-findings.json` | 四阶段共用的问题队列，带 owner_stage 路由 |
| Phase C（C4.6f） | 可追溯索引 | `spec/.a2h/requirements-index.json` | 稳定 ID + spec_uri + assertion_digest，供下游对账 |

### 完整目录结构

```
spec/
├── baseline/                               ← 初始迁移基线（V1 后只读）
│   ├── ui-manifest.md                      ← 【UI 总】页面清单 + 全局约定
│   ├── ui/                                 ← 【UI 分】每页一个 spec
│   │   ├── page_0001_MainActivity.md
│   │   ├── page_0002_HomeFragment.md
│   │   └── ...
│   ├── ui-snapshots/                       ← 三源原始数据
│   │   ├── page_0001_MainActivity/
│   │   │   ├── view.xml
│   │   │   ├── meta.json
│   │   │   └── screenshot.png
│   │   └── ...
│   ├── dialog-snapshots/                   ← 非页面 Dialog 结构证据（不进 page batch）
│   │   ├── dlgsnap_<hash>_<LayoutOwner>/
│   │   │   ├── view.xml
│   │   │   └── meta.json
│   │   └── ...
│   ├── api-inventory/                      ← 【API】B-API 轨产出
│   │   ├── raw_apis.json
│   │   ├── api-inventory.json
│   │   └── api-inventory.md
│   ├── module-dep-graph.json               ← 【Phase 0 仅多子仓】跨模块依赖骨架
│   ├── cross-module-contracts.md           ← 【Phase 0 仅多子仓】seam 语义契约
│   ├── feature-index.md                    ← 【功能 总】功能清单 + 依赖图
│   ├── feature-base.md                     ← 【功能 基础】共享基础设施
│   ├── source-coverage-report.md           ← 【C4.6b】源码侧覆盖审计 + seam 审计
│   └── features/                           ← 【功能 分】每功能一个 spec
│       ├── F001-playback.md
│       ├── F001-playback.state-machine.md  ← 证据触发或溢出的 addendum（C4.6e）
│       ├── F002-subscription.md
│       └── ...
├── features/                               ← V1 后增量功能
├── bugfixes/                               ← V1 后 bug 修复
└── optimizations/                          ← V1 后优化
spec/.a2h/spec-run/
├── dialog-inventory.json                   ← source-only 权威提取结果
├── dialog-index.json                       ← ui-manifest 固定表机器 sidecar
└── dialog-closure-report.json              ← 权威 Dialog 闭合结果（lint 写、auditor 读）
```

### 增量演进产出

| 阶段 | 产出 | 路径 |
|------|------|------|
| 增量功能 | 增量 spec | `spec/features/F0xx-xxx.md` |
| Bug 修复 | bugfix spec | `spec/bugfixes/B0xx-xxx.md` |
| 优化 | 优化 spec | `spec/optimizations/O0xx-xxx.md` |
