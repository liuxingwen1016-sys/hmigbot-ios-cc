<!-- when: designing or consuming interaction contracts; read before changing detector/review schemas -->
<!-- topics: adapter boundary, common effect chain, compatibility -->

# Interaction adapter contract

The interaction engine is an adapter, not a collection of app-specific rules. The
adapter owns click contracts while the future shared effect core owns source
indexing, batching, ownership, source guard, two-round repair, and result
export.

## Common contract

Every interaction contract must expose these fields (legacy `adapter` remains
for compatibility):

```json
{
  "contract_id": "stable-id",
  "stable_id": "content-derived-id",
  "kind": "interaction",
  "facets": ["interaction"],
  "domain": "opaque-domain-name",
  "android_expected_behavior": "...",
  "arkts_actual_behavior": "...",
  "effect_chain": [
    "entry",
    "input_identity",
    "handler",
    "command",
    "async_terminal",
    "durable_effect",
    "invalidation",
    "readback",
    "observable"
  ],
  "edit_targets": [],
  "change_kinds": [],
  "risk": "LOW | MEDIUM | HIGH"
}
```

Review must describe a concrete Android postcondition, the concrete ArkTS
chain, the first broken node, reachability, exact edit target and both success
and failure terminal states. Calling a handler/service or setting a URL is not
an effect completion proof.

## Optional domains

`playback` and `download` are optional interaction extensions. Their AVPlayer,
request-agent, file, database and runtime checks run only when the target
contract is in that domain. For ordinary interactions use the neutral scope:

```text
effect_scope_guard.py --target common
```

The neutral scope performs no media/file checks. `playback`, `download`, and
`all` retain the existing specialized checks for explicit targets.

Specialized checks are selected through the scope guard's capability
`adapter_profile` (see [adapter discovery](adapter-discovery.md)). Adapter IDs
describe implementation patterns, not an application. A missing or unknown
adapter is evidence for Review, not permission to skip the domain or invent a
framework-specific fix.

## Compatibility with the future setting adapter

The setting adapter may use the same contract with `kind: "setting"` and
`facets: ["setting"]`. Its preference fields (`setting_key`, persistence
precedence, activation timing and defaults) are optional interaction-core
extensions, not requirements for a click contract. A setting control that also
has a meaningful click effect can use both facets in one contract rather than
creating duplicate repairs.

## Repair/result confidence

`APPLIED` is an execution status only. Consumers should derive a confidence
view from the evidence:

```text
STATIC_APPLIED   changed source, all required static roles resolved
STATIC_PARTIAL   changed source, one or more roles unresolved
STATIC_NO_CHANGE no source change was made
UNCERTAIN        evidence or reachability is insufficient
```

These views do not replace the existing per-round statuses or add a repair
round. Runtime verification remains optional and domain-specific.
