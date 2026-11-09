# 子代理派发 Prompt — Slice Worker

> 派发前必读: `_common.md` + 本文件


## 任务目标

实现一个完整的功能 Slice，包括 UI 补充、ViewModel、数据层接入、页内接线。


## 输入上下文

```json
{
  "task_id": "slice-002",
  "slice_name": "数据加载功能",
  "feature_spec": "spec/baseline/features/F-002-DataLoading.md",
  "group_id": "group-001",
  "steps": ["3a-ui", "3b-viewmodel", "3c-data", "3d-wiring"],
  "dependencies": {
    "base": ["Base-1", "Base-3"],
    "slices": []
  }
}
```


## 执行步骤

Slice worker 分 4 个子步骤执行：

### Step 3a: UI 补充（如需要）

**检查是否需要新 UI**:

```bash
# 读取 feature spec
Read: spec/baseline/features/F-002-DataLoading.md

# 检查是否需要新页面
if (spec.requires_new_page) {
  # 调用 converter
  调用 i2h-view-converter
} else {
  # 使用现有页面
  使用 Stage 1 已生成的页面
}
```

**如果需要新 UI 组件**:

```typescript
// entry/src/main/ets/components/DataList.ets
@ComponentV2
export struct DataList {
  @Param items: BeanRecord[] = [];
  @Param onItemClick: (item: BeanRecord) => void = () => {};

  build() {
    List() {
      ForEach(this.items, (item: BeanRecord) => {
        ListItem() {
          Row() {
            Text(item.name)
              .fontSize(16)
              .fontColor($r('app.color.text_primary'))
            
            Blank()
            
            Text(item.createdAt.toLocaleDateString())
              .fontSize(14)
              .fontColor($r('app.color.text_secondary'))
          }
          .width('100%')
          .padding(16)
        }
        .onClick(() => {
          this.onItemClick(item);
        })
      })
    }
  }
}
```

### Step 3b: ViewModel + 状态管理

**实现 ViewModel**:

```typescript
// entry/src/main/ets/viewmodels/HomeViewModel.ets
import { BeanRecord } from '../models/BeanRecord';
import { NetworkService } from '../services/NetworkService';
import { DatabaseManager } from '../database/DatabaseManager';

@ObservedV2
export class HomeViewModel {
  @Trace items: BeanRecord[] = [];
  @Trace isLoading: boolean = false;
  @Trace errorMessage: string = '';
  
  pathStack: NavPathStack | null = null;
  
  private networkService: NetworkService = new NetworkService();
  private dbManager: DatabaseManager = new DatabaseManager();

  // Slice-2: 数据加载功能
  async loadData(): Promise<void> {
    this.isLoading = true;
    this.errorMessage = '';
    
    try {
      // 1. 先从本地数据库加载
      const localData = await this.dbManager.queryBeans();
      if (localData.length > 0) {
        this.items = localData;
      }

      // 2. 从网络加载最新数据
      const response = await this.networkService.get<{data: Object[]}>(
        '/api/beans'
      );

      // 3. 转换数据
      this.items = response.data.map(json => BeanRecord.fromJSON(json));

      // 4. 更新本地数据库
      for (const item of this.items) {
        await this.dbManager.insertBean(item);
      }
    } catch (error) {
      this.errorMessage = error.message;
    } finally {
      this.isLoading = false;
    }
  }

  // Slice-2: 刷新功能
  async refresh(): Promise<void> {
    await this.loadData();
  }

  // Slice-3: 搜索功能（占位符）
  async search(keyword: string): Promise<void> {
    // PLACEHOLDER: SLICE-3 | 搜索功能 | 等待 Slice 3 实现搜索逻辑
    throw new Error('PLACEHOLDER: SLICE-3');
  }
}
```

### Step 3c: 数据层接入

**Repository 模式**（可选）:

```typescript
// entry/src/main/ets/repositories/BeanRepository.ets
import { BeanRecord } from '../models/BeanRecord';
import { NetworkService } from '../services/NetworkService';
import { DatabaseManager } from '../database/DatabaseManager';

export class BeanRepository {
  private networkService: NetworkService;
  private dbManager: DatabaseManager;

  constructor(networkService: NetworkService, dbManager: DatabaseManager) {
    this.networkService = networkService;
    this.dbManager = dbManager;
  }

  async fetchBeans(): Promise<BeanRecord[]> {
    // 网络请求
    const response = await this.networkService.get<{data: Object[]}>(
      '/api/beans'
    );

    // 转换数据
    const beans = response.data.map(json => BeanRecord.fromJSON(json));

    // 缓存到数据库
    for (const bean of beans) {
      await this.dbManager.insertBean(bean);
    }

    return beans;
  }

  async loadLocalBeans(): Promise<BeanRecord[]> {
    return await this.dbManager.queryBeans();
  }
}
```

**数据流**:

```
UI (HomePage)
  ↓ 调用
ViewModel (HomeViewModel)
  ↓ 调用
Repository (BeanRepository) — 可选
  ↓ 调用
Services (NetworkService + DatabaseManager)
```

### Step 3d: 页内接线

**连接 UI 和 ViewModel**:

```typescript
// entry/src/main/ets/pages/HomePage.ets
import { HomeViewModel } from '../viewmodels/HomeViewModel';
import { DataList } from '../components/DataList';

@Entry
@ComponentV2
export struct HomePage {
  @Local viewModel: HomeViewModel = new HomeViewModel();

  aboutToAppear(): void {
    // Slice-2: 页面加载时获取数据
    this.viewModel.loadData();
  }

  build() {
    NavDestination() {
      Column() {
        // 加载中状态
        if (this.viewModel.isLoading) {
          LoadingProgress()
            .width(48)
            .height(48)
        }
        // 错误状态
        else if (this.viewModel.errorMessage) {
          Column() {
            Text(this.viewModel.errorMessage)
              .fontSize(14)
              .fontColor($r('app.color.error'))
            
            Button('重试')
              .onClick(() => {
                this.viewModel.loadData();
              })
          }
        }
        // 数据列表
        else {
          Refresh({ refreshing: $$this.viewModel.isLoading }) {
            DataList({
              items: this.viewModel.items,
              onItemClick: (item) => {
                // 跳转到详情页
                this.viewModel.pathStack?.pushPath({
                  name: 'DetailPage',
                  param: item
                });
              }
            })
          }
          .onRefreshing(() => {
            this.viewModel.refresh();
          })
        }
      }
      .width('100%')
      .height('100%')
    }
    .title('首页')
    .onReady((context: NavDestinationContext) => {
      this.viewModel.pathStack = context.pathStack;
    })
  }
}
```

**接线完成性验证**:

接线完成需要满足：
1. ✅ UI 事件已绑定到 ViewModel 方法
2. ✅ ViewModel 状态已绑定到 UI（@Trace → UI 更新）
3. ✅ 页面跳转已实现（pathStack）
4. ✅ 生命周期方法已调用


## 占位符回填

**如果本 Slice 回填其他 Slice 的占位符**:

```typescript
// 之前的占位符（Slice 1）
async loadData(): Promise<void> {
  // PLACEHOLDER: SLICE-2 | 数据加载 | 等待 Slice 2 实现
  throw new Error('PLACEHOLDER: SLICE-2');
}

// Slice 2 回填后
async loadData(): Promise<void> {
  this.isLoading = true;
  try {
    const response = await this.networkService.get('/api/beans');
    this.items = response.data.map(json => BeanRecord.fromJSON(json));
  } catch (error) {
    this.errorMessage = error.message;
  } finally {
    this.isLoading = false;
  }
}
```

**记录到 writeback manifest**:

```json
{
  "fills": [
    {
      "placeholder_id": "PH-005",
      "file": "entry/src/main/ets/viewmodels/HomeViewModel.ets",
      "line_range": [32, 35],
      "new_content": "<complete_implementation>"
    }
  ]
}
```


## 生成 Brief

```markdown
# Brief: Slice-002 数据加载功能

## 任务信息
- Task ID: slice-002
- Slice: 数据加载功能
- Group: group-001
- Worker: slice-worker
- Status: PASS

## 执行统计
- 开始时间: 2024-11-03T12:00:00Z
- 结束时间: 2024-11-03T12:20:00Z
- 耗时: 20 分钟

## 执行步骤

### Step 3a: UI 补充
- 状态: SKIP（使用 Stage 1 已有页面）
- 新增组件: DataList.ets (50 行)

### Step 3b: ViewModel
- 状态: PASS
- 修改文件: HomeViewModel.ets (新增 loadData/refresh 方法)
- 代码量: 新增 80 行

### Step 3c: 数据层
- 状态: PASS
- 新增 Repository: BeanRepository.ets (60 行)
- 数据流: UI → ViewModel → Repository → Service

### Step 3d: 页内接线
- 状态: PASS
- 修改文件: HomePage.ets (接线 loadData)
- 接线验证: ✅ 通过

## 产出文件
- entry/src/main/ets/components/DataList.ets (新建, 50 行)
- entry/src/main/ets/repositories/BeanRepository.ets (新建, 60 行)
- entry/src/main/ets/viewmodels/HomeViewModel.ets (修改, +80 行)
- entry/src/main/ets/pages/HomePage.ets (修改, +30 行)

## 占位符
- 回填: 1 个 (PH-005: 数据加载)
- 新增: 1 个 (PH-008: 搜索功能，等待 Slice 3)

## 依赖
- 依赖的 Base: Base-1 (Models), Base-3 (Network), Base-2 (Database)
- 等待的 Slice: Slice-3 (搜索)

## 接线验证
- ✅ aboutToAppear 调用 loadData
- ✅ Refresh 组件绑定 refresh
- ✅ DataList onItemClick 实现
- ✅ 错误处理完整

## 问题和风险
- 无

## 下一步
- 等待 Group Closer 收尾
- 等待 Slice 3 回填搜索功能
```


## 质量检查清单

### Step 3a: UI

- [ ] 新 UI 组件已创建或复用现有
- [ ] UI 符合设计规范
- [ ] 响应式布局正确

### Step 3b: ViewModel

- [ ] 状态属性已声明（@Trace）
- [ ] 业务方法已实现
- [ ] 错误处理完整
- [ ] 加载状态已管理

### Step 3c: 数据层

- [ ] Repository 已创建（如需要）
- [ ] 数据流清晰
- [ ] Service 调用正确
- [ ] 数据转换正确

### Step 3d: 接线

- [ ] UI 事件已绑定
- [ ] 状态已同步
- [ ] 页面跳转已实现
- [ ] 生命周期正确

### 占位符

- [ ] 回填的占位符已移除
- [ ] 新增占位符已登记

### Brief

- [ ] 4 个步骤状态清晰
- [ ] 产出文件完整
- [ ] 接线验证通过


## 常见问题

### Q1: 如何判断是否需要新 UI？

**A**: 读取 feature spec，查看 `requires_new_page` 字段。

### Q2: Repository 是必须的吗？

**A**: 不是。简单场景可以 ViewModel 直接调用 Service。

### Q3: 占位符回填失败怎么办？

**A**: 
- 如果占位符已被其他 Slice 回填，跳过
- 如果占位符不存在，记录到 brief

### Q4: 接线验证不通过怎么办？

**A**: 
- 返回 FAIL
- 在 brief 中详细说明哪个接线点未完成
- 等待修正


