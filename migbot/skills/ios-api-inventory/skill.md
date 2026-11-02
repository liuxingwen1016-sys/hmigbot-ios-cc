---
name: ios-api-inventory
description: Extract and inventory all API endpoints, network requests, data models, and service interfaces from an iOS project. Analyzes URLSession calls, Alamofire requests, REST endpoints, WebSocket connections, GraphQL queries, and response models. Use when planning iOS→HarmonyOS migration to understand backend dependencies, API contracts, and data layer architecture.
type: domain
domain: migration
tags: [migration, ios, api, network, data-layer]
---

# iOS API Inventory

## Purpose

Extract a comprehensive inventory of all API-related code from an iOS project:
- **Network endpoints**: URLs, HTTP methods, parameters
- **Request models**: Codable structs sent to server
- **Response models**: Codable structs received from server
- **Service interfaces**: NetworkManager, APIService classes
- **Authentication**: Token handling, auth headers
- **WebSocket**: Real-time connections
- **GraphQL**: Queries and mutations (if used)
- **Third-party SDKs**: Firebase, AWS, etc.

Output feeds into HarmonyOS data layer migration planning.

---

## Output

Produces `spec/baseline/ios-api-inventory.json`:

```json
{
  "endpoints": [...],
  "request_models": [...],
  "response_models": [...],
  "services": [...],
  "authentication": {...},
  "websockets": [...],
  "graphql": {...},
  "third_party_apis": [...]
}
```

---

## Workflow

### Step 1: Scan for network code

Find files containing network operations:

```bash
# URLSession
grep -r "URLSession" --include="*.swift" -l

# Alamofire
grep -r "import Alamofire" --include="*.swift" -l

# URLRequest
grep -r "URLRequest" --include="*.swift" -l

# Third-party networking
grep -r "import Moya\|import AFNetworking" --include="*.swift" -l
```

### Step 2: Extract API endpoints

For each network call, extract:
- Base URL
- Endpoint path
- HTTP method
- Parameters
- Headers
- Response type

**URLSession pattern**:
```swift
let url = URL(string: "https://api.example.com/posts")!
var request = URLRequest(url: url)
request.httpMethod = "GET"
```

**Alamofire pattern**:
```swift
AF.request("https://api.example.com/posts", 
           method: .get,
           parameters: ["page": 1])
  .responseDecodable(of: [Post].self)
```

**Output**:
```json
{
  "endpoint": "https://api.example.com/posts",
  "path": "/posts",
  "method": "GET",
  "parameters": [
    {"name": "page", "type": "Int", "required": false}
  ],
  "headers": ["Authorization"],
  "request_body": null,
  "response_type": "[Post]",
  "location": "Services/APIService.swift:45"
}
```

### Step 3: Extract base URLs

Identify API base URLs from:

**Config files**:
```swift
// Config.swift
static let baseURL = "https://api.example.com"
```

**Info.plist**:
```xml
<key>API_BASE_URL</key>
<string>https://api.example.com</string>
```

**Environment variables**:
```swift
ProcessInfo.processInfo.environment["API_URL"]
```

**Output**:
```json
{
  "base_urls": [
    {
      "url": "https://api.example.com",
      "environment": "production",
      "location": "Config.swift:12"
    },
    {
      "url": "https://staging-api.example.com",
      "environment": "staging",
      "location": "Config.swift:13"
    }
  ]
}
```

### Step 4: Extract request models

Find Codable structs used as request bodies:

```bash
# Search for structs with Encodable
grep -A 10 "struct.*Request.*:.*Encodable" *.swift
```

**Example**:
```swift
struct CreatePostRequest: Codable {
    let title: String
    let content: String
    let authorId: UUID
}
```

**Output**:
```json
{
  "name": "CreatePostRequest",
  "file": "Models/Requests/CreatePostRequest.swift",
  "properties": [
    {"name": "title", "type": "String", "required": true},
    {"name": "content", "type": "String", "required": true},
    {"name": "authorId", "type": "UUID", "required": true}
  ],
  "used_in": ["/api/posts (POST)"]
}
```

