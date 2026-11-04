# Phase 4 规划：外部依赖处理

**日期**: 2024-11-04 00:45  
**状态**: 🚀 开始  
**预估工作量**: 8-12h

---

## 📋 Phase 4 目标

将 Phase 3 完成的脚本集成到 i2h-verify 主流程，处理外部依赖。

---

## 🎯 主要任务

### 1. CHECK-3 集成 ⭐⭐⭐⭐⭐

**现状**: 
- ✅ 5 个脚本已完成（设备检测、截图对比、报告生成）
- ✅ device-verification.md 有完整流程

**任务**:
- 创建主集成脚本 `run_check3.sh`
- 集成设备检测 → 截图 → 对比 → 报告
- 错误处理和状态判定
- 与 SKILL.md 主流程对接

**工作量**: 4-6h

---

### 2. CHECK-4 适配 ⭐⭐⭐⭐

**现状**:
- arkts-ut-verifier 部分支持 iOS
- 需要参数映射

**任务**:
- 创建参数适配脚本
- 跳过 Android Oracle
- 测试框架识别
- 产物读取适配

**工作量**: 2-3h

---

### 3. gate-release 集成 ⭐⭐⭐⭐

**现状**:
- i2h-spec gate-release 已完整支持
- 需要读取和处理

**任务**:
- 读取 `spec/gate-release/verify-focus.json`
- 读取 `spec/.i2h/open-findings.json`
- 扩展验证范围
- 生成核实报告

**工作量**: 2-3h

---

## 📊 详细任务分解

### Task 1: CHECK-3 主集成脚本

**文件**: `scripts/run_check3.sh`

**流程**:
```bash
1. 检测设备可用性
   - iOS 设备（模拟器/真机）
   - HarmonyOS 设备
   
2. 准备截图目录
   - spec/verify/screenshots/ios/
   - spec/verify/screenshots/harmonyos/
   - spec/verify/screenshots/comparison/

3. 读取页面列表
   - 从 ui-manifest.md
   - 从 gate-release (如有)

4. iOS 端截图
   - 使用 xcrun simctl 或 idevicescreenshot
   - 每个页面截图

5. HarmonyOS 端截图
   - 安装应用
   - 启动应用
   - 截图并传输

6. 执行对比
   - 调用 compare_screenshots.py
   - 生成 JSON 结果

7. 生成报告
   - 调用 generate_ui_report.py
   - 生成 Markdown 报告

8. 状态判定
   - 读取平均相似度
   - 返回状态码
```

---

### Task 2: CHECK-4 参数适配

**文件**: `scripts/adapt_check4.py`

**功能**:
```python
def adapt_ut_verifier_params(ios_root, harmonyos_root):
    """
    适配 arkts-ut-verifier 参数
    """
    return {
        'ios_source_root': ios_root,  # 参数名适配
        'harmonyos_root': harmonyos_root,
        'mode': 'verify_fix',
        'skip_oracle': True,
        'test_framework': 'xctest'
    }
```

---

### Task 3: gate-release 读取器

**文件**: `scripts/read_gate_release.py`

**功能**:
```python
def read_gate_release(project_root):
    """
    读取迁移放行项
    """
    # 读取 verify-focus.json
    # 读取 open-findings.json
    # 返回待核实项目
    pass

def expand_verification_scope(base_pages, gate_items):
    """
    扩展验证范围
    """
    # 将放行项涉及的页面加入验证
    pass

def generate_verification_table(gate_items, results):
    """
    生成核实报告表格
    """
    # | 决策 | 类型 | 门禁 | 核实问题 | 结论 | 证据 |
    pass
```

---

## 🔄 集成流程

### 主流程更新

在 SKILL.md 中调用：

```markdown
## CHECK-3：视觉对齐（简化版）

执行脚本：
```bash
bash scripts/run_check3.sh \
  --ios-root /path/to/ios \
  --harmonyos-root /path/to/harmonyos \
  --output spec/verify
```

读取结果：
- spec/verify/ui-comparison.md
- spec/verify/screenshots/comparison/comparison-results.json

状态判定：
- 根据平均相似度和状态码
```

---

## 📝 实施顺序

### 阶段 1: CHECK-3 集成（4-6h）

1. ✅ 创建 run_check3.sh 框架
2. ✅ 实现设备检测部分
3. ✅ 实现截图采集部分
4. ✅ 集成对比和报告
5. ✅ 测试和调试

### 阶段 2: CHECK-4 适配（2-3h）

1. ✅ 创建参数适配脚本
2. ✅ 测试 arkts-ut-verifier 调用
3. ✅ 验证产物读取

### 阶段 3: gate-release 集成（2-3h）

1. ✅ 创建读取脚本
2. ✅ 实现范围扩展
3. ✅ 生成核实报告

---

## 🎯 今晚目标

**现实目标**（1-2h）:
- ✅ 创建 run_check3.sh 框架
- ✅ 实现设备检测部分
- ✅ 完成基本流程

**延伸目标**（如有精力）:
- ✅ 实现截图采集
- ✅ 集成对比功能

---

## 📊 预计时间

| 任务 | 今晚 | 明天 | 总计 |
|------|------|------|------|
| CHECK-3 集成 | 1-2h | 3-4h | 4-6h |
| CHECK-4 适配 | - | 2-3h | 2-3h |
| gate-release | - | 2-3h | 2-3h |
| **总计** | **1-2h** | **7-10h** | **8-12h** |

---

**创建时间**: 2024-11-04 00:45  
**状态**: 准备开始  

**让我们开始吧！** 🚀
