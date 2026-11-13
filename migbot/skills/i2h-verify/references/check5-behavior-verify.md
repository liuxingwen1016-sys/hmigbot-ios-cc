# 行为验证（CHECK-5）

## 已提供原生 UITest runner 的项目

用 `/i2h-verify behavior` 运行首轮功能验证。需要修复时，按失败场景定位并修复，再用
`/i2h-verify recheck` 指定要复测的场景。两条命令都可汇总项目已有的原生设备回执。
runner 的每份 `results.json` 必须提供
`device`、`hap_sha256`、`planned_cases` 及带 `status` 和 `passed_steps` 的 `cases`，
原始 HarmonyOS UITest 布局和对应回执同目录。首次使用完整范围的 runner 回执。
原生 runner 优先使用稳定控件 ID。图标或自定义 Button 的文案只暴露在子节点时，
可复用 `scripts/uitest_action.py` 的 `label_action_center`，从当前原始树找到
同窗口、可见且包含该文案的实际 Button。定位冲突时保留失败，点击后继续核对目标状态。
原生 TabBar 将 `selected` 暴露在标签父节点时，可用同一模块的
`selected_tab_label` 读取真正选中项，再与实际页面到达断言一起判断。
取树后、截图或按控件触控前，用 `require_focused_app` 确认当前包拥有前台页面。
遇到其他包、无有效前台或焦点冲突，结束本轮设备操作，保留已完成场景和未跑分母。

```bash
python3 .claude/skills/i2h-plan/scripts/acceptance_plan.py behavior \
  --signed-hap path/to/signed.hap --device DEVICE_ID --run path/to/results.json
```

修复并重新签名后，把首轮回执用于保留场景分母。当前包的场景结果来自本次实跑。

```bash
python3 .claude/skills/i2h-plan/scripts/acceptance_plan.py behavior \
  --baseline path/to/first/results.json --case save_rejected \
  --signed-hap path/to/rebuilt.hap --device DEVICE_ID --run path/to/recheck/results.json
```

同包同设备的局部复测可按时间顺序重复传 `--run`。合并时各回执须提供相同的
`runner_sha256`、`fixture_sha256`，以及一致的版本、数据库和采集配置字段。
`fixture_sha256` 应取实际测试数据和初始化配置的摘要。场景以最后一次计划执行为准，
缺少执行结果时记 `NOT_RUN`。新版 HAP 的待测项也记 `NOT_RUN`。

汇总写入 `spec/verify/check5/behavior-summary.json`。场景分母包含首轮计划场景和验收绑定
里的场景，AC 分母取当前完整规格。Plan 完成标记包含有效的 `acceptance-plan.json` 摘要时，
才按该绑定检查场景是否通过、计划步骤是否存在、原始控件树是否匹配。
缺少已批准绑定时保留 `NO_BINDING`，证据不足时保留 `UNVERIFIED`。
退出码 `0` 表示全部场景与 AC 通过，`1` 表示已出报告但存在失败或未完成项，
`2` 表示输入或工具错误。功能汇总只写自己的报告，完整流水线验收按原 CHECK 执行。
原 `evaluate` 子命令继续输出 `spec/verify/check5/acceptance-evidence.json`。

选择正式 `--require-behavior` 时，完整验证报告的 CHECK-5 必须为 PASS，并用独立行
`behavior-summary-sha256: <report_sha256>` 引用行为命令返回的摘要。恢复检查会重算
该报告的输入。保留本轮签名 HAP 和原始布局证据供复核。重签名后用新包执行并重建报告。

> CHECK-5 是可扩展的行为验证总入口，技术名称为 `arkts-behavior-verify`。子 verifier 可以在自身契约内修改源码，但任何结果都只进入报告，不参与 CHECK-1/2 与已选 CHECK-3/4 的整体判定、页面 verified 回写或外层失败回环。

## 0. 当前状态：DEFERRED

**状态**: ⏸️ **DEFERRED**（iOS 适配进行中）

**原因**: `arkts-behavior-verify` 主要基于 Android Oracle，iOS 支持尚未实现

