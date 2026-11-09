<!-- when: Stage 0 resource-facts handoff validation -->
<!-- topics: target-input, res-index, visual facts, Gate B, D4 consumption -->

# UI 静态资源事实交接契约

仅 ui_facts_policy=static-v1 启用此输入契约。legacy/static-v1-shadow 沿用 stage-0-resources 的旧资源扫描与转换流程，不强制产生 canonical 新索引；shadow 仅比对，不进入 Execute 事实消费。visual/fixture 等静态 sidecar 仅存在时消费，不作为必交硬门。

资源事实阶段只读取 iOS 源码、资源、AAR 和可选 APK，产出静态事实；不访问设备、不截图、不写 HarmonyOS 资源、不生成 ArkTS。

## Canonical inputs and outputs

```text
spec/.i2h/target-input.json
spec/baseline/res-index/values.json
spec/baseline/res-index/drawables.json
spec/baseline/res-index/usage.json
spec/baseline/res-index/design-tokens.json
spec/baseline/ui-snapshots/page_NNNN_Xxx/
  meta.json
  view.xml
  visual.json
  fixture.json
  templates/*.json       # 有列表 item 时
spec/baseline/dialog-snapshots/dlgsnap_*/
```

Every derived file must carry `schema_version`, `tool_version`, `target_input_sha256` and input hashes. `ui-manifest.md` page tokens must be present in `design-tokens.json`.

## Gate B handoff

`spec/.i2h/open-findings.json` must have no unresolved blocking resource-facts finding for the selected pages. Every initially visible obligation must have one disposition:

```text
resolved | preview_policy | deferred | not_applicable
```

An obligation includes visible resources, selector/level inputs, item templates, composition children, custom draw calls, unresolved `?attr` values and finite dynamic tables. A missing disposition blocks Stage 0.

## Execute consumption

Execute uses this precedence for every UI value:

```text
selected-state code override
→ visual.json resolved fact
→ usage-derived design token
→ provenance-recorded direct-source fallback
→ unresolved
```

Execute must not invent Material defaults. `unresolved` becomes a registered `forward-ref-uncertain` placeholder. `fixture.json` values are preview data only; register them as `preview-fixture` and do not claim business wiring is complete.

## Stage 0 responsibilities

1. Validate target identity, hashes, schemas and Gate B findings.
2. Read `usage.json` plus code references to derive the resource closure for the selected scope.
3. Invoke the target resource converter using the facts as input and write the resulting resources under `entry/src/main/resources/`.
4. Run resource/SVG fidelity checks and record unresolved assets in the execute report.

Stage 1 consumes the resulting resources and facts; it does not re-derive resource values from memory.
