# 静态分析与 App 身份校验

## CHECK-1：静态分析

扫描本次范围内各模块的生产 `.ets` 文件，排除构建产物、缓存和第三方依赖。使用 `rg -n -g '*.ets'` 定位候选，再读取上下文确认；注释、字符串和普通同名标识符不作为违规。

### 通用检查（6 项）

| 检查项 | 定位与复核方式 | 级别 | 说明 |
|--------|---------------|------|------|
| `any` 类型 | 搜索 `\bany\b`，确认是否为类型用法 | ERROR | ArkTS 强类型要求，不允许使用 any |
| 旧 `@ohos.*` 导入 | 搜索 `@ohos\.`，确认 import 来源，列出迁移建议 | WARN | API 版本迁移建议 |
| SQL 拼接 | 搜索 SQL 关键字与数据库执行调用，复核是否通过字符串拼接构造 SQL | ERROR | SQL 注入风险 |
| `as` 类型断言 | 搜索 `\bas\b`，确认断言用法 | WARN | 类型安全警告 |
| `eval()` | 搜索 `\beval\s*\(`，确认动态执行调用 | ERROR | 动态执行风险 |
| `aboutToAppear` 中获取路由参数 | 定位 `aboutToAppear` 方法，复核其中的 `pathInfo` 参数读取 | ERROR | 生命周期错误用法 |

### iOS 特有检查（9 项）

详见 [iOS 特有检查规则](ios-specific-checks.md)。

| 检查项 | 定位与复核方式 | 级别 | iOS 上下文 |
|--------|---------------|------|-----------|
| 强制解包 `!` | 搜索 `\w+!\.` 或 `\w+!\s*$`，确认强制解包 | WARN | Swift 可选值强制解包，可能导致运行时崩溃 |
| `@escaping` 闭包 | 搜索 `@escaping`，复核是否已正确转换 | WARN | Swift 闭包逃逸标记，ArkTS 不需要 |
| `weak`/`unowned` | 搜索 `\bweak\b` / `\bunowned\b`，确认是否为内存管理关键字 | WARN | Swift 内存管理，ArkTS 自动管理 |
| `@objc` / `@objcMembers` | 搜索 `@objc`，确认是否为 Objective-C 互操作标记 | WARN | Swift 与 OC 互操作，迁移遗留 |
| `#available` / `@available` | 搜索 `available`，确认是否为版本检查 | WARN | iOS 版本检查，HarmonyOS 不适用 |
| `DispatchQueue` | 搜索 `DispatchQueue`，确认是否为 GCD 调度 | ERROR | 必须改为 ArkTS 并发（TaskPool/Worker）|
| `NotificationCenter` | 搜索 `NotificationCenter`，确认是否为通知中心 | WARN | 需改为 Emitter 事件机制 |
| `UserDefaults` | 搜索 `UserDefaults`，确认是否为本地存储 | ERROR | 必须改为 Preferences |
| `UIKit` / `SwiftUI` 导入 | 搜索 `import UIKit` / `import SwiftUI`，确认导入语句 | ERROR | iOS UI 框架，迁移未完成 |

### 执行方式

对每项检查：

1. **定位候选**：使用 `rg -n -g '*.ets'` 搜索关键字
2. **读取上下文**：读取匹配行前后 3-5 行，确认实际用法
3. **排除误报**：
   - 注释中的匹配 → 不计
   - 字符串中的匹配 → 不计（除非是 import 语句）
   - 普通标识符同名 → 复核后确认
4. **记录违规**：记录文件路径、行号、规则名称、简短依据

### 输出格式

每个有效命中记录：

```
{
  "file": "entry/src/main/ets/pages/HomeView.ets",
  "line": 42,
  "rule": "IOS.FORCE_UNWRAP",
  "level": "WARN",
  "snippet": "let name = user!.name",
  "reason": "使用强制解包 !，可能导致运行时崩溃"
}
```

### 判定规则