**非门控特性**: CHECK-5 的所有状态（SKIP/WARN/DEFERRED/ERROR）均不参与基础及已选视觉/UT 范围结论

---

## 1. 选择与前置边界

- **未选**：外层记 `SKIP`（用户未选择），不检查 roots/设备/skill，不新建 run、不调用引擎或 adapter、不读取历史 check12/check5 结果。SKIP 不伪造原生 result.json。
- **已选但无法初始化**：源码或 skill 缺失记 `DEFERRED`。已经初始化的运行按适配器校验结果报告，不因后来缺环境而覆盖已有失败。SDK/JBR/Hvigor、依赖、签名、HDC 或设备不可用不自动转 SKIP，按可执行范围继续；能跑源码工作就跑，不能就按影响范围记 DEFERRED。
- **只验证、不改产品代码的任务**：选中 CHECK-5 时记 `DEFERRED`（当前能力与只读约束不兼容），不调用默认修复流程或虚构 verify_only。

---

## 2. 执行方式（如未来支持 iOS）

### 调用参数

主对话调用 `Skill(arkts-behavior-verify)` 一次，传：
- `ios_root`（原 `android_root`）- iOS 源码路径
- `arkts_root` - HarmonyOS 工程路径
- `out=<hmos-project>/spec/verify/check5/behavior-effect/<run-id>`
- `max_agents`（默认 6）
- `ios_device_type=<simulator|physical>`（新增参数）

### 修复模式

- **默认**：`repair_mode=single-round`（一轮修复）
- **明确授权**：`--full-repair`（允许第二轮）

### iOS 适配需求

1. **Oracle 来源变化**：
   - Android APK → iOS IPA / .app
   - 需要支持 iOS 应用安装和运行

2. **设备控制命令**：
   - `adb` → `xcrun simctl` / `idevice*`
   - 日志收集：`adb logcat` → `xcrun simctl spawn log` / `idevicesyslog`

3. **行为采集**：
   - 设置持久化验证（UserDefaults → Preferences）
   - 点击效果验证（UIButton → ArkUI Button）

---

## 3. 两条 Lane

### Lane 1: 设置验证（Setting）

**验证内容**：
- 持久化设置是否真正生效
- 设置值是否正确保存
- 重启后设置是否保持

**iOS 特性**：
- UserDefaults → Preferences 的迁移正确性
- NSUserDefaults suite → Preferences store 映射

### Lane 2: 点击验证（Click/Interaction）

**验证内容**：
- 点击事件是否正确响应
- 业务逻辑是否正确执行
- 结果是否符合预期

**iOS 特性**：
- UIButton/UIGestureRecognizer → ArkUI 点击事件
- Target-Action → ArkTS 事件处理

---

## 4. 状态映射

| 原始状态 | CHECK-5 状态 | 说明 |
|---------|-------------|------|
| 已修改并安装，但正确性未验证 | WARN | 修复完成但未完全验证 |
| 前置不满足（iOS 不支持）| DEFERRED | 当前情况 |
| 构建/安装/流程失败 | ERROR | 执行失败 |
| 未选择 | SKIP | 用户未选择 |

---

## 5. 非门控特性

CHECK-5 的全部状态均：

### 不参与的判定

- ❌ 不加入基础及已选视觉/UT 范围结论
- ❌ 不触发 `failure-loop.md` 的 i2h-execute 回环
- ❌ 不决定 `ui-manifest.md` 的 `verified` 回写

### 只做的事情

- ✅ 生成独立报告
- ✅ 记录行为验证结果
- ✅ 标注未验证范围

### 源码修复的影响

- 如果 CHECK-5 修改了源码，需要复检 CHECK-1/2 及已选 CHECK-3/4
- 复检时，原 CHECK-5 证据对应的源码版本需要注明
- 不能复用旧 run 冒充本次结果，也不自动补跑行为修复

---

## 6. 产物位置

