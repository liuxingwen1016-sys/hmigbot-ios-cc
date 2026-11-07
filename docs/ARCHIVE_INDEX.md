# 文档归档索引

根目录只保留当前入口文档；过程文档按阶段归档在本目录。归档内容用于追溯改造过程，不自动代表当前实现状态。

## 当前文档

- [`../README.md`](../README.md)：英文入口和当前限制。
- [`../README_CN.md`](../README_CN.md)：中文入口和当前限制。
- [`../HANDOVER.md`](../HANDOVER.md)：当前交接。
- [`../PROJECT_STATUS.md`](../PROJECT_STATUS.md)：当前状态快照。
- [`../QUICK_REFERENCE.md`](../QUICK_REFERENCE.md)：产物、入口和证据规则。
- [`../CHANGELOG.md`](../CHANGELOG.md)：iOS 版本变更记录。
- [`METHODOLOGY.md`](METHODOLOGY.md)：从过程文档提取的方法论。
- [`ORIGINAL_VS_IOS_ANALYSIS.md`](ORIGINAL_VS_IOS_ANALYSIS.md)：原版 UI/资源/性能机制与 iOS 实际方案对比。
- [`IMPLEMENTATION_AUDIT.md`](IMPLEMENTATION_AUDIT.md)：问题、证据和修复方案。
- [`current/`](current/)：仍有长期参考价值的设计笔记。

## 归档分类

### `cuike-pilot/`

Cuike iOS 试点的分析、计划、转换结果和已知问题。
- [`cuike-pilot/CUIKE_CONVERSION_PLAN.md`](archive/cuike-pilot/CUIKE_CONVERSION_PLAN.md) — Cuike iOS → HarmonyOS 试点转换计划
- [`cuike-pilot/CUIKE_FINAL_REPORT.md`](archive/cuike-pilot/CUIKE_FINAL_REPORT.md) — 🎉 Cuike iOS → HarmonyOS 转换完成报告
- [`cuike-pilot/cuike_analysis_report.md`](archive/cuike-pilot/cuike_analysis_report.md) — Cuike iOS 项目分析报告
- [`cuike-pilot/cuike_conversion_success.md`](archive/cuike-pilot/cuike_conversion_success.md) — 🎉 Cuike 转换成功报告

### `i2h-execute/`

i2h-execute 的深度分析、优化方案、补齐记录、错误经验和完成报告。
- [`i2h-execute/I2H-EXECUTE-V2-SUMMARY.md`](archive/i2h-execute/I2H-EXECUTE-V2-SUMMARY.md) — i2h-execute v2.0 优化完成 ✅
- `archive/i2h-execute/tooling/generate_i2h_execute_files.py` — 一次性生成 references/scripts 框架的历史脚本，不参与运行时。
- `archive/i2h-execute/tooling/supplement_remaining.py` — 一次性批量补齐文件的历史脚本，包含 Android→iOS 字符串替换逻辑，不参与运行时。
- [`i2h-execute/a2h-execute-deep-analysis.md`](archive/i2h-execute/a2h-execute-deep-analysis.md) — Android 原版 a2h-execute 深度分析与 iOS 版本对比
- [`i2h-execute/i2h-execute-before-after-comparison.md`](archive/i2h-execute/i2h-execute-before-after-comparison.md) — i2h-execute 优化前后对比报告
- [`i2h-execute/i2h-execute-complete-report.md`](archive/i2h-execute/i2h-execute-complete-report.md) — i2h-execute 完整补齐完成报告
- [`i2h-execute/i2h-execute-final-completion.md`](archive/i2h-execute/i2h-execute-final-completion.md) — i2h-execute 完整补齐 - 最终完成报告
- [`i2h-execute/i2h-execute-final-summary.md`](archive/i2h-execute/i2h-execute-final-summary.md) — i2h-execute 优化完成总结
- [`i2h-execute/i2h-execute-implementation-plan.md`](archive/i2h-execute/i2h-execute-implementation-plan.md) — i2h-execute 完整补齐实施计划
- [`i2h-execute/i2h-execute-optimization-plan.md`](archive/i2h-execute/i2h-execute-optimization-plan.md) — i2h-execute 优化方案
- [`i2h-execute/i2h-execute-补充计划.md`](archive/i2h-execute/i2h-execute-补充计划.md) — i2h-execute 文档和脚本补充计划
- [`i2h-execute/i2h-execute-错误记录与经验总结.md`](archive/i2h-execute/i2h-execute-错误记录与经验总结.md) — i2h-execute 补齐工作 - 错误记录与经验总结

