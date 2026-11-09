<!-- when: planning full or targeted interaction review, or inspecting an unfamiliar implementation -->
<!-- topics: capability discovery, adapter selection, unknown framework -->

# Capability-driven adapter selection

The interaction engine selects adapters by source capabilities, not by application name, page name,
or a fixed service filename. The deterministic scope guard emits an
`adapter_profile` with one or more capabilities:

```json
{
  "domain": "playback | download",
  "adapter_id": "playback-avplayer | playback-mediakit | playback-custom | playback-unknown",
  "confidence": "HIGH | MEDIUM | LOW | NONE",
  "signals": [],
  "evidence": []
}
```

Review planning first selects Detector candidates plus contracts with concrete
domain action evidence using `effect_review_coverage.py`. Bindings, reachable
commands, event consumers and explicit domain tags determine inclusion. A page
name, `primary/secondary`, state field, label or ordinary HTTP request alone does
not establish an implemented playback/download command. For a domain-targeted
request, use `plan --target-domains playback,download`: include both implemented
actions and blocked candidates with current-control action intent (action labels,
variants, linked Android actions or the concrete callback's enum parameter).
Intent provenance is a reason to review, never proof of implementation or a
defect. Do not prefilter command-only identities and pass them as an explicit
list: doing so loses disabled controls and missing command bindings. An explicit
contract list stays isolated and is reserved for a request naming exact IDs.
The plan records selection provenance and automatically binds a scope guard for
the selected domains, including both domains when necessary. No-finding media
actions still receive AI review of their command prerequisites and terminal
effects; this selection is not a defect finding or permission to patch.

Before dispatch, map each user-reported entry and state to the selected records.
Inspect an unmatched control's actual instance and Android action branch; do not
substitute a working sibling entry. Keep ordinary navigation to a media page,
configuration enums and unrelated dispatcher branches distinct from commands.

Unfamiliar wrappers without recognizable command evidence remain a limitation
of deterministic discovery. Inspect their call chain when reviewing a selected
candidate or an explicit target, record the capability evidence, and retain an
evidence gap when it cannot be resolved. Do not claim that every possible
framework or indirect action has been discovered.

Known technology adapters provide only technology-specific obligations. The
common interaction chain remains mandatory for every domain. A custom service
is not an error: follow its concrete command, terminal state, persistence/file
result, invalidation and observable consumer. If no capability is recognized,
emit `ADAPTER_UNRECOGNIZED` and send the target to AI Review as
`UNCERTAIN/REVIEW_REQUIRED`; never infer `NO_DEFECT` and never synthesize a
framework-specific patch.

The profile may contain multiple adapters. Review must use the evidence paths
and actual call graph to choose the adapter that owns the target click. Do not
make all contracts satisfy every detected adapter. Technology names such as
`AVPlayer`, `request.agent`, `VideoPlayer`, or `HttpClient` are signals, not
required spellings; localized labels, renamed pages and wrapper services must
remain eligible through the generic handler-to-command trace.

When a new framework recurs across projects, add a capability signature and
fixture to the Skill. Do not add a project-specific filename, package name, or
contract id to the detector.
