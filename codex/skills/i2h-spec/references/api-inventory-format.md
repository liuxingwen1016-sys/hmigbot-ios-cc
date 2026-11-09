# API Inventory 格式规范

本文档定义 `spec/baseline/api-inventory/api-inventory.json` 的标准格式，借鉴自 `references/ios-0.14.1` 的设计，对齐 hmigbot 原版规范。

---

## 📊 文件结构

### 1. 顶层结构

```json
{
  "platform": "ios",
  "project_type": "online_service | offline_sample | hybrid",
  "scan_timestamp": "2024-11-03T10:00:00Z",
  "services": [],
  "base_urls": [],
  "url_constants": {},
  "api_related_constants": {},
  "hardcoded_urls": [],
  "third_party_domains": [],
  "ios_frameworks": [],
  "permissions": [],
  "entitlements": []
}
```

---

## 🔧 字段说明

### platform
- **类型**: string
- **值**: `"ios"`（固定）
- **说明**: 标识源平台

### project_type
- **类型**: string
- **值**: `online_service` | `offline_sample` | `hybrid`
- **说明**: 
  - `online_service`: 有真实后端 API
  - `offline_sample`: 纯 UI 演示，无外部 API
  - `hybrid`: 部分在线部分离线

### scan_timestamp
- **类型**: string (ISO 8601)
- **说明**: 扫描时间戳

---

### services (核心字段)

服务清单，每个服务代表一个后端 API 集合或 SDK。

```json
{
  "services": [
    {
      "service_id": "UserService",
      "service_name": "用户服务",
      "endpoints": [
        {
          "endpoint_id": "ep_001",
          "static": {
            "http_method": "POST",
            "path": "/api/users/login",
            "protocol": "REST"
          },
          "source_anchors": [
            "App/Services/UserService.swift:45"
          ],
          "fact_ids": ["api_call_001"]
        }
      ],
      "auth_type": "Bearer | OAuth2 | API_Key | Custom | None",
      "base_url_ref": "base_url_001",
      "source_anchors": [
        "App/Services/UserService.swift:12"
      ]
    }
  ]
}
```

#### service 字段

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `service_id` | string | ✅ | 服务唯一标识 (如 UserService) |
| `service_name` | string | 🟡 | 服务名称（人类可读） |
| `endpoints` | array | ✅ | 端点列表 |
| `auth_type` | string | ✅ | 认证方式 |
| `base_url_ref` | string | 🟡 | 引用 base_urls 中的 ID |
| `source_anchors` | array | ✅ | 源码位置（文件:行号） |

#### endpoint 字段

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `endpoint_id` | string | ✅ | 端点唯一标识 |
| `static` | object | ✅ | 静态分析得到的信息 |
| `static.http_method` | string | ✅ | HTTP 方法 (GET/POST/PUT/DELETE) |
| `static.path` | string | ✅ | 路径 (如 /api/users/:id) |
| `static.protocol` | string | ✅ | 协议 (REST/GraphQL/WebSocket) |
| `source_anchors` | array | ✅ | 源码位置数组 |
| `fact_ids` | array | 🟡 | 关联的 fact ID（如果使用 facts 系统） |

**注意**: 
- ❌ **不包含** `runtime` 和 `reconciled` 字段（references/ 的三段式对账）
- ✅ 只保留 `static` 段（源侧静态契约）
- ✅ 对账工作由下游工具负责，不在 spec 阶段

---

### base_urls

基础 URL 清单。

```json
{
  "base_urls": [
    {
      "id": "base_url_001",
      "url": "https://api.example.com",
      "environment": "production | staging | development",
      "source_anchor": "App/Config/APIConfig.swift:10"
    }
  ]
}
```

---

### url_constants

URL 常量映射。

```json
{
  "url_constants": {
    "API_BASE_URL": "https://api.example.com",
    "AUTH_ENDPOINT": "/auth/login"
  }
}
```

---

### api_related_constants

API 相关常量（如状态码、错误码）。

```json
{
  "api_related_constants": {
    "SUCCESS_CODE": "200",
    "TOKEN_EXPIRED": "401",
    "API_KEY": "constant_reference"
  }
}
```

---

### hardcoded_urls

硬编码的 URL。

```json
{
  "hardcoded_urls": [
    {
      "url": "https://example.com/deeplink/cart",
      "location": "App/DeepLink/Router.swift:25",
      "context": "Deep link handling",
      "usage": "navigation_example | api_call | asset_url"
    }
  ]
}
```

---

### third_party_domains

第三方域名清单。

```json
{
  "third_party_domains": [
    {
      "domain": "analytics.google.com",
      "purpose": "analytics",
      "sdk": "Firebase Analytics"
    }
  ]
}
```

---

### ios_frameworks (iOS 特有)

使用的 iOS 系统框架。

