# Static UI facts validation

Implementation base: main 18825f9d. Rollout remains opt-in; legacy is the default.

## Reproducible checks

    python3 -m unittest discover -s arkts-skills/skills/a2h-spec/scripts/tests -q
    python3 -m unittest discover -s arkts-skills/skills/android-ui-graph-builder/scripts/tests -q
    python3 -m unittest discover -s arkts-skills/skills/android2hmos_resources_convert/tests -q
    python3 -m unittest discover -s build/script-compression/scripts/tests -p test_build_dependencies.py -q

The new suite covers source selection, overlays, units, include cycles, DataBinding,
custom views, preferences/dialogs, exact AAR identity, source-only runs without PATH/ADB,
immutable generated facts, schema compatibility, rendering and packaged imports.

Generality cases vary independent dimensions: adapter classes without Adapter suffixes,
arbitrarily named Fragment subclasses, Kotlin import aliases, custom DataBinding class
names without Binding suffixes, non-res resource roots, arbitrary theme helper names,
opaque style names, and class names inside string literals. Production extraction has
no example-app package/resource IDs or theme-name selection rules.

The optional local probe is tests/probe_example_apps.py. Its curated build targets,
theme choices and 393dp preview width are regression fixtures, not product defaults.
Probe scope is selected primary pages plus the complete required Dialog-owner inventory;
it is not a complete app Spec/LLM-generation timing measurement.

Observed local timings after shared XML/window-table caching: approximately 1–2 seconds
for the first two fixtures; approximately 10–11 seconds cold and 7–8 seconds warm for
the larger fixture. Re-run to establish performance on the caller's own target.

Evidence correction: ic_curved_arrow is a mixed vector: a stroke curve and a filled
arrowhead. Paint checks must be per path; a file-wide stroke-only assumption is invalid.

## Checks still owned downstream

probe_font_unit_sdk.py type-checks calls against the local SDK and records declaration/
fixture hashes. This verifies the signature, not a full ArkTS application build or
runtime font-scale behavior. FONT_DP_AS_FP remains review.

V5 first-pass A/B needs execute D3/D4/D8 consumption. No claim of ArkTS visual equivalence
or default-on readiness is made by static extraction tests or the example probe.
