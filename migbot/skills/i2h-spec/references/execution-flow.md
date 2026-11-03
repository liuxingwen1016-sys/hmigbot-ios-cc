<!-- when: 开始执行 i2h-spec 时加载，理解完整执行流程 -->
<!-- topics: 执行流程、阶段衔接、降级处理、并行策略 -->

# i2h-spec 执行流程详解

## 1. 总体流程

```
启动检查
  ↓
前置检查（.migbot/config.json）
  ↓
智能路由（baseline 存在性判断）
  ↓
Phase A: 数据准备（确定性提取 + 语义分析）
  ├─ Step A1: 扫描项目结构
  ├─ Step A2: 逐页详细分析（骨架 + 语义）
  ├─ Step A3: Info.plist 和权限分析
  └─ Step A4: 输出 Phase A 报告
  ↓
Gate A（自动）
  ↓
Phase B: UI 清单生成
  ├─ Step B1: 生成 ui-manifest.md
  ├─ Step B2: 生成分页 UI Spec（逐页或批量）
  └─ Step B3: UI 覆盖率审计
  ↓
Gate B（可选确认）
  ↓
Phase C: 功能 Spec 生成
  ├─ Step C1: 分析功能模块
  ├─ Step C2: 生成 feature-index.md
  ├─ Step C3: 生成分功能 Spec
  └─ Step C4: 功能覆盖率审计
  ↓
Gate C（可选确认）
  ↓
完成门禁（SPEC-COMPLETE）
  ↓
完成标记 + 最终报告
```

## 2. Phase A 详细流程

### Step A1: 扫描项目结构

**输入**: `$IOS_PATH`（iOS 项目根目录）

**执行逻辑**:

```
1. 检查是否存在 ios-project-scanner skill
   ├─ 存在 → 调用 Python 脚本
   │   ├─ 成功 → 读取 project-skeleton.json 骨架
   │   └─ 失败 → 降级到 LLM 扫描
   └─ 不存在 → LLM 直接扫描

2. LLM 扫描（降级或主流程）
   ├─ 扫描目录，识别 .xcodeproj
   ├─ 查找所有 .swift 文件
   ├─ 识别 SwiftUI View（struct XXX: View）
   ├─ 识别 UIKit ViewController（: UIViewController）
   ├─ 定位 Info.plist
   └─ 定位 Assets.xcassets

3. LLM 补充语义（必做）
   ├─ 为每个 View/ViewController 推断用途
   ├─ 评估复杂度（simple/medium/complex/very_complex）
   ├─ 识别依赖关系
   └─ 确定导航角色

4. 生成 project-skeleton.json
   ├─ 确定性字段（脚本提取或 LLM 扫描）
   └─ 语义字段（LLM 补充）

5. 验证产出
   ├─ 文件路径存在性检查
   ├─ 至少有 1 个 View/ViewController
   └─ 必填字段非空
```

**产出**: `spec/.i2h/project-skeleton.json`

**Confidence**:
- 脚本提取 + LLM 验证 → `high`
- LLM 直接扫描 → `medium`

### Step A2: 逐页详细分析

**输入**: `project-skeleton.json` 中的页面列表

**执行逻辑（对每个页面）**:

```
1. 为页面分配 page_id（page_0001, page_0002, ...）

2. 确定性提取（脚本优先）
   ├─ 检查是否存在 ios-view-analyzer skill
   ├─ 存在 → 调用脚本提取骨架
   │   ├─ 属性列表（@State, @Binding, ...）
   │   ├─ 属性类型和默认值
   │   ├─ body 源码
   │   └─ 依赖的自定义组件
   └─ 不存在/失败 → 降级到 LLM

3. LLM 阅读源码（必做）
   ├─ Read 完整源文件（不能只看摘要）
   ├─ 分析 UI 结构
   │   ├─ 主容器类型（VStack/HStack/List）
   │   ├─ 布局层次（嵌套深度）
   │   └─ 关键组件（Button/TextField/...）
   ├─ 分析状态管理
   │   ├─ 状态变量用途
   │   ├─ 数据流方向
   │   └─ 外部依赖（Store/Service）
   ├─ 分析交互行为
   │   ├─ 按钮动作
   │   ├─ 导航目标
   │   └─ 表单操作
   └─ 评估转换策略
       ├─ 适用转换器
       ├─ 预估自动转换率
       └─ 人工调整项

4. 映射到 HarmonyOS
   ├─ 使用 ios-to-harmonyos-mapping.md
   ├─ 为每个组件找到对应的 ArkTS 组件
   └─ 评估映射复杂度

5. 生成 meta.json
   ├─ 确定性字段（脚本提取）
   ├─ 语义字段（LLM 补充）
   └─ ios_source_anchors（complex 页面必填）

6. 验证和保存
   ├─ 验证所有文件路径存在
   ├─ 检查必填字段非空
   └─ 保存到 spec/baseline/ui-snapshots/page_NNNN_ClassName/meta.json
```

