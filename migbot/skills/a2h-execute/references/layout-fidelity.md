# Source-driven layout and executable Stage-1 acceptance

Use this contract for new empty projects. `schema_version=2` delivery inventories
separate capture identity, implementation ownership and verification ownership.
Do not downgrade to schema 1 to avoid a failed ownership check.

## Before dispatch

`a2h-plan/scripts/ui_delivery.py draft/validate/approve` remains the inventory writer.
Draft includes one unit per component and proposes shell/content roles. Review
every observed state against source composition, click paths and runtime state.
The Activity that captured a state is not necessarily its content owner.

Each unit has `owned_ui_roles`; each required state has `responsibility`:
`shell`, `content`, `overlay`, or `behavior`, plus existing evidence page/state,
arrival mode and reviewed `region_px` / `regions_px`. `layer` and source-backed
`overlap_reason` are required when intentionally overlapping ownership on different
layers. Context may be shared; the same content obligation must not be claimed by
two same-layer owners. `state_setup` records fixture, selected tab/date/month,
scroll anchor and required actions. Keep source numeric relationships adaptive.

`toolchain.sdk_definitions` points to the selected SDK's ETS component declarations.
`presentation` records emulator/profile, actual viewport/density, OS/API, font
scale, system bars, locale, clock/day-night, city and channel. These are frozen
verification inputs; record actual arrival conditions and reject mismatches.

Full UI inventories account for all observed states, including content states
inside a host. A shell-only owner does not account for body content. Exclusions
need source refs and the existing scope decision. A `selected_smoke` pilot instead
lists exact `selected_evidence_states`; its result cannot stand for the whole app.

Input preparation calls `source_layout.extract`: source XML, styles, includes,
adapter layouts identified by the resource index, anchors/margins, gravity,
weight/orientation and dimension resources become hash-bound `layout_obligations`.
Unresolved custom/dynamic calculations stay unresolved for source review. Never
derive these obligations from measured bounds or supply a free-text numerical waiver.

## Choosing ArkUI layout

| Source relationship | ArkUI implementation |
|---|---|
| end-aligned badge/gauge | full-width Row + justifyContent(End), or source-equivalent relative constraints |
| bottom-anchored summary | full-height Column + justifyContent(End), or explicit bottom constraints |
| two-row information card | Column with two Rows and explicit space distribution |
| Stack child gravity | API 20+ `layoutGravity(LocalizedAlignment...)`; below 20 use wrappers or RelativeContainer/alignRules |
| short/conditionally hidden Scroll content | explicit source-consistent content alignment, usually `align(Alignment.Top)` |
| wrap_content / match constraints | intrinsic/adaptive layout, not a fixed number measured in one screenshot |

`.align()` aligns the current component's own content. It is not a general
replacement for parent-relative placement. `.alignSelf()` is contextual, not a
universal gravity replacement. A non-Center alignment on an unexpanded native
Stack child is an error. With explicit size/constraints or custom components it
remains diagnostic: the script cannot prove whether that size exceeds content.
The SDK declares align on CommonMethod; do not invent a component type whitelist.
Do not auto-replace
every enum with a spelling suggestion. Check the project's compatibility floor.

Read layout obligations before selecting primitives. PNGs select state, confirm
values/visibility and verify rendered output. Runtime coordinates do not authorize
rebuilding source relationships as a pile of fixed positions. Numeric literals and
named constants are checked in code, regardless of comments; moving a value to a
resource does not prove its provenance. Source calculations should remain source
calculations or adaptive layout instead of a newly baked-in measured result.

## Context and owned regions

Small regions (less than one quarter of the screen), shell/overlay states and
states with `requires_full_context=true` receive full representative images before
owned crops. Large child bodies normally use their crop, original reference and
ancestor geometry; do not force duplicate full images into every body packet.
`full_context` never grants content ownership or satisfies a child's comparison.
Original PNG/XML bytes remain in traversal; working copies are rebuildable.

Shell crops are derived from reviewed inventory owners, not all raw bindings.
Each state retains its own owner, ROI, layer and coordinate transform. A component
local coordinate cannot be used as a screen coordinate. Verify host composition,
viewport origin and safe-area responsibility after assembly.

## Mandatory execution

1. Freeze the approved schema-2 inventory and exact state scope.
2. Dispatch converter with script prompt; write original code/report and call
   `ui_dispatch.py complete`. It archives G0 and runs source/SDK/layout checks.
   A failed check keeps G0 and blocks handoff; fix in a new attempt.
3. Aggregate G0, assemble, archive G1, run structural and per-unit preflight.
4. Build the current verification package with hmos-builder (`--build-only`),
   initial attempt plus at most two compile repairs; never hide extra loops.
5. Install the same HAP and replay every required state; record actual density,
   viewport, fixture and state setup. Compare with `ui_relationships.py` using
   paired dump text/roles and unique matching. Resource IDs are opaque.
6. Relationship checks cover local order, side, new overlap and gaps in vp across
   different viewports. Duplicate labels use unique semantic ancestor context;
   unresolved duplicate or unmatched source labels give UNRESOLVED, not
   PASS. Independent image review covers appearance, icons, backgrounds and canvas.
7. Record comparison reports with state/setup/build/install provenance. New-contract
   PASS requires script relationship PASS plus an appearance report. Missing
   prerequisites need recorded blockers; a free-text excuse cannot hide NOT_RUN.
8. Run `stage1_acceptance.py --kind summary --out <result>` and final writeback.
   `assembled` only marks converted. `assessed` needs every state verdict.
   `complete` needs current structural/build/visual PASS. No other PASS label is
   Stage-1 acceptance. Preserve visual round-0 and at most two repair rounds.

Use `stage1_acceptance.py --kind next` on resume. New code/resources/build settings
invalidate stale receipts. Formal and Preview arrivals remain separate and neither
automatically proves business integration. Missing baselines remain BLOCKED;
available states still run. SDK enum checks are deliberately not a full typecheck.

## Pilot and contamination control

Use a copy of 1019's frozen baseline spec/plan/evidence and its original G0 outputs
for Main, HomeContainer, NewWeather, Calendar and AirQuality as the old-rule code
control. Do not read its later working code or rerun its old converter. A common
preview harness assembles the real components on the same emulator, with identical
resources, SDK and presentation. Preserve raw G0; separately log minimal compile
fixes, never silently repair control layout. Layout-changing fixes make that case
not directly comparable. Hash the common inputs before running either arm.

Pilot scope explicitly assigns home composition to Main (HomeContainer/NewWeather
own their implementations), existing Calendar and six-row month to Calendar, and
AirQuality header/content start to AirQuality. This scoped review does not pretend
Batch 2's global ownership work is already complete. Six-row month needs new
Android evidence; it has a new-rule result only and is excluded from paired A/B.

Enforce project/Android/explicit SDK-dependency allowlists with host permissions
when possible. Otherwise run `ui_isolation_audit.py --db <readonly-db> --session
<id> --allow-root <root> --out <report>` over each arm and all participating child
sessions. Sibling project reads invalidate the run; unobservable dynamic script IO
makes it INCONCLUSIVE. Transcript auditing detects observed contamination; it is
not confinement and does not prove every possible script read was recorded.

Report code-control differences on common states, new-only six-row results,
compile repairs, first visual round, later repairs, token/time cost and audit
validity separately. Do not call this a full rerun of the old skill or claim causal
isolation of ownership changes while also changing the delivery plan.
