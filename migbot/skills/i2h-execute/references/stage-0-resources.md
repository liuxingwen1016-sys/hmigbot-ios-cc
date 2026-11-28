# Stage 0 资源校验规则

**用途**: 定义 Stage 0 静态资源事实消费与资源落地规则  
**加载时机**: i2h-execute 启动时，Stage 0 执行前

---

## §1 概述

Stage 0 负责**静态资源事实消费与资源落地**，是执行的前置阶段。

**核心原则**:
- 校验事实并按事实完成目标资源落地
- 不重新推导资源值
- 不凭残留文件切换模式

**HARD-GATE**: 资源闭包可解析或显式登记，且保真检查通过，才能进入 Stage 1

---

## §2 执行模式

### 模式选择

通过 `.migbot/bin/i2h execute-inputs` 命令指定：

1. **static-v1** (默认，推荐)
   - 读取 `spec/.i2h/target-input.json`
   - 读取 canonical `spec/baseline/res-index/`
   - 读取 `spec/baseline/ui-delivery-approved.json` 批准范围
   - 执行静态事实校验

2. **legacy** (兼容模式)
   - 通过 `--resource-policy legacy` 显式选择
   - 仍需 `spec/baseline/ui-delivery-approved.json` 确认批准范围
   - 扫描已审批 UI/Feature Spec 及源码中的资源引用
   - 批量落地资源

---

## §3 static-v1 模式执行流程

### Step 1: 校验 target-input.json

**位置**: `spec/.i2h/target-input.json`

**校验内容**:
1. 文件存在性
2. Schema 版本 = 1
3. target_input_sha256 (64位hex)
4. inventory 路径有效

**实际格式** (由 ui_evidence.py 生成):
```json
{
  "schema_version": 1,
  "producer": "ui_evidence.py",
  "timestamp": "2024-11-26T10:00:00Z",
  "target_input_sha256": "abc123...",
  "inventory": "spec/.i2h/resources-inventory.json",
  "locale": "zh_CN",
  "font_family": "HarmonyOS Sans",
  "theme": "light"
}
```

### Step 2: 校验 resources-inventory.json

**位置**: 由 target-input.json 中的 `inventory` 字段指定

**校验内容**:
- 文件存在性
- `target_input_sha256` 与 target-input.json 一致
- `project_root` 与 `.migbot/config.json` 的 `ios` 字段解析后一致

### Step 3: 校验 res-index 文件

**位置**: `spec/baseline/res-index/`

**必须文件**:
- `values.json` — 字符串、颜色、尺寸等值资源
- `drawables.json` — 图片资源
- `usage.json` — 资源引用关系
- `handoff.json` — 资源交接清单
- `design-tokens.json` — 设计 token（可选）

**校验内容**:
- 文件存在性
- 每个文件的 `schema_version` = 1
- 每个文件的 `target_input_sha256` 与 target-input.json 一致

**values.json 示例**:
```json
{
  "schema_version": 1,
  "target_input_sha256": "abc123...",
  "strings": [
    {
      "name": "app_name",
      "value": "我的应用",
      "source_ref": "iOS:Info.plist/CFBundleDisplayName"
    }
  ],
  "colors": [
    {
      "name": "primary",
      "value": "#007AFF",
      "source_ref": "iOS:Assets.xcassets/Colors/primary"
    }
  ]
}
```

### Step 3: 校验 ui-delivery-approved.json

**位置**: `spec/baseline/ui-delivery-approved.json`

**校验内容**:
- 文件存在性（static-v1 和 legacy 都要求）
- `schema_version` = 2
- `status` = "approved"
- `target_input_sha256` 与 target-input.json 一致
- `source_project_root` 与 `.migbot/config.json` 的 `ios` 字段解析后一致
- `units` 数组存在且非空

**格式示例**:
```json
{
  "schema_version": 2,
  "status": "approved",
  "scope": "full_ui",
  "target_input_sha256": "abc123...",
  "source_project_root": "/path/to/ios/project",
  "approval": {
    "timestamp": "2024-11-26T10:00:00Z",
    "confirmation_ref": "user:developer"
  },
  "units": [
    {
      "unit_id": "home_screen",
      "page_id": "HomeView",
      "required": true,
      "source_refs": [
        {
          "file": "HomeView.swift",
          "line": 10,
          "sha256": "def456..."
        }
      ],
      "output": {
        "file": "entry/src/main/ets/pages/HomeView.ets",
        "symbol": "HomeView"
      }
    }
  ]
}
```

### Step 4: 校验 Gate B（资源闭包）

**Gate B**: 资源闭包校验门

