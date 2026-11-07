# Quick Reference

## 先看什么

| 目的 | 文档 |
|---|---|
| 了解工具定位和当前限制 | [`README.md`](README.md) / [`README_CN.md`](README_CN.md) |
| 接手当前工作 | [`HANDOVER.md`](HANDOVER.md) |
| 查看阶段状态 | [`PROJECT_STATUS.md`](PROJECT_STATUS.md) |
| 理解改造方法 | [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md) |
| 对比原版与 iOS 方案 | [`docs/ORIGINAL_VS_IOS_ANALYSIS.md`](docs/ORIGINAL_VS_IOS_ANALYSIS.md) |
| 查看问题和修复顺序 | [`docs/IMPLEMENTATION_AUDIT.md`](docs/IMPLEMENTATION_AUDIT.md) |
| 查找历史过程 | [`docs/ARCHIVE_INDEX.md`](docs/ARCHIVE_INDEX.md) |

## 流水线与主要产物

```text
i2h-spec
  spec/baseline/ui-manifest.md
  spec/baseline/feature-index.md
  spec/baseline/features/*.md
  spec/placeholder-registry.md

      ↓

i2h-plan
  spec/baseline/plans/ui-plan.md
  spec/baseline/plans/feature-plan.md
  spec/baseline/plans/base-plan.md
  spec/baseline/plans/slices/*.md

      ↓

i2h-execute
  spec/execution/briefs/
  spec/execution/writeback/
  HarmonyOS source and resources

      ↓

i2h-verify
  spec/verify-report.md
  spec/verify/

      ↓

i2h-retrospect
  measured delivery report
```

## 参考关系

- Android baseline: `../hmigbot-1.8.0/migbot/skills/a2h-*`
- iOS adaptation: `migbot/skills/i2h-*` and `migbot/skills/ios-*`
- imported iOS expertise: `references/ios-0.14.1-iOS技能与说明/`
- historical reports: `docs/archive/`

## 当前证据口径

- “设计完成”只表示文档、模板或 Skill 已写入仓库。
- “脚本可运行”必须有命令输出和退出码证据。
- “阶段通过”必须有该阶段的产物、门禁输出和必要的复检记录。
- “生产就绪”必须有真实项目的安装、编译、设备和回归证据。
- Cuike 报告中的 90.8% 只保留为历史原型统计，不作为当前质量指标。