- **ERROR 为 0** → CHECK-1 **PASS**
- **有 ERROR** → CHECK-1 **FAIL**
- **仅有 WARN** → CHECK-1 **PASS**，附 WARN 报告

WARN 只附报告，不单独触发修复回环。没有找到应验证的源码时记录输入缺口，不能以零命中判 PASS。

---

## CHECK-2：App 身份校验

读取 iOS 源码的 `Info.plist` 和 HarmonyOS 的 `AppScope/app.json5`、模块配置及实际引用的字符串/图标资源；名称以 **init 锁定的 `.migbot/config.json` 的 `app_name`（即 ArkTS 应用显示名）** 为依据（名称修改权已锁定前移到 init；无 `.migbot/config.json` 或 `app_name` 为空时才回退项目已有 Spec 中的 App 名称）。

### 检查项

| 项目 | 检查规则 | 判定 | iOS 数据源 | HarmonyOS 数据源 |
|------|---------|------|-----------|----------------|
| bundleName | 仍匹配 `com.example.*` | FAIL | `CFBundleIdentifier` | `app.json5` bundleName |
| vendor | 仍为 `example` | FAIL | - | `app.json5` vendor |
| versionName | 与 iOS 版本不一致 | WARN | `CFBundleShortVersionString` | `app.json5` versionName |
| versionCode | 与 iOS 版本号不一致 | WARN | `CFBundleVersion` | `app.json5` versionCode |
| app_name | 与锁定名称不一致 | FAIL | `CFBundleDisplayName` | string.json label |
| 应用图标 | 不存在或引用错误 | FAIL | `Assets.xcassets/AppIcon` | layered-image.json |
| 图标尺寸 | 前景/背景图 ≤ 1 KB | WARN | - | PNG 文件大小 |

### iOS 配置读取

#### Info.plist 解析

使用 Python `plistlib`（标准库）解析 `Info.plist`：

```python
import plistlib
from pathlib import Path

def read_ios_info_plist(ios_project_root):
    """读取 iOS Info.plist"""
    info_plist_path = Path(ios_project_root) / "Info.plist"
    
    # 尝试多个可能的位置
    if not info_plist_path.exists():
        # 尝试 <Project>/<Project>/Info.plist
        project_name = Path(ios_project_root).name
        info_plist_path = Path(ios_project_root) / project_name / "Info.plist"
    
    if not info_plist_path.exists():
        return None, "Info.plist not found"
    
    try:
        with open(info_plist_path, 'rb') as f:
            plist_data = plistlib.load(f)
        
        return {
            'bundle_id': plist_data.get('CFBundleIdentifier', ''),
            'display_name': plist_data.get('CFBundleDisplayName', plist_data.get('CFBundleName', '')),
            'version': plist_data.get('CFBundleShortVersionString', ''),
            'build': plist_data.get('CFBundleVersion', '')
        }, None
    except Exception as e:
        return None, f"Failed to parse Info.plist: {e}"
```

**支持格式**：
- ✅ XML 格式（默认）
- ✅ Binary 格式（plistlib 自动识别）

#### Assets.xcassets 解析

解析 `Assets.xcassets/AppIcon.appiconset/Contents.json`：

```python
import json

def read_ios_app_icon(ios_project_root):
    """读取 iOS 应用图标信息"""
    # 查找 Assets.xcassets
    assets_path = Path(ios_project_root).rglob("Assets.xcassets")
    
    for asset_dir in assets_path:
        appicon_path = asset_dir / "AppIcon.appiconset" / "Contents.json"
        
        if appicon_path.exists():
            try:
                with open(appicon_path) as f:
                    contents = json.load(f)
                
                images = contents.get('images', [])
                icon_files = []
                
                for img in images:
                    filename = img.get('filename')
                    if filename:
                        icon_files.append({
                            'filename': filename,
                            'size': img.get('size', ''),
                            'scale': img.get('scale', ''),
                            'idiom': img.get('idiom', '')
                        })
                
                return icon_files, None
            except Exception as e:
                return None, f"Failed to parse Contents.json: {e}"
    
    return None, "AppIcon.appiconset not found"
```