**检查内容**:
- 读取 `usage.json` 中的 `resources` 数组
- 对于 `ui-delivery-approved.json` 中 `units` 的 `source_refs` 指向的文件：
  - 检查该文件中引用的资源是否有 `disposition: "unresolved"` 或 `resolved: false`
  - 如果有未解决的资源，标记为 BLOCKED
- 其他未选中源文件中的未解决资源：诊断保留但不全局阻断

**blocking 条件**:
- 批准范围内的源文件引用了未解决的资源

### Step 5: 形成资源闭包

**资源闭包**: 批准范围内代码引用的资源集合

**收集方式**:
- 从 `usage.json` 读取资源引用
- 过滤出批准 `units` 的 `source_refs` 文件中的引用
- 保留 locale、font_family、theme 等事实指针
- 不重新推导资源值

### Step 5: 资源落地

**目标**: 将已验证的资源事实转换为 HarmonyOS 格式并写入目标目录

**输出位置**: `entry/src/main/resources/`

**转换内容**:
1. **图片资源** → `base/media/`
2. **颜色资源** → `base/element/color.json`
3. **字符串资源** → `zh_CN/element/string.json` (或其他 locale)
4. **尺寸资源** → `base/element/float.json`

**执行方式**:
- 读取已验证的 res-index (values/drawables/usage/handoff)
- 按照 locale、font_family、theme 事实指针确定输出格式
- 保留 target_input_sha256 绑定
- 不重新推导资源值

**硬门**:
- 所有批准范围内的必需资源必须完成转换
- 转换后的资源必须通过保真检查
- 未解决的普通资源（image/color/localization）阻断进入 Stage 1
- 系统符号映射义务记录但不阻断（后续映射）

### Step 6: SVG/资源保真检查

**检查内容**:
1. 图片尺寸是否保真
2. 颜色值是否准确
3. 字符串是否完整

**SVG 检查**:
- SVG 文件格式正确
- 尺寸比例保持
- 颜色值一致

### Step 7: 资源占位登记（HARD-GATE）

**强制校验**: 每个 `MISSING_xxx`、fallback 资产、`[TODO: translate]` 必须在 placeholder-registry.json 中登记

**检查示例**:
```bash
# 检查待翻译字符串
trans_count=$(grep -c '\[TODO: translate\]' entry/src/main/resources/*/element/*.json | \
  awk -F: '{s+=$2} END{print s}')

registry_trans=$(jq '.placeholders | map(select(.kind == "resource-pending-translation")) | length' \
  spec/execution/placeholder-registry.json)

if [ "$trans_count" -ne "$registry_trans" ]; then
  echo "❌ 待翻译资源未全部登记"
  exit 1
fi
```

**必须登记的类型**:
- `MISSING_xxx` — 缺失的资源
- fallback 资产 — 使用默认资源
- `[TODO: translate]` — 待翻译字符串
- `preview-fixture` — 预览用占位资源

---

## §4 资源落地规则

### 4.1 资源映射

**iOS → HarmonyOS 映射表**:

| iOS 资源类型 | iOS 位置 | HarmonyOS 位置 |
|------------|---------|---------------|
| 图片 | Assets.xcassets | base/media/ |
| 颜色 | Colors.xcassets | base/element/color.json |
| 字符串 | Localizable.strings | zh_CN/element/string.json |
| 尺寸 | 代码中的 CGFloat | base/element/float.json |

### 4.2 资源命名

**命名规则**:
- 使用下划线分隔 (snake_case)
- 避免使用特殊字符
- 保持语义清晰

**示例**:
```
iOS: icon-home@2x.png
HarmonyOS: icon_home.png

iOS: primaryColor
HarmonyOS: color_primary
```

### 4.3 资源格式

**图片格式**:
- PNG — 透明图片
- JPG — 照片
- SVG — 矢量图标（推荐）

**颜色格式**:
```json
{
  "color": [
    {
      "name": "primary",
      "value": "#007AFF"
    }
  ]
}
```

**字符串格式**:
```json
{
  "string": [
    {
      "name": "app_name",
      "value": "我的应用"
    }
  ]
}
```

---

## §5 App 身份落地

### 自动调用 arkts-app-identity

**时机**: 资源迁移后、进 Stage 1 前

**调用方式**:
```typescript
Skill({
  skill: "arkts-app-identity",
  args: "scope=dev-identity ios_root=<ios_path> feature_base=spec/baseline/feature-base.md"
})
```

