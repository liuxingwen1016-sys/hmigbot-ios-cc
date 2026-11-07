# Offline iOS → HarmonyOS fixture

This fixture is intentionally small and deterministic. It contains one
SwiftUI view, one UIKit view controller, an asset catalog, a localized string,
and a static-only HarmonyOS skeleton. It is consumed by
`tests/test_e2e_i2h_fixture.py`.

The fixture does not claim to have a simulator capture, an `hdc` install, or a
real DevEco build. Those checks are recorded as `DEFERRED` in the generated
verification and migration reports. The test only exercises source evidence,
resource hashes, delivery ownership, stage-marker recovery, and report
prerequisites.
