# iOS 特有检查规则详解

本文档详细说明 CHECK-1 静态分析中的 9 项 iOS 特有检查规则。

---

## 1. 强制解包 `!`

### 检查目标

Swift 可选值（Optional）的强制解包操作符 `!`

### iOS 上下文

在 Swift 中，可选值是一种类型，表示值可能存在或为 `nil`。使用 `!` 强制解包时，如果值为 `nil`，会导致运行时崩溃。

```swift
// iOS Swift 代码
let user: User? = getUser()
let name = user!.name  // 强制解包，如果 user 为 nil 会崩溃
```

### 迁移到 ArkTS

ArkTS 使用可选类型和安全访问：

```typescript
// ArkTS 代码
let user: User | null = getUser()
let name = user?.name  // 安全访问，user 为 null 时返回 undefined
```

### 检查方式

```bash
# 搜索强制解包
rg -n '\w+!\.' --glob '*.ets'
rg -n '\w+!\s*$' --glob '*.ets'
```

### 复核标准

确认是否为以下情况：
- ✅ **违规**：`user!.name`、`value!`
- ❌ **误报**：注释中的 `!`、字符串中的 `!`

### 级别

**WARN** - 可能导致运行时崩溃，但可能是误报（注释或字符串）

### 建议修复

```typescript
// 错误写法
let name = user!.name

// 正确写法 1: 可选链
let name = user?.name

// 正确写法 2: 空值合并
let name = user?.name ?? 'Unknown'

// 正确写法 3: 类型守卫
if (user) {
  let name = user.name
}
```

---

## 2. `@escaping` 闭包

### 检查目标

Swift 闭包逃逸标记 `@escaping`

### iOS 上下文

在 Swift 中，当闭包作为参数传递给函数，但在函数返回后才执行时，需要标记为 `@escaping`。

```swift
// iOS Swift 代码
func fetchData(completion: @escaping (Data) -> Void) {
    DispatchQueue.global().async {
        let data = loadData()
        completion(data)  // 闭包在函数返回后执行
    }
}
```

### 迁移到 ArkTS

ArkTS 不需要显式标记闭包逃逸，自动管理生命周期。

```typescript
// ArkTS 代码
function fetchData(completion: (data: Data) => void) {
  // 直接使用回调，无需特殊标记
  taskpool.execute(() => {
    let data = loadData()
    completion(data)
  })
}
```

### 检查方式

```bash
rg -n '@escaping' --glob '*.ets'
```

### 复核标准

- ✅ **违规**：代码中出现 `@escaping` 关键字
- ❌ **误报**：注释或文档字符串中的 `@escaping`

### 级别

**WARN** - Swift 特有语法，ArkTS 不需要

### 建议修复

直接移除 `@escaping` 标记，保留函数类型定义。

---

## 3. `weak` / `unowned`

### 检查目标

Swift 内存管理关键字 `weak` 和 `unowned`

### iOS 上下文

Swift 使用 ARC（自动引用计数），需要手动打破循环引用：

```swift
// iOS Swift 代码
class ViewController {
    var closure: (() -> Void)?
    
    func setup() {
        closure = { [weak self] in
            self?.updateUI()  // 使用 weak 避免循环引用
        }
    }
}
```

### 迁移到 ArkTS

ArkTS 使用垃圾回收（GC），不需要手动管理内存。

```typescript
// ArkTS 代码
class ViewController {
  closure: (() => void) | null = null
  
  setup() {
    this.closure = () => {
      this.updateUI()  // 直接使用，GC 自动管理
    }
  }
}
```

### 检查方式

```bash
rg -n '\bweak\b' --glob '*.ets'
rg -n '\bunowned\b' --glob '*.ets'
```

### 复核标准

确认是否为 Swift 内存管理关键字：
- ✅ **违规**：`weak self`、`unowned self`、`weak var`
- ❌ **误报**：普通变量名包含 "weak"（如 `weakSignal`）

### 级别

**WARN** - Swift 内存管理遗留，ArkTS 不需要

### 建议修复

移除 `weak`/`unowned` 关键字，直接使用变量。

---

## 4. `@objc` / `@objcMembers`

### 检查目标

Swift 与 Objective-C 互操作标记

### iOS 上下文

在 Swift 中，使用 `@objc` 标记使类、方法或属性可以被 Objective-C 代码访问。

```swift
// iOS Swift 代码
@objc class MyClass: NSObject {
    @objc func doSomething() {
        // OC 可以调用这个方法
    }
}

@objcMembers
class AnotherClass {
    // 所有成员自动暴露给 OC
}
```

### 迁移到 ArkTS

ArkTS 不与 Objective-C 互操作，不需要这些标记。

### 检查方式

```bash
rg -n '@objc' --glob '*.ets'
rg -n '@objcMembers' --glob '*.ets'
```

### 复核标准

- ✅ **违规**：`@objc`、`@objcMembers` 出现在代码中
- ❌ **误报**：注释或文档中的说明

### 级别

**WARN** - Swift/OC 互操作遗留

### 建议修复

移除所有 `@objc` 和 `@objcMembers` 标记。

---

## 5. `#available` / `@available`