对于 i2h 的最终产物，`dev-identity` 只描述默认的资源迁移权限，不代表可以把模板身份当作验收结果。执行器必须额外读取 iOS `CFBundleIdentifier` / `BUNDLE_PREFIX`，并把它与实际 signing profile 一起登记。

### 落地内容（dev-identity scope）

**只写 dev 安全字段**:
- `app_name` — 应用名称
- `versionName` — 版本名
- `versionCode` — 版本号
- 图标资源 — 应用图标

**不碰的字段**:
- `bundleName` — 与签名强绑定
- `vendor` — 与 AGC 强绑定

**原因**: 
- bundleName/vendor 与签名/AGC 强绑定
- dev 阶段写入会导致签名装机不一致
- 保留脚手架占位，部署期再落地

**i2h 例外与门禁**:
- 如果 signing profile 已与源工程 bundle ID 对齐，i2h 必须在 Stage 0 直接写入真实 `bundleName`、`vendor` 和版本字段，并在 `identity_status=PASS` 时进入 Stage 1。
- 如果 signing profile 仍绑定模板 bundleName，允许保留模板值仅用于诊断或未签名构建，但必须写入 `identity_signing_pending` 阻断项。真实 i2h verify 不得把 `com.example.*` / `vendor=example` 判为 PASS，也不得用 unsigned HAP 代替安装验证。
- `spec/execution/stage0-environment.json` 必须记录 `source_bundle_id`、`target_bundle_name` 和 `signing_profile_bundle_name`，三者不一致时保持 BLOCKED。

### 非阻断策略

**失败处理**:
- 身份字段非编译必需
- 返回非 0 时写迁移报告 WARN
- 不阻断 Stage 1

---

## §6 占位符登记规则

### 必须登记的资源占位符

**类型**:
1. **MISSING_xxx** — 缺失资源
   ```json
   {
     "id": "PH-R001",
     "kind": "resource-pending-asset",
     "file": "entry/src/main/resources/base/media/",
     "name": "MISSING_icon_search",
     "reason": "iOS 资源不存在",
     "status": "open"
   }
   ```

2. **[TODO: translate]** — 待翻译
   ```json
   {
     "id": "PH-R002",
     "kind": "resource-pending-translation",
     "file": "entry/src/main/resources/zh_CN/element/string.json",
     "name": "welcome_message",
     "reason": "等待翻译",
     "status": "open"
   }
   ```

3. **preview-fixture** — 预览占位
   ```json
   {
     "id": "PH-R003",
     "kind": "resource-preview-fixture",
     "file": "entry/src/main/resources/base/media/",
     "name": "preview_avatar",
     "reason": "预览用占位图片",
     "status": "open"
   }
   ```

---

## §7 完成标志

### 输出报告

**位置**: `spec/execution/stage0-resources-report.md`

**包含内容**:
1. target-input hash 验证结果
2. res-index 文件和 hash 验证结果
3. Gate B finding 对账结果
4. 资源闭包统计
5. 目标资源输出统计
6. 保真检查结果
7. placeholder 对账结果
8. §3.0a-bis HARD-GATE 状态

**示例**:
```markdown
# Stage 0 资源落地报告

## target-input 验证
- ✅ 文件存在
- ✅ Schema 正确
- ✅ Hash: abc123...

## res-index 验证
- ✅ values.json (123 个资源)
- ✅ drawables.json (45 个图片)
- ✅ usage.json (89 处引用)
- ✅ Hash 一致

## Gate B 验证
- ✅ 无 blocking finding

## 资源闭包
- 引用资源: 123 个
- 已落地: 120 个
- 缺失登记: 3 个

## 目标资源输出
- 图片: 45 个
- 颜色: 20 个
- 字符串: 58 个

## 保真检查
- ✅ 图片尺寸保真
- ✅ 颜色值准确
- ✅ 字符串完整

## Placeholder 对账
- MISSING: 3 个 (已登记)
- [TODO: translate]: 5 个 (已登记)
- preview-fixture: 2 个 (已登记)

## HARD-GATE 状态
- ✅ PASS
```

---

## §8 常见问题

### Q1: 资源缺失怎么办？

**A**: 
1. 标记为 `MISSING_xxx`
2. 在 placeholder-registry.json 中登记
3. 不阻断执行

### Q2: Gate B 失败怎么办？

**A**: 
1. 检查 blocking finding
2. 解决资源问题
3. 重新校验

### Q3: App 身份落地失败怎么办？

**A**: 
- 非阻断错误
- 写入 WARN 到报告
- 继续执行

### Q4: 资源保真检查失败怎么办？

**A**: 
- 是 HARD-GATE
- 必须修复
- 才能进入 Stage 1
