# Agent 派发 Prompt — Base Worker

> 派发前必读: `_common.md` + 本文件


## 任务目标

实现 Base 层基础设施（Models、Network、Database、Preferences 等）。


## 输入上下文

派发时主线程会提供：

```json
{
  "task_id": "base-001",
  "base_name": "Models",
  "base_spec": "spec/baseline/features/Base-1-Models.md",
  "ios_files": [
    "<ios_project>/Models/BeanRecord.swift",
    "<ios_project>/Models/User.swift"
  ],
  "target_dir": "entry/src/main/ets/models/"
}
```


## Base 层类型

### Base-1: Models (数据模型)

**任务**: 转换 iOS 数据模型为 ArkTS 类

**iOS → ArkTS**:

```typescript
// iOS: struct BeanRecord (Swift)
struct BeanRecord: Codable {
  let id: String
  let name: String
  let createdAt: Date
}

// HarmonyOS: class BeanRecord (ArkTS)
export class BeanRecord {
  id: string = '';
  name: string = '';
  createdAt: Date = new Date();

  constructor() {}

  static fromJSON(json: Record<string, Object>): BeanRecord {
    const obj = new BeanRecord();
    obj.id = String(json['id']);
    obj.name = String(json['name']);
    obj.createdAt = new Date(Number(json['createdAt']));
    return obj;
  }

  toJSON(): Record<string, Object> {
    const json: Record<string, Object> = {};
    json['id'] = this.id;
    json['name'] = this.name;
    json['createdAt'] = this.createdAt.getTime();
    return json;
  }
}
```

**关键点**:
- ✅ 使用 `String()` / `Number()` 转换，不用 `as unknown as`
- ✅ `fromJSON` / `toJSON` 先创建实例再赋值
- ✅ 日期使用 `Date` 类型
- ✅ 导出 `export class`

### Base-2: Database (数据库)

**任务**: 实现关系型数据库封装

**使用 HarmonyOS RDB**:

```typescript
// entry/src/main/ets/database/DatabaseManager.ets
import { relationalStore } from '@kit.ArkData';

export class DatabaseManager {
  private store: relationalStore.RdbStore | null = null;

  async init(context: Context): Promise<void> {
    const config: relationalStore.StoreConfig = {
      name: 'app.db',
      securityLevel: relationalStore.SecurityLevel.S1
    };

    this.store = await relationalStore.getRdbStore(context, config);

    // 创建表并执行幂等升级。CREATE TABLE IF NOT EXISTS 只覆盖首装，不能替代迁移。
    await this.createTables();
    await this.migrateSchema();
  }

  private async createTables(): Promise<void> {
    const sql = `
      CREATE TABLE IF NOT EXISTS beans (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        created_at INTEGER NOT NULL
      )
    `;
    await this.store?.executeSql(sql);
  }

  private async migrateSchema(): Promise<void> {
    // 迁移步骤必须可重复执行。先探测列/版本，再 ALTER TABLE，不能假设旧表已经是最新结构。
    // 生产代码应为每个新增列保留默认值，并在 schema_version 更新后再继续读取新列。
    await this.store?.executeSql(
      'CREATE TABLE IF NOT EXISTS schema_meta (key TEXT PRIMARY KEY, version INTEGER NOT NULL)'
    );
  }

  async count(table: string, keyColumn: string = 'id'): Promise<number> {
    const predicates = new relationalStore.RdbPredicates(table);
    const resultSet = await this.store?.query(predicates, [keyColumn]);
    const count = resultSet?.rowCount ?? 0;
    resultSet?.close();
    return count;
  }

// 迁移实现要求
// - 对旧表逐列探测并使用 ALTER TABLE ... ADD COLUMN ... DEFAULT ...，重复运行必须安全。
// - 不要在通用 count(table) 中固定 query(['id'])。library_metadata 这类表可能只有 key 主键，
//   也可以直接执行 SELECT COUNT(*)，避免二次冷启动因列不存在而误报数据损坏。
// - execute 阶段必须用旧数据库快照覆盖升级一次，再 force-stop/冷启动一次，确认旧数据仍可读。

  async insertBean(bean: BeanRecord): Promise<void> {
    const valueBucket: relationalStore.ValuesBucket = {
      'id': bean.id,
      'name': bean.name,
      'created_at': bean.createdAt.getTime()
    };
    await this.store?.insert('beans', valueBucket);
  }

  async queryBeans(): Promise<BeanRecord[]> {
    const predicates = new relationalStore.RdbPredicates('beans');
    const resultSet = await this.store?.query(predicates, ['id', 'name', 'created_at']);

    const beans: BeanRecord[] = [];
    if (resultSet) {
      while (resultSet.goToNextRow()) {
        const bean = new BeanRecord();
        bean.id = resultSet.getString(resultSet.getColumnIndex('id'));
        bean.name = resultSet.getString(resultSet.getColumnIndex('name'));
        bean.createdAt = new Date(resultSet.getLong(resultSet.getColumnIndex('created_at')));
        beans.push(bean);
      }
      resultSet.close();
    }

    return beans;
  }
}
```

