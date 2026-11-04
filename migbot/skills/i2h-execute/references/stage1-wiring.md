# Stage 1 接线规则

**用途**: 定义 Stage 1 的最小接线规则（S1-W）  
**加载时机**: Stage 1 所有 Batch 完成后

---

## §1 概述

Stage 1 接线（S1-W）是指将转换后的页面连接到 Navigation 导航系统，使页面可以相互跳转。

### 接线目标

- ✅ 所有页面都在 main_pages.json 中注册
- ✅ 所有页面都在 Index.ets Navigation 中注册
- ✅ 页面间的跳转路由已实现
- ✅ 入口页面（首页）已配置

---

## §2 最小接线规则

### 2.1 三要素

**接线完成需要满足三要素**:

1. **页面注册** — 在 main_pages.json 中
2. **路由注册** — 在 Index.ets PageMap 中
3. **跳转实现** — pathStack.pushPath 调用

### 2.2 接线清单

```json
{
  "wiring_manifest": {
    "version": "1.0",
    "pages": [
      {
        "name": "HomePage",
        "registered": true,
        "routed": true,
        "navigations": [
          {
            "from": "HomePage",
            "to": "DetailPage",
            "method": "pushPath",
            "implemented": true
          }
        ]
      }
    ]
  }
}
```

---

## §3 页面注册

### 3.1 main_pages.json

**位置**: `entry/src/main/resources/base/profile/main_pages.json`

**格式**:

```json
{
  "src": [
    "pages/Index",
    "pages/HomePage",
    "pages/ProfilePage",
    "pages/SettingsPage",
    "pages/DetailPage"
  ]
}
```

**规则**:
- Index 必须在第一个
- 页面路径相对于 entry/src/main/ets/
- 不带 .ets 后缀
- 顺序不影响功能（但习惯上入口页面在前）

### 3.2 自动注册

**Batch closer 自动注册**:

```typescript
// Batch closer 内部
const mainPages = {
  src: ['pages/Index']
};

// 添加本 Batch 的页面
for (const page of batch.pages) {
  mainPages.src.push(`pages/${page.name}`);
}

// 合并已有页面（如果存在）
if (fs.existsSync('entry/src/main/resources/base/profile/main_pages.json')) {
  const existing = JSON.parse(fs.readFileSync('...'));
  mainPages.src = [...new Set([...mainPages.src, ...existing.src])];
}

// 写入 writeback manifest
manifest.operations.push({
  type: 'create',
  file: 'entry/src/main/resources/base/profile/main_pages.json',
  content: JSON.stringify(mainPages, null, 2)
});
```

---

## §4 路由注册

### 4.1 Index.ets Navigation

**位置**: `entry/src/main/ets/pages/Index.ets`

**完整示例**:

```typescript
import { HomePage } from './HomePage';
import { ProfilePage } from './ProfilePage';
import { SettingsPage } from './SettingsPage';
import { DetailPage } from './DetailPage';

@Entry
@ComponentV2
struct Index {
  @Local pathStack: NavPathStack = new NavPathStack();

  @Builder
  PageMap(name: string) {
    // 首页
    if (name === 'HomePage') {
      HomePage()
    }
    // 个人中心
    else if (name === 'ProfilePage') {
      ProfilePage()
    }
    // 设置
    else if (name === 'SettingsPage') {
      SettingsPage()
    }
    // 详情页
    else if (name === 'DetailPage') {
      DetailPage()
    }
    // 未知页面
    else {
      Text(`未知页面: ${name}`)
        .fontSize(16)
        .fontColor($r('app.color.error'))
    }
  }

  build() {
    Navigation(this.pathStack) {
      // 默认显示首页
      HomePage()
    }
    .navDestination(this.PageMap)
    .mode(NavigationMode.Stack)
    .hideToolBar(true)
  }
}
```

**关键点**:
- PageMap 是一个 @Builder 函数
- 使用 if-else 映射页面名称到组件
- Navigation 的 navDestination 绑定 PageMap
- 默认显示首页（放在 Navigation 内部）

### 4.2 增量更新

**后续 Batch 增量添加**:

```typescript
// 读取现有 Index.ets
const indexContent = fs.readFileSync('entry/src/main/ets/pages/Index.ets', 'utf-8');

// 添加新的 import
const newImport = `import { ${newPageName} } from './${newPageName}';`;

// 添加到 PageMap
const newRoute = `
    else if (name === '${newPageName}') {
      ${newPageName}()
    }
`;

// 写入 writeback manifest
manifest.operations.push({
  type: 'modify',
  file: 'entry/src/main/ets/pages/Index.ets',
  changes: [
    {
      line_range: [4, 4], // import 位置
      old_content: '',
      new_content: newImport
    },
    {
      line_range: [25, 25], // PageMap 末尾
      old_content: '    // 未知页面',
      new_content: `${newRoute}\n    // 未知页面`
    }
  ]
});
```

---

## §5 跳转实现

### 5.1 页面跳转方法

**pushPath（推荐）**:

```typescript
// 在 ViewModel 中
export class HomeViewModel {
  pathStack: NavPathStack | null = null;

  navigateToDetail(item: BeanRecord): void {
    this.pathStack?.pushPath({
      name: 'DetailPage',
      param: item
    });
  }
}

