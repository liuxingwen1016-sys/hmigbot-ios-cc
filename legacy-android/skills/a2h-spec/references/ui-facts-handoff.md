# 静态 UI 事实：execute owner 交接契约

spec 负责资源事实、sidecar、生成章节和 Gate B；execute owner 实施 D2–D8。
本文件是消费契约，不表示 execute 已支持。

| 项 | 消费要求 |
|---|---|
| D2 | Base-6 DesignTokens.ets 从 usage token table 生成，保留 resource_id、role、theme/config |
| D3 | Stage 0 按 usage closure 及 code refs 准备资源，不能只转换 app/src/main/res |
| D4 | 读取 visual.json，代码覆盖只在匹配初始状态下生效；记录 fact ID 的使用、忽略或覆盖原因 |
| D5 | dp/dip textSize→vp，sp→fp；invisible→Hidden，gone→None；shape 保留伸缩；vector 不添加源中不存在的 fill |
| D6 | FONT_DP_AS_FP（SDK fixture 通过前 review）、TOKEN_NOT_IN_TABLE、STRETCH_SHAPE_AS_IMAGE；stroke-only fill、Material baseline fallback 作为 review |
| D7 | 按 descriptor 的 fill/stroke/state/level/density/intrinsic dimensions 消费；未知部分登记带 fact ID 的 forward-ref-uncertain |
| D8 | preview-fixture：generated UI binding 为 location，trigger_condition/resolve_by 为 Slice N Step 3c，来源为 fixture.json 字段和 source_ref |

新增 registry kind 建议行（execute/plan owner 同步修改模板、验证器及完成统计后采用）：

| kind | 场景 | location | trigger_condition | source |
|---|---|---|---|---|
| preview-fixture | 有来源的示例展示数据，真实 provider 尚未接线 | entry/src/main/ets/<file>#<binding> | Slice N Step 3c | <fixture.json field> + <source_ref> |

open preview-fixture 不计为业务接线完成。运行时图片采用有来源的 placeholder policy。

font-size SDK 验证资产见 assets/font-unit-fixture/FontUnitFixture.ets。
在支持 SDK 构建后，在外部环境改变 font scale，验证 vp 固定、fp 随配置改变。
保存 SDK、构建和测量证据；仅有 d.ts 签名不升级为 hard gate。

V5 A/B 冻结 Android revision、execute prompt/实现、模型、preview config、页面/状态。
分别归档 spec inputs、第一次 ArkTS、第一次 build/visual result、后续修改。
三 App 缺陷回放是主要验收；第一轮色彩/形状/字体/尺寸 ALIGN 改善目标 ≥50%，编译失败不增加。