**产出**: 每个页面一个 `meta.json`

**关键约束**:
- 必须 Read 完整源文件
- complex/very_complex 页面必须填写 ios_source_anchors
- 所有文件路径必须验证存在

### Step A3: Info.plist 分析

**执行逻辑**:

```
1. 定位 Info.plist
   ├─ 从 project-skeleton.json 获取路径
   └─ 或在项目根目录搜索

2. Read Info.plist（XML 或二进制格式）
   ├─ 提取 Bundle ID
   ├─ 提取版本号
   ├─ 提取权限声明
   ├─ 提取 URL Schemes
   └─ 提取后台模式

3. 映射权限到 HarmonyOS
   ├─ 使用 ios-to-harmonyos-mapping.md § 权限映射
   ├─ 为每个 iOS 权限找到对应的鸿蒙权限
   └─ 说明权限用途（通过阅读代码推断）

4. 生成 info-plist-analysis.json
```

**产出**: `spec/.i2h/info-plist-analysis.json`

## 3. Phase B 详细流程

### Step B1: 生成 ui-manifest.md

**执行逻辑**:

```
1. 加载模板
   ├─ MUST READ: templates/ui-manifest-template.md 全文
   └─ 理解所有必需章节

2. 汇总 Phase A 数据
   ├─ 读取 project-skeleton.json
   ├─ 读取所有 meta.json
   └─ 读取 info-plist-analysis.json

3. 生成各章节
   ├─ 全局约定（页面 ID 规则、复杂度标准）
   ├─ SwiftUI Views 清单（表格）
   ├─ UIKit ViewControllers 清单（表格）
   ├─ 页面关系图（导航层次）
   │   ├─ 分析 NavigationLink 目标
   │   ├─ 分析 .sheet 调用
   │   └─ 绘制导航树
   ├─ 状态管理总览
   │   ├─ 统计各种状态管理模式
   │   └─ 识别全局 Store
   ├─ 系统功能使用
   │   ├─ 从 info-plist-analysis.json 获取
   │   └─ 从代码中识别 AVFoundation 等使用
   ├─ 转换批次规划
   │   ├─ 按复杂度和依赖关系分批
   │   └─ 预估每批用时
   ├─ 共享组件
   │   ├─ 识别自定义组件
   │   └─ 统计使用次数
   ├─ 资源清单
   │   ├─ 图片资源
   │   ├─ 颜色资源
   │   └─ 本地化字符串
   └─ 统计摘要

4. 验证完整性
   ├─ 所有必需章节都存在
   ├─ 表格完整，无 TODO
   └─ 页面 ID 命名一致

5. 保存到 spec/baseline/ui-manifest.md
```

**产出**: `spec/baseline/ui-manifest.md`

### Step B2: 生成分页 UI Spec

**执行策略**:

```
可选策略 1: 逐页生成（串行）
  for each page in pages:
    生成 page_NNNN_ClassName.md

可选策略 2: 批量并行（如果支持）
  将页面分成若干批次
  并行生成每批页面的 spec
  
默认: 逐页串行生成（更稳定）
```

**执行逻辑（对每个页面）**:

```
1. 加载模板
   ├─ MUST READ: templates/page-spec-template.md 全文
   └─ 理解所有必填字段

2. 读取页面数据
   ├─ 读取 meta.json
   └─ Read 源文件（再次确认）

3. 生成各章节
   ├─ 基本信息（从 meta.json）
   ├─ ios_source_anchors（complex 页面必填）
   ├─ 页面结构（至少 5 行实质内容）
   │   ├─ 主容器
   │   ├─ UI 层次（绘制树形结构）
   │   └─ 关键组件表格
   ├─ 状态管理
   │   ├─ 状态变量表格
   │   └─ 数据流图
   ├─ 交互行为
   │   ├─ 导航交互表格
   │   ├─ 操作交互表格
   │   └─ 生命周期映射
   ├─ 转换策略
   │   ├─ 选择适用转换器
   │   ├─ 预估转换率
   │   └─ 列出转换难点
   ├─ 依赖关系
   │   ├─ 组件依赖
   │   ├─ 数据依赖
   │   └─ 系统依赖
   ├─ 风险评估
   │   ├─ 技术风险
   │   ├─ 数据迁移风险
   │   └─ 性能风险
   ├─ 占位策略（如需要）
   └─ 验证清单

4. 验证完整性
   ├─ 所有必填字段非空
   ├─ ios_source_anchors 完整（complex 页面）
   ├─ 页面结构非空行 >= 5
   └─ 文件路径已验证存在

5. 保存到 spec/baseline/ui/page_NNNN_ClassName.md
```