### `i2h-plan/`

i2h-plan 的差距分析、迁移指南、Phase 报告和最终总结。
- [`i2h-plan/i2h-plan-final-summary.md`](archive/i2h-plan/i2h-plan-final-summary.md) — i2h-plan 优化项目最终总结报告
- [`i2h-plan/i2h-plan-gap-analysis.md`](archive/i2h-plan/i2h-plan-gap-analysis.md) — i2h-plan vs a2h-plan 对比报告
- [`i2h-plan/i2h-plan-improvement-summary.md`](archive/i2h-plan/i2h-plan-improvement-summary.md) — i2h-plan 改进总结
- [`i2h-plan/i2h-plan-migration-guide.md`](archive/i2h-plan/i2h-plan-migration-guide.md) — i2h-plan 使用指南
- [`i2h-plan/reports/i2h-plan-gap-analysis.md`](archive/i2h-plan/reports/i2h-plan-gap-analysis.md) — i2h-plan 差距分析报告
- [`i2h-plan/reports/i2h-plan-improvement-plan.md`](archive/i2h-plan/reports/i2h-plan-improvement-plan.md) — i2h-plan 改进执行计划
- [`i2h-plan/reports/i2h-plan-phase1-complete.md`](archive/i2h-plan/reports/i2h-plan-phase1-complete.md) — i2h-plan Phase 1 完成报告
- [`i2h-plan/reports/i2h-plan-phase2-complete.md`](archive/i2h-plan/reports/i2h-plan-phase2-complete.md) — i2h-plan Phase 2 完成报告
- [`i2h-plan/reports/i2h-plan-phase3-complete.md`](archive/i2h-plan/reports/i2h-plan-phase3-complete.md) — i2h-plan Phase 3 完成报告
- [`i2h-plan/reports/i2h-plan-phase4-complete.md`](archive/i2h-plan/reports/i2h-plan-phase4-complete.md) — i2h-plan Phase 4 完成报告
- [`i2h-plan/reports/i2h-plan-skillmd-fix.md`](archive/i2h-plan/reports/i2h-plan-skillmd-fix.md) — i2h-plan SKILL.md 格式修复报告

### `i2h-spec/`

