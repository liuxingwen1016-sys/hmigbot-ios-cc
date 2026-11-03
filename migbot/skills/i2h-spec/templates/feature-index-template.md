<!-- Phase C: 功能索引模板 -->
<!-- 用于生成 spec/baseline/feature-index.md -->

# 功能索引

**项目**: {项目名称}  
**生成时间**: {ISO 8601 时间戳}  
**数据来源**: Phase C - 功能分析

---

## 1. 功能命名规则

- **格式**: `FXXX` (F001, F002, ..., F999)
- **编号范围**:
  - F001-F099: 核心业务功能
  - F100-F199: 系统集成功能
  - F200-F299: 辅助功能和工具

---

## 2. 核心业务功能 (F001-F099)

### F001: 数据存储

**基本信息**:
- **源文件**: `App/Data/BeanStore.swift`, `App/Models/Bean.swift`
- **技术**: SwiftData
- **复杂度**: `high`
- **优先级**: P0 (关键依赖)

**iOS 实现**:
- 使用 SwiftData 管理数据模型
- 模型: `BeanRecord`, `RecipeRecord`, `BrewRecord`
- 支持: CRUD 操作, 查询, 关系映射

**HarmonyOS 目标**:
- **框架**: `@ohos.data.relationalStore` (关系型数据库)
- **迁移策略**: 重新设计数据模型，保持结构相似
- **数据迁移**: 需要提供数据导入/导出工具

**依赖关系**:
- 被依赖: F002 (导航路由), F003 (用户偏好)
- 依赖: 无

**Spec 文件**: `spec/baseline/features/feat_001_data_storage.md`

---

### F002: 导航路由

**基本信息**:
- **源文件**: `App/Navigation/AppRouter.swift`
- **技术**: NavigationStack + NavigationPath
- **复杂度**: `medium`
- **优先级**: P0

**iOS 实现**:
- 使用 SwiftUI NavigationStack
- 路由管理: 基于 NavigationPath
- 深度链接支持

**HarmonyOS 目标**:
- **组件**: `Navigation` + `NavPathStack`
- **迁移策略**: 重新设计路由管理器

**依赖关系**:
- 被依赖: 所有页面
- 依赖: F001 (导航需要数据)

**Spec 文件**: `spec/baseline/features/feat_002_navigation.md`

---

### F003: 用户偏好

**基本信息**:
- **源文件**: 分散在多个文件中，使用 `@AppStorage`
- **技术**: UserDefaults
- **复杂度**: `low`
- **优先级**: P1

**iOS 实现**:
- 使用 `@AppStorage` 包装器
- 存储用户设置（主题、语言、通知偏好等）

**HarmonyOS 目标**:
- **框架**: `@ohos.data.preferences`
- **映射**: `@AppStorage` → `@StorageLink`

**依赖关系**:
- 被依赖: SettingsView
- 依赖: 无

**Spec 文件**: `spec/baseline/features/feat_003_user_preferences.md`

---

## 3. 系统集成功能 (F100-F199)

### F101: 相机扫描

**基本信息**:
- **源文件**: `App/Services/ScanViewController.swift`
- **技术**: AVFoundation + VisionKit
- **复杂度**: `very_complex`
- **优先级**: P0 (核心功能)

**iOS 实现**:
- UIKit ViewController (非 SwiftUI)
- AVCaptureSession 相机会话
- VNDocumentCameraViewController OCR 扫描

**HarmonyOS 目标**:
- **框架**: `@ohos.multimedia.camera`
- **OCR**: 华为 ML Kit OCR 服务
- **迁移策略**: 完全重写为 ArkTS

**权限要求**:
- iOS: `NSCameraUsageDescription`
- HarmonyOS: `ohos.permission.CAMERA`

**依赖关系**:
- 被依赖: 多个页面调用扫描功能
- 依赖: 无

**Spec 文件**: `spec/baseline/features/feat_101_camera_scan.md`

---

### F102: 通知服务

**基本信息**:
- **源文件**: `App/Services/NotificationService.swift`
- **技术**: UserNotifications framework
- **复杂度**: `medium`
- **优先级**: P2

**iOS 实现**:
- 本地通知（冲泡提醒）
- 通知权限请求和管理

**HarmonyOS 目标**:
- **框架**: `@ohos.notificationManager`
- **映射**: 相似 API，需要适配