### HarmonyOS 配置读取

#### app.json5 解析

```python
import json5  # 或使用 hjson
from pathlib import Path

def read_harmonyos_app_config(harmonyos_root):
    """读取 HarmonyOS app.json5"""
    app_json5 = Path(harmonyos_root) / "AppScope" / "app.json5"
    
    if not app_json5.exists():
        return None, "app.json5 not found"
    
    try:
        with open(app_json5) as f:
            # 简单处理：移除注释后用 json 解析
            content = f.read()
            # 移除单行注释
            lines = [line for line in content.split('\n') 
                    if not line.strip().startswith('//')]
            clean_content = '\n'.join(lines)
            
            data = json.loads(clean_content)
            app = data.get('app', {})
            
            return {
                'bundle_name': app.get('bundleName', ''),
                'vendor': app.get('vendor', ''),
                'version_name': app.get('versionName', ''),
                'version_code': app.get('versionCode', 0)
            }, None
    except Exception as e:
        return None, f"Failed to parse app.json5: {e}"
```

#### 应用名称读取

```python
def read_harmonyos_app_name(harmonyos_root):
    """读取 HarmonyOS 应用显示名称"""
    # 读取 module.json5 获取 label 资源 ID
    module_json5 = Path(harmonyos_root) / "entry" / "src" / "main" / "module.json5"
    
    if not module_json5.exists():
        return None, "module.json5 not found"
    
    with open(module_json5) as f:
        content = f.read()
        lines = [line for line in content.split('\n') 
                if not line.strip().startswith('//')]
        clean_content = '\n'.join(lines)
        module_data = json.loads(clean_content)
    
    label_id = module_data.get('module', {}).get('label', '')
    
    # 解析资源 ID，如 $string:app_name
    if label_id.startswith('$string:'):
        string_key = label_id.replace('$string:', '')
        
        # 读取 string.json
        string_json = Path(harmonyos_root) / "entry" / "src" / "main" / "resources" / "base" / "element" / "string.json"
        
        if string_json.exists():
            with open(string_json) as f:
                string_data = json.load(f)
                
            for item in string_data.get('string', []):
                if item.get('name') == string_key:
                    return item.get('value', ''), None
    
    return None, "Failed to resolve app name"
```

#### 图标检查

```python
def check_harmonyos_icon(harmonyos_root):
    """检查 HarmonyOS 应用图标"""
    # 检查 layered-image.json
    layered_image = Path(harmonyos_root) / "AppScope" / "resources" / "base" / "media" / "layered-image.json"
    
    if not layered_image.exists():
        return None, "layered-image.json not found"
    
    try:
        with open(layered_image) as f:
            data = json.load(f)
        
        foreground = data.get('foreground', '')
        background = data.get('background', '')
        
        # 检查引用的文件是否存在
        media_dir = layered_image.parent
        
        foreground_file = media_dir / foreground
        background_file = media_dir / background
        
        results = {
            'foreground': {
                'exists': foreground_file.exists(),
                'size': foreground_file.stat().st_size if foreground_file.exists() else 0
            },
            'background': {
                'exists': background_file.exists(),
                'size': background_file.stat().st_size if background_file.exists() else 0
            }
        }
        
        return results, None
    except Exception as e:
        return None, f"Failed to check icon: {e}"
```

### 比对逻辑

