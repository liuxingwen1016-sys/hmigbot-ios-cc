<!-- when: a2h-execute SKILL.md §3.0 static resource-facts handoff validation -->
<!-- topics: target-input, res-index, Gate B, resource closure, placeholder registry -->

# Stage 0：静态资源事实消费与资源落地（HARD-GATE，必须最先执行）

> 前置阶段生成静态事实；本阶段校验事实并按事实完成目标资源落地，不重新推导资源值。

先沿用 Spec 本次运行 ui_facts_policy（未选择时为 legacy）；不凭残留文件切换模式。

- legacy/static-v1-shadow：读 plans/base-plan.md 的 Base-0（旧 plan 回退 feature-plan.md），扫描已审批 UI/Feature Spec 及源码中的资源引用，调用 android2hmos_resources_convert 批量落地并生成 resource-mapping.md。保留资源闭包、SVG 保真与 placeholder 对账；不要求 target-input/res-index，不将 shadow 事实升格为 canonical。
- static-v1：读取 `spec/.a2h/target-input.json`、canonical `spec/baseline/res-index/` 和 open-findings，执行下述静态事实校验。visual.json/fixture.json 仅存在时读取，不以缺失阻断。

以下 §3.0a 的 target/hash/Gate B 专属 static-v1；资源落地、placeholder 对账及 App 身份适用所有模式。

## §3.0a 执行流程

校验 target identity/schema/hash → 校验 `res-index/values.json`、`drawables.json`、`usage.json`、`design-tokens.json` 的 `target_input_sha256` → 校验 Gate B 没有 selected scope 的 blocking finding → 读取 usage/code refs 形成资源闭包 → 调用资源转换器写入 `entry/src/main/resources/` → 运行 SVG/资源保真检查 → **HARD-GATE**：闭包可解析或显式登记 `MISSING_xxx`，且保真检查通过，才进入 Stage 1。不得猜测资源值。

## §3.0a-bis 资源层占位登记 HARD-GATE

强制校验：每个 `MISSING_xxx`、fallback 资产、`[TODO: translate]` 和 `preview-fixture` 必须在 `spec/placeholder-registry.md` 有对应登记。`preview-fixture` 不得用于声明业务 wiring 已完成。

校验示例：

```bash
trans_count=$(grep -c '\[TODO: translate\]' entry/src/main/resources/*/element/*.json | awk -F: '{s+=$2} END{print s}')
registry_trans=$(grep -c 'kind=resource-pending-translation' spec/placeholder-registry.md)
test "$trans_count" -eq "$registry_trans" || exit 1
```

## §3.0b 外部翻译和资源债务

翻译、fallback 资源和资源缺口按事实状态处理：execute 不发明翻译或默认值；unresolved 进入 placeholder registry，并阻断初始可见义务未处置的页面。

## §3.0b-bis 落地 App 身份（dev 安全字段，无签名影响）

资源迁移后、进 Stage 1 前，主线程**自动调用** `arkts-app-identity`（**`scope=dev-identity`**）从 Android 源落地 App 身份，消除脚手架默认值（`app_name` 滞留 "MyApplication" / `versionName` 滞留 "1.0.0" 会卡真机识别与 a2h-verify App 身份校验项）：

```
Skill({
  skill: "arkts-app-identity",
  args: "scope=dev-identity android_root=<$ANDROID_SRC> feature_base=spec/baseline/feature-base.md"
})
```

只写 dev 安全字段：`app_name`（label 文本）/ `versionName` / `versionCode` / 图标资源；**不碰 `bundleName` / `vendor`**——二者与签名 / AGC 强绑定属部署期 D-009，dev 阶段写入会致签名装机不一致（保留脚手架占位，部署期再以 `scope=full` 落地）。幂等、不覆盖无关字段。**非阻断**：身份字段非编译必需，`arkts-app-identity` 返回非 0 时写迁移报告 WARN 但不阻断 Stage 1。

## §3.0c 完成标志

报告：target-input hash / res-index 文件和 hash / Gate B finding 对账 / 资源闭包 / 目标资源输出 / 保真检查 / placeholder 对账 / §3.0a-bis HARD-GATE 状态（FAIL 则阻断 Stage 1）。