```
spec/verify/check5/
├── CHECK5_SUMMARY.md              # 总体摘要
└── behavior-effect/<run-id>/      # 运行目录
    ├── result.json                # 原始结果
    ├── behavior-effect-adapter.json  # 适配结果
    ├── setting/                   # 设置验证
    │   └── ...
    └── click/                     # 点击验证
        └── ...
```

---

## 7. 报告生成

### CHECK-5 报告内容

生成 `spec/verify/check5/CHECK5_SUMMARY.md`：

```markdown
# CHECK-5: 行为验证（非门控）

**状态**: DEFERRED

**原因**: arkts-behavior-verify 主要基于 Android Oracle，iOS 适配进行中

**执行情况**:
- 设置验证（Setting Lane）: 未执行
- 点击验证（Click Lane）: 未执行

**恢复条件**:
1. 实现 iOS Oracle 支持
2. 或使用 HarmonyOS 端行为作为验证基准

**注意**: 
- CHECK-5 是非门控检查，不影响整体验证结论
- 可以通过 CHECK-3 视觉对齐观察部分 UI 行为问题
- 建议在后续版本中补充完整的行为验证

---

**生成时间**: 2024-11-03  
**版本**: v1.0
```

---

## 8. 恢复条件

要启用 CHECK-5，需要满足以下条件之一：

### 方案 A: iOS Oracle 支持

1. **实现 iOS 应用构建**：
   - 从 iOS 源码构建 IPA 或 .app
   - 支持安装到模拟器/真机

2. **实现 iOS 行为采集**：
   - 设置操作采集（UserDefaults 读写）
   - 点击操作采集（UI 事件响应）

3. **设备控制适配**：
   - iOS 模拟器：`xcrun simctl`
   - iOS 真机：`idevice*` 工具链

### 方案 B: 简化验证

1. **仅验证 HarmonyOS 端**：
   - 基于 Spec 定义的预期行为
   - 不对比 iOS 实际行为

2. **手动验证补充**：
   - 自动化测试 + 人工确认
   - 记录验证结果到报告

---

## 9. 使用建议

### 当前阶段

由于 CHECK-5 处于 DEFERRED 状态，建议：

1. **依赖其他检查项**：
   - CHECK-1 静态分析可发现明显问题
   - CHECK-3 视觉对齐可观察 UI 行为
   - CHECK-4 单元测试可验证逻辑正确性

2. **手动补充验证**：
   - 人工测试关键交互流程
   - 记录测试结果
   - 补充到验证报告

3. **标注未覆盖范围**：
   - 在报告中明确说明 CHECK-5 未执行
   - 列出未验证的行为点
   - 建议后续补充

### 未来支持后

当 CHECK-5 支持 iOS 后：

1. **选择验证范围**：
   - 全选：`--mode full`
   - 仅设置：`--lane setting`
   - 仅点击：`--lane click`

2. **修复授权**：
   - 默认一轮：`repair_mode=single-round`
   - 深度修复：`--full-repair`

3. **结果解读**：
   - WARN：已修复但未完全验证
   - ERROR：执行失败
   - 参考报告中的详细分析

---

## 10. 与 Android 版本对比

| 特性 | Android 版本 | iOS 版本（当前）| iOS 版本（计划）|
|------|------------|---------------|---------------|
| Oracle 来源 | Android APK | - | iOS IPA/.app |
| 设备控制 | adb | - | xcrun/idevice* |
| 设置验证 | SharedPreferences | - | UserDefaults → Preferences |
| 点击验证 | View.onClick | - | UIButton → ArkUI |
| 修复支持 | ✅ | ❌ | ✅（计划）|
| 状态 | 可用 | DEFERRED | 计划支持 |

---

## 11. 参考资料

| 资源 | 用途 |
|------|------|
| Android 版本 SKILL.md | 参考实现逻辑 |
| arkts-behavior-verify | 原版 skill 定义 |
| iOS 设备控制文档 | xcrun/idevice* 命令 |
| HarmonyOS 行为验证指南 | 验证方法论 |

---

**版本**: v1.0  
**创建时间**: 2024-11-03  
**作者**: Claude Opus 5.5  
**状态**: DEFERRED（iOS 适配进行中）