```python
def check_app_identity(ios_root, harmonyos_root, locked_app_name=None):
    """执行 App 身份校验"""
    issues = []
    
    # 1. 读取 iOS 配置
    ios_info, error = read_ios_info_plist(ios_root)
    if error:
        issues.append({
            'level': 'DEFERRED',
            'item': 'iOS Info.plist',
            'message': error
        })
        return issues
    
    # 2. 读取 HarmonyOS 配置
    hos_config, error = read_harmonyos_app_config(harmonyos_root)
    if error:
        issues.append({
            'level': 'FAIL',
            'item': 'HarmonyOS app.json5',
            'message': error
        })
        return issues
    
    # 3. 检查 bundleName
    if hos_config['bundle_name'].startswith('com.example.'):
        issues.append({
            'level': 'FAIL',
            'item': 'bundleName',
            'message': f"仍为示例值: {hos_config['bundle_name']}",
            'ios_value': ios_info['bundle_id'],
            'expected': ios_info['bundle_id']
        })
    
    # 4. 检查 vendor
    if hos_config['vendor'] == 'example':
        issues.append({
            'level': 'FAIL',
            'item': 'vendor',
            'message': "仍为示例值: example"
        })
    
    # 5. 检查版本
    if hos_config['version_name'] != ios_info['version']:
        issues.append({
            'level': 'WARN',
            'item': 'versionName',
            'message': f"与 iOS 版本不一致",
            'ios_value': ios_info['version'],
            'hos_value': hos_config['version_name']
        })
    
    # 6. 检查应用名称
    hos_app_name, error = read_harmonyos_app_name(harmonyos_root)
    if not error:
        # 优先使用锁定名称
        expected_name = locked_app_name or ios_info['display_name']
        if hos_app_name != expected_name:
            issues.append({
                'level': 'FAIL',
                'item': 'app_name',
                'message': "与锁定名称不一致",
                'expected': expected_name,
                'actual': hos_app_name
            })
    
    # 7. 检查图标
    icon_info, error = check_harmonyos_icon(harmonyos_root)
    if error:
        issues.append({
            'level': 'FAIL',
            'item': 'app_icon',
            'message': error
        })
    elif icon_info:
        if not icon_info['foreground']['exists']:
            issues.append({
                'level': 'FAIL',
                'item': 'foreground_icon',
                'message': "前景图标文件不存在"
            })
        elif icon_info['foreground']['size'] <= 1024:
            issues.append({
                'level': 'WARN',
                'item': 'foreground_icon',
                'message': f"前景图标过小 ({icon_info['foreground']['size']} bytes)，疑似默认图"
            })
        
        if not icon_info['background']['exists']:
            issues.append({
                'level': 'FAIL',
                'item': 'background_icon',
                'message': "背景图标文件不存在"
            })
        elif icon_info['background']['size'] <= 1024:
            issues.append({
                'level': 'WARN',
                'item': 'background_icon',
                'message': f"背景图标过小 ({icon_info['background']['size']} bytes)，疑似默认图"
            })
    
    return issues
```

### 判定规则

- **有明确 FAIL** → CHECK-2 **FAIL**
- **仅因缺失输入无法完成必要判断** → CHECK-2 **PARTIAL/DEFERRED**
- **其余** → CHECK-2 **PASS**，附 WARN 和不适用项说明

路径与资源名按当前工程解析，避免把示例文件名当作唯一合法配置。未记录预期 App 名称（无锁定值且 Spec 未记录）时注明未做名称一致性比较；无法读取必要配置或资源时记录相应缺口。

---

## 实现脚本

建议实现以下脚本：

| 脚本 | 作用 | 优先级 |
|------|------|--------|
| `scripts/ios_static_analyzer.py` | 执行 15 项静态分析 | ⭐⭐⭐⭐⭐ |
| `scripts/ios_config_parser.py` | 解析 iOS Info.plist 和 Assets | ⭐⭐⭐⭐⭐ |
| `scripts/ios_icon_checker.py` | 检查图标文件 | ⭐⭐⭐⭐ |
| `scripts/check_app_identity.py` | 完整身份校验流程 | ⭐⭐⭐⭐⭐ |

---

**版本**: v1.0  
**创建时间**: 2024-11-03  
**作者**: 模型 Opus 5.5