### 检查目标

iOS 版本可用性检查

### iOS 上下文

在 Swift 中，使用 `#available` 检查 API 在当前 iOS 版本是否可用：

```swift
// iOS Swift 代码
if #available(iOS 15.0, *) {
    // 使用 iOS 15+ API
    view.backgroundColor = .systemBackground
} else {
    // iOS 14 及以下的兼容代码
    view.backgroundColor = .white
}

@available(iOS 14.0, *)
func newFeature() {
    // 仅 iOS 14+ 可用
}
```

### 迁移到 ArkTS

HarmonyOS 有自己的 API 版本管理体系，不使用 iOS 版本号。

```typescript
// ArkTS 代码
// 使用 HarmonyOS API Level 检查
if (canIUse('SystemCapability.ArkUI.ArkUI.Full')) {
  // 使用新 API
}
```

### 检查方式

```bash
rg -n '#available' --glob '*.ets'
rg -n '@available' --glob '*.ets'
```

### 复核标准

- ✅ **违规**：`#available(iOS...)`、`@available(iOS...)`
- ❌ **误报**：注释中的说明

### 级别

**WARN** - iOS 版本检查在 HarmonyOS 不适用

### 建议修复

```typescript
// 移除 iOS 版本检查，使用 HarmonyOS API Level
// 或根据具体需求使用 canIUse()
if (canIUse('SystemCapability.xxx')) {
  // 使用对应功能
}
```

---

## 6. `DispatchQueue`

### 检查目标

iOS Grand Central Dispatch (GCD) 调度队列

### iOS 上下文

`DispatchQueue` 是 iOS 的并发编程核心：

```swift
// iOS Swift 代码
DispatchQueue.global().async {
    // 后台线程执行
    let data = loadData()
    
    DispatchQueue.main.async {
        // 回到主线程更新 UI
        self.updateUI(data)
    }
}
```

### 迁移到 ArkTS

ArkTS 使用 TaskPool 和 Worker 进行并发：

```typescript
// ArkTS 代码
import taskpool from '@ohos.taskpool'

// 后台任务
taskpool.execute(() => {
  let data = loadData()
  return data
}).then((data) => {
  // 自动回到主线程
  this.updateUI(data)
})
```

### 检查方式

```bash
rg -n 'DispatchQueue' --glob '*.ets'
```

### 复核标准

- ✅ **违规**：`DispatchQueue.main`、`DispatchQueue.global()`
- ❌ **误报**：注释或字符串中的 "DispatchQueue"

### 级别

**ERROR** - 必须改为 ArkTS 并发机制

### 建议修复

```typescript
// 错误写法
DispatchQueue.global().async { ... }

// 正确写法 1: TaskPool（轻量任务）
import taskpool from '@ohos.taskpool'
taskpool.execute(asyncFunction)

// 正确写法 2: Worker（长时任务）
import worker from '@ohos.worker'
const workerInstance = new worker.ThreadWorker('workers/MyWorker.ts')
```

---

## 7. `NotificationCenter`

### 检查目标

iOS 通知中心（NotificationCenter）

### iOS 上下文

`NotificationCenter` 是 iOS 的事件通知机制：

```swift
// iOS Swift 代码
// 发送通知
NotificationCenter.default.post(name: .userDidLogin, object: user)

// 接收通知
NotificationCenter.default.addObserver(
    self, 
    selector: #selector(handleLogin), 
    name: .userDidLogin, 
    object: nil
)
```

### 迁移到 ArkTS

ArkTS 使用 Emitter 事件机制：

```typescript
// ArkTS 代码
import emitter from '@ohos.events.emitter'

// 发送事件
emitter.emit({ eventId: 1001 }, { data: { user: user } })

// 接收事件
emitter.on({ eventId: 1001 }, (data) => {
  this.handleLogin(data.data.user)
})
```

### 检查方式

```bash
rg -n 'NotificationCenter' --glob '*.ets'
```

### 复核标准

- ✅ **违规**：`NotificationCenter.default`、`NotificationCenter.post`
- ❌ **误报**：注释或字符串

### 级别

**WARN** - 需要改为 Emitter

### 建议修复

```typescript
// 错误写法
NotificationCenter.default.post(...)

// 正确写法
import emitter from '@ohos.events.emitter'

// 定义事件 ID
const EVENT_USER_LOGIN = 1001

// 发送事件
emitter.emit({ eventId: EVENT_USER_LOGIN }, { data: userData })

// 接收事件
emitter.on({ eventId: EVENT_USER_LOGIN }, (eventData) => {
  // 处理事件
})
```

---

## 8. `UserDefaults`

### 检查目标

iOS 本地存储 API `UserDefaults`

### iOS 上下文

`UserDefaults` 是 iOS 的轻量级键值对存储：

```swift
// iOS Swift 代码
// 保存
UserDefaults.standard.set("John", forKey: "username")
UserDefaults.standard.set(25, forKey: "age")

// 读取
let username = UserDefaults.standard.string(forKey: "username")
let age = UserDefaults.standard.integer(forKey: "age")
```

### 迁移到 ArkTS

ArkTS 使用 Preferences（首选项）：