```json
{
  "ios_frameworks": [
    {
      "name": "Foundation.URLSession",
      "usage_count": 15,
      "files": ["App/Services/NetworkService.swift"],
      "harmonyos_mapping": {
        "target": "@ohos.net.http",
        "confidence": "high"
      }
    },
    {
      "name": "Alamofire",
      "version": "5.0",
      "usage_count": 8,
      "is_third_party": true,
      "harmonyos_alternative": "http 模块封装"
    }
  ]
}
```

---

### permissions (iOS 特有)

需要的系统权限。

```json
{
  "permissions": [
    {
      "key": "NSCameraUsageDescription",
      "value": "需要相机权限以扫描二维码",
      "source": "Info.plist",
      "harmonyos_permission": "ohos.permission.CAMERA"
    }
  ]
}
```

---

### entitlements (iOS 特有)

App 的 Entitlements。

```json
{
  "entitlements": [
    {
      "key": "com.apple.developer.networking.networkextension",
      "value": true,
      "source": "App.entitlements",
      "notes": "VPN 功能需要"
    }
  ]
}
```

---

## 📝 完整示例

### 示例 1: 离线应用 (对齐 JetSnack)

```json
{
  "platform": "ios",
  "project_type": "offline_sample",
  "scan_timestamp": "2024-11-03T10:00:00Z",
  "services": [],
  "base_urls": [],
  "url_constants": {},
  "api_related_constants": {},
  "hardcoded_urls": [
    {
      "url": "cuike://app/recipe/detail",
      "location": "App/DeepLink/Router.swift:15",
      "context": "Deep link demonstration",
      "usage": "navigation_example"
    }
  ],
  "third_party_domains": [],
  "ios_frameworks": [
    {
      "name": "Foundation.UserDefaults",
      "usage_count": 3,
      "files": ["App/Data/BrewStore.swift"],
      "harmonyos_mapping": {
        "target": "@ohos.data.preferences",
        "confidence": "high"
      }
    },
    {
      "name": "SwiftData",
      "usage_count": 5,
      "files": ["App/Data/Models.swift", "App/Data/BrewStore.swift"],
      "harmonyos_mapping": {
        "target": "@ohos.data.relationalStore",
        "confidence": "medium"
      }
    }
  ],
  "permissions": [],
  "entitlements": []
}
```

---

### 示例 2: 在线应用

```json
{
  "platform": "ios",
  "project_type": "online_service",
  "scan_timestamp": "2024-11-03T10:00:00Z",
  "services": [
    {
      "service_id": "UserService",
      "service_name": "用户服务",
      "endpoints": [
        {
          "endpoint_id": "ep_001",
          "static": {
            "http_method": "POST",
            "path": "/api/v1/users/login",
            "protocol": "REST"
          },
          "source_anchors": [
            "App/Services/UserService.swift:45"
          ]
        },
        {
          "endpoint_id": "ep_002",
          "static": {
            "http_method": "GET",
            "path": "/api/v1/users/profile",
            "protocol": "REST"
          },
          "source_anchors": [
            "App/Services/UserService.swift:78"
          ]
        }
      ],
      "auth_type": "Bearer",
      "base_url_ref": "base_url_001",
      "source_anchors": [
        "App/Services/UserService.swift:12"
      ]
    },
    {
      "service_id": "ProductService",
      "service_name": "商品服务",
      "endpoints": [
        {
          "endpoint_id": "ep_003",
          "static": {
            "http_method": "GET",
            "path": "/api/v1/products",
            "protocol": "REST"
          },
          "source_anchors": [
            "App/Services/ProductService.swift:30"
          ]
        }
      ],
      "auth_type": "Bearer",
      "base_url_ref": "base_url_001",
      "source_anchors": [
        "App/Services/ProductService.swift:10"
      ]
    }
  ],
  "base_urls": [
    {
      "id": "base_url_001",
      "url": "https://api.example.com",
      "environment": "production",
      "source_anchor": "App/Config/APIConfig.swift:10"
    }
  ],
  "url_constants": {
    "API_BASE_URL": "https://api.example.com",
    "LOGIN_PATH": "/api/v1/users/login"
  },
  "api_related_constants": {
    "SUCCESS_CODE": "200",
    "TOKEN_EXPIRED_CODE": "401",
    "API_VERSION": "v1"
  },
  "hardcoded_urls": [],
  "third_party_domains": [
    {
      "domain": "analytics.google.com",
      "purpose": "analytics",
      "sdk": "Firebase Analytics"
    }
  ],
  "ios_frameworks": [
    {
      "name": "Foundation.URLSession",
      "usage_count": 20,
      "files": [
        "App/Services/NetworkService.swift",
        "App/Services/UserService.swift"
      ],
      "harmonyos_mapping": {
        "target": "@ohos.net.http",
        "confidence": "high"
      }
    },
    {
      "name": "Alamofire",
      "version": "5.8.0",
      "usage_count": 10,
      "is_third_party": true,
      "harmonyos_alternative": "封装 @ohos.net.http"
    }
  ],
  "permissions": [
    {
      "key": "NSCameraUsageDescription",
      "value": "扫描商品二维码",
      "source": "Info.plist",
      "harmonyos_permission": "ohos.permission.CAMERA"
    },
    {
      "key": "NSPhotoLibraryUsageDescription",
      "value": "上传商品图片",
      "source": "Info.plist",
      "harmonyos_permission": "ohos.permission.READ_MEDIA"
    }
  ],
  "entitlements": [
    {
      "key": "com.apple.developer.associated-domains",
      "value": ["applinks:example.com"],
      "source": "App.entitlements",
      "notes": "Universal Links"
    }
  ]
}
```

