# Phase 1 Day 2 执行计划: api-inventory/ 生成

**目标**: 生成完整的 API 清单 (api-inventory/)  
**时间**: 2024-11-03  
**优先级**: P0 (最高)  
**预计用时**: 4-6 小时

---

## 📊 任务概述

### 需要生成的文件

```
spec/baseline/api-inventory/
├── raw_apis.json          (原始扫描结果)
├── api-inventory.json     (结构化清单)
└── api-inventory.md       (人类可读报告)
```

### 参考资料

已准备好的文档：
- ✅ `migbot/skills/i2h-spec/references/api-inventory-format.md` (完整格式规范)
- ✅ `references/ios-0.14.1/skills/ios-api-inventory/SKILL.md` (原版方法论)
- ✅ 原版示例: `~/DevEcoStudioProjects/JetSnackHarmony/spec/baseline/api-inventory/`

---

## 🎯 扫描目标

### 1. 网络层 API

**扫描内容**:
- URLSession 使用
- Alamofire/Moya/AFNetworking 等第三方库
- HTTP 请求定义
- API 端点 URL
- 请求方法 (GET/POST/PUT/DELETE)

**示例代码模式**:
```swift
// URLSession
let url = URL(string: "https://api.example.com/users")!
URLSession.shared.dataTask(with: url) { ... }

// Alamofire
AF.request("https://api.example.com/users").response { ... }
```

### 2. iOS 系统框架

**扫描内容**:
- Foundation (URLSession, UserDefaults, FileManager)
- SwiftData / Core Data
- AVFoundation (相机、音频)
- CoreLocation (定位)
- UserNotifications (通知)

### 3. 权限 (Info.plist)

**扫描内容**:
- NSCameraUsageDescription
- NSPhotoLibraryUsageDescription
- NSLocationWhenInUseUsageDescription
- NSUserTrackingUsageDescription
- 等等...

### 4. Entitlements

**扫描内容**:
- com.apple.developer.associated-domains
- com.apple.developer.networking.networkextension
- com.apple.security.application-groups

### 5. 第三方 SDK

**扫描内容**:
- CocoaPods (Podfile)
- Swift Package Manager (Package.swift, Package.resolved)
- 依赖库版本

---

## 🔧 实现步骤

### Step 1: 创建 Python 脚本

**文件**: `~/.migbot/bin/scripts/ios/generate_api_inventory.py`

**核心函数**:
```python
def scan_network_layer(ios_root)      # 扫描网络层
def scan_url_constants(ios_root)      # 扫描 URL 常量
def scan_hardcoded_urls(ios_root)     # 扫描硬编码 URL
def scan_ios_frameworks(ios_root)     # 扫描系统框架
def scan_permissions(ios_root)        # 扫描权限
def scan_entitlements(ios_root)       # 扫描 Entitlements
def scan_dependencies(ios_root)       # 扫描第三方依赖
```

### Step 2: 实现扫描逻辑

使用 grep + Python 组合：
- 快速扫描（grep）
- 结构化处理（Python）
- 无需外部依赖

### Step 3: 生成三个文件

1. **raw_apis.json** - 原始扫描数据
2. **api-inventory.json** - 结构化清单（符合格式规范）
3. **api-inventory.md** - Markdown 报告（人类可读）

### Step 4: 测试验证

在 Cuike01 项目上运行并验证输出

---

## 📋 验收标准

### 必须满足

- [ ] `spec/baseline/api-inventory/` 目录存在
- [ ] 包含 3 个文件 (raw_apis.json, api-inventory.json, api-inventory.md)
- [ ] api-inventory.json 符合格式规范
- [ ] 包含 iOS 特有字段 (ios_frameworks, permissions, entitlements)
- [ ] JSON 格式正确，可以被 jq 解析
- [ ] Markdown 报告清晰可读

### 格式兼容性

- [ ] 与原版 JetSnackHarmony 结构一致
- [ ] platform = "ios"
- [ ] 所有必需字段齐全
- [ ] source_anchors 包含文件路径和行号

---

## ⏱️ 时间估算

| 步骤 | 时间 | 说明 |
|------|------|------|
| Step 1: 脚本架构设计 | 30 分钟 | 确定函数结构 |
| Step 2: 网络层扫描 | 1-1.5 小时 | URLSession, Alamofire |
| Step 3: 权限扫描 | 30 分钟 | Info.plist 解析 |
| Step 4: 框架扫描 | 1 小时 | 系统框架识别 |
| Step 5: 依赖扫描 | 30 分钟 | CocoaPods, SPM |
| Step 6: 生成 JSON | 1 小时 | 结构化输出 |
| Step 7: 生成 Markdown | 30 分钟 | 人类可读报告 |
| Step 8: 测试验证 | 1 小时 | 在 Cuike01 测试 |
| **总计** | **5.5-6.5 小时** | |

---

**创建时间**: 2024-11-03  
**状态**: 计划就绪，开始执行
