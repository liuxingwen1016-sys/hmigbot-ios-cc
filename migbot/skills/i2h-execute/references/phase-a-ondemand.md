<!-- when: Stage 3 Step 3a 发现目标页面 ui-snapshots 数据缺失、需触发 i2h-spec Phase A 按需模式时加载 -->
<!-- topics: Phase A 按需触发, 数据缺失, 最小数据集, 降级处理 -->

# Phase A 按需触发机制

Stage 3 Step 3a（UI 补充）发现目标页面的 ui-snapshots 数据缺失时，自动触发 i2h-spec 的 Phase A 按需模式。

宿主页拥有的 Dialog snapshot 缺失也触发同一机制，但只重建
`spec/baseline/dialog-snapshots/<snapshot-id>/`，不得新增 page/ui-manifest 页面行。

## 1. 触发条件（同时满足）

1. `ui-manifest.md` 中目标页面的 status 不是 `converted` 或 `verified`
2. `ui-snapshots/page_NNNN/` 目录不存在或数据不完整（缺少 view.xml 或 meta.json）

Dialog 分支触发条件：先调用 `i2h-spec/scripts/dialog_index.py --owned-by <当前 page spec>`，其
`owned_dialog_snapshots` 中任一非 `none` snapshot_ref 缺 meta.json，
或有 layout_sources 但缺 view.xml。

## 2. 执行流程

```
Step 3a 检查到数据缺失
  ▼
调用 i2h-spec Phase A 按需模式:
  ├─ 对该单个页面执行源码分析（从 Activity 源码定位 layout XML）
  ├─ 生成最小数据集（至少包含源码 layout XML 解析结果）
  ├─ 增量更新 ui-manifest.md（新增页面条目 + confidence 标记）
  └─ 增量生成 spec/baseline/ui/page_NNNN.md
  ▼
数据准备完成 → 继续调用 a2h-activity-converter 转换该页面 → 继续 Slice 执行，无需中断整个 Pipeline
```

Dialog 分支逐项调用 `prepare_dialog_artifacts.py --only <snapshot-id>`；完成后只向迁移报告记录
`snapshot_synthesized`，不创建独立 Dialog page spec。

## 3. 降级处理

按需模式无法为该页面生成足够数据（如页面动态生成、无静态 layout XML）时：
- 标记该页面 confidence: low
- 生成最小 UI 骨架（基于 Activity/Fragment 类名推断）
- 在 placeholder-registry.md 注册需要人工补充的占位项
- 不阻断 Slice 执行（后续步骤可以先用骨架 UI）