### Step 5: Extract response models

Find Codable structs used to decode responses:

```bash
# Search for structs with Decodable
grep -A 10 "struct.*Response.*:.*Decodable" *.swift
grep -A 10 "struct.*:.*Codable" *.swift
```

**Example**:
```swift
struct Post: Codable {
    let id: UUID
    let title: String
    let content: String
    let authorId: UUID
    let createdAt: Date
}
```

**Output**:
```json
{
  "name": "Post",
  "file": "Models/Post.swift",
  "properties": [
    {"name": "id", "type": "UUID"},
    {"name": "title", "type": "String"},
    {"name": "content", "type": "String"},
    {"name": "authorId", "type": "UUID"},
    {"name": "createdAt", "type": "Date"}
  ],
  "used_in": ["/api/posts (GET)", "/api/posts/:id (GET)"]
}
```

### Step 6: Extract service interfaces

Identify service/manager classes:

```bash
find . -name "*Service.swift" -o -name "*Manager.swift" -o -name "*API.swift"
```

For each service, extract:
- Class name
- Methods (API calls)
- Dependencies (injected services)
- Base URL configuration

**Example**:
```swift
class APIService {
    private let baseURL = "https://api.example.com"
    private let session: URLSession
    
    func fetchPosts() async throws -> [Post] { ... }
    func createPost(_ post: CreatePostRequest) async throws -> Post { ... }
}
```

**Output**:
```json
{
  "name": "APIService",
  "file": "Services/APIService.swift",
  "base_url": "https://api.example.com",
  "methods": [
    {
      "name": "fetchPosts",
      "endpoint": "/posts",
      "method": "GET",
      "return_type": "[Post]"
    },
    {
      "name": "createPost",
      "endpoint": "/posts",
      "method": "POST",
      "parameters": ["CreatePostRequest"],
      "return_type": "Post"
    }
  ],
  "dependencies": ["URLSession"]
}
```

### Step 7: Extract authentication

Identify auth mechanisms:

**Token storage**:
```bash
grep -r "Keychain\|UserDefaults.*token" --include="*.swift"
```

**Auth headers**:
```bash
grep -r "Authorization.*Bearer\|setValue.*Authorization" --include="*.swift"
```

**OAuth flows**:
```bash
grep -r "OAuth\|AuthenticationSession" --include="*.swift"
```

**Output**:
```json
{
  "authentication": {
    "type": "Bearer Token",
    "storage": "Keychain",
    "token_key": "authToken",
    "refresh_token": true,
    "refresh_endpoint": "/auth/refresh",
    "header_name": "Authorization",
    "header_format": "Bearer {token}",
    "implementation": "Services/AuthService.swift"
  }
}
```

### Step 8: Extract WebSocket connections

Find WebSocket usage:

```bash
grep -r "URLSessionWebSocketTask\|Starscream\|SocketIO" --include="*.swift"
```

**Example**:
```swift
let socket = URLSession.shared.webSocketTask(with: url)
socket.resume()
```

**Output**:
```json
{
  "websockets": [
    {
      "url": "wss://api.example.com/ws",
      "protocol": "URLSessionWebSocketTask",
      "purpose": "Real-time notifications",
      "location": "Services/WebSocketService.swift:23"
    }
  ]
}
```

### Step 9: Extract GraphQL (if present)

Find GraphQL usage:

```bash
grep -r "import Apollo\|GraphQL" --include="*.swift"
```

**Example**:
```swift
query FetchPosts {
    posts {
        id
        title
        content
    }
}
```

**Output**:
```json
{
  "graphql": {
    "enabled": true,
    "endpoint": "https://api.example.com/graphql",
    "client": "Apollo",
    "queries": [
      {
        "name": "FetchPosts",
        "file": "GraphQL/Queries/FetchPosts.graphql",
        "fields": ["id", "title", "content"]
      }
    ],
    "mutations": [
      {
        "name": "CreatePost",
        "file": "GraphQL/Mutations/CreatePost.graphql"
      }
    ]
  }
}
```

### Step 10: Extract third-party API SDKs

Identify third-party API integrations:

```bash
# Firebase
grep -r "import Firebase" --include="*.swift"

# AWS
grep -r "import AWSCore\|import AWSS3" --include="*.swift"

# Stripe
grep -r "import Stripe" --include="*.swift"

# Google Maps
grep -r "import GoogleMaps" --include="*.swift"
```

**Output**:
```json
{
  "third_party_apis": [
    {
      "name": "Firebase",
      "services": ["Authentication", "Firestore", "Analytics"],
      "location": ["AppDelegate.swift", "Services/FirebaseService.swift"]
    },
    {
      "name": "Stripe",
      "purpose": "Payment processing",
      "location": ["Services/PaymentService.swift"]
    }
  ]
}
```

---

## API Endpoint Classification

Classify each endpoint by:

**REST patterns**:
- **CRUD**: GET /posts, POST /posts, PUT /posts/:id, DELETE /posts/:id
- **List**: GET /posts (with pagination)
- **Detail**: GET /posts/:id
- **Action**: POST /posts/:id/publish
- **Batch**: POST /posts/batch

**Authentication**:
- **Public**: No auth required
- **Authenticated**: Requires auth token
- **Admin**: Requires admin role

**Data operations**:
- **Read-only**: GET endpoints
- **Mutation**: POST, PUT, DELETE
- **File upload**: multipart/form-data
- **File download**: Binary response

**Output**:
```json
{
  "endpoint": "/api/posts/:id",
  "method": "GET",
  "classification": {
    "pattern": "CRUD_detail",
    "auth_required": true,
    "auth_level": "user",
    "operation": "read",
    "has_path_params": true,
    "has_query_params": false,
    "has_body": false
  }
}
```

---

## Migration Planning

Use inventory to plan HarmonyOS data layer:

### Network library mapping
| iOS | HarmonyOS |
|-----|-----------|
| URLSession | @ohos.net.http |
| Alamofire | @ohos.net.http (wrapper needed) |
| WebSocket | @ohos.net.webSocket |
| Apollo GraphQL | Custom implementation |

### Authentication mapping
| iOS | HarmonyOS |
|-----|-----------|
| Keychain | @ohos.security.huks |
| UserDefaults (tokens) | @ohos.data.preferences |
| OAuth | @ohos.account.appAccount |

### Data model mapping
| iOS | HarmonyOS |
|-----|-----------|
| Codable | JSON.parse/stringify |
| JSONEncoder | Custom serializer |
| JSONDecoder | Custom deserializer |
| Date formatting | @ohos.i18n.I18n |

---

## Output Summary

Generate migration summary:

```markdown
# API Inventory Summary

## Overview
- Total endpoints: 45
- Base URLs: 2 (production, staging)
- Request models: 12
- Response models: 18
- Services: 5

## Network Stack
- Primary: URLSession
- Third-party: Alamofire (3 usages)
- WebSocket: Yes (1 connection)
- GraphQL: No

## Authentication
- Type: Bearer Token
- Storage: Keychain
- Refresh: Automatic

## Endpoints by Category
- CRUD operations: 28
- List operations: 8
- Action endpoints: 5
- File uploads: 2
- File downloads: 2

## Third-party APIs
- Firebase (Auth, Firestore, Analytics)
- Stripe (Payments)
- Google Maps (Location)

## Migration Complexity
- 🟢 Low: 30 endpoints (simple REST)
- 🟡 Medium: 12 endpoints (complex auth/pagination)
- 🔴 High: 3 endpoints (file upload, WebSocket)

## Recommendations
1. Implement network wrapper for @ohos.net.http
2. Migrate authentication to @ohos.security.huks
3. Create Codable-equivalent serialization layer
4. Plan WebSocket alternative (if needed)
5. Review Firebase migration options
```

---

## Quick Triage

Use this skill when:
- "Extract all API endpoints from iOS project"
- "What network calls does this app make?"
- "Show me all API models"
- "What authentication does this app use?"
- "Inventory all third-party API integrations"

Do not use for:
- UI analysis (use ios-ui-graph-builder)
- Full code analysis (use ios-fact-tree)
- Actual migration work