// 在 Page 中
@Entry
@ComponentV2
export struct HomePage {
  @Local viewModel: HomeViewModel = new HomeViewModel();

  build() {
    NavDestination() {
      // UI 内容
      Button('详情')
        .onClick(() => {
          this.viewModel.navigateToDetail(item);
        })
    }
    .onReady((context: NavDestinationContext) => {
      // 获取 pathStack
      this.viewModel.pathStack = context.pathStack;
    })
  }
}
```

**replacePath（替换）**:

```typescript
// 替换当前页面（不保留历史）
this.pathStack?.replacePath({
  name: 'LoginPage'
});
```

**pop（返回）**:

```typescript
// 返回上一页
this.pathStack?.pop();

// 返回到指定页面
this.pathStack?.popToName('HomePage');
```

### 5.2 参数传递

**传递参数**:

```typescript
// 发送方
this.pathStack?.pushPath({
  name: 'DetailPage',
  param: {
    id: item.id,
    name: item.name
  }
});

// 接收方
@Entry
@ComponentV2
export struct DetailPage {
  @Local itemId: string = '';
  @Local itemName: string = '';

  build() {
    NavDestination() {
      Text(`ID: ${this.itemId}`)
      Text(`Name: ${this.itemName}`)
    }
    .onReady((context: NavDestinationContext) => {
      // 获取参数
      const param = context.pathInfo.param as Record<string, Object>;
      this.itemId = String(param['id']);
      this.itemName = String(param['name']);
    })
  }
}
```

---

## §6 接线验证

### 6.1 S1-R 可达性检查

**调用脚本验证**:

```bash
python3 scripts/stage1_reachability.py \
  --project-root . \
  --wiring-manifest spec/execution/wiring/wiring-manifest.json \
  --output-json spec/execution/stage1_reachability.json
```

**检查内容**:
1. 所有页面都在 main_pages.json 中
2. 所有页面都在 Index.ets PageMap 中
3. 所有跳转的目标页面都存在
4. 入口页面可达

**检查结果**:

```json
{
  "status": "PASS",
  "pages": {
    "HomePage": {"registered": true, "routed": true, "reachable": true},
    "DetailPage": {"registered": true, "routed": true, "reachable": true}
  },
  "unreachable": [],
  "missing_routes": []
}
```

### 6.2 人工验证清单

- [ ] 在 DevEco Studio 中打开项目
- [ ] 编译通过
- [ ] 安装到设备/模拟器
- [ ] 从首页可以导航到其他页面
- [ ] 点击返回按钮可以返回
- [ ] 参数传递正确

---

## §7 Strict Wiring 契约（可选）

### 7.1 严格接线模式

**启用条件**: 用户明确要求严格接线验证

**额外要求**:
1. ✅ 所有跳转必须有对应的返回路径
2. ✅ 参数类型必须匹配
3. ✅ 生命周期方法必须正确处理 pathStack

### 7.2 契约文件

```json
{
  "strict_wiring": {
    "enabled": true,
    "rules": {
      "bidirectional_navigation": true,
      "param_type_check": true,
      "lifecycle_check": true
    }
  }
}
```

---

## §8 常见问题

### Q1: 页面注册了但不显示？

**A**: 检查 Index.ets 的 PageMap 是否包含该页面的路由。

### Q2: 跳转后页面空白？

**A**: 
1. 检查目标页面是否正确导入
2. 检查目标页面的 build() 方法是否有内容
3. 检查是否有运行时错误（查看 DevEco 日志）

### Q3: 参数传递失败？

**A**:
1. 检查参数是否正确传递（pushPath 的 param）
2. 检查接收方是否在 onReady 中获取参数
3. 检查类型转换是否正确（使用 String() / Number()）

### Q4: 返回按钮不工作？

**A**:
1. 检查是否正确获取 pathStack
2. 检查是否调用了 pathStack.pop()
3. 检查 Navigation 是否设置了 mode: Stack

---

## §9 占位符处理

### 9.1 跳转占位符

**Stage 1 可以先用占位符**:

```typescript
// 跳转到尚未实现的页面
navigateToSearch(): void {
  // PLACEHOLDER: SLICE-3 | 搜索页面 | 等待 Slice 3 实现搜索页面
  throw new Error('PLACEHOLDER: SLICE-3');
}
```

**Slice 3 回填**:

```typescript
navigateToSearch(): void {
  this.pathStack?.pushPath({
    name: 'SearchPage',
    param: { keyword: this.searchKeyword }
  });
}
```

---

## §10 EntryAbility 配置

### 10.1 设置入口页面

**位置**: `entry/src/main/ets/entryability/EntryAbility.ets`

```typescript
onWindowStageCreate(windowStage: window.WindowStage): void {
  windowStage.loadContent('pages/Index', (err) => {
    if (err.code) {
      hilog.error(0x0000, 'EntryAbility', 
        `Failed to load content. Cause: ${JSON.stringify(err)}`);
      return;
    }
    hilog.info(0x0000, 'EntryAbility', 'Succeeded in loading content');
  });
}
```

**关键点**:
- loadContent 参数是 'pages/Index'（不带 .ets）
- 这是应用的入口文件
- Index.ets 内部再显示首页（HomePage）

---

**版本**: 1.0  
**更新时间**: 2024-11-03  
**适用**: i2h-execute Stage 1 接线验证