### Base-3: Network (网络请求)

**任务**: 实现网络请求封装

**使用 HarmonyOS HTTP**:

```typescript
// entry/src/main/ets/services/NetworkService.ets
import { http } from '@kit.NetworkKit';

export class NetworkService {
  private baseURL: string = 'https://api.example.com';

  async get<T>(path: string): Promise<T> {
    const request = http.createHttp();

    const response = await request.request(
      `${this.baseURL}${path}`,
      {
        method: http.RequestMethod.GET,
        expectDataType: http.HttpDataType.OBJECT
      }
    );

    request.destroy();

    if (response.responseCode === 200) {
      return response.result as T;
    } else {
      throw new Error(`HTTP ${response.responseCode}: ${response.result}`);
    }
  }

  async post<T>(path: string, data: Object): Promise<T> {
    const request = http.createHttp();

    const response = await request.request(
      `${this.baseURL}${path}`,
      {
        method: http.RequestMethod.POST,
        header: { 'Content-Type': 'application/json' },
        extraData: JSON.stringify(data),
        expectDataType: http.HttpDataType.OBJECT
      }
    );

    request.destroy();

    if (response.responseCode === 200) {
      return response.result as T;
    } else {
      throw new Error(`HTTP ${response.responseCode}: ${response.result}`);
    }
  }
}
```

### Base-4: Events (事件总线)

**任务**: 实现事件总线

```typescript
// entry/src/main/ets/utils/EventBus.ets
type EventCallback = (data?: Object) => void;

export class EventBus {
  private static instance: EventBus;
  private listeners: Map<string, EventCallback[]> = new Map();

  static getInstance(): EventBus {
    if (!EventBus.instance) {
      EventBus.instance = new EventBus();
    }
    return EventBus.instance;
  }

  on(event: string, callback: EventCallback): void {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, []);
    }
    this.listeners.get(event)?.push(callback);
  }

  off(event: string, callback: EventCallback): void {
    const callbacks = this.listeners.get(event);
    if (callbacks) {
      const index = callbacks.indexOf(callback);
      if (index > -1) {
        callbacks.splice(index, 1);
      }
    }
  }

  emit(event: string, data?: Object): void {
    const callbacks = this.listeners.get(event);
    if (callbacks) {
      callbacks.forEach(callback => callback(data));
    }
  }
}
```

### Base-5: Preferences (键值存储)

**任务**: 实现轻量级存储