```typescript
// ArkTS 代码
import preferences from '@ohos.data.preferences'

// 获取实例
let prefs = await preferences.getPreferences(context, 'myStore')

// 保存
await prefs.put('username', 'John')
await prefs.put('age', 25)
await prefs.flush()

// 读取
let username = await prefs.get('username', '')
let age = await prefs.get('age', 0)
```

### 检查方式

```bash
rg -n 'UserDefaults' --glob '*.ets'
```

### 复核标准

- ✅ **违规**：`UserDefaults.standard`、`UserDefaults.set`
- ❌ **误报**：注释或字符串

### 级别

**ERROR** - 必须改为 Preferences

### 建议修复

```typescript
// 错误写法
UserDefaults.standard.set(value, forKey: key)

// 正确写法
import preferences from '@ohos.data.preferences'

class UserDefaultsHelper {
  private prefs: preferences.Preferences | null = null
  
  async init(context: Context) {
    this.prefs = await preferences.getPreferences(context, 'myStore')
  }
  
  async set(key: string, value: string | number | boolean) {
    await this.prefs?.put(key, value)
    await this.prefs?.flush()
  }
  
  async get(key: string, defaultValue: string | number | boolean) {
    return await this.prefs?.get(key, defaultValue)
  }
}
```

---

## 9. `UIKit` / `SwiftUI` 导入

### 检查目标

iOS UI 框架导入语句

### iOS 上下文

iOS 应用使用 UIKit 或 SwiftUI 构建界面：

```swift
// iOS Swift 代码
import UIKit
import SwiftUI

class ViewController: UIViewController {
    // UIKit 代码
}

struct ContentView: View {
    // SwiftUI 代码
}
```

### 迁移到 ArkTS

ArkTS 使用 ArkUI 框架，不需要导入（内置）：

```typescript
// ArkTS 代码
// 无需导入，直接使用 ArkUI 组件

@Entry
@Component
struct ContentView {
  build() {
    Column() {
      Text('Hello')
      Button('Click')
    }
  }
}
```

### 检查方式

```bash
rg -n 'import UIKit' --glob '*.ets'
rg -n 'import SwiftUI' --glob '*.ets'
```

### 复核标准

- ✅ **违规**：`import UIKit`、`import SwiftUI`
- ❌ **误报**：注释中的示例代码

### 级别

**ERROR** - iOS UI 框架，迁移未完成

### 建议修复

```typescript
// 错误写法
import UIKit

class ViewController {
  // ...
}

// 正确写法
// 移除 import，使用 ArkUI 组件

@Entry
@Component
struct MyPage {
  build() {
    Column() {
      // ArkUI 组件
    }
  }
}
```

---

## 实现建议

### 脚本实现

建议在 `scripts/ios_static_analyzer.py` 中实现这 9 项检查：

```python
IOS_SPECIFIC_CHECKS = [
    {
        'id': 'IOS.FORCE_UNWRAP',
        'pattern': r'\w+!\.|\w+!\s*$',
        'level': 'WARN',
        'message': '使用强制解包 !，可能导致运行时崩溃'
    },
    {
        'id': 'IOS.ESCAPING_CLOSURE',
        'pattern': r'@escaping',
        'level': 'WARN',
        'message': 'Swift 闭包逃逸标记，ArkTS 不需要'
    },
    {
        'id': 'IOS.WEAK_UNOWNED',
        'pattern': r'\bweak\b|\bunowned\b',
        'level': 'WARN',
        'message': 'Swift 内存管理关键字，ArkTS 自动管理'
    },
    {
        'id': 'IOS.OBJC_INTEROP',
        'pattern': r'@objc',
        'level': 'WARN',
        'message': 'Swift/OC 互操作标记，迁移遗留'
    },
    {
        'id': 'IOS.AVAILABLE_CHECK',
        'pattern': r'#available|@available',
        'level': 'WARN',
        'message': 'iOS 版本检查，HarmonyOS 不适用'
    },
    {
        'id': 'IOS.DISPATCH_QUEUE',
        'pattern': r'DispatchQueue',
        'level': 'ERROR',
        'message': 'GCD 调度队列，必须改为 TaskPool/Worker'
    },
    {
        'id': 'IOS.NOTIFICATION_CENTER',
        'pattern': r'NotificationCenter',
        'level': 'WARN',
        'message': 'iOS 通知中心，需要改为 Emitter'
    },
    {
        'id': 'IOS.USER_DEFAULTS',
        'pattern': r'UserDefaults',
        'level': 'ERROR',
        'message': 'iOS 本地存储，必须改为 Preferences'
    },
    {
        'id': 'IOS.UI_FRAMEWORK',
        'pattern': r'import (UIKit|SwiftUI)',
        'level': 'ERROR',
        'message': 'iOS UI 框架，迁移未完成'
    }
]
```

### 误报处理

每个检查需要复核上下文，排除：
- 注释：行以 `//` 或 `/*` 开头
- 字符串：匹配在引号内
- 普通标识符：如变量名包含关键字但不是实际用法

---

**版本**: v1.0  
**创建时间**: 2024-11-03  
**作者**: 模型 Opus 5.5