**产出**: N 个 `page_NNNN_ClassName.md`

### Step B3: UI 覆盖率审计

**执行逻辑**:

```
1. 读取 project-skeleton.json
   ├─ 获取所有 View/ViewController 列表
   └─ 总数 = N

2. 检查每个页面是否有对应的 page spec
   ├─ 检查 spec/baseline/ui/page_NNNN_ClassName.md 存在
   └─ 已覆盖数 = M

3. 计算覆盖率
   ├─ 覆盖率 = M / N * 100%
   └─ 目标: >= 90%

4. 检查命名一致性
   ├─ meta.json 中的 page_id
   ├─ 文件名中的 page_NNNN
   └─ ui-manifest.md 中的引用

5. 报告 findings
   ├─ 页面 spec 缺失 → SPEC.PAGE_SPEC_MISSING（精确类，blocking）
   ├─ 页面 ID 不一致 → SPEC.PAGE_ID_MISMATCH（精确类，blocking）
   └─ 覆盖率 < 90% → SPEC.UI_COVERAGE_LOW（推断类，warning）
```

## 4. Phase C 详细流程

### Step C1: 分析功能模块

**执行逻辑**:

```
1. 扫描项目目录结构
   ├─ 识别功能划分（Data/Services/Navigation/...）
   └─ 记录每个目录的文件列表

2. 分析关键技术栈
   ├─ 搜索 SwiftData/Core Data 使用 → 数据存储功能
   ├─ 搜索 URLSession 使用 → 网络请求功能
   ├─ 搜索 AVFoundation 使用 → 相机功能
   ├─ 搜索 @AppStorage 使用 → 用户偏好功能
   └─ ...

3. 识别系统集成
   ├─ 从 info-plist-analysis.json 读取权限
   ├─ 推断对应的系统功能
   └─ 从代码中确认实际使用

4. 功能编号分配
   ├─ F001-F099: 核心业务功能
   ├─ F100-F199: 系统集成功能
   └─ F200-F299: 辅助功能

5. 分析依赖关系
   ├─ 功能之间的依赖
   ├─ 功能与页面的依赖
   └─ 绘制依赖图
```

### Step C2: 生成 feature-index.md

**执行逻辑**:

```
1. 加载模板
   ├─ MUST READ: templates/feature-index-template.md 全文
   └─ 理解所有必需章节

2. 生成各章节
   ├─ 功能命名规则
   ├─ 核心业务功能清单（F001-F099）
   ├─ 系统集成功能清单（F100-F199）
   ├─ 辅助功能清单（F200-F299）
   ├─ 功能依赖图（文本或 Mermaid）
   ├─ 复杂度统计
   ├─ 优先级分配（P0/P1/P2/P3）
   ├─ 迁移时间预估
   ├─ 技术栈映射总览
   └─ 风险评估

3. 验证完整性
   ├─ 所有识别的功能都有条目
   ├─ 依赖关系明确
   └─ 复杂度评估完整

4. 保存到 spec/baseline/feature-index.md
```

### Step C3: 生成分功能 Spec

**执行逻辑（对每个功能）**:

```
1. 加载模板
   ├─ MUST READ: templates/feature-spec-template.md 全文
   └─ 理解所有必填字段

2. 分析 iOS 实现
   ├─ Read 相关源文件
   ├─ 理解架构设计
   ├─ 识别核心类和函数
   └─ 提取数据模型

3. 设计 HarmonyOS 方案
   ├─ 使用 ios-to-harmonyos-mapping.md
   ├─ 选择对应的鸿蒙框架
   ├─ 设计实现步骤（至少 5 步）
   └─ 编写代码示例（可运行的 ArkTS 代码）

4. 生成各章节
   ├─ 基本信息
   ├─ ios_source_anchors（high/very_complex 必填）
   ├─ iOS 实现分析（至少 5 行）
   ├─ HarmonyOS 迁移方案（至少 5 行）
   ├─ 实现步骤（至少 5 步）
   ├─ 代码示例（可运行）
   ├─ 数据迁移（如适用）
   ├─ 依赖关系
   ├─ 占位策略
   ├─ 测试策略
   └─ 风险评估

5. 验证完整性
   ├─ 所有必填字段非空
   ├─ 代码示例可运行
   ├─ 实现步骤详细可操作
   └─ 不用 TODO 占位

6. 保存到 spec/baseline/features/feat_XXX_feature_name.md
```

## 5. 门禁处理流程

### 门禁检查通用流程