i2h-spec 的差异分析、Phase 1/2 计划、验收和修复记录。
- [`i2h-spec/i2h-spec-fix-summary.md`](archive/i2h-spec/i2h-spec-fix-summary.md) — i2h-spec 修复工作摘要
- [`i2h-spec/i2h-spec-gap-analysis.md`](archive/i2h-spec/i2h-spec-gap-analysis.md) — i2h-spec 产物差异分析报告
- [`i2h-spec/i2h-spec-improvement-summary.md`](archive/i2h-spec/i2h-spec-improvement-summary.md) — i2h-spec 改进完成总结
- [`i2h-spec/i2h-spec-optimization-complete.md`](archive/i2h-spec/i2h-spec-optimization-complete.md) — i2h-spec 优化完成总结
- [`i2h-spec/i2h-spec-v2.2-fix-complete.md`](archive/i2h-spec/i2h-spec-v2.2-fix-complete.md) — i2h-spec v2.2 修复完成总结
- [`i2h-spec/i2h-spec-v2.2-improvements.md`](archive/i2h-spec/i2h-spec-v2.2-improvements.md) — i2h-spec v2.2 改进说明
- [`i2h-spec/phase1-day1-acceptance.md`](archive/i2h-spec/phase1-day1-acceptance.md) — Phase 1 Day 1 验收报告
- [`i2h-spec/phase1-day1-plan.md`](archive/i2h-spec/phase1-day1-plan.md) — Phase 1 Day 1 执行计划: toolkit-fact-tree.json 生成
- [`i2h-spec/phase1-day1-summary.md`](archive/i2h-spec/phase1-day1-summary.md) — Phase 1 Day 1 完成总结
- [`i2h-spec/phase1-day2-acceptance.md`](archive/i2h-spec/phase1-day2-acceptance.md) — Phase 1 Day 2 验收报告
- [`i2h-spec/phase1-day2-plan.md`](archive/i2h-spec/phase1-day2-plan.md) — Phase 1 Day 2 执行计划: api-inventory/ 生成
- [`i2h-spec/phase1-day3-acceptance.md`](archive/i2h-spec/phase1-day3-acceptance.md) — Phase 1 Day 3 验收报告
- [`i2h-spec/phase1-day3-plan.md`](archive/i2h-spec/phase1-day3-plan.md) — Phase 1 Day 3 执行计划: feature-base.md 生成
- [`i2h-spec/phase1-summary.md`](archive/i2h-spec/phase1-summary.md) — Phase 1 完成总结报告
- [`i2h-spec/phase2-day4-acceptance.md`](archive/i2h-spec/phase2-day4-acceptance.md) — Phase 2 Day 4 验收报告 (Batch 1)
- [`i2h-spec/phase2-day5-acceptance.md`](archive/i2h-spec/phase2-day5-acceptance.md) — Phase 2 Day 5 验收报告 (Batch 2)
- [`i2h-spec/phase2-plan.md`](archive/i2h-spec/phase2-plan.md) — Phase 2 执行计划: P1 格式规范修复
- [`i2h-spec/product-comparison-report.md`](archive/i2h-spec/product-comparison-report.md) — iOS vs Android 版本产物对比分析报告
- [`i2h-spec/references-borrowing-report.md`](archive/i2h-spec/references-borrowing-report.md) — i2h-spec 借鉴工作完成报告
- [`i2h-spec/references-integration-analysis.md`](archive/i2h-spec/references-integration-analysis.md) — references/ 目录 iOS Skills 集成可行性分析报告

### `i2h-verify/`

i2h-verify 的调研、Phase 1-4 实施、gate-release 和工具可用性记录。
- [`i2h-verify/i2h-verify-analysis.md`](archive/i2h-verify/i2h-verify-analysis.md) — i2h-verify 深度分析与改造方案
- [`i2h-verify/i2h-verify-daily-summary-2024-11-03.md`](archive/i2h-verify/i2h-verify-daily-summary-2024-11-03.md) — 今日工作总结 - 2024-11-03
- [`i2h-verify/i2h-verify-executive-summary.md`](archive/i2h-verify/i2h-verify-executive-summary.md) — i2h-verify 改造执行摘要
- [`i2h-verify/i2h-verify-gate-release-summary.md`](archive/i2h-verify/i2h-verify-gate-release-summary.md) — i2h-verify gate-release 功能总结
- [`i2h-verify/i2h-verify-investigation-report.md`](archive/i2h-verify/i2h-verify-investigation-report.md) — i2h-verify 外部依赖调研报告
- [`i2h-verify/i2h-verify-phase1-2-complete.md`](archive/i2h-verify/i2h-verify-phase1-2-complete.md) — Phase 1 & Phase 2 完成报告
- [`i2h-verify/i2h-verify-phase1-progress.md`](archive/i2h-verify/i2h-verify-phase1-progress.md) — Phase 1 进度报告
- [`i2h-verify/i2h-verify-phase3-complete.md`](archive/i2h-verify/i2h-verify-phase3-complete.md) — Phase 3 完成报告 🎉
- [`i2h-verify/i2h-verify-phase3-start.md`](archive/i2h-verify/i2h-verify-phase3-start.md) — Phase 3 启动报告
- [`i2h-verify/i2h-verify-phase4-plan.md`](archive/i2h-verify/i2h-verify-phase4-plan.md) — Phase 4 规划：外部依赖处理
- [`i2h-verify/i2h-verify-production-ready.md`](archive/i2h-verify/i2h-verify-production-ready.md) — 🎉 i2h-verify 可用状态报告
- [`i2h-verify/i2h-verify-research-complete.md`](archive/i2h-verify/i2h-verify-research-complete.md) — i2h-verify 调研完整总结
- [`i2h-verify/README-i2h-verify-research.md`](archive/i2h-verify/README-i2h-verify-research.md) — i2h-verify 调研文档索引
- `archive/i2h-verify/SKILL.md.backup` — 未启用的历史 Skill 备份