```typescript
// entry/src/main/ets/services/PreferencesManager.ets
import { preferences } from '@kit.ArkData';

export class PreferencesManager {
  private prefs: preferences.Preferences | null = null;

  async init(context: Context): Promise<void> {
    this.prefs = await preferences.getPreferences(context, 'app_prefs');
  }

  async setString(key: string, value: string): Promise<void> {
    await this.prefs?.put(key, value);
    await this.prefs?.flush();
  }

  async getString(key: string, defaultValue: string = ''): Promise<string> {
    const value = await this.prefs?.get(key, defaultValue);
    return String(value);
  }

  async setNumber(key: string, value: number): Promise<void> {
    await this.prefs?.put(key, value);
    await this.prefs?.flush();
  }

  async getNumber(key: string, defaultValue: number = 0): Promise<number> {
    const value = await this.prefs?.get(key, defaultValue);
    return Number(value);
  }

  async setBoolean(key: string, value: boolean): Promise<void> {
    await this.prefs?.put(key, value);
    await this.prefs?.flush();
  }

  async getBoolean(key: string, defaultValue: boolean = false): Promise<boolean> {
    const value = await this.prefs?.get(key, defaultValue);
    return Boolean(value);
  }

  async remove(key: string): Promise<void> {
    await this.prefs?.delete(key);
    await this.prefs?.flush();
  }

  async clear(): Promise<void> {
    await this.prefs?.clear();
    await this.prefs?.flush();
  }
}
```

### Base-6: 公共组件库

**任务**: 创建可复用的 UI 组件

```typescript
// entry/src/main/ets/components/LoadingDialog.ets
@CustomDialog
export struct LoadingDialog {
  controller: CustomDialogController;
  message: string = '加载中...';

  build() {
    Column() {
      LoadingProgress()
        .width(48)
        .height(48)
        .margin({ bottom: 16 })

      Text(this.message)
        .fontSize(14)
        .fontColor($r('app.color.text_secondary'))
    }
    .padding(24)
    .backgroundColor(Color.White)
    .borderRadius(8)
  }
}

// entry/src/main/ets/components/EmptyView.ets
@Component
export struct EmptyView {
  message: string = '暂无数据';
  @BuilderParam actionBuilder?: () => void;

  build() {
    Column() {
      Image($r('app.media.empty'))
        .width(120)
        .height(120)
        .margin({ bottom: 16 })

      Text(this.message)
        .fontSize(14)
        .fontColor($r('app.color.text_secondary'))
        .margin({ bottom: 16 })

      if (this.actionBuilder) {
        this.actionBuilder()
      }
    }
    .width('100%')
    .padding(24)
    .justifyContent(FlexAlign.Center)
  }
}
```

### Base-7: 编译门

**Base-7 不是 worker 任务**，而是主线程在所有 Base 完成后调用的编译验证：

```bash
# 主线程调用
Skill({
  skill: "hmos-builder",
  args: "--caller i2h-execute --stage-hint stage-2-base-7 --round 1"
})
```


## 执行步骤

### Step 1: 读取 Base Spec

```bash
Read: spec/baseline/features/Base-1-Models.md
```

### Step 2: 读取 iOS 源码

```bash
Read: <ios_project>/Models/BeanRecord.swift
Read: <ios_project>/Models/User.swift
```

### Step 3: 生成 HarmonyOS 代码

根据 Base 类型，按照上述模板生成代码。

### Step 4: 生成 Brief

```markdown
# Brief: Base-1 Models

## 任务信息
- Task ID: base-001
- Base: Base-1 (Models)
- Worker: base-worker
- Status: PASS

## 执行统计
- 开始时间: 2024-11-03T11:00:00Z
- 结束时间: 2024-11-03T11:10:00Z
- 耗时: 10 分钟

## 产出文件
- entry/src/main/ets/models/BeanRecord.ets (新建, 60 行)
- entry/src/main/ets/models/User.ets (新建, 80 行)
- entry/src/main/ets/models/index.ets (新建, 5 行)

## iOS → HarmonyOS 映射
- Swift struct → ArkTS class
- Codable → fromJSON/toJSON
- Date → Date

## 占位符
- 无

## 依赖
- 无（Base 层无依赖）

## 问题和风险
- 无

## 下一步
- 等待其他 Base 完成
- 等待 Base-7 编译门
```


## 质量检查清单

- [ ] 所有 iOS 文件已转换
- [ ] 代码符合 ArkTS 规范
- [ ] 导出语句正确
- [ ] 类型定义完整
- [ ] fromJSON/toJSON 正确实现
- [ ] Brief 完整


