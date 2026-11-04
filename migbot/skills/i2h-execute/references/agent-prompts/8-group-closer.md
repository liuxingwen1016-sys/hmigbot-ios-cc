# Agent 派发 Prompt — Group Closer

> 派发前必读: `_common.md` + 本文件

---

## 任务目标

完成一个 Group 的收尾工作，包括跨文件接线、资源 sweep、结构 fix-forward、产出 writeback manifest。

---

## 输入上下文

```json
{
  "group_id": "group-001",
  "slices": ["slice-001", "slice-002", "slice-003"],
  "slice_briefs": [
    "spec/execution/briefs/stage3-slice-001-brief.md",
    "spec/execution/briefs/stage3-slice-002-brief.md",
    "spec/execution/briefs/stage3-slice-003-brief.md"
  ]
}
```

---

## 执行步骤

### Step 1: 跨文件接线

**检查跨 Slice 依赖**:

```typescript
// Slice 1 定义接口
// entry/src/main/ets/interfaces/ISearchService.ets
export interface ISearchService {
  search(keyword: string): Promise<SearchResult[]>;
}

// Slice 2 使用接口（占位符）
class HomeViewModel {
  private searchService: ISearchService;
  
  // PLACEHOLDER: SLICE-3 | 搜索服务 | 等待 Slice 3 实现
  async search(keyword: string): Promise<void> {
    throw new Error('PLACEHOLDER: SLICE-3');
  }
}

// Slice 3 实现接口
export class SearchService implements ISearchService {
  async search(keyword: string): Promise<SearchResult[]> {
    // 实现
  }
}

// Group Closer: 连接
class HomeViewModel {
  private searchService: ISearchService = new SearchService();  // ✅ 接线完成
  
  async search(keyword: string): Promise<void> {
    const results = await this.searchService.search(keyword);
    this.searchResults = results;
  }
}
```

### Step 2: 资源 Sweep

与 batch-closer 相同，调用 `sweep_resources.py`。

### Step 3: 结构 fix-forward（关键）

**Group closer 内部调用结构审计**:

```bash
# 调用 arkts-structural-closure
Skill({
  skill: "arkts-structural-closure",
  args: "mode=group target=${groupId}"
})
```

**Fix-forward 循环**（最多 3 轮）:

```
轮次 1:
├─ 调用 arkts-structural-closure
├─ 获取 FAIL 列表
├─ 自动修复（如果是已知问题）
└─ 重新审计

轮次 2:
├─ 调用 arkts-structural-closure
├─ FAIL 减少 → 继续
└─ FAIL 不减少 → STALLED

轮次 3:
├─ 调用 arkts-structural-closure
├─ CONVERGED → 成功
└─ 其他状态 → 冒泡到主线程
```

**已知问题自动修复**:

```typescript
// 问题 1: 缺少导入
// 修复: 自动添加 import

// 问题 2: 类型不匹配
// 修复: 添加类型转换

// 问题 3: 占位符应该回填
// 修复: 检查是否有对应实现，回填
```

### Step 4: 产出 Writeback Manifest

```json
{
  "group_id": "group-001",
  "operations": [
    {
      "type": "modify",
      "file": "entry/src/main/ets/viewmodels/HomeViewModel.ets",
      "changes": [
        {
          "line_range": [15, 18],
          "old_content": "throw new Error('PLACEHOLDER: SLICE-3');",
          "new_content": "const results = await this.searchService.search(keyword);\nthis.searchResults = results;"
        }
      ]
    }
  ],
  "structural_closure": {
    "final_state": "CONVERGED",
    "iterations": 2,
    "initial_fails": 5,
    "final_fails": 0
  }
}
```

### Step 5: 生成 Brief

```markdown
# Brief: Group-001 收尾

## 任务信息
- Group ID: group-001
- Slices: 3 个
- Worker: group-closer
- Status: PASS

## 跨文件接线
- HomeViewModel ←→ SearchService: ✅ 已连接
- ProfileViewModel ←→ UserService: ✅ 已连接

## 资源 Sweep
- 转换: 8 个
- 失败: 0 个

## 结构 Fix-Forward
- 初始 FAIL: 5 个
- 轮次 1: 5 → 2
- 轮次 2: 2 → 0
- 最终状态: CONVERGED

## Writeback Manifest
- 文件: spec/execution/writeback/group-001-writeback.json
- 操作数: 3 个

## 下一步
- 主线程应用 writeback
- 进入下一个 Group
```

---

## 质量检查清单

- [ ] 跨文件接线已完成
- [ ] 资源 sweep 已执行
- [ ] 结构审计已收敛
- [ ] Writeback manifest 已生成
- [ ] Brief 完整

---

**版本**: 1.0  
**更新时间**: 2024-11-03  
**适用**: Stage 3 Group 收尾