```
1. 运行 linter（如果存在）
   └─ 收集所有 findings

2. 按类别分类 findings
   ├─ 精确类
   ├─ 推断类
   ├─ 管线类
   └─ 环境类

3. 按类别和 severity 处理
   ├─ 精确类 + blocking → 必须修复（最多 3 次）
   ├─ 推断类 + blocking → 尝试修复 2 次 → 记账放行
   ├─ 管线类 → 记账 + 推到下游
   └─ 环境类 → 尝试降级 → 记账"工具缺口"

4. 判定门禁结果
   ├─ 无 blocking findings → 自动通过
   ├─ 有 blocking 但已记账 → 自动通过
   └─ 有 blocking 且未记账 → 失败（或用户确认）

5. 记录决策
   ├─ 更新 spec/decision-ledger.md
   └─ 更新 spec/.i2h/open-findings.json
```

### 无人值守模式

```
默认行为: 自动按规则处理
  ├─ 无 blocking → 自动通过
  ├─ 有 blocking 已记账 → 自动通过
  └─ 有 blocking 未记账 → 按类别自动处理
      ├─ 精确类 → 修复（最多 3 次）→ 仍失败 → 停止
      └─ 推断类 → 修复（最多 2 次）→ 记账放行
```

### 用户确认模式

```
用户明确要求时启用:
  ├─ 停在 Gate 等待确认
  ├─ 提供 2-4 个具体选项
  ├─ 用户回复编号
  └─ 记录决策（approval_source: user-confirmed）
```

## 6. 降级处理流程

### 脚本不存在或失败

```
检查脚本
  ├─ 不存在 → 直接降级
  └─ 存在
      ├─ 调用脚本
      ├─ 成功 → 使用脚本产出
      └─ 失败
          ├─ 记录失败原因
          ├─ 降级到 LLM
          └─ 记账"工具缺口，已降级"

LLM 降级流程:
  ├─ 执行等价的确定性提取
  ├─ 补充所有语义字段
  ├─ Confidence 标记为 medium
  └─ 继续后续流程
```

### 源文件缺失

```
尝试读取源文件
  ├─ 成功 → 正常分析
  └─ 失败
      ├─ 记录缺失的文件
      ├─ Confidence 标记为 low
      ├─ 在 spec 中添加 TODO（唯一允许的情况）
      └─ 不阻断后续阶段
```

## 7. 并行处理策略（可选）

### Phase A2: 并行分析页面

```
如果支持并行（多个 LLM 线程）:
  ├─ 将页面列表分批（每批 3-5 个）
  ├─ 并行处理每批
  │   └─ 每个线程独立生成 meta.json
  └─ 等待所有批次完成

如果不支持:
  ├─ 串行处理每个页面
  └─ 更稳定，但较慢
```

### Phase B2: 并行生成 page spec

```
同 Phase A2，可选并行策略
```

## 8. 错误恢复机制

### 中断恢复

```
如果 i2h-spec 执行中断:
  ├─ 检查已完成的阶段
  │   ├─ Phase A 完成 → 从 Phase B 继续
  │   ├─ Phase B 完成 → 从 Phase C 继续
  │   └─ Phase C 完成 → 只需生成最终报告
  └─ 读取已生成的产物
      └─ 避免重复工作
```

### 产物损坏

```
如果发现产物格式错误:
  ├─ 尝试修复（重新生成）
  ├─ 最多重试 2 次
  └─ 2 次后仍失败
      ├─ 记账放行
      ├─ Confidence 标记为 low
      └─ 继续后续阶段
```

## 9. 性能优化建议

### 减少重复读取

```
Phase A2 读取的源文件:
  ├─ 缓存在内存/上下文中
  └─ Phase B2 生成 page spec 时复用
```

### 批量操作

```
需要对多个文件执行相同操作时:
  ├─ 尽量批量处理
  └─ 减少工具调用次数
```

### 早期验证

```
生成产物后立即自检:
  ├─ 检查必填字段
  ├─ 验证文件路径
  └─ 发现问题立即修正（而不是等到 Gate）
```

## 10. 质量保证

### 自检清单（每个产物）

```
生成产物后，LLM 自检:
  □ 所有必填字段非空
  □ 文件路径已验证存在
  □ 命名规范一致
  □ 代码示例可运行（如有）
  □ 没有用 TODO 占位（除非源文件缺失）
  □ 页面结构非空行 >= 5（page spec）
  □ 实现步骤 >= 5（feature spec）
```

### 交叉验证

```
Phase B 完成后:
  □ 检查 ui-manifest.md 中的页面 ID
  □ 与 meta.json 中的 page_id 一致
  □ 与文件名一致

Phase C 完成后:
  □ 检查 feature-index.md 中的功能 ID
  □ 与 feature spec 文件名一致
```

### 最终验证

```
Gate: SPEC-COMPLETE 时:
  □ 所有必需文件存在
  □ UI 覆盖率 >= 90%
  □ 功能覆盖率 >= 85%
  □ 无 blocking findings（或已记账）
  □ decision-ledger.md 完整
```