### `initial-design/`

2024-11-01/02 的初始设计、原型、转换问题和阶段性完成报告。
- [`initial-design/CONVERSION_ISSUES_AND_FIXES.md`](archive/initial-design/CONVERSION_ISSUES_AND_FIXES.md) — 转换效果差的问题分析与解决方案
- [`initial-design/CORRECT_PLAN.md`](archive/initial-design/CORRECT_PLAN.md) — 工作重新规划 - 从头开始做对
- [`initial-design/DELIVERY_SUMMARY.md`](archive/initial-design/DELIVERY_SUMMARY.md) — 项目交付总结 - iOS to HarmonyOS Migration Tool
- [`initial-design/FINAL_100_PERCENT.md`](archive/initial-design/FINAL_100_PERCENT.md) — 🎉 iOS → HarmonyOS 迁移工具 - 100% 完成！
- [`initial-design/FINAL_SESSION_SUMMARY.md`](archive/initial-design/FINAL_SESSION_SUMMARY.md) — 🎉 会话最终总结
- [`initial-design/FINAL_SUMMARY.md`](archive/initial-design/FINAL_SUMMARY.md) — 🎉 最终工作总结 - 2024-11-01
- [`initial-design/FINAL_SUMMARY_V2.md`](archive/initial-design/FINAL_SUMMARY_V2.md) — 今日工作最终总结 - 2024-11-01
- [`initial-design/IMPLEMENTATION_COMPLETE.md`](archive/initial-design/IMPLEMENTATION_COMPLETE.md) — 🎉 iOS → HarmonyOS 迁移工具 - 完成报告
- [`initial-design/IMPLEMENTATION_PROGRESS.md`](archive/initial-design/IMPLEMENTATION_PROGRESS.md) — 🎉 实施进度报告 - Phase 2 Started
- [`initial-design/IMPLEMENTATION_SUMMARY.md`](archive/initial-design/IMPLEMENTATION_SUMMARY.md) — iOS to HarmonyOS Migration Tool - Implementation Summary
- [`initial-design/PHASE2_COMPLETION.md`](archive/initial-design/PHASE2_COMPLETION.md) — Phase 2 完成报告 - SwiftUI 模板转换器
- [`initial-design/SESSION_COMPLETE.md`](archive/initial-design/SESSION_COMPLETE.md) — 🎉 iOS → HarmonyOS 迁移工具链完成报告
- [`initial-design/SESSION_SUMMARY.md`](archive/initial-design/SESSION_SUMMARY.md) — 会话总结：hmigbot-ios 改造工作
- [`initial-design/TODAY_FINAL_SUMMARY.md`](archive/initial-design/TODAY_FINAL_SUMMARY.md) — 📊 今日工作总结 - 2024-11-01 最终版
- [`initial-design/TODAY_SUMMARY.md`](archive/initial-design/TODAY_SUMMARY.md) — 📊 今日工作总结 - 2024-11-01

### `session-history/`

旧交接、工作日志和阶段总结，按日期保留。
- [`session-history/FINAL-SUMMARY-2024-11-03.md`](archive/session-history/FINAL-SUMMARY-2024-11-03.md) — 🎉 2024-11-03 工作总结
- [`session-history/HANDOVER-2024-11-03.md`](archive/session-history/HANDOVER-2024-11-03.md) — 会话交接文档 - hmigbot-ios 工具改造
- [`session-history/PROJECT_STATUS-2024-11-01.md`](archive/session-history/PROJECT_STATUS-2024-11-01.md) — 📊 项目状态报告 - 2024-11-01
- [`session-history/QUICK_REFERENCE-2024-11-01.md`](archive/session-history/QUICK_REFERENCE-2024-11-01.md) — Quick Reference - iOS to HarmonyOS Migration Tool
- [`session-history/WORK-LOG-2024-11-03-04.md`](archive/session-history/WORK-LOG-2024-11-03-04.md) — 工作日志 2024-11-03/04

### `source-android/`

从原版仓库带入的 Android → HarmonyOS 变更记录，仅作为参考，不代表 iOS 状态。
- [`source-android/CHANGELOG-ANDROID-REFERENCE.md`](archive/source-android/CHANGELOG-ANDROID-REFERENCE.md) — Changelog