---

## 🔄 与原版对比

### 相同之处 ✅

1. **顶层结构**: `platform`, `project_type`, `services`, `base_urls` 等字段保持一致
2. **endpoint 结构**: 使用 `static` 对象包含 HTTP 方法、路径、协议
3. **source_anchors**: 保留源码锚点追溯
4. **auth_type**: 认证方式枚举

### 差异之处 🔄

| 项目 | 原版 (Android) | iOS 版本 | 说明 |
|------|---------------|---------|------|
| `platform` | `"android"` | `"ios"` | 平台标识 |
| `ios_frameworks` | ❌ 无 | ✅ 有 | iOS 特有：系统框架使用 |
| `permissions` | `android.permission.*` | `NS*UsageDescription` | iOS 的 Info.plist 权限 |
| `entitlements` | ❌ 无 | ✅ 有 | iOS 特有：App 能力 |
| `interceptors` | ✅ 有 (Retrofit) | ❌ 无 | iOS 不常见 |
| `body_assembly_sites` | ✅ 有 | ❌ 无 | iOS 不常见 |
| `gradle_config` | ✅ 有 | ❌ 无 | 改为 xcodeproj 分析 |

### 不引入的 references/ 特性 ❌

根据 `references-integration-analysis.md` 的建议：

1. ❌ **不使用三段式对账** (`runtime`, `reconciled` 字段)
   - references/ 设计：`static` / `runtime` / `reconciled`
   - 我们只保留：`static`
   - 理由：对账工作由下游工具负责，spec 阶段只做静态分析

2. ❌ **不使用 fact_ids 系统**（可选）
   - 如果不使用 references/ 的 facts 系统，可以省略
   - 保持简洁

3. ❌ **不使用复杂的 obligations 机制**
   - references/ 有独立的 `ios-obligations.json`
   - 我们将义务直接嵌入相关字段

---

## 🎯 生成流程

### Phase B: API 扫描 (i2h-spec 调用)

```python
def generate_api_inventory(ios_project_path):
    """
    生成 API 清单
    
    输出: spec/baseline/api-inventory/
      ├── raw_apis.json (原始扫描结果)
      ├── api-inventory.json (结构化清单)
      └── api-inventory.md (人类可读报告)
    """
    
    # 1. 扫描网络层
    services = scan_network_layer(ios_project_path)
    
    # 2. 扫描 URL 常量
    url_constants = scan_url_constants(ios_project_path)
    
    # 3. 扫描硬编码 URL
    hardcoded_urls = scan_hardcoded_urls(ios_project_path)
    
    # 4. 扫描第三方 SDK
    third_party = scan_third_party_sdks(ios_project_path)
    
    # 5. 扫描系统框架
    frameworks = scan_ios_frameworks(ios_project_path)
    
    # 6. 扫描权限
    permissions = scan_info_plist_permissions(ios_project_path)
    
    # 7. 扫描 Entitlements
    entitlements = scan_entitlements(ios_project_path)
    
    # 8. 组装
    inventory = {
        'platform': 'ios',
        'project_type': infer_project_type(services),
        'scan_timestamp': datetime.utcnow().isoformat() + 'Z',
        'services': services,
        'base_urls': extract_base_urls(url_constants),
        'url_constants': url_constants,
        'hardcoded_urls': hardcoded_urls,
        'third_party_domains': third_party,
        'ios_frameworks': frameworks,
        'permissions': permissions,
        'entitlements': entitlements
    }
    
    return inventory
```

---

## 📚 参考资源

- **原版格式**: `~/DevEcoStudioProjects/JetSnackHarmony/spec/baseline/api-inventory/api-inventory.json`
- **references/ 设计**: `~/Codes/ios2harmony/hmigbot-ios/references/ios-0.14.1-iOS技能与说明/skills/ios-api-inventory/SKILL.md`
- **集成分析**: `~/Codes/ios2harmony/hmigbot-ios/references-integration-analysis.md`

---

**最后更新**: 2024-11-03  
**版本**: 1.0  
**状态**: 规范定义，待实现