**权限要求**:
- iOS: `NSUserNotificationsUsageDescription`
- HarmonyOS: `ohos.permission.NOTIFICATION`

**依赖关系**:
- 被依赖: BrewTimer 功能
- 依赖: 无

**Spec 文件**: `spec/baseline/features/feat_102_notification.md`

---

## 4. 辅助功能 (F200-F299)

### F201: 数据导出

**基本信息**:
- **源文件**: `App/Services/ExportService.swift`
- **技术**: FileManager + JSON encoding
- **复杂度**: `low`
- **优先级**: P3 (可选功能)

**iOS 实现**:
- 导出咖啡豆和配方数据为 JSON
- 使用系统分享面板

**HarmonyOS 目标**:
- **框架**: `@ohos.file.fs` + 分享组件
- **迁移策略**: 直接映射

**标记**: 可选功能，可在 Phase 2+ 实现

**Spec 文件**: `spec/baseline/features/feat_201_data_export.md`

---

## 5. 功能依赖图

```
F001 (数据存储)
  ├─ F002 (导航路由)
  │   └─ 所有页面
  ├─ F003 (用户偏好)
  │   └─ SettingsView
  └─ F201 (数据导出)

F101 (相机扫描)
  └─ ScanViewController
  └─ HomeView (触发扫描)

F102 (通知服务)
  └─ BrewTimer
```

---

## 6. 复杂度统计

| 复杂度 | 数量 | 功能列表 |
|--------|------|---------|
| `low` | 2 | F003, F201 |
| `medium` | 2 | F002, F102 |
| `high` | 1 | F001 |
| `very_complex` | 1 | F101 |

---

## 7. 优先级分配

| 优先级 | 数量 | 说明 |
|--------|------|------|
| P0 (必须) | 3 | F001, F002, F101 |
| P1 (重要) | 1 | F003 |
| P2 (增强) | 1 | F102 |
| P3 (可选) | 1 | F201 |

---

## 8. 迁移时间预估

| 功能 | 复杂度 | 预估用时 | 阶段 |
|------|--------|---------|------|
| F001 | high | 8-12 小时 | Stage 2 |
| F002 | medium | 4-6 小时 | Stage 1 |
| F003 | low | 2-3 小时 | Stage 1 |
| F101 | very_complex | 12-16 小时 | Stage 3 |
| F102 | medium | 4-6 小时 | Stage 2 |
| F201 | low | 2-3 小时 | Stage 4+ (可选) |

**总计**: 32-46 小时（不含可选功能）

---

## 9. 技术栈映射总览

| iOS 技术 | 使用功能 | HarmonyOS 映射 |
|---------|---------|---------------|
| SwiftData | F001 | @ohos.data.relationalStore |
| NavigationStack | F002 | Navigation + NavPathStack |
| UserDefaults | F003 | @ohos.data.preferences |
| AVFoundation | F101 | @ohos.multimedia.camera |
| VisionKit | F101 | 华为 ML Kit OCR |
| UserNotifications | F102 | @ohos.notificationManager |
| FileManager | F201 | @ohos.file.fs |

---

## 10. 风险评估

### 高风险功能

| 功能 | 风险 | 原因 | 缓解措施 |
|------|------|------|---------|
| F001 | 🔴 High | SwiftData 到关系型数据库需完全重新设计 | 优先实现，提供充分测试 |
| F101 | 🔴 High | UIKit + 相机，无法自动转换 | 分配专门时间，参考官方示例 |

### 中风险功能

| 功能 | 风险 | 原因 | 缓解措施 |
|------|------|------|---------|
| F002 | 🟡 Medium | 导航机制差异大 | 统一使用 NavPathStack 管理 |
| F102 | 🟡 Medium | 通知 API 有差异 | 参考鸿蒙文档适配 |

### 低风险功能

| 功能 | 风险 | 原因 |
|------|------|------|
| F003 | 🟢 Low | API 相似，直接映射 |
| F201 | 🟢 Low | 简单功能，可选 |

---

## 11. 下一步

1. ✅ Phase C.1 完成 — 功能索引生成（本文档）
2. ⏭️ **Phase C.2** — 生成分功能 spec（`spec/baseline/features/feat_*.md`）
3. ⏭️ **Phase C.3** — 功能覆盖率审计
4. ⏭️ **Gate C** — Spec 完成审批

---

**文档版本**: v1.0  
**最后更新**: {时间戳}
